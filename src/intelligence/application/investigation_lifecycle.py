"""Typed F4.1 investigation commands, durable records, and safe results."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CollectionRunId,
    CompanyId,
    CorrelationId,
    EntityCandidateBatchId,
    EntityCandidateId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    InvestigationTransitionId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import IdentificationInput
from intelligence.domain.investigations import (
    TERMINAL_INVESTIGATION_STATES,
    InvestigationState,
    InvestigationTransition,
)
from intelligence.domain.time import normalize_utc
from intelligence.entity_resolution.contracts import CandidateSubmissionBatch
from intelligence.entity_resolution.policy import MatchClassification, MatchPolicy

_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class InvestigationCommandType(StrEnum):
    """Closed lifecycle commands authorized through F4.2."""

    START_IDENTIFICATION = "START_IDENTIFICATION"
    CANCEL_INVESTIGATION = "CANCEL_INVESTIGATION"
    REQUEST_ENTITY_CONFIRMATION = "REQUEST_ENTITY_CONFIRMATION"
    CONFIRM_ENTITY_CANDIDATE = "CONFIRM_ENTITY_CANDIDATE"
    START_COLLECTION = "START_COLLECTION"


class InvestigationCancellationReason(StrEnum):
    """Closed, public cancellation reasons without free text."""

    USER_REQUESTED = "USER_REQUESTED"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"
    NO_LONGER_REQUIRED = "NO_LONGER_REQUIRED"
    POLICY_REQUIRED = "POLICY_REQUIRED"


@dataclass(frozen=True, slots=True)
class InvestigationCommandDigest:
    """Canonical SHA-256 command digest safe for durable storage."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or _SHA256_PATTERN.fullmatch(self.value) is None:
            raise InvariantViolationError(
                "Investigation command digest must be a lowercase SHA-256 value."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class StartIdentification:
    """Typed command for the only authorized start transition."""

    command_id: InvestigationCommandId
    investigation_id: InvestigationId
    expected_state_version: int
    identification_input: IdentificationInput = field(repr=False)

    def __post_init__(self) -> None:
        _validate_command_common(
            command_id=self.command_id,
            investigation_id=self.investigation_id,
            expected_state_version=self.expected_state_version,
        )
        if not isinstance(self.identification_input, IdentificationInput):
            raise InvariantViolationError("StartIdentification identification_input must be typed.")

    def __repr__(self) -> str:
        return (
            "StartIdentification("
            f"command_id={self.command_id!r}, "
            f"investigation_id={self.investigation_id!r}, "
            f"expected_state_version={self.expected_state_version}, "
            "identification_input=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CancelInvestigation:
    """Typed command for terminal cancellation of a non-terminal investigation."""

    command_id: InvestigationCommandId
    investigation_id: InvestigationId
    expected_state_version: int
    reason: InvestigationCancellationReason

    def __post_init__(self) -> None:
        _validate_command_common(
            command_id=self.command_id,
            investigation_id=self.investigation_id,
            expected_state_version=self.expected_state_version,
        )
        if not isinstance(self.reason, InvestigationCancellationReason):
            raise InvariantViolationError(
                "CancelInvestigation reason must use the closed vocabulary."
            )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RequestEntityConfirmation:
    """Typed internal command to persist candidates and pause for human review."""

    command_id: InvestigationCommandId
    investigation_id: InvestigationId
    expected_state_version: int
    candidate_batch: CandidateSubmissionBatch = field(repr=False)
    matching_policy: MatchPolicy = field(repr=False)

    def __post_init__(self) -> None:
        _validate_command_common(
            command_id=self.command_id,
            investigation_id=self.investigation_id,
            expected_state_version=self.expected_state_version,
        )
        if not isinstance(self.candidate_batch, CandidateSubmissionBatch):
            raise InvariantViolationError(
                "RequestEntityConfirmation candidate batch must be typed."
            )
        if not isinstance(self.matching_policy, MatchPolicy):
            raise InvariantViolationError(
                "RequestEntityConfirmation matching policy must be typed."
            )

    def __repr__(self) -> str:
        return (
            "RequestEntityConfirmation("
            f"command_id={self.command_id!r}, "
            f"investigation_id={self.investigation_id!r}, "
            f"expected_state_version={self.expected_state_version}, "
            f"candidate_count={len(self.candidate_batch.candidates)}, "
            f"policy_id={self.matching_policy.policy_id!r}, payload=<redacted>)"
        )


type InvestigationLifecycleCommand = (
    StartIdentification | CancelInvestigation | RequestEntityConfirmation
)


@dataclass(frozen=True, slots=True, kw_only=True)
class InvestigationTransitionRecord:
    """Append-only durable record coordinating transition and idempotency."""

    id: InvestigationTransitionId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    command_id: InvestigationCommandId
    command_type: InvestigationCommandType
    state_before: InvestigationState
    version_before: int
    state_after: InvestigationState
    version_after: int
    actor_user_id: UserId
    reason: InvestigationCancellationReason | None
    occurred_at: datetime
    command_digest: InvestigationCommandDigest
    correlation_id: CorrelationId
    candidate_batch_id: EntityCandidateBatchId | None = None
    candidate_count: int | None = None
    top_classification: MatchClassification | None = None
    policy_id: str | None = None
    policy_version: int | None = None
    confirmation_decision_id: EntityResolutionDecisionId | None = None
    confirmed_company_id: CompanyId | None = None
    confirmed_candidate_batch_id: EntityCandidateBatchId | None = None
    confirmed_candidate_id: EntityCandidateId | None = None
    confirmation_reason_code: str | None = None
    confirmed_candidate_classification: MatchClassification | None = None
    confirmed_candidate_rank: int | None = None
    matching_policy_id: str | None = None
    matching_policy_version: int | None = None
    materialization_policy_id: str | None = None
    materialization_policy_version: int | None = None
    collection_run_id: CollectionRunId | None = None
    collection_company_id: CompanyId | None = None
    collection_plan_id: InvestigationPlanId | None = None
    collection_operation_count: int | None = None
    collection_activation_policy_id: str | None = None
    collection_activation_policy_version: int | None = None

    def __post_init__(self) -> None:
        _validate_record_types(self)
        if self.version_before < 1 or self.version_after != self.version_before + 1:
            raise InvariantViolationError(
                "Investigation transition record must increment state_version exactly once."
            )
        if self.command_type is InvestigationCommandType.START_IDENTIFICATION:
            if (
                self.state_before is not InvestigationState.CREATED
                or self.state_after is not InvestigationState.IDENTIFYING
                or self.reason is not None
            ):
                raise InvariantViolationError(
                    "StartIdentification record has an invalid transition shape."
                )
            _require_no_candidate_metadata(self)
            _require_no_confirmation_metadata(self)
            _require_no_collection_metadata(self)
        elif self.command_type is InvestigationCommandType.CANCEL_INVESTIGATION:
            if (
                self.state_before in TERMINAL_INVESTIGATION_STATES
                or self.state_after is not InvestigationState.CANCELLED
                or self.reason is None
            ):
                raise InvariantViolationError(
                    "CancelInvestigation record has an invalid transition shape."
                )
            _require_no_candidate_metadata(self)
            _require_no_confirmation_metadata(self)
            _require_no_collection_metadata(self)
        elif self.command_type is InvestigationCommandType.REQUEST_ENTITY_CONFIRMATION:
            if (
                self.state_before is not InvestigationState.IDENTIFYING
                or self.state_after is not InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
                or self.reason is not None
                or self.candidate_batch_id is None
                or self.candidate_count is None
                or self.top_classification is None
                or self.policy_id is None
                or self.policy_version is None
            ):
                raise InvariantViolationError(
                    "RequestEntityConfirmation record has an invalid transition shape."
                )
            _require_no_confirmation_metadata(self)
            _require_no_collection_metadata(self)
        elif self.command_type is InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE:
            _require_no_candidate_metadata(self)
            _require_no_collection_metadata(self)
            if (
                self.state_before is not InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
                or self.state_after is not InvestigationState.PLANNING
                or self.reason is not None
                or not _confirmation_metadata_complete(self)
            ):
                raise InvariantViolationError(
                    "ConfirmEntityCandidate record has an invalid transition shape."
                )
        elif self.command_type is InvestigationCommandType.START_COLLECTION:
            _require_no_candidate_metadata(self)
            _require_no_confirmation_metadata(self)
            if (
                self.state_before is not InvestigationState.PLANNING
                or self.state_after is not InvestigationState.COLLECTING
                or self.reason is not None
                or not _collection_metadata_complete(self)
            ):
                raise InvariantViolationError(
                    "StartInvestigationCollection record has an invalid transition shape."
                )
        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at))

    @classmethod
    def from_transition(
        cls,
        *,
        record_id: InvestigationTransitionId,
        actor: ActorContext,
        command: InvestigationLifecycleCommand,
        transition: InvestigationTransition,
        command_digest: InvestigationCommandDigest,
        candidate_batch_id: EntityCandidateBatchId | None = None,
        candidate_count: int | None = None,
        top_classification: MatchClassification | None = None,
    ) -> InvestigationTransitionRecord:
        """Create a durable application record from a pure domain transition."""

        command_type = command_type_of(command)
        return cls(
            id=record_id,
            workspace_id=actor.workspace_id,
            investigation_id=command.investigation_id,
            command_id=command.command_id,
            command_type=command_type,
            state_before=transition.state_before,
            version_before=transition.version_before,
            state_after=transition.state_after,
            version_after=transition.version_after,
            actor_user_id=actor.user_id,
            reason=command.reason if isinstance(command, CancelInvestigation) else None,
            occurred_at=transition.occurred_at,
            command_digest=command_digest,
            correlation_id=actor.correlation_id,
            candidate_batch_id=candidate_batch_id,
            candidate_count=candidate_count,
            top_classification=top_classification,
            policy_id=(
                command.matching_policy.policy_id
                if isinstance(command, RequestEntityConfirmation)
                else None
            ),
            policy_version=(
                command.matching_policy.version
                if isinstance(command, RequestEntityConfirmation)
                else None
            ),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class InvestigationLifecycleResult:
    """Stable public result derived solely from an append-only transition record."""

    investigation_id: InvestigationId
    state: InvestigationState
    state_version: int
    occurred_at: datetime
    replayed: bool
    candidate_batch_id: EntityCandidateBatchId | None = None
    candidate_count: int | None = None
    top_classification: MatchClassification | None = None

    @classmethod
    def from_record(
        cls,
        record: InvestigationTransitionRecord,
        *,
        replayed: bool,
    ) -> InvestigationLifecycleResult:
        return cls(
            investigation_id=record.investigation_id,
            state=record.state_after,
            state_version=record.version_after,
            occurred_at=record.occurred_at,
            replayed=replayed,
            candidate_batch_id=record.candidate_batch_id,
            candidate_count=record.candidate_count,
            top_classification=record.top_classification,
        )


def command_type_of(command: InvestigationLifecycleCommand) -> InvestigationCommandType:
    """Return the closed discriminator without accepting arbitrary destinations."""

    if isinstance(command, StartIdentification):
        return InvestigationCommandType.START_IDENTIFICATION
    if isinstance(command, CancelInvestigation):
        return InvestigationCommandType.CANCEL_INVESTIGATION
    if isinstance(command, RequestEntityConfirmation):
        return InvestigationCommandType.REQUEST_ENTITY_CONFIRMATION
    raise TypeError("Unsupported investigation lifecycle command.")


def digest_investigation_command(
    actor: ActorContext,
    command: InvestigationLifecycleCommand,
) -> InvestigationCommandDigest:
    """Hash an explicit allowlist; exclude server time and retry correlation."""

    if not isinstance(actor, ActorContext):
        raise TypeError("actor must be an ActorContext")
    content: dict[str, object] = {
        "actor_user_id": str(actor.user_id),
        "command_type": command_type_of(command).value,
        "expected_state_version": command.expected_state_version,
        "investigation_id": str(command.investigation_id),
        "workspace_id": str(actor.workspace_id),
    }
    if isinstance(command, StartIdentification):
        content["identification_input"] = command.identification_input.to_canonical_json()
    elif isinstance(command, CancelInvestigation):
        content["reason"] = command.reason.value
    else:
        content["candidate_batch"] = command.candidate_batch.to_canonical_json()
        content["matching_policy"] = command.matching_policy.to_canonical_json()
    serialized = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return InvestigationCommandDigest(sha256(serialized.encode("utf-8")).hexdigest())


def _validate_command_common(
    *,
    command_id: InvestigationCommandId,
    investigation_id: InvestigationId,
    expected_state_version: int,
) -> None:
    if not isinstance(command_id, InvestigationCommandId):
        raise InvariantViolationError("command_id must be an InvestigationCommandId.")
    if not isinstance(investigation_id, InvestigationId):
        raise InvariantViolationError("investigation_id must be an InvestigationId.")
    if (
        isinstance(expected_state_version, bool)
        or not isinstance(expected_state_version, int)
        or expected_state_version < 1
    ):
        raise InvariantViolationError("expected_state_version must be a positive integer.")


def _validate_record_types(record: InvestigationTransitionRecord) -> None:
    typed_fields = (
        (record.id, InvestigationTransitionId, "id"),
        (record.workspace_id, WorkspaceId, "workspace_id"),
        (record.investigation_id, InvestigationId, "investigation_id"),
        (record.command_id, InvestigationCommandId, "command_id"),
        (record.actor_user_id, UserId, "actor_user_id"),
        (record.correlation_id, CorrelationId, "correlation_id"),
    )
    for value, expected_type, field_name in typed_fields:
        if not isinstance(value, expected_type):
            raise InvariantViolationError(
                f"Investigation transition record {field_name} has an invalid type."
            )
    if not isinstance(record.command_type, InvestigationCommandType):
        raise InvariantViolationError(
            "Investigation transition record command_type has an invalid type."
        )
    if not isinstance(record.state_before, InvestigationState) or not isinstance(
        record.state_after, InvestigationState
    ):
        raise InvariantViolationError(
            "Investigation transition record states have an invalid type."
        )
    if isinstance(record.version_before, bool) or not isinstance(record.version_before, int):
        raise InvariantViolationError(
            "Investigation transition record version_before must be an integer."
        )
    if isinstance(record.version_after, bool) or not isinstance(record.version_after, int):
        raise InvariantViolationError(
            "Investigation transition record version_after must be an integer."
        )
    if record.reason is not None and not isinstance(record.reason, InvestigationCancellationReason):
        raise InvariantViolationError("Investigation transition record reason has an invalid type.")
    if not isinstance(record.command_digest, InvestigationCommandDigest):
        raise InvariantViolationError(
            "Investigation transition record command_digest has an invalid type."
        )
    if record.candidate_batch_id is not None and not isinstance(
        record.candidate_batch_id, EntityCandidateBatchId
    ):
        raise InvariantViolationError("Transition candidate_batch_id has an invalid type.")
    if record.candidate_count is not None and (
        isinstance(record.candidate_count, bool)
        or not isinstance(record.candidate_count, int)
        or not 1 <= record.candidate_count <= 100
    ):
        raise InvariantViolationError("Transition candidate_count has an invalid value.")
    if record.top_classification is not None and not isinstance(
        record.top_classification, MatchClassification
    ):
        raise InvariantViolationError("Transition top_classification has an invalid type.")
    if record.policy_id is not None and (
        not isinstance(record.policy_id, str) or not record.policy_id
    ):
        raise InvariantViolationError("Transition policy_id has an invalid value.")
    if record.policy_version is not None and (
        isinstance(record.policy_version, bool)
        or not isinstance(record.policy_version, int)
        or record.policy_version < 1
    ):
        raise InvariantViolationError("Transition policy_version has an invalid value.")
    confirmation_typed_ids = (
        (record.confirmation_decision_id, EntityResolutionDecisionId),
        (record.confirmed_company_id, CompanyId),
        (record.confirmed_candidate_batch_id, EntityCandidateBatchId),
        (record.confirmed_candidate_id, EntityCandidateId),
    )
    for confirmation_value, confirmation_type in confirmation_typed_ids:
        if confirmation_value is not None and not isinstance(confirmation_value, confirmation_type):
            raise InvariantViolationError("Transition confirmation identifier has an invalid type.")
    if record.confirmation_reason_code is not None and record.confirmation_reason_code not in {
        "IDENTIFIERS_REVIEWED",
        "CORPORATE_DATA_REVIEWED",
        "SOURCE_REFERENCE_REVIEWED",
        "MANUAL_OVERRIDE",
    }:
        raise InvariantViolationError("Transition confirmation reason has an invalid value.")
    if record.confirmed_candidate_classification is not None and (
        not isinstance(record.confirmed_candidate_classification, MatchClassification)
        or record.confirmed_candidate_classification is MatchClassification.EXCLUDED
    ):
        raise InvariantViolationError("Transition confirmed classification is invalid.")
    if record.confirmed_candidate_rank is not None and (
        isinstance(record.confirmed_candidate_rank, bool)
        or not isinstance(record.confirmed_candidate_rank, int)
        or not 1 <= record.confirmed_candidate_rank <= 100
    ):
        raise InvariantViolationError("Transition confirmed candidate rank is invalid.")
    for policy_id, policy_version, kind in (
        (record.matching_policy_id, record.matching_policy_version, "matching"),
        (
            record.materialization_policy_id,
            record.materialization_policy_version,
            "materialization",
        ),
    ):
        if policy_id is not None and (not isinstance(policy_id, str) or not policy_id):
            raise InvariantViolationError(f"Transition {kind} policy ID is invalid.")
        if policy_version is not None and (
            isinstance(policy_version, bool)
            or not isinstance(policy_version, int)
            or policy_version < 1
        ):
            raise InvariantViolationError(f"Transition {kind} policy version is invalid.")
    if record.collection_run_id is not None and not isinstance(
        record.collection_run_id, CollectionRunId
    ):
        raise InvariantViolationError("Transition collection run ID has an invalid type.")
    if record.collection_company_id is not None and not isinstance(
        record.collection_company_id, CompanyId
    ):
        raise InvariantViolationError("Transition collection Company ID has an invalid type.")
    if record.collection_plan_id is not None and not isinstance(
        record.collection_plan_id, InvestigationPlanId
    ):
        raise InvariantViolationError("Transition collection plan ID has an invalid type.")
    if record.collection_operation_count is not None and (
        isinstance(record.collection_operation_count, bool)
        or not isinstance(record.collection_operation_count, int)
        or not 1 <= record.collection_operation_count <= 10
    ):
        raise InvariantViolationError("Transition collection operation count is invalid.")
    if record.collection_activation_policy_id is not None and (
        not isinstance(record.collection_activation_policy_id, str)
        or not record.collection_activation_policy_id
    ):
        raise InvariantViolationError("Transition collection policy ID is invalid.")
    if record.collection_activation_policy_version is not None and (
        isinstance(record.collection_activation_policy_version, bool)
        or not isinstance(record.collection_activation_policy_version, int)
        or record.collection_activation_policy_version < 1
    ):
        raise InvariantViolationError("Transition collection policy version is invalid.")


def _require_no_candidate_metadata(record: InvestigationTransitionRecord) -> None:
    if any(
        value is not None
        for value in (
            record.candidate_batch_id,
            record.candidate_count,
            record.top_classification,
            record.policy_id,
            record.policy_version,
        )
    ):
        raise InvariantViolationError(
            "Only RequestEntityConfirmation records can contain candidate metadata."
        )


def _confirmation_metadata(record: InvestigationTransitionRecord) -> tuple[object | None, ...]:
    return (
        record.confirmation_decision_id,
        record.confirmed_company_id,
        record.confirmed_candidate_batch_id,
        record.confirmed_candidate_id,
        record.confirmation_reason_code,
        record.confirmed_candidate_classification,
        record.confirmed_candidate_rank,
        record.matching_policy_id,
        record.matching_policy_version,
        record.materialization_policy_id,
        record.materialization_policy_version,
    )


def _confirmation_metadata_complete(record: InvestigationTransitionRecord) -> bool:
    return all(value is not None for value in _confirmation_metadata(record))


def _require_no_confirmation_metadata(record: InvestigationTransitionRecord) -> None:
    if any(value is not None for value in _confirmation_metadata(record)):
        raise InvariantViolationError(
            "Only ConfirmEntityCandidate records can contain confirmation metadata."
        )


def _collection_metadata(record: InvestigationTransitionRecord) -> tuple[object | None, ...]:
    return (
        record.collection_run_id,
        record.collection_company_id,
        record.collection_plan_id,
        record.collection_operation_count,
        record.collection_activation_policy_id,
        record.collection_activation_policy_version,
    )


def _collection_metadata_complete(record: InvestigationTransitionRecord) -> bool:
    return all(value is not None for value in _collection_metadata(record))


def _require_no_collection_metadata(record: InvestigationTransitionRecord) -> None:
    if any(value is not None for value in _collection_metadata(record)):
        raise InvariantViolationError(
            "Only StartInvestigationCollection records can contain collection metadata."
        )


__all__ = [
    "CancelInvestigation",
    "InvestigationCancellationReason",
    "InvestigationCommandDigest",
    "InvestigationCommandType",
    "InvestigationLifecycleCommand",
    "InvestigationLifecycleResult",
    "InvestigationTransitionRecord",
    "RequestEntityConfirmation",
    "StartIdentification",
    "command_type_of",
    "digest_investigation_command",
]
