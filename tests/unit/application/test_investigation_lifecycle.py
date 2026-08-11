"""Unit tests for typed F4.1 command and durable transition contracts."""

from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.investigation_lifecycle import (
    CancelInvestigation,
    InvestigationCancellationReason,
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationLifecycleResult,
    InvestigationTransitionRecord,
    RequestEntityConfirmation,
    StartIdentification,
    command_type_of,
    digest_investigation_command,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CorrelationId,
    EntityCandidateBatchId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationTransitionId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import (
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import (
    InvestigationState,
    InvestigationTransition,
)
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    CandidateOriginSnapshot,
    CandidateSubmissionBatch,
    EntityCandidateInput,
)
from intelligence.entity_resolution.policy import (
    INITIAL_MATCH_POLICY,
    MatchClassification,
    MatchPolicy,
)

NOW = datetime(2026, 7, 29, 16, tzinfo=UTC)


def _actor() -> ActorContext:
    return ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )


def _input(name: str = "Empresa A") -> IdentificationInput:
    return IdentificationInput(
        legal_name=OriginalAndNormalizedText(
            original_value=name,
            normalized_value=name.lower(),
        )
    )


def _start() -> StartIdentification:
    return StartIdentification(
        command_id=InvestigationCommandId.new(),
        investigation_id=InvestigationId.new(),
        expected_state_version=1,
        identification_input=_input(),
    )


def _request() -> RequestEntityConfirmation:
    identification_input = _input()
    legal_name = identification_input.legal_name
    assert legal_name is not None
    return RequestEntityConfirmation(
        command_id=InvestigationCommandId.new(),
        investigation_id=InvestigationId.new(),
        expected_state_version=2,
        candidate_batch=CandidateSubmissionBatch(
            input_digest=identification_input.digest,
            candidates=(
                EntityCandidateInput(
                    candidate_key="candidate-1",
                    identity=CandidateIdentitySnapshot(
                        legal_name=legal_name,
                        country_code=CountryCode("BR"),
                    ),
                    origin=CandidateOriginSnapshot(
                        source_id="SYNTHETIC_SOURCE",
                        connector_id="synthetic.source",
                        connector_version="1.0.0",
                        source_candidate_reference="opaque-1",
                        collected_at=NOW,
                    ),
                ),
            ),
        ),
        matching_policy=INITIAL_MATCH_POLICY,
    )


def test_command_types_are_closed_typed_and_redact_input() -> None:
    start = _start()
    cancel = CancelInvestigation(
        command_id=InvestigationCommandId.new(),
        investigation_id=start.investigation_id,
        expected_state_version=2,
        reason=InvestigationCancellationReason.USER_REQUESTED,
    )

    assert command_type_of(start) is InvestigationCommandType.START_IDENTIFICATION
    assert command_type_of(cancel) is InvestigationCommandType.CANCEL_INVESTIGATION
    assert "Empresa A" not in repr(start)


def test_command_rejects_invalid_expected_version() -> None:
    with pytest.raises(InvariantViolationError, match="positive integer"):
        StartIdentification(
            command_id=InvestigationCommandId.new(),
            investigation_id=InvestigationId.new(),
            expected_state_version=0,
            identification_input=_input(),
        )


def test_request_command_validates_typed_payload_and_redacts_candidate() -> None:
    command = _request()

    assert command_type_of(command) is InvestigationCommandType.REQUEST_ENTITY_CONFIRMATION
    assert "Empresa A" not in repr(command)
    with pytest.raises(InvariantViolationError, match="candidate batch"):
        replace(command, candidate_batch=cast(CandidateSubmissionBatch, "invalid"))
    with pytest.raises(InvariantViolationError, match="matching policy"):
        replace(command, matching_policy=cast(MatchPolicy, "invalid"))


