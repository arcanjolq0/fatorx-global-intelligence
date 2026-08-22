"""Immutable global Evidence admissibility decisions and historical projection."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceAdmissibilityCommandId,
    EvidenceAdmissibilityDecisionId,
    EvidenceId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.time import normalize_utc
from intelligence.evidence.errors import (
    EvidenceAdmissibilityHistoryError,
    EvidenceAdmissibilityIntegrityError,
    EvidenceNotExistingAtCutoffError,
)
from intelligence.evidence.models import (
    Evidence,
    EvidenceHistory,
    EvidenceLifecycleEventType,
)

EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION = 1
_SHA256 = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_POLICY_ID = re.compile(r"[A-Z][A-Z0-9_.:-]{0,127}", flags=re.ASCII)


class EvidenceAdmissibilityRequestedAction(StrEnum):
    ADMIT = "ADMIT"
    RESTRICT = "RESTRICT"
    REJECT = "REJECT"


class EvidenceAdmissibilityDecisionOutcome(StrEnum):
    ADMISSIBLE = "ADMISSIBLE"
    RESTRICTED = "RESTRICTED"
    REJECTED = "REJECTED"


class EffectiveEvidenceAdmissibilityStatus(StrEnum):
    PENDING = "PENDING"
    ADMISSIBLE = "ADMISSIBLE"
    RESTRICTED = "RESTRICTED"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    REJECTED = "REJECTED"


class EvidenceAdmissibilityPurpose(StrEnum):
    INTERNAL_FACTUAL_EVIDENCE_USE = "INTERNAL_FACTUAL_EVIDENCE_USE"


class EvidenceAdmissionBasis(StrEnum):
    CONTROLLED_TEST_EVIDENCE = "CONTROLLED_TEST_EVIDENCE"


class EvidenceAdmissibilityReason(StrEnum):
    CONTROLLED_TEST_EVIDENCE_ADMITTED = "CONTROLLED_TEST_EVIDENCE_ADMITTED"
    POLICY_OR_VERIFIABILITY_RESTRICTED = "POLICY_OR_VERIFIABILITY_RESTRICTED"
    CONTENT_OR_CONTEXT_REJECTED = "CONTENT_OR_CONTEXT_REJECTED"


_OUTCOME_REASON = {
    EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE: (
        EvidenceAdmissibilityReason.CONTROLLED_TEST_EVIDENCE_ADMITTED
    ),
    EvidenceAdmissibilityDecisionOutcome.RESTRICTED: (
        EvidenceAdmissibilityReason.POLICY_OR_VERIFIABILITY_RESTRICTED
    ),
    EvidenceAdmissibilityDecisionOutcome.REJECTED: (
        EvidenceAdmissibilityReason.CONTENT_OR_CONTEXT_REJECTED
    ),
}


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EvidenceAdmissibilityDecision:
    id: EvidenceAdmissibilityDecisionId
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    subject_company_id: CompanyId
    entity_resolution_decision_id: EntityResolutionDecisionId
    evidence_id: EvidenceId
    evidence_series_id: EvidenceId
    evidence_version: int
    evidence_digest: str
    decision_sequence: int
    supersedes_decision_id: EvidenceAdmissibilityDecisionId | None
    outcome: EvidenceAdmissibilityDecisionOutcome
    reason_code: EvidenceAdmissibilityReason
    policy_id: str
    policy_version: int
    purpose: EvidenceAdmissibilityPurpose
    admission_basis: EvidenceAdmissionBasis
    controlled_trust_root_id: str
    controlled_trust_root_version: int
    controlled_trust_root_digest: str
    valid_until: datetime | None
    command_id: EvidenceAdmissibilityCommandId
    command_digest: str
    decided_by: UserId
    decided_at: datetime
    decision_digest: str
    schema_version: int = EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        expected_types = (
            (self.id, EvidenceAdmissibilityDecisionId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.subject_company_id, CompanyId),
            (self.entity_resolution_decision_id, EntityResolutionDecisionId),
            (self.evidence_id, EvidenceId),
            (self.evidence_series_id, EvidenceId),
            (self.command_id, EvidenceAdmissibilityCommandId),
            (self.decided_by, UserId),
        )
        if any(not isinstance(value, kind) for value, kind in expected_types):
            raise InvariantViolationError("Admissibility decision identifier type is invalid.")
        if self.supersedes_decision_id is not None and not isinstance(
            self.supersedes_decision_id, EvidenceAdmissibilityDecisionId
        ):
            raise InvariantViolationError("Admissibility predecessor identifier is invalid.")
        for integer_value, name in (
            (self.evidence_version, "evidence version"),
            (self.decision_sequence, "decision sequence"),
            (self.policy_version, "policy version"),
            (self.controlled_trust_root_version, "trust-root version"),
        ):
            if (
                not isinstance(integer_value, int)
                or isinstance(integer_value, bool)
                or integer_value < 1
            ):
                raise InvariantViolationError(f"Admissibility {name} must be positive.")
        if (self.decision_sequence == 1) != (self.supersedes_decision_id is None):
            raise InvariantViolationError("Admissibility predecessor shape is invalid.")
        for digest_value, name in (
            (self.evidence_digest, "Evidence"),
            (self.controlled_trust_root_digest, "trust-root"),
            (self.command_digest, "command"),
            (self.decision_digest, "decision"),
        ):
            if not isinstance(digest_value, str) or _SHA256.fullmatch(digest_value) is None:
                raise InvariantViolationError(f"Admissibility {name} digest is invalid.")
        if (
            _POLICY_ID.fullmatch(self.policy_id) is None
            or _POLICY_ID.fullmatch(self.controlled_trust_root_id) is None
        ):
            raise InvariantViolationError("Admissibility policy or trust-root ID is invalid.")
        if not isinstance(self.outcome, EvidenceAdmissibilityDecisionOutcome) or not isinstance(
            self.reason_code, EvidenceAdmissibilityReason
        ):
            raise InvariantViolationError("Admissibility outcome vocabulary is invalid.")
        if _OUTCOME_REASON[self.outcome] is not self.reason_code:
            raise InvariantViolationError("Admissibility outcome and reason are incompatible.")
        if not isinstance(self.purpose, EvidenceAdmissibilityPurpose) or not isinstance(
            self.admission_basis, EvidenceAdmissionBasis
        ):
            raise InvariantViolationError("Admissibility purpose or basis is invalid.")
        decided_at = normalize_utc(self.decided_at)
        valid_until = normalize_utc(self.valid_until) if self.valid_until else None
        if self.outcome is EvidenceAdmissibilityDecisionOutcome.ADMISSIBLE:
            if valid_until is not None and valid_until <= decided_at:
                raise InvariantViolationError("Admissibility expiration must follow decision time.")
        elif valid_until is not None:
            raise InvariantViolationError("Only ADMISSIBLE decisions can expire.")
        if self.schema_version != EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION:
            raise InvariantViolationError("Admissibility decision schema is unsupported.")
        object.__setattr__(self, "decided_at", decided_at)
        object.__setattr__(self, "valid_until", valid_until)
        if self.decision_digest != evidence_admissibility_decision_digest(self):
            raise EvidenceAdmissibilityIntegrityError("Admissibility decision digest failed.")

    def __repr__(self) -> str:
        return (
            f"EvidenceAdmissibilityDecision(id={self.id!r}, evidence_id={self.evidence_id!r}, "
            f"sequence={self.decision_sequence}, outcome={self.outcome.value!r})"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceAdmissibilityHistory:
    decisions: tuple[EvidenceAdmissibilityDecision, ...]

    def __post_init__(self) -> None:
        if not self.decisions:
            raise EvidenceAdmissibilityHistoryError("Admissibility history cannot be empty.")
        first = self.decisions[0]
        if len({item.id for item in self.decisions}) != len(self.decisions) or len(
            {item.command_id for item in self.decisions}
        ) != len(self.decisions):
            raise EvidenceAdmissibilityHistoryError("Admissibility identities must be unique.")
        for index, item in enumerate(self.decisions):
            previous = self.decisions[index - 1] if index else None
            if item.decision_sequence != index + 1 or item.supersedes_decision_id != (
                previous.id if previous else None
            ):
                raise EvidenceAdmissibilityHistoryError("Admissibility chain is not contiguous.")
            if any(
                (
                    item.workspace_id != first.workspace_id,
                    item.investigation_id != first.investigation_id,
                    item.subject_company_id != first.subject_company_id,
                    item.entity_resolution_decision_id != first.entity_resolution_decision_id,
                    item.evidence_id != first.evidence_id,
                    item.evidence_series_id != first.evidence_series_id,
                    item.evidence_version != first.evidence_version,
                    item.evidence_digest != first.evidence_digest,
                    item.policy_id != first.policy_id,
                    item.policy_version != first.policy_version,
                    item.purpose is not first.purpose,
                    item.admission_basis is not first.admission_basis,
                    item.controlled_trust_root_id != first.controlled_trust_root_id,
                    item.controlled_trust_root_version != first.controlled_trust_root_version,
                    item.controlled_trust_root_digest != first.controlled_trust_root_digest,
                    item.schema_version != first.schema_version,
                )
            ):
                raise EvidenceAdmissibilityHistoryError("Admissibility history scope changed.")
            if previous is not None and item.decided_at < previous.decided_at:
                raise EvidenceAdmissibilityHistoryError("Admissibility timestamps are regressive.")

    @property
    def latest(self) -> EvidenceAdmissibilityDecision:
        return self.decisions[-1]

    def through(self, decision_id: EvidenceAdmissibilityDecisionId) -> EvidenceAdmissibilityHistory:
        for index, decision in enumerate(self.decisions):
            if decision.id == decision_id:
                return EvidenceAdmissibilityHistory(decisions=self.decisions[: index + 1])
        raise EvidenceAdmissibilityHistoryError("Admissibility decision is absent from history.")

    def validate_against(self, evidence_history: EvidenceHistory) -> None:
        target = _target_evidence(evidence_history, self.latest.evidence_id)
        first = self.decisions[0]
        if any(
            (
                first.workspace_id != target.workspace_id,
                first.investigation_id != target.investigation_id,
                first.subject_company_id != target.subject_company_id,
                first.entity_resolution_decision_id != target.entity_resolution_decision_id,
                first.evidence_series_id != target.series_id,
                first.evidence_version != target.version,
                first.evidence_digest != target.evidence_digest,
            )
        ):
            raise EvidenceAdmissibilityHistoryError("Decision does not bind the exact Evidence.")
        upper_bound = _evidence_interval_upper_bound(evidence_history, target)
        for decision in self.decisions:
            if decision.decided_at < target.created_at or (
                upper_bound is not None and decision.decided_at >= upper_bound
            ):
                raise EvidenceAdmissibilityHistoryError(
                    "Decision lies outside the Evidence historical interval."
                )


@dataclass(frozen=True, slots=True, kw_only=True)
class EffectiveEvidenceAdmissibility:
    status: EffectiveEvidenceAdmissibilityStatus
    evidence_id: EvidenceId
    evidence_series_id: EvidenceId
    evidence_version: int
    evidence_digest: str
    decision_id: EvidenceAdmissibilityDecisionId | None
    as_of: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "as_of", normalize_utc(self.as_of))


def build_evidence_admissibility_decision(
    *,
    decision_id: EvidenceAdmissibilityDecisionId,
    evidence: Evidence,
    decision_sequence: int,
    supersedes_decision_id: EvidenceAdmissibilityDecisionId | None,
    outcome: EvidenceAdmissibilityDecisionOutcome,
    reason_code: EvidenceAdmissibilityReason,
    policy_id: str,
    policy_version: int,
    purpose: EvidenceAdmissibilityPurpose,
    admission_basis: EvidenceAdmissionBasis,
    controlled_trust_root_id: str,
    controlled_trust_root_version: int,
    controlled_trust_root_digest: str,
    valid_until: datetime | None,
    command_id: EvidenceAdmissibilityCommandId,
    command_digest: str,
    decided_by: UserId,
    decided_at: datetime,
) -> EvidenceAdmissibilityDecision:
    values: dict[str, object] = {
        "id": decision_id,
        "workspace_id": evidence.workspace_id,
        "investigation_id": evidence.investigation_id,
        "subject_company_id": evidence.subject_company_id,
        "entity_resolution_decision_id": evidence.entity_resolution_decision_id,
        "evidence_id": evidence.id,
        "evidence_series_id": evidence.series_id,
        "evidence_version": evidence.version,
        "evidence_digest": evidence.evidence_digest,
        "decision_sequence": decision_sequence,
        "supersedes_decision_id": supersedes_decision_id,
        "outcome": outcome,
        "reason_code": reason_code,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "purpose": purpose,
        "admission_basis": admission_basis,
        "controlled_trust_root_id": controlled_trust_root_id,
        "controlled_trust_root_version": controlled_trust_root_version,
        "controlled_trust_root_digest": controlled_trust_root_digest,
        "valid_until": normalize_utc(valid_until) if valid_until else None,
        "command_id": command_id,
        "command_digest": command_digest,
        "decided_by": decided_by,
        "decided_at": normalize_utc(decided_at),
        "schema_version": EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION,
    }
    return EvidenceAdmissibilityDecision(
        id=decision_id,
        workspace_id=evidence.workspace_id,
        investigation_id=evidence.investigation_id,
        subject_company_id=evidence.subject_company_id,
        entity_resolution_decision_id=evidence.entity_resolution_decision_id,
        evidence_id=evidence.id,
        evidence_series_id=evidence.series_id,
        evidence_version=evidence.version,
        evidence_digest=evidence.evidence_digest,
        decision_sequence=decision_sequence,
        supersedes_decision_id=supersedes_decision_id,
        outcome=outcome,
        reason_code=reason_code,
        policy_id=policy_id,
        policy_version=policy_version,
        purpose=purpose,
        admission_basis=admission_basis,
        controlled_trust_root_id=controlled_trust_root_id,
        controlled_trust_root_version=controlled_trust_root_version,
        controlled_trust_root_digest=controlled_trust_root_digest,
        valid_until=normalize_utc(valid_until) if valid_until else None,
        command_id=command_id,
        command_digest=command_digest,
        decided_by=decided_by,
        decided_at=normalize_utc(decided_at),
        schema_version=EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION,
        decision_digest=_decision_digest_values(values),
    )


def evidence_admissibility_decision_digest(
    decision: EvidenceAdmissibilityDecision,
) -> str:
    return _decision_digest_values(_decision_values(decision))


def project_effective_evidence_admissibility(
    *,
    evidence_history: EvidenceHistory,
    decision_histories: tuple[EvidenceAdmissibilityHistory, ...],
    as_of: datetime,
) -> EffectiveEvidenceAdmissibility:
    """Project global status at an explicit cutoff without reading a clock."""

    cutoff = normalize_utc(as_of)
    if cutoff < evidence_history.versions[0].created_at:
        raise EvidenceNotExistingAtCutoffError("Evidence did not exist at the cutoff.")
    seen: set[EvidenceId] = set()
    for decision_history in decision_histories:
        decision_history.validate_against(evidence_history)
        if decision_history.latest.evidence_id in seen:
            raise EvidenceAdmissibilityHistoryError("Duplicate decision history for Evidence.")
        seen.add(decision_history.latest.evidence_id)
    applicable_revocations = tuple(
        event
        for event in evidence_history.events
        if event.event_type is EvidenceLifecycleEventType.REVOKED and event.occurred_at <= cutoff
    )
    current = max(
        (item for item in evidence_history.versions if item.created_at <= cutoff),
        key=lambda item: item.version,
    )
    if applicable_revocations:
        return _effective(EffectiveEvidenceAdmissibilityStatus.REVOKED, current, None, cutoff)
    applicable_history = next(
        (item for item in decision_histories if item.latest.evidence_id == current.id), None
    )
    if applicable_history is None:
        return _effective(EffectiveEvidenceAdmissibilityStatus.PENDING, current, None, cutoff)
    decision = next(
        (item for item in reversed(applicable_history.decisions) if item.decided_at <= cutoff),
        None,
    )
    if decision is None:
        return _effective(EffectiveEvidenceAdmissibilityStatus.PENDING, current, None, cutoff)
    if decision.outcome is EvidenceAdmissibilityDecisionOutcome.RESTRICTED:
        status = EffectiveEvidenceAdmissibilityStatus.RESTRICTED
    elif decision.outcome is EvidenceAdmissibilityDecisionOutcome.REJECTED:
        status = EffectiveEvidenceAdmissibilityStatus.REJECTED
    elif decision.valid_until is not None and cutoff >= decision.valid_until:
        status = EffectiveEvidenceAdmissibilityStatus.EXPIRED
    else:
        status = EffectiveEvidenceAdmissibilityStatus.ADMISSIBLE
    return _effective(status, current, decision, cutoff)


def _effective(
    status: EffectiveEvidenceAdmissibilityStatus,
    evidence: Evidence,
    decision: EvidenceAdmissibilityDecision | None,
    as_of: datetime,
) -> EffectiveEvidenceAdmissibility:
    return EffectiveEvidenceAdmissibility(
        status=status,
        evidence_id=evidence.id,
        evidence_series_id=evidence.series_id,
        evidence_version=evidence.version,
        evidence_digest=evidence.evidence_digest,
        decision_id=decision.id if decision else None,
        as_of=as_of,
    )


def _target_evidence(history: EvidenceHistory, evidence_id: EvidenceId) -> Evidence:
    try:
        return next(item for item in history.versions if item.id == evidence_id)
    except StopIteration as error:
        raise EvidenceAdmissibilityHistoryError("Decision targets absent Evidence.") from error


def _evidence_interval_upper_bound(history: EvidenceHistory, target: Evidence) -> datetime | None:
    boundaries = [
        event.occurred_at
        for event in history.events
        if (
            event.event_type is EvidenceLifecycleEventType.SUPERSEDED
            and event.evidence_id == target.id
        )
        or event.event_type is EvidenceLifecycleEventType.REVOKED
    ]
    return min(boundaries) if boundaries else None


def _decision_values(decision: EvidenceAdmissibilityDecision) -> dict[str, object]:
    return {
        "id": decision.id,
        "workspace_id": decision.workspace_id,
        "investigation_id": decision.investigation_id,
        "subject_company_id": decision.subject_company_id,
        "entity_resolution_decision_id": decision.entity_resolution_decision_id,
        "evidence_id": decision.evidence_id,
        "evidence_series_id": decision.evidence_series_id,
        "evidence_version": decision.evidence_version,
        "evidence_digest": decision.evidence_digest,
        "decision_sequence": decision.decision_sequence,
        "supersedes_decision_id": decision.supersedes_decision_id,
        "outcome": decision.outcome,
        "reason_code": decision.reason_code,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "purpose": decision.purpose,
        "admission_basis": decision.admission_basis,
        "controlled_trust_root_id": decision.controlled_trust_root_id,
        "controlled_trust_root_version": decision.controlled_trust_root_version,
        "controlled_trust_root_digest": decision.controlled_trust_root_digest,
        "valid_until": decision.valid_until,
        "command_id": decision.command_id,
        "command_digest": decision.command_digest,
        "decided_by": decision.decided_by,
        "decided_at": decision.decided_at,
        "schema_version": decision.schema_version,
    }


def _decision_digest_values(values: dict[str, object]) -> str:
    def scalar(value: object) -> object:
        if hasattr(value, "value"):
            raw = value.value
            return str(raw)
        if isinstance(value, datetime):
            return normalize_utc(value).isoformat().replace("+00:00", "Z")
        return value

    canonical = {key: scalar(value) for key, value in values.items()}
    return sha256(
        json.dumps(canonical, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


__all__ = [
    "EVIDENCE_ADMISSIBILITY_DECISION_SCHEMA_VERSION",
    "EffectiveEvidenceAdmissibility",
    "EffectiveEvidenceAdmissibilityStatus",
    "EvidenceAdmissibilityDecision",
    "EvidenceAdmissibilityDecisionOutcome",
    "EvidenceAdmissibilityHistory",
    "EvidenceAdmissibilityPurpose",
    "EvidenceAdmissibilityReason",
    "EvidenceAdmissibilityRequestedAction",
    "EvidenceAdmissionBasis",
    "build_evidence_admissibility_decision",
    "evidence_admissibility_decision_digest",
    "project_effective_evidence_admissibility",
]
