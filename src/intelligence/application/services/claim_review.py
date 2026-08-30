"""Atomic F5.4 internal factual Claim review and effective projections."""

from datetime import datetime
from typing import Never

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    AuditReasonCode,
    append_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.authorization import ContextualAuthorizer, Permission
from intelligence.application.claim_review import (
    ClaimReviewOperationResult,
    ClaimReviewReadResult,
    DecideClaimReview,
    digest_decide_claim_review,
)
from intelligence.application.claim_review_policy import (
    F5_4_INTERNAL_FACTUAL_CLAIM_REVIEW_V1,
    ClaimReviewPolicyError,
    ClaimReviewPolicyV1,
    ClaimReviewSelfApprovalPolicyError,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    ClaimReviewCommandCollisionError,
    ClaimReviewPredecessorError,
    InvalidClaimReviewError,
    PersistenceDataError,
    ResourceNotFoundError,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.claims.models import Claim, ClaimEvidenceLink, ClaimHistory
from intelligence.claims.review import (
    ClaimReviewBasisEntry,
    ClaimReviewDecision,
    ClaimReviewHistory,
    ClaimReviewOutcome,
    ClaimReviewRequestedAction,
    EffectiveClaimReview,
    EffectiveClaimReviewStatus,
    build_claim_review_decision,
    claim_review_basis_digest,
)
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import ClaimId, ClaimReviewDecisionId, InvestigationId
from intelligence.domain.investigations import InvestigationState
from intelligence.domain.time import normalize_utc
from intelligence.evidence.admissibility import (
    EffectiveEvidenceAdmissibilityStatus,
    project_effective_evidence_admissibility,
)

_READABLE_STATES = frozenset(
    {
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    }
)


class ClaimReviewService:
    """Coordinate append-only exact-Claim human review through one UoW."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
        policy: ClaimReviewPolicyV1 = F5_4_INTERNAL_FACTUAL_CLAIM_REVIEW_V1,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock
        self._policy = policy

    def decide(self, actor: ActorContext, command: DecideClaimReview) -> ClaimReviewOperationResult:
        if not isinstance(command, DecideClaimReview):
            raise TypeError("command must be a DecideClaimReview")
        command_digest = digest_decide_claim_review(actor, command)
        permission = {
            ClaimReviewRequestedAction.ACCEPT: Permission.CLAIM_REVIEW_ACCEPT,
            ClaimReviewRequestedAction.REJECT: Permission.CLAIM_REVIEW_REJECT,
            ClaimReviewRequestedAction.RETURN_FOR_CORRECTION: (
                Permission.CLAIM_REVIEW_RETURN_FOR_CORRECTION
            ),
        }[command.requested_action]
        action = AuditActionCode.CLAIM_REVIEW_DECIDED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, permission, action)
            unit_of_work.claim_reviews.acquire_command_lock(actor.workspace_id, command.command_id)
            replay = unit_of_work.claim_reviews.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if replay is not None:
                return self._replay(unit_of_work, actor, command, command_digest, replay)
            unit_of_work.claims.acquire_history_lock(actor.workspace_id, command.claim_id)
            claim_history = unit_of_work.claims.get_history(actor.workspace_id, command.claim_id)
            if claim_history is None:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.RESOURCE_NOT_FOUND,
                    ResourceNotFoundError(),
                )
            target = self._target_claim(claim_history, command.claim_id)
            links = self._links_for(claim_history, target)
            self._acquire_dependency_locks(unit_of_work, actor, links)
            unit_of_work.claim_reviews.acquire_history_lock(actor.workspace_id, target.id)
            # Re-read only after every lock in the prescribed global order.
            claim_history = unit_of_work.claims.get_history(actor.workspace_id, command.claim_id)
            if claim_history is None:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.RESOURCE_NOT_FOUND,
                    ResourceNotFoundError(),
                )
            target = self._target_claim(claim_history, command.claim_id)
            links = self._links_for(claim_history, target)
            prior = unit_of_work.claim_reviews.get_history(actor.workspace_id, target.id)
            if prior is not None:
                self._authorize(
                    unit_of_work,
                    actor,
                    Permission.CLAIM_REVIEW_SUPERSEDE,
                    AuditActionCode.CLAIM_REVIEW_SUPERSEDED,
                )
                action = AuditActionCode.CLAIM_REVIEW_SUPERSEDED
            occurred_at = normalize_utc(self._clock.now())
            try:
                self._validate_context(
                    unit_of_work, actor, command.investigation_id, claim_history, target, True
                )
                if (prior is None and command.expected_previous_decision_digest is not None) or (
                    prior is not None
                    and prior.latest.decision_digest != command.expected_previous_decision_digest
                ):
                    raise ClaimReviewPredecessorError()
                if prior is not None:
                    self._validate_review_history(unit_of_work, actor, claim_history, target, prior)
                basis = self._basis(unit_of_work, actor, target, links, occurred_at)
                evaluation = self._policy.evaluate(
                    claim=target,
                    links=links,
                    entries=basis,
                    command=command,
                    decided_by=actor.user_id,
                )
                decision = build_claim_review_decision(
                    decision_id=ClaimReviewDecisionId.new(),
                    claim=target,
                    decision_sequence=len(prior.decisions) + 1 if prior else 1,
                    supersedes_decision_id=prior.latest.id if prior else None,
                    outcome=evaluation.outcome,
                    reason_code=evaluation.reason_code,
                    policy_id=evaluation.policy_id,
                    policy_version=evaluation.policy_version,
                    purpose=evaluation.purpose,
                    review_basis_digest=claim_review_basis_digest(claim=target, entries=basis),
                    command_id=command.command_id,
                    command_digest=command_digest,
                    decided_by=actor.user_id,
                    decided_at=occurred_at,
                )
                history = ClaimReviewHistory(
                    decisions=(*prior.decisions, decision) if prior else (decision,)
                )
                history.validate_against(claim_history)
            except ClaimReviewPredecessorError as error:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_REVIEW_PREDECESSOR_INVALID,
                    error,
                    occurred_at,
                )
            except InvalidClaimReviewError as error:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_REVIEW_CONTEXT_INVALID,
                    error,
                    occurred_at,
                )
            except ClaimReviewSelfApprovalPolicyError as cause:
                review_error = InvalidClaimReviewError()
                review_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_REVIEW_SELF_APPROVAL,
                    review_error,
                    occurred_at,
                )
            except (ClaimReviewPolicyError, DomainError) as cause:
                review_error = InvalidClaimReviewError()
                review_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_REVIEW_POLICY_INVALID,
                    review_error,
                    occurred_at,
                )
            if prior is None:
                unit_of_work.claim_reviews.add_initial(decision)
            else:
                unit_of_work.claim_reviews.add_superseding(decision)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=command.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            effective = self._effective(
                unit_of_work, actor, claim_history, target, links, history, occurred_at
            )
            unit_of_work.commit()
            return ClaimReviewOperationResult(history=history, effective=effective, replayed=False)

    def read(
        self, actor: ActorContext, claim_id: ClaimId, *, as_of: datetime
    ) -> ClaimReviewReadResult:
        if not isinstance(claim_id, ClaimId):
            raise TypeError("claim_id must be a ClaimId")
        cutoff = normalize_utc(as_of)
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(
                unit_of_work,
                actor,
                Permission.CLAIM_REVIEW_READ,
                AuditActionCode.CLAIM_REVIEW_READ_DENIED,
            )
            try:
                unit_of_work.claims.acquire_history_lock(actor.workspace_id, claim_id)
                history = unit_of_work.claims.get_history(actor.workspace_id, claim_id)
                if history is None:
                    self._reject(
                        unit_of_work,
                        actor,
                        AuditActionCode.CLAIM_REVIEW_READ_DENIED,
                        AuditReasonCode.RESOURCE_NOT_FOUND,
                        ResourceNotFoundError(),
                    )
                target = max(
                    (item for item in history.versions if item.created_at <= cutoff),
                    key=lambda item: item.version,
                )
                links = self._links_for(history, target)
                self._acquire_dependency_locks(unit_of_work, actor, links)
                unit_of_work.claim_reviews.acquire_history_lock(actor.workspace_id, target.id)
                history = unit_of_work.claims.get_history(actor.workspace_id, claim_id)
                if history is None:
                    raise InvalidClaimReviewError()
                target = max(
                    (item for item in history.versions if item.created_at <= cutoff),
                    key=lambda item: item.version,
                )
                links = self._links_for(history, target)
                self._validate_context(
                    unit_of_work, actor, target.investigation_id, history, target, False
                )
                review = unit_of_work.claim_reviews.get_history(actor.workspace_id, target.id)
                if review is not None:
                    self._validate_review_history(unit_of_work, actor, history, target, review)
                effective = self._effective(
                    unit_of_work, actor, history, target, links, review, cutoff
                )
            except (ClaimReviewPolicyError, DomainError, PersistenceDataError, ValueError) as cause:
                error = InvalidClaimReviewError()
                error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    AuditActionCode.CLAIM_REVIEW_READ_DENIED,
                    AuditReasonCode.CLAIM_REVIEW_HISTORY_INVALID,
                    error,
                )
            unit_of_work.commit()
            return ClaimReviewReadResult(history=review, effective=effective)

    def _target_claim(self, history: ClaimHistory, claim_id: ClaimId) -> Claim:
        try:
            return next(item for item in history.versions if item.id == claim_id)
        except StopIteration as error:
            raise InvalidClaimReviewError() from error

    @staticmethod
    def _links_for(history: ClaimHistory, claim: Claim) -> tuple[ClaimEvidenceLink, ...]:
        return tuple(item for item in history.links if item.claim_id == claim.id)

    def _acquire_dependency_locks(
        self, unit_of_work: UnitOfWork, actor: ActorContext, links: tuple[ClaimEvidenceLink, ...]
    ) -> None:
        for evidence_id in sorted((item.evidence_id for item in links), key=lambda item: str(item)):
            unit_of_work.evidence.acquire_history_lock(actor.workspace_id, evidence_id)
        for evidence_id in sorted((item.evidence_id for item in links), key=lambda item: str(item)):
            unit_of_work.evidence_admissibility.acquire_history_lock(
                actor.workspace_id, evidence_id
            )

    def _basis(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        claim: Claim,
        links: tuple[ClaimEvidenceLink, ...],
        cutoff: datetime,
    ) -> tuple[ClaimReviewBasisEntry, ...]:
        result: list[ClaimReviewBasisEntry] = []
        for link in sorted(links, key=lambda item: (str(item.evidence_id), item.role.value)):
            evidence_history = unit_of_work.evidence.get_history(
                actor.workspace_id, link.evidence_id
            )
            if evidence_history is None:
                raise InvalidClaimReviewError()
            evidence = next(
                (item for item in evidence_history.versions if item.id == link.evidence_id), None
            )
            if evidence is None or evidence.evidence_digest != link.evidence_digest:
                raise InvalidClaimReviewError()
            admissibility = unit_of_work.evidence_admissibility.get_history(
                actor.workspace_id, link.evidence_id
            )
            effective = project_effective_evidence_admissibility(
                evidence_history=evidence_history,
                decision_histories=(admissibility,) if admissibility else (),
                as_of=cutoff,
            )
            decision_digest = None
            if effective.decision_id is not None and admissibility is not None:
                decision = next(
                    item for item in admissibility.decisions if item.id == effective.decision_id
                )
                decision_digest = decision.decision_digest
            result.append(
                ClaimReviewBasisEntry(
                    link_digest=link.link_digest,
                    role=link.role,
                    evidence_id=link.evidence_id,
                    evidence_digest=link.evidence_digest,
                    contextual_outcome=link.use_decision.outcome.value,
                    effective_status=effective.status,
                    admissibility_decision_id=effective.decision_id,
                    admissibility_decision_digest=decision_digest,
                )
            )
        return tuple(result)

    def _validate_context(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        investigation_id: InvestigationId,
        history: ClaimHistory,
        target: Claim,
        for_mutation: bool,
    ) -> None:
        investigation = unit_of_work.investigations.get(actor.workspace_id, investigation_id)
        resolution = unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id, investigation_id
        )
        if investigation is None or resolution is None:
            raise InvalidClaimReviewError()
        allowed = (
            investigation.state is InvestigationState.VERIFYING
            if for_mutation
            else investigation.state in _READABLE_STATES
        )
        if any(
            (
                not allowed,
                target.workspace_id != actor.workspace_id,
                target.investigation_id != investigation_id,
                target.subject_company_id != resolution.company_id,
                target.entity_resolution_decision_id != resolution.id,
                investigation.confirmed_company_id != resolution.company_id,
                for_mutation and history.latest.id != target.id,
            )
        ):
            raise InvalidClaimReviewError()

    def _validate_review_history(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        claim_history: ClaimHistory,
        claim: Claim,
        review: ClaimReviewHistory,
    ) -> None:
        review.validate_against(claim_history)
        links = self._links_for(claim_history, claim)
        for decision in review.decisions:
            basis = self._basis(unit_of_work, actor, claim, links, decision.decided_at)
            if (
                claim_review_basis_digest(claim=claim, entries=basis)
                != decision.review_basis_digest
            ):
                raise InvalidClaimReviewError()
            if decision.outcome is ClaimReviewOutcome.ACCEPTED_FOR_INTERNAL_FACTUAL_USE:
                valid = {
                    item.evidence_id
                    for item in basis
                    if item.contextual_outcome == "ELIGIBLE"
                    and item.effective_status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
                }
                if (
                    decision.decided_by == claim.created_by
                    or not any(
                        link.role.value == "SUPPORTS" and link.evidence_id in valid
                        for link in links
                    )
                    or any(
                        link.role.value == "CONTRADICTS" and link.evidence_id in valid
                        for link in links
                    )
                ):
                    raise InvalidClaimReviewError()

    def _effective(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        claim_history: ClaimHistory,
        claim: Claim,
        links: tuple[ClaimEvidenceLink, ...],
        review: ClaimReviewHistory | None,
        cutoff: datetime,
    ) -> EffectiveClaimReview:
        decision = (
            next((item for item in reversed(review.decisions) if item.decided_at <= cutoff), None)
            if review
            else None
        )
        if decision is None:
            status = EffectiveClaimReviewStatus.PENDING
        elif decision.outcome is ClaimReviewOutcome.REJECTED_FOR_INTERNAL_FACTUAL_USE:
            status = EffectiveClaimReviewStatus.REJECTED
        elif decision.outcome is ClaimReviewOutcome.NEEDS_CORRECTION:
            status = EffectiveClaimReviewStatus.NEEDS_CORRECTION
        else:
            status = (
                EffectiveClaimReviewStatus.ACCEPTED
                if self._positive_still_valid(unit_of_work, actor, claim, links, decision, cutoff)
                else EffectiveClaimReviewStatus.INVALIDATED
            )
        return EffectiveClaimReview(
            status=status,
            claim_id=claim.id,
            claim_series_id=claim.series_id,
            claim_version=claim.version,
            claim_digest=claim.claim_digest,
            decision_id=decision.id if decision else None,
            as_of=cutoff,
        )

    def _positive_still_valid(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        claim: Claim,
        links: tuple[ClaimEvidenceLink, ...],
        decision: ClaimReviewDecision,
        cutoff: datetime,
    ) -> bool:
        baseline = self._basis(unit_of_work, actor, claim, links, decision.decided_at)
        if claim_review_basis_digest(claim=claim, entries=baseline) != decision.review_basis_digest:
            raise InvalidClaimReviewError()
        # Every persisted dependency transition is checked. A later re-admission
        # cannot reactivate this review epoch.
        times = {decision.decided_at, cutoff}
        for link in links:
            evidence = unit_of_work.evidence.get_history(actor.workspace_id, link.evidence_id)
            if evidence is None:
                raise InvalidClaimReviewError()
            times.update(
                item.created_at
                for item in evidence.versions
                if decision.decided_at < item.created_at <= cutoff
            )
            times.update(
                item.occurred_at
                for item in evidence.events
                if decision.decided_at < item.occurred_at <= cutoff
            )
            admissibility = unit_of_work.evidence_admissibility.get_history(
                actor.workspace_id, link.evidence_id
            )
            if admissibility:
                times.update(
                    item.decided_at
                    for item in admissibility.decisions
                    if decision.decided_at < item.decided_at <= cutoff
                )
                times.update(
                    item.valid_until
                    for item in admissibility.decisions
                    if item.valid_until and decision.decided_at < item.valid_until <= cutoff
                )
        baseline_by_id = {item.evidence_id: item for item in baseline}
        for instant in sorted(times):
            current = {
                item.evidence_id: item
                for item in self._basis(unit_of_work, actor, claim, links, instant)
            }
            for link in links:
                previous = baseline_by_id[link.evidence_id]
                now = current[link.evidence_id]
                previous_valid = (
                    previous.contextual_outcome == "ELIGIBLE"
                    and previous.effective_status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
                )
                now_valid = (
                    now.contextual_outcome == "ELIGIBLE"
                    and now.effective_status is EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
                )
                if (
                    link.role.value == "SUPPORTS"
                    and previous_valid
                    and (
                        not now_valid
                        or now.admissibility_decision_id != previous.admissibility_decision_id
                        or now.admissibility_decision_digest
                        != previous.admissibility_decision_digest
                    )
                ):
                    return False
                if link.role.value == "CONTRADICTS" and now_valid:
                    return False
        return True

    def _replay(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        command: DecideClaimReview,
        command_digest: str,
        review: ClaimReviewHistory,
    ) -> ClaimReviewOperationResult:
        matched = tuple(item for item in review.decisions if item.command_id == command.command_id)
        if len(matched) != 1 or matched[0].command_digest != command_digest:
            self._reject(
                unit_of_work,
                actor,
                AuditActionCode.CLAIM_REVIEW_DECIDED,
                AuditReasonCode.COMMAND_ID_COLLISION,
                ClaimReviewCommandCollisionError(),
            )
        persisted = matched[0]
        claim_history = unit_of_work.claims.get_history(actor.workspace_id, persisted.claim_id)
        if claim_history is None:
            self._reject(
                unit_of_work,
                actor,
                AuditActionCode.CLAIM_REVIEW_DECIDED,
                AuditReasonCode.CLAIM_REVIEW_HISTORY_INVALID,
                InvalidClaimReviewError(),
            )
        claim = self._target_claim(claim_history, persisted.claim_id)
        self._acquire_dependency_locks(unit_of_work, actor, self._links_for(claim_history, claim))
        self._validate_review_history(unit_of_work, actor, claim_history, claim, review)
        original = ClaimReviewHistory(decisions=review.decisions[: persisted.decision_sequence])
        effective = self._effective(
            unit_of_work,
            actor,
            claim_history,
            claim,
            self._links_for(claim_history, claim),
            original,
            persisted.decided_at,
        )
        unit_of_work.commit()
        return ClaimReviewOperationResult(history=original, effective=effective, replayed=True)

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        permission: Permission,
        action: AuditActionCode,
    ) -> None:
        decision = self._authorizer.authorize(unit_of_work, actor, permission)
        if decision.is_allowed:
            return
        if decision.denial_reason is None:
            raise RuntimeError("Denied authorization requires a reason.")
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=decision.denial_reason,
            occurred_at=self._clock.now(),
        )
        raise AuthorizationDeniedError()

    def _reject(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        reason: AuditReasonCode,
        error: Exception,
        occurred_at: datetime | None = None,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.FAILURE,
            reason=reason,
            occurred_at=occurred_at or self._clock.now(),
        )
        raise error


__all__ = ["ClaimReviewService"]