def test_request_transition_rejects_invalid_candidate_metadata() -> None:
    actor = _actor()
    command = _request()
    transition = InvestigationTransition(
        investigation_id=command.investigation_id,
        state_before=InvestigationState.IDENTIFYING,
        version_before=2,
        state_after=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
        version_after=3,
        occurred_at=NOW,
    )
    record = InvestigationTransitionRecord.from_transition(
        record_id=InvestigationTransitionId.new(),
        actor=actor,
        command=command,
        transition=transition,
        command_digest=digest_investigation_command(actor, command),
        candidate_batch_id=EntityCandidateBatchId.new(),
        candidate_count=1,
        top_classification=MatchClassification.LOW,
    )

    invalid_cases: tuple[tuple[str, object, str], ...] = (
        ("candidate_batch_id", "batch", "candidate_batch_id"),
        ("candidate_count", True, "candidate_count"),
        ("top_classification", "LOW", "top_classification"),
        ("policy_id", "", "policy_id"),
        ("policy_version", 0, "policy_version"),
    )
    for field_name, value, expected in invalid_cases:
        with pytest.raises(InvariantViolationError, match=expected):
            replace(record, **{field_name: value})  # type: ignore[arg-type]

    with pytest.raises(InvariantViolationError, match="invalid transition shape"):
        replace(record, candidate_count=None)
    with pytest.raises(InvariantViolationError, match="Only RequestEntityConfirmation"):
        replace(
            record,
            command_type=InvestigationCommandType.START_IDENTIFICATION,
            state_before=InvestigationState.CREATED,
            state_after=InvestigationState.IDENTIFYING,
        )


def test_digest_is_stable_but_changes_with_allowlisted_semantics() -> None:
    actor = _actor()
    command = _start()
    retry_actor = ActorContext(
        user_id=actor.user_id,
        workspace_id=actor.workspace_id,
        correlation_id=CorrelationId.new(),
    )

    first = digest_investigation_command(actor, command)
    second = digest_investigation_command(retry_actor, command)
    changed = digest_investigation_command(
        actor,
        StartIdentification(
            command_id=command.command_id,
            investigation_id=command.investigation_id,
            expected_state_version=command.expected_state_version,
            identification_input=_input("Empresa B"),
        ),
    )

    assert first == second
    assert first != changed
    assert len(first.value) == 64
    assert "Empresa" not in first.value


def test_transition_record_and_result_preserve_only_closed_result_shape() -> None:
    actor = _actor()
    command = _start()
    transition = InvestigationTransition(
        investigation_id=command.investigation_id,
        state_before=InvestigationState.CREATED,
        version_before=1,
        state_after=InvestigationState.IDENTIFYING,
        version_after=2,
        occurred_at=NOW,
    )
    record = InvestigationTransitionRecord.from_transition(
        record_id=InvestigationTransitionId.new(),
        actor=actor,
        command=command,
        transition=transition,
        command_digest=digest_investigation_command(actor, command),
    )

    result = InvestigationLifecycleResult.from_record(record, replayed=True)

    assert record.command_type is InvestigationCommandType.START_IDENTIFICATION
    assert record.reason is None
    assert result.investigation_id == command.investigation_id
    assert result.state is InvestigationState.IDENTIFYING
    assert result.state_version == 2
    assert result.replayed


def test_record_rejects_generic_or_incoherent_transition_shape() -> None:
    actor = _actor()
    command = _start()
    with pytest.raises(InvariantViolationError, match="invalid transition shape"):
        InvestigationTransitionRecord(
            id=InvestigationTransitionId.new(),
            workspace_id=actor.workspace_id,
            investigation_id=command.investigation_id,
            command_id=command.command_id,
            command_type=InvestigationCommandType.START_IDENTIFICATION,
            state_before=InvestigationState.CREATED,
            version_before=1,
            state_after=InvestigationState.PLANNING,
            version_after=2,
            actor_user_id=actor.user_id,
            reason=None,
            occurred_at=NOW,
            command_digest=digest_investigation_command(actor, command),
            correlation_id=actor.correlation_id,
        )


