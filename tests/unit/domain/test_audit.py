"""Tests for immutable minimal audit events."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from intelligence.domain.audit import (
    ACTION_CODE_MAX_LENGTH,
    REASON_CODE_MAX_LENGTH,
    AuditEvent,
    AuditOutcome,
    AuditResourceType,
)
from intelligence.domain.errors import InvalidDateTimeError, InvariantViolationError
from intelligence.domain.identifiers import (
    AuditEventId,
    CompanyId,
    CorrelationId,
    InvestigationId,
    MembershipId,
    UserId,
    WorkspaceId,
)


def _audit_event(**overrides: object) -> AuditEvent:
    values: dict[str, object] = {
        "id": AuditEventId.new(),
        "workspace_id": WorkspaceId.new(),
        "actor_user_id": UserId.new(),
        "action_code": "  investigation.read  ",
        "resource_type": AuditResourceType.INVESTIGATION,
        "resource_id": InvestigationId.new(),
        "outcome": AuditOutcome.SUCCESS,
        "reason_code": "  membership.active  ",
        "correlation_id": CorrelationId.new(),
        "occurred_at": datetime(
            2026,
            7,
            28,
            9,
            30,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
    }
    values.update(overrides)
    return AuditEvent(**cast(Any, values))


def test_audit_event_normalizes_codes_and_timestamp() -> None:
    event = _audit_event()

    assert event.action_code == "INVESTIGATION.READ"
    assert event.reason_code == "MEMBERSHIP.ACTIVE"
    assert event.occurred_at == datetime(2026, 7, 28, 12, 30, tzinfo=UTC)


def test_audit_vocabularies_are_closed() -> None:
    assert {outcome.value for outcome in AuditOutcome} == {
        "SUCCESS",
        "DENIED",
        "FAILURE",
    }
    assert {resource.value for resource in AuditResourceType} == {
        "WORKSPACE",
        "USER",
        "MEMBERSHIP",
        "COMPANY",
        "INVESTIGATION",
    }


@pytest.mark.parametrize("outcome", list(AuditOutcome))
def test_audit_event_accepts_every_outcome(outcome: AuditOutcome) -> None:
    event = _audit_event(outcome=outcome)

    assert event.outcome is outcome


@pytest.mark.parametrize(
    ("resource_type", "resource_id"),
    [
        (AuditResourceType.WORKSPACE, WorkspaceId.new()),
        (AuditResourceType.USER, UserId.new()),
        (AuditResourceType.MEMBERSHIP, MembershipId.new()),
        (AuditResourceType.COMPANY, CompanyId.new()),
        (AuditResourceType.INVESTIGATION, InvestigationId.new()),
    ],
)
def test_audit_event_accepts_every_resource_type_with_a_typed_id(
    resource_type: AuditResourceType,
    resource_id: WorkspaceId | UserId | MembershipId | CompanyId | InvestigationId,
) -> None:
    event = _audit_event(resource_type=resource_type, resource_id=resource_id)

    assert event.resource_type is resource_type
    assert event.resource_id == resource_id


def test_audit_event_accepts_absent_resource_and_reason() -> None:
    event = _audit_event(resource_id=None, reason_code=None)

    assert event.resource_id is None
    assert event.reason_code is None


@pytest.mark.parametrize(
    "invalid_action_code",
    ["", "  ", "invalid action", "9INVALID", "A" * (ACTION_CODE_MAX_LENGTH + 1)],
)
def test_audit_event_rejects_invalid_action_code(invalid_action_code: str) -> None:
    with pytest.raises(InvariantViolationError):
        _audit_event(action_code=invalid_action_code)


@pytest.mark.parametrize(
    "invalid_reason_code",
    ["invalid reason", "9INVALID", "R" * (REASON_CODE_MAX_LENGTH + 1)],
)
def test_audit_event_rejects_invalid_reason_code(invalid_reason_code: str) -> None:
    with pytest.raises(InvariantViolationError):
        _audit_event(reason_code=invalid_reason_code)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("id", "event"),
        ("workspace_id", "workspace"),
        ("actor_user_id", "user"),
        ("resource_type", "INVESTIGATION"),
        ("resource_id", "investigation"),
        ("outcome", "SUCCESS"),
        ("correlation_id", "correlation"),
    ],
)
def test_audit_event_rejects_untyped_fields(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(InvariantViolationError):
        _audit_event(**{field_name: invalid_value})


def test_audit_event_rejects_non_text_codes() -> None:
    with pytest.raises(InvariantViolationError):
        _audit_event(action_code=42)
    with pytest.raises(InvariantViolationError):
        _audit_event(reason_code=42)


def test_audit_event_rejects_naive_timestamp() -> None:
    with pytest.raises(InvalidDateTimeError):
        _audit_event(occurred_at=datetime(2026, 7, 28, 12, 30))


def test_audit_event_is_immutable() -> None:
    event = _audit_event()

    with pytest.raises(FrozenInstanceError):
        event.__setattr__("outcome", AuditOutcome.FAILURE)
