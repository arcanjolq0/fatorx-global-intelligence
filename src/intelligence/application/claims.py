"""Typed, redacted commands and results for F5.2 claim use cases."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.claims.models import (
    ClaimAssessment,
    ClaimCorrectionReason,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidenceRole,
    ClaimHistory,
    ClaimPredicate,
    ClaimTemporal,
    ClaimValue,
    claim_temporal_to_snapshot,
    claim_value_to_snapshot,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import ClaimCommandId, ClaimId, EvidenceId, InvestigationId

CLAIM_COMMAND_SCHEMA_VERSION = 1
MAX_CLAIM_LINKS = 50
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


@dataclass(frozen=True, slots=True)
class ProposedClaimEvidenceLink:
    evidence_id: EvidenceId
    expected_evidence_digest: str
    role: ClaimEvidenceRole

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_id, EvidenceId):
            raise InvariantViolationError("Proposed Claim Evidence ID must be typed.")
        _digest(self.expected_evidence_digest)
        if not isinstance(self.role, ClaimEvidenceRole):
            raise InvariantViolationError("Proposed Claim Evidence role is invalid.")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class RegisterClaim:
    command_id: ClaimCommandId
    investigation_id: InvestigationId
    predicate_code: ClaimPredicate
    predicate_version: int
    value: ClaimValue = field(repr=False)
    temporal: ClaimTemporal
    criticality: ClaimCriticality
    creation_method: ClaimCreationMethod
    creation_method_version: int
    links: tuple[ProposedClaimEvidenceLink, ...]
    schema_version: int = CLAIM_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _command_common(self)

    def __repr__(self) -> str:
        return (
            f"RegisterClaim(command_id={self.command_id!r}, "
            f"investigation_id={self.investigation_id!r}, value=<redacted>, "
            f"link_count={len(self.links)})"
        )


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CorrectClaim:
    command_id: ClaimCommandId
    claim_id: ClaimId
    expected_claim_digest: str
    predicate_code: ClaimPredicate
    predicate_version: int
    value: ClaimValue = field(repr=False)
    temporal: ClaimTemporal
    criticality: ClaimCriticality
    creation_method: ClaimCreationMethod
    creation_method_version: int
    correction_reason: ClaimCorrectionReason
    links: tuple[ProposedClaimEvidenceLink, ...]
    schema_version: int = CLAIM_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.claim_id, ClaimId):
            raise InvariantViolationError("Claim correction ID must be typed.")
        _digest(self.expected_claim_digest)
        if not isinstance(self.correction_reason, ClaimCorrectionReason):
            raise InvariantViolationError("Claim correction reason is invalid.")
        _command_common(self)

    def __repr__(self) -> str:
        return (
            f"CorrectClaim(command_id={self.command_id!r}, claim_id={self.claim_id!r}, "
            f"value=<redacted>, link_count={len(self.links)})"
        )


@dataclass(frozen=True, slots=True)
class ClaimOperationResult:
    history: ClaimHistory
    assessment: ClaimAssessment
    replayed: bool


def digest_register_claim(actor: ActorContext, command: RegisterClaim) -> str:
    return _command_digest(actor, command.command_id, "REGISTER", _payload(command))


def digest_correct_claim(actor: ActorContext, command: CorrectClaim) -> str:
    payload = _payload(command)
    payload.update(
        {
            "claim_id": str(command.claim_id),
            "correction_reason": command.correction_reason.value,
            "expected_claim_digest": command.expected_claim_digest,
        }
    )
    return _command_digest(actor, command.command_id, "CORRECT", payload)


def _payload(command: RegisterClaim | CorrectClaim) -> dict[str, object]:
    value_type, value_snapshot = claim_value_to_snapshot(command.value)
    temporal_type, temporal_snapshot = claim_temporal_to_snapshot(command.temporal)
    links = sorted(command.links, key=lambda item: str(item.evidence_id))
    return {
        "creation_method": command.creation_method.value,
        "creation_method_version": command.creation_method_version,
        "criticality": command.criticality.value,
        "links": [
            {
                "evidence_digest": item.expected_evidence_digest,
                "evidence_id": str(item.evidence_id),
                "role": item.role.value,
            }
            for item in links
        ],
        "predicate_code": command.predicate_code.value,
        "predicate_version": command.predicate_version,
        "schema_version": command.schema_version,
        "temporal": temporal_snapshot,
        "temporal_type": temporal_type,
        "value": value_snapshot,
        "value_type": value_type,
        **(
            {"investigation_id": str(command.investigation_id)}
            if isinstance(command, RegisterClaim)
            else {}
        ),
    }


def _command_digest(
    actor: ActorContext,
    command_id: ClaimCommandId,
    command_type: str,
    payload: dict[str, object],
) -> str:
    value = {
        "actor_user_id": str(actor.user_id),
        "command_id": str(command_id),
        "command_type": command_type,
        "payload": payload,
        "workspace_id": str(actor.workspace_id),
    }
    serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def _command_common(command: RegisterClaim | CorrectClaim) -> None:
    if not isinstance(command.command_id, ClaimCommandId):
        raise InvariantViolationError("Claim command ID must be typed.")
    if isinstance(command, RegisterClaim) and not isinstance(
        command.investigation_id, InvestigationId
    ):
        raise InvariantViolationError("Claim Investigation ID must be typed.")
    if not isinstance(command.predicate_code, ClaimPredicate) or command.predicate_version != 1:
        raise InvariantViolationError("Claim command predicate is unsupported.")
    if not isinstance(command.criticality, ClaimCriticality) or not isinstance(
        command.creation_method, ClaimCreationMethod
    ):
        raise InvariantViolationError("Claim command vocabulary is invalid.")
    if (
        not isinstance(command.creation_method_version, int)
        or isinstance(command.creation_method_version, bool)
        or command.creation_method_version < 1
    ):
        raise InvariantViolationError("Claim creation method version must be positive.")
    if (
        not isinstance(command.links, tuple)
        or not command.links
        or len(command.links) > MAX_CLAIM_LINKS
        or not all(isinstance(item, ProposedClaimEvidenceLink) for item in command.links)
    ):
        raise InvariantViolationError("Claim links are invalid or exceed the limit.")
    if len({item.evidence_id for item in command.links}) != len(command.links):
        raise InvariantViolationError("Claim command duplicates Evidence.")
    if not any(item.role is ClaimEvidenceRole.SUPPORTS for item in command.links):
        raise InvariantViolationError("Claim command requires an explicit support link.")
    if command.schema_version != CLAIM_COMMAND_SCHEMA_VERSION:
        raise InvariantViolationError("Claim command schema is unsupported.")
    claim_value_to_snapshot(command.value)
    claim_temporal_to_snapshot(command.temporal)


def _digest(value: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError("Claim expected digest is invalid.")


__all__ = [
    "CLAIM_COMMAND_SCHEMA_VERSION",
    "MAX_CLAIM_LINKS",
    "ClaimOperationResult",
    "CorrectClaim",
    "ProposedClaimEvidenceLink",
    "RegisterClaim",
    "digest_correct_claim",
    "digest_register_claim",
]
