"""Tests for the closed F2.4.2 application audit vocabulary and helpers."""

from datetime import UTC, datetime
from typing import cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    AuditReasonCode,
    build_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.ports.unit_of_work import UnitOfWork
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.identifiers import CompanyId, CorrelationId, UserId, WorkspaceId
from tests.unit.application.fakes import FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)


def _actor() -> ActorContext:
    return ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )


def test_closed_audit_catalog_contains_the_required_actions_and_reasons() -> None:
    assert {code.value for code in AuditActionCode} == {
        "MEMBERSHIP_ADDED",
        "MEMBERSHIP_ROLE_CHANGED",
        "MEMBERSHIP_DEACTIVATED",
        "MEMBERSHIP_REACTIVATED",
        "COMPANY_CREATED",
        "INVESTIGATION_CREATED",
        "INVESTIGATION_IDENTIFICATION_STARTED",
        "INVESTIGATION_CANCELLED",
        "INVESTIGATION_ENTITY_CONFIRMATION_REQUESTED",
        "INVESTIGATION_ENTITY_CANDIDATE_CONFIRMED",
        "INVESTIGATION_PLAN_CREATED",
        "INVESTIGATION_COLLECTION_STARTED",
        "COLLECTION_OPERATION_EXECUTED",
        "EVIDENCE_REGISTERED",
        "EVIDENCE_CORRECTED",
        "EVIDENCE_REVOKED",
        "EVIDENCE_READ_DENIED",
        "EVIDENCE_ADMISSIBILITY_DECIDED",
        "EVIDENCE_ADMISSIBILITY_SUPERSEDED",
        "EVIDENCE_ADMISSIBILITY_READ_DENIED",
        "COMPANY_READ_DENIED",
        "INVESTIGATION_READ_DENIED",
        "CLAIM_REGISTERED",
        "CLAIM_CORRECTED",
        "CLAIM_READ_DENIED",
    }
    assert {
        "ACTOR_USER_NOT_FOUND",
        "PERMISSION_DENIED",
        "LAST_OWNER_PROTECTED",
        "PERSISTENCE_FAILURE",
        "STATE_VERSION_CONFLICT",
        "COMMAND_ID_COLLISION",
        "INVALID_TRANSITION",
        "INPUT_DIGEST_MISMATCH",
        "CANDIDATE_REVIEW_INVALID",
        "CANDIDATE_BATCH_INACTIVE",
        "CANDIDATE_NOT_IN_BATCH",
        "CANDIDATE_EXCLUDED",
        "CONFIRMATION_REASON_INCOMPATIBLE",
        "MATERIALIZATION_POLICY_INVALID",
        "PLANNING_POLICY_INVALID",
        "PLANNING_CONTEXT_INVALID",
        "REQUIRED_CAPABILITY_UNAVAILABLE",
        "PLANNING_BUDGET_EXCEEDED",
        "PLANNING_DEADLINE_EXCEEDED",
        "INVESTIGATION_PLAN_ALREADY_EXISTS",
        "COLLECTION_ACTIVATION_POLICY_INVALID",
        "COLLECTION_CONTEXT_INVALID",
        "COLLECTION_DEADLINE_EXCEEDED",
        "COLLECTION_RUN_ALREADY_EXISTS",
        "COLLECTION_EXECUTION_INVALID",
        "COLLECTION_EXECUTION_ALREADY_OWNED",
        "COLLECTION_EXECUTION_IN_PROGRESS",
        "COLLECTION_EXECUTION_DEPENDENCY_PENDING",
        "EVIDENCE_CONTEXT_INVALID",
        "EVIDENCE_VERSION_CONFLICT",
        "EVIDENCE_ALREADY_REVOKED",
        "EVIDENCE_ADMISSIBILITY_SELF_APPROVAL",
        "EVIDENCE_ADMISSIBILITY_CONTEXT_INVALID",
        "EVIDENCE_ADMISSIBILITY_POLICY_INVALID",
        "EVIDENCE_ADMISSIBILITY_PREDECESSOR_INVALID",
        "EVIDENCE_ADMISSIBILITY_HISTORY_INVALID",
        "CLAIM_CONTEXT_INVALID",
        "CLAIM_VERSION_CONFLICT",
        "CLAIM_EVIDENCE_INVALID",
        "CANCELLATION_USER_REQUESTED",
    } <= {code.value for code in AuditReasonCode}


def test_event_uses_only_actor_scope_correlation_and_closed_codes() -> None:
    actor = _actor()
    company_id = CompanyId.new()

    event = build_audit_event(
        actor=actor,
        action=AuditActionCode.COMPANY_CREATED,
        resource_type=AuditResourceType.COMPANY,
        resource_id=company_id,
        outcome=AuditOutcome.SUCCESS,
        reason=None,
        occurred_at=NOW,
    )

    assert event.workspace_id == actor.workspace_id
    assert event.actor_user_id == actor.user_id
    assert event.correlation_id == actor.correlation_id
    assert event.resource_id == company_id
    assert event.action_code == AuditActionCode.COMPANY_CREATED.value
    assert event.reason_code is None


def test_denied_and_failed_events_require_a_closed_reason() -> None:
    actor = _actor()

    with pytest.raises(ValueError, match="require a reason"):
        build_audit_event(
            actor=actor,
            action=AuditActionCode.COMPANY_READ_DENIED,
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=None,
            occurred_at=NOW,
        )
    with pytest.raises(TypeError, match="action"):
        build_audit_event(
            actor=actor,
            action=cast(AuditActionCode, "DYNAMIC"),
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.SUCCESS,
            reason=None,
            occurred_at=NOW,
        )
    with pytest.raises(TypeError, match="reason"):
        build_audit_event(
            actor=actor,
            action=AuditActionCode.COMPANY_READ_DENIED,
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=cast(AuditReasonCode, "DYNAMIC"),
            occurred_at=NOW,
        )


def test_standalone_outcome_commits_event_and_preserves_correlation() -> None:
    actor = _actor()
    factory = FakeUnitOfWorkFactory()
    with factory() as unit_of_work:
        persisted = commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=AuditActionCode.COMPANY_READ_DENIED,
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=AuditReasonCode.PERMISSION_DENIED,
            occurred_at=NOW,
        )

    assert persisted
    assert factory.database.audit_events[0].correlation_id == actor.correlation_id
    assert factory.created[0].commit_calls == 1


def test_standalone_outcome_does_not_replace_original_when_audit_is_unavailable() -> None:
    actor = _actor()
    factory = FakeUnitOfWorkFactory(fail_audit=True)
    with factory() as concrete:
        persisted = commit_standalone_outcome(
            cast(UnitOfWork, concrete),
            actor=actor,
            action=AuditActionCode.COMPANY_READ_DENIED,
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=AuditReasonCode.ACTOR_USER_NOT_FOUND,
            occurred_at=NOW,
        )

    assert not persisted
    assert factory.database.audit_events == []