def test_cancel_digest_record_and_string_value_cover_closed_cancel_shape() -> None:
    actor = _actor()
    command = CancelInvestigation(
        command_id=InvestigationCommandId.new(),
        investigation_id=InvestigationId.new(),
        expected_state_version=4,
        reason=InvestigationCancellationReason.POLICY_REQUIRED,
    )
    digest = digest_investigation_command(actor, command)
    record = InvestigationTransitionRecord.from_transition(
        record_id=InvestigationTransitionId.new(),
        actor=actor,
        command=command,
        transition=InvestigationTransition(
            investigation_id=command.investigation_id,
            state_before=InvestigationState.ANALYZING,
            version_before=4,
            state_after=InvestigationState.CANCELLED,
            version_after=5,
            occurred_at=NOW,
        ),
        command_digest=digest,
    )

    assert record.reason is InvestigationCancellationReason.POLICY_REQUIRED
    assert str(digest) == digest.value


@pytest.mark.parametrize("value", ["A" * 64, "a" * 63, 123])
def test_command_digest_rejects_non_sha256_values(value: object) -> None:
    with pytest.raises(InvariantViolationError, match="SHA-256"):
        InvestigationCommandDigest(cast(str, value))


def test_commands_and_digest_reject_invalid_boundary_types() -> None:
    start = _start()
    with pytest.raises(InvariantViolationError, match="command_id"):
        replace(start, command_id=cast(InvestigationCommandId, InvestigationId.new()))
    with pytest.raises(InvariantViolationError, match="investigation_id"):
        replace(start, investigation_id=cast(InvestigationId, InvestigationCommandId.new()))
    with pytest.raises(InvariantViolationError, match="positive integer"):
        replace(start, expected_state_version=True)
    with pytest.raises(InvariantViolationError, match="identification_input"):
        replace(start, identification_input=cast(IdentificationInput, "invalid"))

    cancel = CancelInvestigation(
        command_id=InvestigationCommandId.new(),
        investigation_id=InvestigationId.new(),
        expected_state_version=1,
        reason=InvestigationCancellationReason.USER_REQUESTED,
    )
    with pytest.raises(InvariantViolationError, match="closed vocabulary"):
        replace(cancel, reason=cast(InvestigationCancellationReason, "OTHER"))
    with pytest.raises(TypeError, match="Unsupported"):
        command_type_of(cast(StartIdentification, object()))
    with pytest.raises(TypeError, match="ActorContext"):
        digest_investigation_command(cast(ActorContext, object()), start)


def test_transition_record_rejects_invalid_types_versions_and_cancel_shape() -> None:
    actor = _actor()
    command = _start()
    transition = InvestigationTransition(
        investigation_id=command.investigation_id,
        state_before=InvestigationState.CREATED,
        version_before=1,
        state_after=InvestigationState.IDENTIFYING,
        version_after=2,
        occurred_at=NOW,
    )
    record = InvestigationTransitionRecord.from_transition(
        record_id=InvestigationTransitionId.new(),
        actor=actor,
        command=command,
        transition=transition,
        command_digest=digest_investigation_command(actor, command),
    )

    invalid_cases: tuple[tuple[str, object, str], ...] = (
        ("id", InvestigationId.new(), "invalid type"),
        ("command_type", "START", "command_type"),
        ("state_before", "CREATED", "states"),
        ("version_before", True, "version_before"),
        ("version_after", True, "version_after"),
        ("reason", "OTHER", "reason"),
        ("command_digest", "a" * 64, "command_digest"),
    )
    for field_name, value, expected in invalid_cases:
        with pytest.raises(InvariantViolationError, match=expected):
            replace(record, **{field_name: value})  # type: ignore[arg-type]

    with pytest.raises(InvariantViolationError, match="increment"):
        replace(record, version_after=3)
    with pytest.raises(InvariantViolationError, match="CancelInvestigation"):
        replace(
            record,
            command_type=InvestigationCommandType.CANCEL_INVESTIGATION,
            state_after=InvestigationState.CANCELLED,
            reason=None,
        )
