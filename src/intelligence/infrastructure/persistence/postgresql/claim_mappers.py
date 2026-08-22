"""Strict relational mapping for immutable F5.2 Claims and Evidence links."""

from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID

from intelligence.claims.models import (
    Claim,
    ClaimCorrectionReason,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidenceLink,
    ClaimEvidencePurpose,
    ClaimEvidenceRole,
    ClaimEvidenceUseDecision,
    ClaimEvidenceUseOutcome,
    ClaimEvidenceUseReason,
    ClaimPredicate,
    claim_temporal_from_snapshot,
    claim_temporal_to_snapshot,
    claim_value_from_snapshot,
    claim_value_to_snapshot,
)
from intelligence.domain.identifiers import (
    ClaimCommandId,
    ClaimId,
    CompanyId,
    EntityResolutionDecisionId,
    EvidenceId,
    InvestigationId,
    UserId,
    WorkspaceId,
)

type RelationalValues = Mapping[str, object]


def claim_to_values(claim: Claim) -> dict[str, object]:
    value_type, value_snapshot = claim_value_to_snapshot(claim.value)
    temporal_type, temporal_snapshot = claim_temporal_to_snapshot(claim.temporal)
    return {
        "id": claim.id.value,
        "series_id": claim.series_id.value,
        "version": claim.version,
        "supersedes_claim_id": (
            claim.supersedes_claim_id.value if claim.supersedes_claim_id else None
        ),
        "workspace_id": claim.workspace_id.value,
        "investigation_id": claim.investigation_id.value,
        "subject_company_id": claim.subject_company_id.value,
        "entity_resolution_decision_id": claim.entity_resolution_decision_id.value,
        "command_id": claim.command_id.value,
        "command_digest": claim.command_digest,
        "predicate_code": claim.predicate_code.value,
        "predicate_version": claim.predicate_version,
        "value_type": value_type,
        "value_snapshot": value_snapshot,
        "temporal_type": temporal_type,
        "temporal_snapshot": temporal_snapshot,
        "criticality": claim.criticality.value,
        "creation_method": claim.creation_method.value,
        "creation_method_version": claim.creation_method_version,
        "created_by": claim.created_by.value,
        "created_at": claim.created_at,
        "correction_reason": claim.correction_reason.value if claim.correction_reason else None,
        "claim_digest": claim.claim_digest,
        "schema_version": claim.schema_version,
    }


def claim_from_values(values: RelationalValues) -> Claim:
    value_snapshot = cast(dict[str, object], _required(values, "value_snapshot", dict))
    temporal_snapshot = cast(dict[str, object], _required(values, "temporal_snapshot", dict))
    return Claim(
        id=ClaimId(_required(values, "id", UUID)),
        series_id=ClaimId(_required(values, "series_id", UUID)),
        version=_required_int(values, "version"),
        supersedes_claim_id=(
            ClaimId(value) if (value := _optional(values, "supersedes_claim_id", UUID)) else None
        ),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        subject_company_id=CompanyId(_required(values, "subject_company_id", UUID)),
        entity_resolution_decision_id=EntityResolutionDecisionId(
            _required(values, "entity_resolution_decision_id", UUID)
        ),
        command_id=ClaimCommandId(_required(values, "command_id", UUID)),
        command_digest=_required(values, "command_digest", str),
        predicate_code=ClaimPredicate(_required(values, "predicate_code", str)),
        predicate_version=_required_int(values, "predicate_version"),
        value=claim_value_from_snapshot(_required(values, "value_type", str), value_snapshot),
        temporal=claim_temporal_from_snapshot(
            _required(values, "temporal_type", str), temporal_snapshot
        ),
        criticality=ClaimCriticality(_required(values, "criticality", str)),
        creation_method=ClaimCreationMethod(_required(values, "creation_method", str)),
        creation_method_version=_required_int(values, "creation_method_version"),
        created_by=UserId(_required(values, "created_by", UUID)),
        created_at=_required(values, "created_at", datetime),
        correction_reason=(
            ClaimCorrectionReason(reason)
            if (reason := _optional(values, "correction_reason", str))
            else None
        ),
        claim_digest=_required(values, "claim_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )


def claim_link_to_values(link: ClaimEvidenceLink) -> dict[str, object]:
    decision = link.use_decision
    return {
        "claim_id": link.claim_id.value,
        "claim_version": link.claim_version,
        "workspace_id": link.workspace_id.value,
        "investigation_id": link.investigation_id.value,
        "subject_company_id": link.subject_company_id.value,
        "entity_resolution_decision_id": link.entity_resolution_decision_id.value,
        "evidence_id": link.evidence_id.value,
        "evidence_digest": link.evidence_digest,
        "role": link.role.value,
        "use_outcome": decision.outcome.value,
        "use_reason": decision.reason_code.value,
        "policy_id": decision.policy_id,
        "policy_version": decision.policy_version,
        "purpose": decision.purpose.value,
        "manifest_version": decision.controlled_corpus_manifest_version,
        "manifest_digest": decision.controlled_corpus_manifest_digest,
        "requested_by": decision.requested_by.value,
        "evaluated_at": decision.evaluated_at,
        "link_digest": link.link_digest,
        "schema_version": link.schema_version,
    }


def claim_link_from_values(values: RelationalValues) -> ClaimEvidenceLink:
    decision = ClaimEvidenceUseDecision(
        outcome=ClaimEvidenceUseOutcome(_required(values, "use_outcome", str)),
        reason_code=ClaimEvidenceUseReason(_required(values, "use_reason", str)),
        policy_id=_required(values, "policy_id", str),
        policy_version=_required_int(values, "policy_version"),
        purpose=ClaimEvidencePurpose(_required(values, "purpose", str)),
        controlled_corpus_manifest_version=_required_int(values, "manifest_version"),
        controlled_corpus_manifest_digest=_required(values, "manifest_digest", str),
        requested_by=UserId(_required(values, "requested_by", UUID)),
        evaluated_at=_required(values, "evaluated_at", datetime),
    )
    return ClaimEvidenceLink(
        claim_id=ClaimId(_required(values, "claim_id", UUID)),
        claim_version=_required_int(values, "claim_version"),
        workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
        investigation_id=InvestigationId(_required(values, "investigation_id", UUID)),
        subject_company_id=CompanyId(_required(values, "subject_company_id", UUID)),
        entity_resolution_decision_id=EntityResolutionDecisionId(
            _required(values, "entity_resolution_decision_id", UUID)
        ),
        evidence_id=EvidenceId(_required(values, "evidence_id", UUID)),
        evidence_digest=_required(values, "evidence_digest", str),
        role=ClaimEvidenceRole(_required(values, "role", str)),
        use_decision=decision,
        link_digest=_required(values, "link_digest", str),
        schema_version=_required_int(values, "schema_version"),
    )


def _required[T](values: RelationalValues, key: str, expected_type: type[T]) -> T:
    value = values.get(key)
    if not isinstance(value, expected_type):
        raise ValueError(f"Persisted Claim field {key} is invalid.")
    return value


def _optional[T](values: RelationalValues, key: str, expected_type: type[T]) -> T | None:
    value = values.get(key)
    if value is None:
        return None
    if not isinstance(value, expected_type):
        raise ValueError(f"Persisted Claim field {key} is invalid.")
    return value


def _required_int(values: RelationalValues, key: str) -> int:
    value = _required(values, key, int)
    if isinstance(value, bool):
        raise ValueError(f"Persisted Claim field {key} is invalid.")
    return value


__all__ = [
    "claim_from_values",
    "claim_link_from_values",
    "claim_link_to_values",
    "claim_to_values",
]
