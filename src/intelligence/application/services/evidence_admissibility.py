"""Atomic F5.3 global Evidence admissibility decisions and historical reads."""

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
from intelligence.application.errors import (
    AuthorizationDeniedError,
    EvidenceAdmissibilityCommandCollisionError,
    EvidenceAdmissibilityPredecessorError,
    InvalidEvidenceAdmissibilityError,
    ResourceNotFoundError,
)
from intelligence.application.evidence_admissibility import (
    DecideEvidenceAdmissibility,
    EvidenceAdmissibilityOperationResult,
    EvidenceAdmissibilityReadResult,
    digest_decide_evidence_admissibility,
)
from intelligence.application.evidence_admissibility_policy import (
    F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1,
    EvidenceAdmissibilityPolicyError,
    EvidenceAdmissibilityPolicyV1,
    EvidenceSelfApprovalPolicyError,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import (
    EvidenceAdmissibilityDecisionId,
    EvidenceId,
    InvestigationId,
)
from intelligence.domain.investigations import InvestigationState
from intelligence.domain.time import normalize_utc
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityHistory,
    EvidenceAdmissibilityRequestedAction,
    build_evidence_admissibility_decision,
    project_effective_evidence_admissibility,
)
from intelligence.evidence.models import EvidenceHistory

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


