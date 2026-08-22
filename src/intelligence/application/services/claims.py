"""Atomic F5.2 Claim registration, correction, reading, and current assessment."""

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
from intelligence.application.claim_evidence_policy import (
    F5_2_CONTROLLED_CORPUS_V1,
    ClaimEvidenceEligibilityPolicyV1,
    ClaimEvidencePolicyError,
)
from intelligence.application.claims import (
    ClaimOperationResult,
    CorrectClaim,
    ProposedClaimEvidenceLink,
    RegisterClaim,
    digest_correct_claim,
    digest_register_claim,
)
from intelligence.application.entity_confirmation import EntityResolutionDecisionRecord
from intelligence.application.errors import (
    AuthorizationDeniedError,
    ClaimCommandCollisionError,
    ClaimVersionConflictError,
    InvalidClaimContextError,
    InvalidClaimEvidenceError,
    ResourceNotFoundError,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.claims.models import (
    Claim,
    ClaimAssessment,
    ClaimEvidenceLink,
    ClaimHistory,
    assess_links,
    build_claim,
    build_claim_link,
)
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import (
    ClaimCommandId,
    ClaimId,
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceId,
    InvestigationId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.evidence.models import EvidenceHistory

_READABLE_STATES = frozenset(
    {
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
    }
)


class ClaimService:
    """Coordinate Claim invariants through tenant-scoped application ports."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
        policy: ClaimEvidenceEligibilityPolicyV1 = F5_2_CONTROLLED_CORPUS_V1,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock
        self._policy = policy

    def register(self, actor: ActorContext, command: RegisterClaim) -> ClaimOperationResult:
        if not isinstance(command, RegisterClaim):
            raise TypeError("command must be a RegisterClaim")
        command_digest = digest_register_claim(actor, command)
        action = AuditActionCode.CLAIM_REGISTERED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.CLAIM_REGISTER, action)
            unit_of_work.claims.acquire_command_lock(actor.workspace_id, command.command_id)
            existing = unit_of_work.claims.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if existing is not None:
                return self._replay(
                    unit_of_work,
                    actor,
                    action,
                    existing,
                    command.command_id,
                    command_digest,
                )
            occurred_at = self._clock.now()
            try:
                decision = self._validated_context(
                    unit_of_work, actor, command.investigation_id, for_mutation=True
                )
                histories = self._locked_evidence_histories(
                    unit_of_work,
                    actor,
                    command.links,
                    command.investigation_id,
                    decision.company_id,
                    decision.id,
                )
                claim_id = ClaimId.new()
                claim = build_claim(
                    claim_id=claim_id,
                    series_id=claim_id,
                    version=1,
                    supersedes_claim_id=None,
                    workspace_id=actor.workspace_id,
                    investigation_id=command.investigation_id,
                    subject_company_id=decision.company_id,
                    entity_resolution_decision_id=decision.id,
                    command_id=command.command_id,
                    command_digest=command_digest,
                    predicate_code=command.predicate_code,
                    predicate_version=command.predicate_version,
                    value=command.value,
                    temporal=command.temporal,
                    criticality=command.criticality,
                    creation_method=command.creation_method,
                    creation_method_version=command.creation_method_version,
                    created_by=actor.user_id,
                    created_at=occurred_at,
                    correction_reason=None,
                )
                links = self._build_links(actor, claim, command.links, histories, occurred_at)
                history = ClaimHistory(versions=(claim,), links=links)
                assessment = self._assessment(unit_of_work, actor, history)
            except InvalidClaimContextError as context_error:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_CONTEXT_INVALID,
                    context_error,
                    occurred_at,
                )
            except (ClaimEvidencePolicyError, DomainError) as cause:
                evidence_error = InvalidClaimEvidenceError()
                evidence_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_EVIDENCE_INVALID,
                    evidence_error,
                    occurred_at,
                )
            unit_of_work.claims.add_initial(claim, links)
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
            unit_of_work.commit()
            return ClaimOperationResult(history, assessment, False)

    def correct(self, actor: ActorContext, command: CorrectClaim) -> ClaimOperationResult:
        if not isinstance(command, CorrectClaim):
            raise TypeError("command must be a CorrectClaim")
        command_digest = digest_correct_claim(actor, command)
        action = AuditActionCode.CLAIM_CORRECTED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.CLAIM_CORRECT, action)
            unit_of_work.claims.acquire_command_lock(actor.workspace_id, command.command_id)
            existing = unit_of_work.claims.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if existing is not None:
                return self._replay(
                    unit_of_work,
                    actor,
                    action,
                    existing,
                    command.command_id,
                    command_digest,
                )
            unit_of_work.claims.acquire_history_lock(actor.workspace_id, command.claim_id)
            current = unit_of_work.claims.get_history(actor.workspace_id, command.claim_id)
            if current is None:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.RESOURCE_NOT_FOUND,
                    ResourceNotFoundError(),
                )
            if (
                current.latest.id != command.claim_id
                or current.latest.claim_digest != command.expected_claim_digest
                or current.latest.predicate_code is not command.predicate_code
                or current.latest.predicate_version != command.predicate_version
            ):
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_VERSION_CONFLICT,
                    ClaimVersionConflictError(),
                )
            occurred_at = self._clock.now()
            try:
                decision = self._validated_context(
                    unit_of_work,
                    actor,
                    current.latest.investigation_id,
                    for_mutation=True,
                )
                if (
                    decision.id != current.latest.entity_resolution_decision_id
                    or decision.company_id != current.latest.subject_company_id
                ):
                    raise InvalidClaimContextError()
                histories = self._locked_evidence_histories(
                    unit_of_work,
                    actor,
                    command.links,
                    current.latest.investigation_id,
                    current.latest.subject_company_id,
                    current.latest.entity_resolution_decision_id,
                )
                claim = build_claim(
                    claim_id=ClaimId.new(),
                    series_id=current.latest.series_id,
                    version=current.latest.version + 1,
                    supersedes_claim_id=current.latest.id,
                    workspace_id=current.latest.workspace_id,
                    investigation_id=current.latest.investigation_id,
                    subject_company_id=current.latest.subject_company_id,
                    entity_resolution_decision_id=current.latest.entity_resolution_decision_id,
                    command_id=command.command_id,
                    command_digest=command_digest,
                    predicate_code=command.predicate_code,
                    predicate_version=command.predicate_version,
                    value=command.value,
                    temporal=command.temporal,
                    criticality=command.criticality,
                    creation_method=command.creation_method,
                    creation_method_version=command.creation_method_version,
                    created_by=actor.user_id,
                    created_at=occurred_at,
                    correction_reason=command.correction_reason,
                )
                links = self._build_links(actor, claim, command.links, histories, occurred_at)
                history = ClaimHistory(
                    versions=(*current.versions, claim),
                    links=(*current.links, *links),
                )
                assessment = self._assessment(unit_of_work, actor, history)
            except InvalidClaimContextError as context_error:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_CONTEXT_INVALID,
                    context_error,
                    occurred_at,
                )
            except (ClaimEvidencePolicyError, DomainError) as cause:
                evidence_error = InvalidClaimEvidenceError()
                evidence_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.CLAIM_EVIDENCE_INVALID,
                    evidence_error,
                    occurred_at,
                )
            unit_of_work.claims.add_correction(claim, links)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=current.latest.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return ClaimOperationResult(history, assessment, False)

    def get_history(self, actor: ActorContext, claim_id: ClaimId) -> ClaimOperationResult:
        if not isinstance(claim_id, ClaimId):
            raise TypeError("claim_id must be a ClaimId")
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(
                unit_of_work,
                actor,
                Permission.CLAIM_READ,
                AuditActionCode.CLAIM_READ_DENIED,
            )
            history = unit_of_work.claims.get_history(actor.workspace_id, claim_id)
            if history is None:
                commit_standalone_outcome(
                    unit_of_work,
                    actor=actor,
                    action=AuditActionCode.CLAIM_READ_DENIED,
                    resource_type=AuditResourceType.INVESTIGATION,
                    resource_id=None,
                    outcome=AuditOutcome.DENIED,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    occurred_at=self._clock.now(),
                )
                raise ResourceNotFoundError()
            try:
                self._validated_context(
                    unit_of_work,
                    actor,
                    history.latest.investigation_id,
                    for_mutation=False,
                )
            except InvalidClaimContextError as error:
                self._reject(
                    unit_of_work,
                    actor,
                    AuditActionCode.CLAIM_READ_DENIED,
                    AuditReasonCode.CLAIM_CONTEXT_INVALID,
                    error,
                )
            assessment = self._assessment(unit_of_work, actor, history)
            unit_of_work.commit()
            return ClaimOperationResult(history, assessment, False)

    def _validated_context(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        investigation_id: InvestigationId,
        *,
        for_mutation: bool,
    ) -> EntityResolutionDecisionRecord:
        investigation = unit_of_work.investigations.get(actor.workspace_id, investigation_id)
        decision = unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id, investigation_id
        )
        allowed_state = investigation is not None and (
            investigation.state is InvestigationState.VERIFYING
            if for_mutation
            else investigation.state in _READABLE_STATES
        )
        if (
            investigation is None
            or decision is None
            or not allowed_state
            or investigation.confirmed_company_id != decision.company_id
        ):
            raise InvalidClaimContextError()
        return decision

    def _locked_evidence_histories(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        proposed: tuple[ProposedClaimEvidenceLink, ...],
        investigation_id: InvestigationId,
        company_id: CompanyId,
        decision_id: EntityResolutionDecisionId,
    ) -> dict[EvidenceId, EvidenceHistory]:
        result: dict[EvidenceId, EvidenceHistory] = {}
        for item in sorted(proposed, key=lambda value: str(value.evidence_id)):
            unit_of_work.evidence.acquire_history_lock(actor.workspace_id, item.evidence_id)
        for item in sorted(proposed, key=lambda value: str(value.evidence_id)):
            history = unit_of_work.evidence.get_history(actor.workspace_id, item.evidence_id)
            if history is None:
                raise ClaimEvidencePolicyError("Evidence was not found in the actor workspace.")
            if (
                history.latest.investigation_id != investigation_id
                or history.latest.subject_company_id != company_id
                or history.latest.entity_resolution_decision_id != decision_id
            ):
                raise ClaimEvidencePolicyError("Evidence scope does not match the Claim.")
            result[item.evidence_id] = history
        return result

    def _build_links(
        self,
        actor: ActorContext,
        claim: Claim,
        proposed: tuple[ProposedClaimEvidenceLink, ...],
        histories: dict[EvidenceId, EvidenceHistory],
        evaluated_at: datetime,
    ) -> tuple[ClaimEvidenceLink, ...]:
        links: list[ClaimEvidenceLink] = []
        for item in sorted(proposed, key=lambda value: str(value.evidence_id)):
            history = histories[item.evidence_id]
            decision = self._policy.evaluate(
                history=history,
                expected_evidence_id=item.evidence_id,
                expected_evidence_digest=item.expected_evidence_digest,
                workspace_id=claim.workspace_id,
                investigation_id=claim.investigation_id,
                subject_company_id=claim.subject_company_id,
                entity_resolution_decision_id=claim.entity_resolution_decision_id,
                requested_by=actor.user_id,
                evaluated_at=evaluated_at,
            )
            links.append(
                build_claim_link(
                    claim=claim,
                    evidence_id=item.evidence_id,
                    evidence_digest=item.expected_evidence_digest,
                    role=item.role,
                    use_decision=decision,
                )
            )
        return tuple(links)

    def _assessment(
        self, unit_of_work: UnitOfWork, actor: ActorContext, history: ClaimHistory
    ) -> ClaimAssessment:
        valid: set[EvidenceId] = set()
        for link in history.latest_links:
            evidence = unit_of_work.evidence.get_history(actor.workspace_id, link.evidence_id)
            if evidence is None:
                continue
            try:
                current = self._policy.evaluate(
                    history=evidence,
                    expected_evidence_id=link.evidence_id,
                    expected_evidence_digest=link.evidence_digest,
                    workspace_id=history.latest.workspace_id,
                    investigation_id=history.latest.investigation_id,
                    subject_company_id=history.latest.subject_company_id,
                    entity_resolution_decision_id=history.latest.entity_resolution_decision_id,
                    requested_by=link.use_decision.requested_by,
                    evaluated_at=link.use_decision.evaluated_at,
                )
            except ClaimEvidencePolicyError:
                continue
            if current == link.use_decision:
                valid.add(link.evidence_id)
        return assess_links(history.latest_links, frozenset(valid))

    def _replay(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        history: ClaimHistory,
        command_id: ClaimCommandId,
        command_digest: str,
    ) -> ClaimOperationResult:
        matched = tuple(item for item in history.versions if item.command_id == command_id)
        if len(matched) != 1 or matched[0].command_digest != command_digest:
            self._reject(
                unit_of_work,
                actor,
                action,
                AuditReasonCode.COMMAND_ID_COLLISION,
                ClaimCommandCollisionError(),
            )
        assessment = self._assessment(unit_of_work, actor, history)
        unit_of_work.commit()
        return ClaimOperationResult(history, assessment, True)

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
        reason = decision.denial_reason
        if reason is None:
            raise RuntimeError("A denied authorization decision requires a reason.")
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=reason,
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


__all__ = ["ClaimService"]
