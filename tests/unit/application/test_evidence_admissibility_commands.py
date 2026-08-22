"""F5.3 command boundary and canonical digest tests."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.evidence_admissibility import (
    DecideEvidenceAdmissibility,
    digest_decide_evidence_admissibility,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CorrelationId,
    EvidenceAdmissibilityCommandId,
    EvidenceId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
)


def _actor() -> ActorContext:
    return ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )


def _command() -> DecideEvidenceAdmissibility:
    return DecideEvidenceAdmissibility(
        command_id=EvidenceAdmissibilityCommandId.new(),
        investigation_id=InvestigationId.new(),
        evidence_id=EvidenceId.new(),
        expected_evidence_digest="a" * 64,
        expected_previous_decision_digest=None,
        requested_action=EvidenceAdmissibilityRequestedAction.ADMIT,
        reason_code=EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED,
        requested_valid_until=datetime(2027, 1, 1, tzinfo=UTC),
    )


def test_digest_is_deterministic_actor_and_workspace_bound_and_repr_redacts() -> None:
    actor = _actor()
    command = _command()
    first = digest_decide_evidence_admissibility(actor, command)
    assert first == digest_decide_evidence_admissibility(actor, command)
    assert first != digest_decide_evidence_admissibility(_actor(), command)
    assert command.expected_evidence_digest not in repr(command)


def test_command_rejects_untyped_ids_hashes_vocabulary_schema_and_negative_expiration() -> None:
    command = _command()
    with pytest.raises(InvariantViolationError):
        replace(command, command_id=cast(EvidenceAdmissibilityCommandId, EvidenceId.new()))
    with pytest.raises(InvariantViolationError):
        replace(command, expected_evidence_digest="A" * 64)
    with pytest.raises(InvariantViolationError):
        replace(command, expected_previous_decision_digest="short")
    with pytest.raises(InvariantViolationError):
        replace(
            command,
            requested_action=cast(EvidenceAdmissibilityRequestedAction, "ADMIT"),
        )
    with pytest.raises(InvariantViolationError):
        replace(command, schema_version=2)
    with pytest.raises(InvariantViolationError):
        replace(command, requested_action=EvidenceAdmissibilityRequestedAction.RESTRICT)