class EvidenceAdmissibilityService:
    """Coordinate exact-version decisions through existing transaction boundaries."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
        policy: EvidenceAdmissibilityPolicyV1 = F5_3_CONTROLLED_TEST_ADMISSIBILITY_V1,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock
        self._policy = policy

    def decide(
        self, actor: ActorContext, command: DecideEvidenceAdmissibility
    ) -> EvidenceAdmissibilityOperationResult:
        if not isinstance(command, DecideEvidenceAdmissibility):
            raise TypeError("command must be a DecideEvidenceAdmissibility")
        command_digest = digest_decide_evidence_admissibility(actor, command)
        permission = {
            EvidenceAdmissibilityRequestedAction.ADMIT: Permission.EVIDENCE_ADMISSIBILITY_ADMIT,
            EvidenceAdmissibilityRequestedAction.RESTRICT: (
                Permission.EVIDENCE_ADMISSIBILITY_RESTRICT
            ),
            EvidenceAdmissibilityRequestedAction.REJECT: (Permission.EVIDENCE_ADMISSIBILITY_REJECT),
        }[command.requested_action]
        action = AuditActionCode.EVIDENCE_ADMISSIBILITY_DECIDED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, permission, action)
            unit_of_work.evidence_admissibility.acquire_command_lock(
                actor.workspace_id, command.command_id
            )
            replay = unit_of_work.evidence_admissibility.get_history_by_command(
                actor.workspace_id, command.command_id
            )
            if replay is not None:
                return self._replay(unit_of_work, actor, command, command_digest, replay)
            unit_of_work.evidence.acquire_history_lock(actor.workspace_id, command.evidence_id)
            unit_of_work.evidence_admissibility.acquire_history_lock(
                actor.workspace_id, command.evidence_id
            )
            evidence_history = unit_of_work.evidence.get_history(
                actor.workspace_id, command.evidence_id
            )
            if evidence_history is None:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.RESOURCE_NOT_FOUND,
                    ResourceNotFoundError(),
                )
            prior = unit_of_work.evidence_admissibility.get_history(
                actor.workspace_id, command.evidence_id
            )
            if prior is not None:
                self._authorize(
                    unit_of_work,
                    actor,
                    Permission.EVIDENCE_ADMISSIBILITY_SUPERSEDE,
                    AuditActionCode.EVIDENCE_ADMISSIBILITY_SUPERSEDED,
                )
                action = AuditActionCode.EVIDENCE_ADMISSIBILITY_SUPERSEDED
            occurred_at = self._clock.now()
            try:
                self._validate_context(
                    unit_of_work,
                    actor,
                    command.investigation_id,
                    evidence_history,
                    command.evidence_id,
                    command.expected_evidence_digest,
                    for_mutation=True,
                )
                if (prior is None and command.expected_previous_decision_digest is not None) or (
                    prior is not None
                    and prior.latest.decision_digest != command.expected_previous_decision_digest
                ):
                    raise EvidenceAdmissibilityPredecessorError()
                if prior is not None:
                    prior.validate_against(evidence_history)
                evaluation = self._policy.evaluate(
                    history=evidence_history,
                    expected_evidence_id=command.evidence_id,
                    expected_evidence_digest=command.expected_evidence_digest,
                    requested_action=command.requested_action,
                    reason_code=command.reason_code,
                    requested_valid_until=command.requested_valid_until,
                    decided_by=actor.user_id,
                    decided_at=occurred_at,
                )
                decision = build_evidence_admissibility_decision(
                    decision_id=EvidenceAdmissibilityDecisionId.new(),
                    evidence=evidence_history.latest,
                    decision_sequence=len(prior.decisions) + 1 if prior else 1,
                    supersedes_decision_id=prior.latest.id if prior else None,
                    outcome=evaluation.outcome,
                    reason_code=evaluation.reason_code,
                    policy_id=evaluation.policy_id,
                    policy_version=evaluation.policy_version,
                    purpose=evaluation.purpose,
                    admission_basis=evaluation.admission_basis,
                    controlled_trust_root_id=evaluation.controlled_trust_root_id,
                    controlled_trust_root_version=evaluation.controlled_trust_root_version,
                    controlled_trust_root_digest=evaluation.controlled_trust_root_digest,
                    valid_until=evaluation.valid_until,
                    command_id=command.command_id,
                    command_digest=command_digest,
                    decided_by=actor.user_id,
                    decided_at=occurred_at,
                )
                history = EvidenceAdmissibilityHistory(
                    decisions=((*prior.decisions, decision) if prior else (decision,))
                )
                history.validate_against(evidence_history)
            except EvidenceAdmissibilityPredecessorError as predecessor_error:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.EVIDENCE_ADMISSIBILITY_PREDECESSOR_INVALID,
                    predecessor_error,
                    occurred_at,
                )
            except InvalidEvidenceAdmissibilityError as context_error:
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.EVIDENCE_ADMISSIBILITY_CONTEXT_INVALID,
                    context_error,
                    occurred_at,
                )
            except EvidenceSelfApprovalPolicyError as cause:
                admissibility_error = InvalidEvidenceAdmissibilityError()
                admissibility_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.EVIDENCE_ADMISSIBILITY_SELF_APPROVAL,
                    admissibility_error,
                    occurred_at,
                )
            except (EvidenceAdmissibilityPolicyError, DomainError) as cause:
                admissibility_error = InvalidEvidenceAdmissibilityError()
                admissibility_error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    action,
                    AuditReasonCode.EVIDENCE_ADMISSIBILITY_POLICY_INVALID,
                    admissibility_error,
                    occurred_at,
                )
            if prior is None:
                unit_of_work.evidence_admissibility.add_initial(decision)
            else:
                unit_of_work.evidence_admissibility.add_superseding(decision)
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
            effective = project_effective_evidence_admissibility(
                evidence_history=evidence_history,
                decision_histories=(history,),
                as_of=decision.decided_at,
            )
            return EvidenceAdmissibilityOperationResult(
                history=history, effective=effective, replayed=False
            )

    def read(
        self, actor: ActorContext, evidence_id: EvidenceId, *, as_of: datetime
    ) -> EvidenceAdmissibilityReadResult:
        if not isinstance(evidence_id, EvidenceId):
            raise TypeError("evidence_id must be an EvidenceId")
        cutoff = normalize_utc(as_of)
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(
                unit_of_work,
                actor,
                Permission.EVIDENCE_ADMISSIBILITY_READ,
                AuditActionCode.EVIDENCE_ADMISSIBILITY_READ_DENIED,
            )
            evidence = unit_of_work.evidence.get_history(actor.workspace_id, evidence_id)
            if evidence is None:
                self._reject(
                    unit_of_work,
                    actor,
                    AuditActionCode.EVIDENCE_ADMISSIBILITY_READ_DENIED,
                    AuditReasonCode.RESOURCE_NOT_FOUND,
                    ResourceNotFoundError(),
                )
            try:
                self._validate_context(
                    unit_of_work,
                    actor,
                    evidence.latest.investigation_id,
                    evidence,
                    None,
                    None,
                    for_mutation=False,
                )
                histories = self._decision_histories(unit_of_work, actor, evidence)
                effective = project_effective_evidence_admissibility(
                    evidence_history=evidence, decision_histories=histories, as_of=cutoff
                )
            except (InvalidEvidenceAdmissibilityError, DomainError) as cause:
                error = InvalidEvidenceAdmissibilityError()
                error.__cause__ = cause
                self._reject(
                    unit_of_work,
                    actor,
                    AuditActionCode.EVIDENCE_ADMISSIBILITY_READ_DENIED,
                    AuditReasonCode.EVIDENCE_ADMISSIBILITY_HISTORY_INVALID,
                    error,
                )
            unit_of_work.commit()
            return EvidenceAdmissibilityReadResult(
                evidence_history=evidence,
                decision_histories=histories,
                effective=effective,
            )

    def _validate_context(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        investigation_id: InvestigationId,
        history: EvidenceHistory,
        expected_id: EvidenceId | None,
        expected_digest: str | None,
        *,
        for_mutation: bool,
    ) -> None:
        investigation = unit_of_work.investigations.get(actor.workspace_id, investigation_id)
        resolution = unit_of_work.entity_resolution_decisions.get_by_investigation(
            actor.workspace_id, investigation_id
        )
        state_allowed = investigation is not None and (
            investigation.state is InvestigationState.VERIFYING
            if for_mutation
            else investigation.state in _READABLE_STATES
        )
        latest = history.latest
        if (
            investigation is None
            or resolution is None
            or not state_allowed
            or latest.workspace_id != actor.workspace_id
            or latest.investigation_id != investigation_id
            or latest.subject_company_id != resolution.company_id
            or latest.entity_resolution_decision_id != resolution.id
            or investigation.confirmed_company_id != resolution.company_id
            or (expected_id is not None and latest.id != expected_id)
            or (expected_digest is not None and latest.evidence_digest != expected_digest)
            or (for_mutation and history.is_revoked)
        ):
            raise InvalidEvidenceAdmissibilityError()

    def _decision_histories(
        self, unit_of_work: UnitOfWork, actor: ActorContext, evidence: EvidenceHistory
    ) -> tuple[EvidenceAdmissibilityHistory, ...]:
        result = tuple(
            history
            for item in evidence.versions
            if (
                history := unit_of_work.evidence_admissibility.get_history(
                    actor.workspace_id, item.id
                )
            )
            is not None
        )
        for history in result:
            history.validate_against(evidence)
        return result

    def _replay(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        command: DecideEvidenceAdmissibility,
        command_digest: str,
        history: EvidenceAdmissibilityHistory,
    ) -> EvidenceAdmissibilityOperationResult:
        matched = tuple(item for item in history.decisions if item.command_id == command.command_id)
        if len(matched) != 1 or matched[0].command_digest != command_digest:
            self._reject(
                unit_of_work,
                actor,
                AuditActionCode.EVIDENCE_ADMISSIBILITY_DECIDED,
                AuditReasonCode.COMMAND_ID_COLLISION,
                EvidenceAdmissibilityCommandCollisionError(),
            )
        persisted = matched[0]
        evidence = unit_of_work.evidence.get_history(actor.workspace_id, persisted.evidence_id)
        if evidence is None:
            self._reject(
                unit_of_work,
                actor,
                AuditActionCode.EVIDENCE_ADMISSIBILITY_DECIDED,
                AuditReasonCode.EVIDENCE_ADMISSIBILITY_HISTORY_INVALID,
                InvalidEvidenceAdmissibilityError(),
            )
        original_history = history.through(persisted.id)
        original_history.validate_against(evidence)
        effective = project_effective_evidence_admissibility(
            evidence_history=evidence,
            decision_histories=(original_history,),
            as_of=persisted.decided_at,
        )
        unit_of_work.commit()
        return EvidenceAdmissibilityOperationResult(
            history=original_history, effective=effective, replayed=True
        )

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


__all__ = ["EvidenceAdmissibilityService"]
