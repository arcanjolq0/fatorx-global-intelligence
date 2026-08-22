"""Strict relational mapping for immutable F5.3 admissibility decisions."""

from collections.abc import Mapping
from datetime import datetime
from uuid import UUID

from intelligence.application.evidence_admissibility_policy import (
    EVIDENCE_ADMISSIBILITY_POLICY_ID,
    EVIDENCE_ADMISSIBILITY_POLICY_VERSION,
    F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1,
)
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
from intelligence.evidence.admissibility import (
    EvidenceAdmissibilityDecision,
    EvidenceAdmissibilityDecisionOutcome,
    EvidenceAdmissibilityPurpose,
    EvidenceAdmissibilityReason,
    EvidenceAdmissionBasis,
)

type RelationalValues = Mapping[str, object]


def evidence_admissibility_decision_to_values(
    decision: EvidenceAdmissibilityDecision,
) -> dict[str, object]:
    return {
        "id": decision.id.value,
        "workspace_id": decision.workspace_id.value,
        "investigation_id": decision.investigation_id.value,
        "subject_company_id": decision.subject_company_id.value,
        "entity_resolution_decision_id": decision.entity_resolution_decision_id.value,
        "evidence_id": decision.evidence_id.value,
        "evidence_series_id": decision.evidence_series_id.value,
        "evidence_version": decision.evidence_version,
        "evidence_digest": decision.evidence_digest,
        "decision_sequence": decision.decision_sequence,
        "supersedes_decision_id": (
            decision.supersedes_decision_id.value if decision.supersedes_decision_id else None
        ),
        "outcome": decision.outcome.value,
        "reason_code": decision.reason_code.value,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "purpose": decision.purpose.value,
        "admission_basis": decision.admission_basis.value,
        "controlled_trust_root_id": decision.controlled_trust_root_id,
        "controlled_trust_root_version": decision.controlled_trust_root_version,
        "controlled_trust_root_digest": decision.controlled_trust_root_digest,
        "valid_until": decision.valid_until,
        "command_id": decision.command_id.value,
        "command_digest": decision.command_digest,
        "decided_by": decision.decided_by.value,
        "decided_at": decision.decided_at,
        "decision_digest": decision.decision_digest,
        "schema_version": decision.schema_version,
    }


def evidence_admissibility_decision_from_values(
    values: RelationalValues,
) -> EvidenceAdmissibilityDecision:
    predecessor = _optional(values, "supersedes_decision_id", UUID)
    decision = EvidenceAdmissibilityDecision(
        id=EvidenceAdmissibilityDecisionId(_required(values, "id", UUID)),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        subject_company_id=CompanyId(_required(values, "subject_company_id", UUID)),
        entity_resolution_decision_id=EntityResolutionDecisionId(
            _required(values, "entity_resolution_decision_id", UUID)
        ),
        evidence_id=EvidenceId(_required(values, "evidence_id", UUID)),
        evidence_series_id=EvidenceId(_required(values, "evidence_series_id", UUID)),
        evidence_version=_required_int(values, "evidence_version"),
        evidence_digest=_required(values, "evidence_digest", str),
        decision_sequence=_required_int(values, "decision_sequence"),
        supersedes_decision_id=(
            EvidenceAdmissibilityDecisionId(predecessor) if predecessor else None
        ),
        outcome=EvidenceAdmissibilityDecisionOutcome(_required(values, "outcome", str)),
        reason_code=EvidenceAdmissibilityReason(_required(values, "reason_code", str)),
        policy_id=_required(values, "policy_id", str),
        policy_version=_required_int(values, "policy_version"),
        purpose=EvidenceAdmissibilityPurpose(_required(values, "purpose", str)),
        admission_basis=EvidenceAdmissionBasis(_required(values, "admission_basis", str)),
        controlled_trust_root_id=_required(values, "controlled_trust_root_id", str),
        controlled_trust_root_version=_required_int(values, "controlled_trust_root_version"),
        controlled_trust_root_digest=_required(values, "controlled_trust_root_digest", str),
        valid_until=_optional(values, "valid_until", datetime),
        command_id=EvidenceAdmissibilityCommandId(_required(values, "command_id", UUID)),
        command_digest=_required(values, "command_digest", str),
        decided_by=UserId(_required(values, "decided_by", UUID)),
        decided_at=_required(values, "decided_at", datetime),
        decision_digest=_required(values, "decision_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )
    if (
        decision.policy_id != EVIDENCE_ADMISSIBILITY_POLICY_ID
        or decision.policy_version != EVIDENCE_ADMISSIBILITY_POLICY_VERSION
        or decision.purpose is not EvidenceAdmissibilityPurpose.INTERNAL_FACTUAL_EVIDENCE_USE
        or decision.admission_basis is not EvidenceAdmissionBasis.CONTROLLED_TEST_EVIDENCE
        or decision.controlled_trust_root_id
        != F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.manifest_id
        or decision.controlled_trust_root_version
        != F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.version
        or decision.controlled_trust_root_digest != F5_3_CONTROLLED_TEST_EVIDENCE_MANIFEST_V1.digest
    ):
        raise ValueError("Persisted admissibility policy snapshot is invalid.")
    return decision


def _required[T](values: RelationalValues, key: str, expected: type[T]) -> T:
    value = values.get(key)
    if not isinstance(value, expected):
        raise ValueError(f"Persisted admissibility field {key} is invalid.")
    return value


def _optional[T](values: RelationalValues, key: str, expected: type[T]) -> T | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, expected):
        raise ValueError(f"Persisted admissibility field {key} is invalid.")
    return value


def _required_int(values: RelationalValues, key: str) -> int:
    value = _required(values, key, int)
    if isinstance(value, bool):
        raise ValueError(f"Persisted admissibility field {key} is invalid.")
    return value


__all__ = [
    "evidence_admissibility_decision_from_values",
    "evidence_admissibility_decision_to_values",
]
