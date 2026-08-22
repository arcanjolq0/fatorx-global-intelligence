"""Commands and redacted results for F5.3 global Evidence admissibility."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    EvidenceAdmissibilityCommandId,
    EvidenceId,
    InvestigationId,
)
from intelligence.domain.time import normalize_utc
from intelligence.evidence.admissibility import (
    EffectiveEvidenceAdmissibility,
    EvidenceAdmissibilityHistory,
    EvidenceAdmissibilityReason,
    EvidenceAdmissibilityRequestedAction,
)
from intelligence.evidence.models import EvidenceHistory

EVIDENCE_ADMISSIBILITY_COMMAND_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class DecideEvidenceAdmissibility:
    command_id: EvidenceAdmissibilityCommandId
    investigation_id: InvestigationId
    evidence_id: EvidenceId
    expected_evidence_digest: str
    expected_previous_decision_digest: str | None
    requested_action: EvidenceAdmissibilityRequestedAction
    reason_code: EvidenceAdmissibilityReason
    requested_valid_until: datetime | None = None
    schema_version: int = EVIDENCE_ADMISSIBILITY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            not isinstance(self.command_id, EvidenceAdmissibilityCommandId)
            or not isinstance(self.investigation_id, InvestigationId)
            or not isinstance(self.evidence_id, EvidenceId)
        ):
            raise InvariantViolationError("Admissibility command identifiers must be typed.")
        _digest(self.expected_evidence_digest)
        if self.expected_previous_decision_digest is not None:
            _digest(self.expected_previous_decision_digest)
        if not isinstance(self.requested_action, EvidenceAdmissibilityRequestedAction) or (
            not isinstance(self.reason_code, EvidenceAdmissibilityReason)
        ):
            raise InvariantViolationError("Admissibility command vocabulary is invalid.")
        if self.requested_valid_until is not None:
            object.__setattr__(
                self, "requested_valid_until", normalize_utc(self.requested_valid_until)
            )
        if self.requested_action is not EvidenceAdmissibilityRequestedAction.ADMIT and (
            self.requested_valid_until is not None
        ):
            raise InvariantViolationError("Only ADMIT may request an expiration.")
        if self.schema_version != EVIDENCE_ADMISSIBILITY_COMMAND_SCHEMA_VERSION:
            raise InvariantViolationError("Admissibility command schema is unsupported.")

    def __repr__(self) -> str:
        return (
            f"DecideEvidenceAdmissibility(command_id={self.command_id!r}, "
            f"investigation_id={self.investigation_id!r}, evidence_id={self.evidence_id!r}, "
            f"requested_action={self.requested_action.value!r}, digests=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceAdmissibilityOperationResult:
    history: EvidenceAdmissibilityHistory
    effective: EffectiveEvidenceAdmissibility
    replayed: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class EvidenceAdmissibilityReadResult:
    evidence_history: EvidenceHistory
    decision_histories: tuple[EvidenceAdmissibilityHistory, ...]
    effective: EffectiveEvidenceAdmissibility


def digest_decide_evidence_admissibility(
    actor: ActorContext, command: DecideEvidenceAdmissibility
) -> str:
    value = {
        "actor_user_id": str(actor.user_id),
        "command_id": str(command.command_id),
        "command_type": "DECIDE_EVIDENCE_ADMISSIBILITY",
        "payload": {
            "evidence_id": str(command.evidence_id),
            "expected_evidence_digest": command.expected_evidence_digest,
            "expected_previous_decision_digest": command.expected_previous_decision_digest,
            "investigation_id": str(command.investigation_id),
            "reason_code": command.reason_code.value,
            "requested_action": command.requested_action.value,
            "requested_valid_until": (
                command.requested_valid_until.isoformat()
                if command.requested_valid_until is not None
                else None
            ),
            "schema_version": command.schema_version,
        },
        "workspace_id": str(actor.workspace_id),
    }
    return sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _digest(value: str) -> None:
    try:
        valid = len(value) == 64 and bytes.fromhex(value).hex() == value
    except TypeError, ValueError:
        valid = False
    if not valid:
        raise InvariantViolationError("Admissibility digest is invalid.")


__all__ = [
    "EVIDENCE_ADMISSIBILITY_COMMAND_SCHEMA_VERSION",
    "DecideEvidenceAdmissibility",
    "EvidenceAdmissibilityOperationResult",
    "EvidenceAdmissibilityReadResult",
    "digest_decide_evidence_admissibility",
]
