"""Typed human confirmation command and immutable entity-resolution decision."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.application.entity_candidate_review import (
    EntityCandidateBatchRecord,
    EntityCandidateRecord,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandDigest,
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.domain.companies import Company
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CompanyId,
    EntityCandidateBatchId,
    EntityCandidateId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.time import normalize_utc
from intelligence.entity_resolution.contracts import SourceRegistrationStatus
from intelligence.entity_resolution.errors import EntityResolutionError
from intelligence.entity_resolution.materialization import (
    COMPANY_MATERIALIZATION_V1,
    CompanyMaterializationPolicy,
    company_snapshot_digest,
)
from intelligence.entity_resolution.policy import MatchClassification

ENTITY_CONFIRMATION_COMMAND_SCHEMA_VERSION = 1
ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION = 1
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}", flags=re.ASCII)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class EntityConfirmationReason(StrEnum):
    """Closed reasons available to the human reviewer."""

    IDENTIFIERS_REVIEWED = "IDENTIFIERS_REVIEWED"
    CORPORATE_DATA_REVIEWED = "CORPORATE_DATA_REVIEWED"
    SOURCE_REFERENCE_REVIEWED = "SOURCE_REFERENCE_REVIEWED"
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class EntityResolutionDecisionType(StrEnum):
    """Only positive confirmation is authorized in F4.3."""

    CONFIRMED = "CONFIRMED"


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ConfirmEntityCandidate:
    """Explicit human command selecting one candidate already persisted in F4.2."""

    command_id: InvestigationCommandId
    investigation_id: InvestigationId
    expected_state_version: int
    candidate_batch_id: EntityCandidateBatchId
    candidate_id: EntityCandidateId
    review_reason: EntityConfirmationReason
    materialization_policy: CompanyMaterializationPolicy = field(repr=False)
    schema_version: int = ENTITY_CONFIRMATION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed_ids = (
            (self.command_id, InvestigationCommandId),
            (self.investigation_id, InvestigationId),
            (self.candidate_batch_id, EntityCandidateBatchId),
            (self.candidate_id, EntityCandidateId),
        )
        if any(not isinstance(value, expected) for value, expected in typed_ids):
            raise InvariantViolationError("Entity confirmation identifiers must be typed.")
        if (
            isinstance(self.expected_state_version, bool)
            or not isinstance(self.expected_state_version, int)
            or self.expected_state_version < 1
        ):
            raise InvariantViolationError(
                "Entity confirmation expected_state_version must be positive."
            )
        if not isinstance(self.review_reason, EntityConfirmationReason):
            raise InvariantViolationError(
                "Entity confirmation reason must use the closed vocabulary."
            )
        if not isinstance(self.materialization_policy, CompanyMaterializationPolicy):
            raise InvariantViolationError(
                "Entity confirmation materialization policy must be typed."
            )
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != ENTITY_CONFIRMATION_COMMAND_SCHEMA_VERSION
        ):
            raise InvariantViolationError("Entity confirmation command schema is unsupported.")

    def __repr__(self) -> str:
        return (
            "ConfirmEntityCandidate("
            f"command_id={self.command_id!r}, investigation_id={self.investigation_id!r}, "
            f"expected_state_version={self.expected_state_version}, "
            f"candidate_batch_id={self.candidate_batch_id!r}, "
            f"candidate_id={self.candidate_id!r}, review_reason={self.review_reason.value!r}, "
            f"materialization_policy_id={self.materialization_policy.policy_id!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EntityResolutionDecisionRecord:
    """Append-only positive decision linked to persisted candidate and Company records."""

    id: EntityResolutionDecisionId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    command_id: InvestigationCommandId
    command_digest: InvestigationCommandDigest
    candidate_batch_id: EntityCandidateBatchId
    candidate_id: EntityCandidateId
    company_id: CompanyId
    reviewed_by: UserId
    review_reason: EntityConfirmationReason
    decided_at: datetime
    candidate_rank: int
    candidate_classification: MatchClassification
    candidate_total_score: int
    candidate_coverage: int
    candidate_identity_digest: str
    candidate_evaluation_digest: str
    batch_submission_digest: str
    batch_evaluation_digest: str
    matching_policy_id: str
    matching_policy_version: int
    matching_policy_digest: str
    input_digest: str
    materialization_policy_id: str
    materialization_policy_version: int
    materialization_policy_digest: str
    materialization_policy_snapshot: str = field(repr=False)
    company_snapshot_digest: str
    decision_digest: str
    decision_type: EntityResolutionDecisionType = EntityResolutionDecisionType.CONFIRMED
    decision_schema_version: int = ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed_ids = (
            (self.id, EntityResolutionDecisionId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.command_id, InvestigationCommandId),
            (self.candidate_batch_id, EntityCandidateBatchId),
            (self.candidate_id, EntityCandidateId),
            (self.company_id, CompanyId),
            (self.reviewed_by, UserId),
        )
        if any(not isinstance(value, expected) for value, expected in typed_ids):
            raise InvariantViolationError("Entity resolution decision identifiers must be typed.")
        if not isinstance(self.command_digest, InvestigationCommandDigest):
            raise InvariantViolationError(
                "Entity resolution decision command digest must be typed."
            )
        if not isinstance(self.review_reason, EntityConfirmationReason):
            raise InvariantViolationError("Entity resolution decision reason is invalid.")
        if self.decision_type is not EntityResolutionDecisionType.CONFIRMED:
            raise InvariantViolationError("Only confirmed entity decisions are supported.")
        if (
            isinstance(self.decision_schema_version, bool)
            or self.decision_schema_version != ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION
        ):
            raise InvariantViolationError("Entity resolution decision schema is unsupported.")
        if (
            isinstance(self.candidate_rank, bool)
            or not isinstance(self.candidate_rank, int)
            or not 1 <= self.candidate_rank <= 100
        ):
            raise InvariantViolationError("Entity resolution decision rank is invalid.")
        for score_value, field_name in (
            (self.candidate_total_score, "score"),
            (self.candidate_coverage, "coverage"),
        ):
            if (
                isinstance(score_value, bool)
                or not isinstance(score_value, int)
                or not 0 <= score_value <= 10_000
            ):
                raise InvariantViolationError(
                    f"Entity resolution decision candidate {field_name} is invalid."
                )
        if (
            not isinstance(self.candidate_classification, MatchClassification)
            or self.candidate_classification is MatchClassification.EXCLUDED
        ):
            raise InvariantViolationError(
                "Entity resolution decision candidate classification is invalid."
            )
        if (
            self.candidate_classification is MatchClassification.LOW or self.candidate_rank != 1
        ) and self.review_reason is not EntityConfirmationReason.MANUAL_OVERRIDE:
            raise InvariantViolationError(
                "Entity resolution decision requires a manual override reason."
            )
        for digest_value, field_name in (
            (self.command_digest.value, "command"),
            (self.candidate_identity_digest, "candidate identity"),
            (self.candidate_evaluation_digest, "candidate evaluation"),
            (self.batch_submission_digest, "batch submission"),
            (self.batch_evaluation_digest, "batch evaluation"),
            (self.matching_policy_digest, "matching policy"),
            (self.input_digest, "input"),
            (self.materialization_policy_digest, "materialization policy"),
            (self.company_snapshot_digest, "company snapshot"),
            (self.decision_digest, "decision"),
        ):
            _digest(digest_value, field_name)
        _policy_reference(
            self.matching_policy_id,
            self.matching_policy_version,
            "matching",
        )
        _policy_reference(
            self.materialization_policy_id,
            self.materialization_policy_version,
            "materialization",
        )
        try:
            materialization_policy = CompanyMaterializationPolicy.from_canonical_json(
                self.materialization_policy_snapshot
            )
        except EntityResolutionError as error:
            raise InvariantViolationError(
                "Entity resolution materialization policy snapshot is invalid."
            ) from error
        if (
            materialization_policy.policy_id != self.materialization_policy_id
            or materialization_policy.version != self.materialization_policy_version
            or materialization_policy.digest != self.materialization_policy_digest
        ):
            raise InvariantViolationError(
                "Entity resolution materialization policy snapshot is inconsistent."
            )
        object.__setattr__(self, "decided_at", normalize_utc(self.decided_at))
        if self.decision_digest != _decision_digest(self):
            raise InvariantViolationError("Entity resolution decision digest is inconsistent.")

    def __repr__(self) -> str:
        return (
            "EntityResolutionDecisionRecord("
            f"id={self.id!r}, investigation_id={self.investigation_id!r}, "
            f"company_id={self.company_id!r}, candidate_id={self.candidate_id!r}, "
            f"review_reason={self.review_reason.value!r}, payload=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EntityConfirmationResult:
    """Stable result containing the persisted decision and materialized Company."""

    decision: EntityResolutionDecisionRecord
    company: Company
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.decision, EntityResolutionDecisionRecord) or not isinstance(
            self.company, Company
        ):
            raise InvariantViolationError("Entity confirmation result records must be typed.")
        if self.company.id != self.decision.company_id:
            raise InvariantViolationError("Entity confirmation result records are inconsistent.")
        if not isinstance(self.replayed, bool):
            raise InvariantViolationError("Entity confirmation replay indicator must be boolean.")

    def __repr__(self) -> str:
        return (
            "EntityConfirmationResult("
            f"decision_id={self.decision.id!r}, company_id={self.company.id!r}, "
            f"replayed={self.replayed}, payload=<redacted>)"
        )


def digest_entity_confirmation_command(
    actor: ActorContext,
    command: ConfirmEntityCandidate,
) -> InvestigationCommandDigest:
    """Hash only the closed command semantics, excluding generated IDs and time."""

    if not isinstance(actor, ActorContext) or not isinstance(command, ConfirmEntityCandidate):
        raise TypeError("Entity confirmation digest requires typed actor and command.")
    canonical = _canonical_json(
        {
            "actor_user_id": str(actor.user_id),
            "candidate_batch_id": str(command.candidate_batch_id),
            "candidate_id": str(command.candidate_id),
            "command_schema_version": command.schema_version,
            "expected_state_version": command.expected_state_version,
            "investigation_id": str(command.investigation_id),
            "materialization_policy": command.materialization_policy.to_canonical_json(),
            "review_reason": command.review_reason.value,
            "workspace_id": str(actor.workspace_id),
        }
    )
    return InvestigationCommandDigest(sha256(canonical.encode("utf-8")).hexdigest())


def validate_confirmation_reason(
    candidate: EntityCandidateRecord,
    reason: EntityConfirmationReason,
) -> None:
    """Enforce explicit override for low-ranked or non-leading selections."""

    if not isinstance(candidate, EntityCandidateRecord) or not isinstance(
        reason, EntityConfirmationReason
    ):
        raise InvariantViolationError("Entity confirmation review inputs must be typed.")
    if candidate.classification is MatchClassification.EXCLUDED:
        raise InvariantViolationError("An excluded candidate cannot be confirmed.")
    requires_override = candidate.classification is MatchClassification.LOW or candidate.rank != 1
    if requires_override and reason is not EntityConfirmationReason.MANUAL_OVERRIDE:
        raise InvariantViolationError("The selected candidate requires a manual override reason.")


def build_entity_resolution_decision_record(
    *,
    decision_id: EntityResolutionDecisionId,
    actor: ActorContext,
    command: ConfirmEntityCandidate,
    command_digest: InvestigationCommandDigest,
    batch: EntityCandidateBatchRecord,
    candidate: EntityCandidateRecord,
    company: Company,
    decided_at: datetime,
) -> EntityResolutionDecisionRecord:
    """Build a complete immutable decision from already validated persisted context."""

    snapshot_digest = company_snapshot_digest(
        company=company,
        policy_digest=command.materialization_policy.digest,
        candidate_identity_digest=candidate.identity.digest,
    )
    values: dict[str, object] = {
        "id": decision_id,
        "workspace_id": actor.workspace_id,
        "investigation_id": command.investigation_id,
        "command_id": command.command_id,
        "command_digest": command_digest,
        "candidate_batch_id": command.candidate_batch_id,
        "candidate_id": command.candidate_id,
        "company_id": company.id,
        "reviewed_by": actor.user_id,
        "review_reason": command.review_reason,
        "decided_at": normalize_utc(decided_at),
        "candidate_rank": candidate.rank,
        "candidate_classification": candidate.classification,
        "candidate_total_score": candidate.total_score,
        "candidate_coverage": candidate.coverage,
        "candidate_identity_digest": candidate.identity.digest,
        "candidate_evaluation_digest": candidate.evaluation_digest,
        "batch_submission_digest": batch.submission_digest,
        "batch_evaluation_digest": batch.evaluation_digest,
        "matching_policy_id": batch.policy_id,
        "matching_policy_version": batch.policy_version,
        "matching_policy_digest": batch.policy_digest,
        "input_digest": batch.input_digest,
        "materialization_policy_id": command.materialization_policy.policy_id,
        "materialization_policy_version": command.materialization_policy.version,
        "materialization_policy_digest": command.materialization_policy.digest,
        "materialization_policy_snapshot": command.materialization_policy.to_canonical_json(),
        "company_snapshot_digest": snapshot_digest,
        "decision_type": EntityResolutionDecisionType.CONFIRMED,
        "decision_schema_version": ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION,
    }
    return EntityResolutionDecisionRecord(
        id=decision_id,
        workspace_id=actor.workspace_id,
        investigation_id=command.investigation_id,
        command_id=command.command_id,
        command_digest=command_digest,
        candidate_batch_id=command.candidate_batch_id,
        candidate_id=command.candidate_id,
        company_id=company.id,
        reviewed_by=actor.user_id,
        review_reason=command.review_reason,
        decided_at=normalize_utc(decided_at),
        candidate_rank=candidate.rank,
        candidate_classification=candidate.classification,
        candidate_total_score=candidate.total_score,
        candidate_coverage=candidate.coverage,
        candidate_identity_digest=candidate.identity.digest,
        candidate_evaluation_digest=candidate.evaluation_digest,
        batch_submission_digest=batch.submission_digest,
        batch_evaluation_digest=batch.evaluation_digest,
        matching_policy_id=batch.policy_id,
        matching_policy_version=batch.policy_version,
        matching_policy_digest=batch.policy_digest,
        input_digest=batch.input_digest,
        materialization_policy_id=command.materialization_policy.policy_id,
        materialization_policy_version=command.materialization_policy.version,
        materialization_policy_digest=command.materialization_policy.digest,
        materialization_policy_snapshot=command.materialization_policy.to_canonical_json(),
        company_snapshot_digest=snapshot_digest,
        decision_digest=_decision_digest_from_values(values),
    )


def validate_entity_resolution_decision_context(
    record: EntityResolutionDecisionRecord,
    *,
    transition: InvestigationTransitionRecord,
    investigation: Investigation,
    batch: EntityCandidateBatchRecord,
    company: Company,
) -> None:
    """Validate the immutable confirmation fact against its current context."""

    if (
        transition.command_type is not InvestigationCommandType.CONFIRM_ENTITY_CANDIDATE
        or transition.workspace_id != record.workspace_id
        or transition.investigation_id != record.investigation_id
        or transition.command_id != record.command_id
        or transition.command_digest != record.command_digest
        or transition.actor_user_id != record.reviewed_by
        or transition.state_before is not InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
        or transition.state_after is not InvestigationState.PLANNING
        or transition.version_after != transition.version_before + 1
        or transition.occurred_at != record.decided_at
        or transition.confirmation_decision_id != record.id
        or transition.confirmed_company_id != record.company_id
        or transition.confirmed_candidate_batch_id != record.candidate_batch_id
        or transition.confirmed_candidate_id != record.candidate_id
        or transition.confirmation_reason_code != record.review_reason.value
        or transition.confirmed_candidate_classification is not record.candidate_classification
        or transition.confirmed_candidate_rank != record.candidate_rank
        or transition.matching_policy_id != record.matching_policy_id
        or transition.matching_policy_version != record.matching_policy_version
        or transition.materialization_policy_id != record.materialization_policy_id
        or transition.materialization_policy_version != record.materialization_policy_version
    ):
        raise InvariantViolationError("Persisted entity decision transition is inconsistent.")
    if (
        record.workspace_id != investigation.workspace_id
        or record.investigation_id != investigation.id
        or investigation.state not in _POST_CONFIRMATION_STATES
        or investigation.confirmed_company_id != record.company_id
        or investigation.active_candidate_batch_id is not None
        or investigation.state_version < transition.version_after
        or (
            investigation.state_version == transition.version_after
            and investigation.state is not InvestigationState.PLANNING
        )
    ):
        raise InvariantViolationError("Persisted entity decision investigation is inconsistent.")
    identification_input = investigation.identification_input
    if identification_input is None or identification_input.digest != record.input_digest:
        raise InvariantViolationError("Persisted entity decision input is inconsistent.")
    if (
        batch.workspace_id != record.workspace_id
        or batch.investigation_id != record.investigation_id
        or batch.id != record.candidate_batch_id
    ):
        raise InvariantViolationError("Persisted entity decision batch is inconsistent.")
    candidate = next((item for item in batch.candidates if item.id == record.candidate_id), None)
    if candidate is None:
        raise InvariantViolationError("Persisted entity decision candidate is inconsistent.")
    validate_confirmation_reason(candidate, record.review_reason)
    if (
        candidate.rank != record.candidate_rank
        or candidate.classification is not record.candidate_classification
        or candidate.total_score != record.candidate_total_score
        or candidate.coverage != record.candidate_coverage
        or candidate.identity.digest != record.candidate_identity_digest
        or candidate.evaluation_digest != record.candidate_evaluation_digest
        or batch.submission_digest != record.batch_submission_digest
        or batch.evaluation_digest != record.batch_evaluation_digest
        or batch.policy_id != record.matching_policy_id
        or batch.policy_version != record.matching_policy_version
        or batch.policy_digest != record.matching_policy_digest
        or batch.input_digest != record.input_digest
    ):
        raise InvariantViolationError("Persisted entity decision evaluation is inconsistent.")
    if company.id != record.company_id or company.workspace_id != record.workspace_id:
        raise InvariantViolationError("Persisted entity decision Company is inconsistent.")
    materialization_policy = CompanyMaterializationPolicy.from_canonical_json(
        record.materialization_policy_snapshot
    )
    if materialization_policy != COMPANY_MATERIALIZATION_V1:
        raise InvariantViolationError("Persisted entity decision policy is unsupported.")
    identity = candidate.identity
    if identity.registry_status is SourceRegistrationStatus.ACTIVE:
        expected_status = "ACTIVE"
    elif identity.registry_status is SourceRegistrationStatus.INACTIVE:
        expected_status = "INACTIVE"
    else:
        expected_status = "UNKNOWN"
    if (
        company.legal_name != identity.legal_name.original_value
        or company.trade_name
        != (identity.trade_name.original_value if identity.trade_name is not None else None)
        or company.country_code != identity.country_code
        or company.status.value != expected_status
        or company.incorporated_on != identity.incorporated_on
        or company.official_domain
        != (
            identity.corporate_domain.normalized_value
            if identity.corporate_domain is not None
            else None
        )
        or company.legal_form is not None
        or company.dissolved_on is not None
        or company.created_at != record.decided_at
        or company.updated_at != record.decided_at
    ):
        raise InvariantViolationError("Persisted entity decision Company is inconsistent.")
    expected_company_digest = company_snapshot_digest(
        company=company,
        policy_digest=record.materialization_policy_digest,
        candidate_identity_digest=record.candidate_identity_digest,
    )
    if expected_company_digest != record.company_snapshot_digest:
        raise InvariantViolationError("Persisted entity decision Company digest is inconsistent.")


_POST_CONFIRMATION_STATES = frozenset(
    {
        InvestigationState.PLANNING,
        InvestigationState.COLLECTING,
        InvestigationState.NORMALIZING,
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    }
)


def _decision_digest(record: EntityResolutionDecisionRecord) -> str:
    return _decision_digest_from_values(record.__dict__ if hasattr(record, "__dict__") else record)


def _decision_digest_from_values(values: object) -> str:
    def value(name: str) -> object:
        if isinstance(values, dict):
            return values[name]
        return getattr(values, name)

    decided_at = value("decided_at")
    if not isinstance(decided_at, datetime):
        raise InvariantViolationError("Entity resolution decision timestamp is invalid.")
    content = {
        "batch_evaluation_digest": value("batch_evaluation_digest"),
        "batch_submission_digest": value("batch_submission_digest"),
        "candidate_batch_id": str(value("candidate_batch_id")),
        "candidate_classification": _enum_value(value("candidate_classification")),
        "candidate_coverage": value("candidate_coverage"),
        "candidate_evaluation_digest": value("candidate_evaluation_digest"),
        "candidate_id": str(value("candidate_id")),
        "candidate_identity_digest": value("candidate_identity_digest"),
        "candidate_rank": value("candidate_rank"),
        "candidate_total_score": value("candidate_total_score"),
        "command_digest": str(value("command_digest")),
        "command_id": str(value("command_id")),
        "company_id": str(value("company_id")),
        "company_snapshot_digest": value("company_snapshot_digest"),
        "decided_at": normalize_utc(decided_at).isoformat().replace("+00:00", "Z"),
        "decision_id": str(value("id")),
        "decision_schema_version": value("decision_schema_version"),
        "decision_type": _enum_value(value("decision_type")),
        "input_digest": value("input_digest"),
        "investigation_id": str(value("investigation_id")),
        "matching_policy_digest": value("matching_policy_digest"),
        "matching_policy_id": value("matching_policy_id"),
        "matching_policy_version": value("matching_policy_version"),
        "materialization_policy_digest": value("materialization_policy_digest"),
        "materialization_policy_id": value("materialization_policy_id"),
        "materialization_policy_version": value("materialization_policy_version"),
        "review_reason": _enum_value(value("review_reason")),
        "reviewed_by": str(value("reviewed_by")),
        "workspace_id": str(value("workspace_id")),
    }
    return sha256(_canonical_json(content).encode("utf-8")).hexdigest()


def _enum_value(value: object) -> str:
    if not isinstance(value, StrEnum):
        raise InvariantViolationError("Entity resolution decision vocabulary is invalid.")
    return value.value


def _policy_reference(policy_id: str, version: int, kind: str) -> None:
    if not isinstance(policy_id, str) or _CODE_PATTERN.fullmatch(policy_id) is None:
        raise InvariantViolationError(f"Entity resolution {kind} policy ID is invalid.")
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise InvariantViolationError(f"Entity resolution {kind} policy version is invalid.")


def _digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(
            f"Entity resolution {field_name} digest must be a lowercase SHA-256 value."
        )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=True,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


__all__ = [
    "ENTITY_CONFIRMATION_COMMAND_SCHEMA_VERSION",
    "ENTITY_RESOLUTION_DECISION_SCHEMA_VERSION",
    "ConfirmEntityCandidate",
    "EntityConfirmationReason",
    "EntityConfirmationResult",
    "EntityResolutionDecisionRecord",
    "EntityResolutionDecisionType",
    "build_entity_resolution_decision_record",
    "digest_entity_confirmation_command",
    "validate_confirmation_reason",
    "validate_entity_resolution_decision_context",
]
