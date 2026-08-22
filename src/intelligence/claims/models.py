"""Pure immutable F5.2 claim, evidence-link, and assessment models."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256

from intelligence.claims.errors import ClaimHistoryError, ClaimIntegrityError
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
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
from intelligence.domain.time import normalize_utc

CLAIM_SCHEMA_VERSION = 1
CLAIM_LINK_SCHEMA_VERSION = 1
CLAIM_PREDICATE_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]{0,127}", flags=re.ASCII)


class ClaimPredicate(StrEnum):
    LEGAL_NAME = "LEGAL_NAME"
    REGISTRATION_STATUS = "REGISTRATION_STATUS"
    INCORPORATION_DATE = "INCORPORATION_DATE"
    COUNTRY_OF_REGISTRATION = "COUNTRY_OF_REGISTRATION"
    REGISTRATION_IDENTIFIER = "REGISTRATION_IDENTIFIER"


class RegistrationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISSOLVED = "DISSOLVED"
    UNKNOWN = "UNKNOWN"


class ClaimCriticality(StrEnum):
    STANDARD = "STANDARD"
    CRITICAL = "CRITICAL"


class ClaimCreationMethod(StrEnum):
    MANUAL = "MANUAL"


class ClaimCorrectionReason(StrEnum):
    VALUE_CORRECTION = "VALUE_CORRECTION"
    TEMPORAL_CORRECTION = "TEMPORAL_CORRECTION"
    CRITICALITY_CORRECTION = "CRITICALITY_CORRECTION"
    METHOD_CORRECTION = "METHOD_CORRECTION"
    EVIDENCE_LINK_CORRECTION = "EVIDENCE_LINK_CORRECTION"
    MULTIPLE_FIELDS_CORRECTION = "MULTIPLE_FIELDS_CORRECTION"


class ClaimEvidenceRole(StrEnum):
    SUPPORTS = "SUPPORTS"
    CONTRADICTS = "CONTRADICTS"
    QUALIFIES = "QUALIFIES"


class ClaimEvidenceUseOutcome(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    RESTRICTED = "RESTRICTED"
    REJECTED = "REJECTED"


class ClaimEvidenceUseReason(StrEnum):
    CONTROLLED_EVIDENCE_ELIGIBLE = "CONTROLLED_EVIDENCE_ELIGIBLE"
    CONTROLLED_CORPUS_NOT_PROVEN = "CONTROLLED_CORPUS_NOT_PROVEN"
    CONTROLLED_EVIDENCE_NOT_PROVEN = "CONTROLLED_EVIDENCE_NOT_PROVEN"
    STORAGE_MODE_RESTRICTED = "STORAGE_MODE_RESTRICTED"
    RETENTION_MODE_RESTRICTED = "RETENTION_MODE_RESTRICTED"
    DISPLAY_MODE_RESTRICTED = "DISPLAY_MODE_RESTRICTED"
    CONTENT_ORIGINAL_REQUIRED = "CONTENT_ORIGINAL_REQUIRED"
    USE_EXPLICITLY_PROHIBITED = "USE_EXPLICITLY_PROHIBITED"


_USE_REASONS_BY_OUTCOME: dict[ClaimEvidenceUseOutcome, frozenset[ClaimEvidenceUseReason]] = {
    ClaimEvidenceUseOutcome.ELIGIBLE: frozenset(
        {ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_ELIGIBLE}
    ),
    ClaimEvidenceUseOutcome.RESTRICTED: frozenset(
        {
            ClaimEvidenceUseReason.CONTROLLED_CORPUS_NOT_PROVEN,
            ClaimEvidenceUseReason.CONTROLLED_EVIDENCE_NOT_PROVEN,
            ClaimEvidenceUseReason.STORAGE_MODE_RESTRICTED,
            ClaimEvidenceUseReason.RETENTION_MODE_RESTRICTED,
            ClaimEvidenceUseReason.DISPLAY_MODE_RESTRICTED,
            ClaimEvidenceUseReason.CONTENT_ORIGINAL_REQUIRED,
        }
    ),
    ClaimEvidenceUseOutcome.REJECTED: frozenset({ClaimEvidenceUseReason.USE_EXPLICITLY_PROHIBITED}),
}


class ClaimEvidencePurpose(StrEnum):
    INTERNAL_CLAIM_VERIFICATION = "INTERNAL_CLAIM_VERIFICATION"


class ClaimAssessmentOutcome(StrEnum):
    INSUFFICIENT = "INSUFFICIENT"
    SUPPORTED = "SUPPORTED"
    CONFLICTED = "CONFLICTED"


class ClaimAssessmentReason(StrEnum):
    NO_ELIGIBLE_SUPPORT = "NO_ELIGIBLE_SUPPORT"
    ELIGIBLE_CONTRADICTION_WITHOUT_SUPPORT = "ELIGIBLE_CONTRADICTION_WITHOUT_SUPPORT"
    ELIGIBLE_SUPPORT = "ELIGIBLE_SUPPORT"
    ELIGIBLE_CONFLICT = "ELIGIBLE_CONFLICT"


class TemporalAbsenceReason(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    NOT_PROVIDED = "NOT_PROVIDED"


@dataclass(frozen=True, slots=True)
class TextClaimValue:
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        _text(self.value, "Claim text", 512)


@dataclass(frozen=True, slots=True)
class RegistrationStatusClaimValue:
    status: RegistrationStatus

    def __post_init__(self) -> None:
        if not isinstance(self.status, RegistrationStatus):
            raise InvariantViolationError("Claim registration status is invalid.")


@dataclass(frozen=True, slots=True)
class DateClaimValue:
    value: date

    def __post_init__(self) -> None:
        if not isinstance(self.value, date) or isinstance(self.value, datetime):
            raise InvariantViolationError("Claim date must be a civil date.")


@dataclass(frozen=True, slots=True)
class CountryCodeClaimValue:
    country: CountryCode

    def __post_init__(self) -> None:
        if not isinstance(self.country, CountryCode):
            raise InvariantViolationError("Claim country must be typed.")


@dataclass(frozen=True, slots=True, repr=False)
class RegistrationIdentifierClaimValue:
    identifier_type: str
    original_value: str = field(repr=False)
    jurisdiction: CountryCode

    def __post_init__(self) -> None:
        _code(self.identifier_type, "Claim identifier type")
        _text(self.original_value, "Claim identifier value", 256)
        if not isinstance(self.jurisdiction, CountryCode):
            raise InvariantViolationError("Claim identifier jurisdiction must be typed.")


type ClaimValue = (
    TextClaimValue
    | RegistrationStatusClaimValue
    | DateClaimValue
    | CountryCodeClaimValue
    | RegistrationIdentifierClaimValue
)


@dataclass(frozen=True, slots=True)
class PointClaimTemporal:
    occurred_at: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at))


@dataclass(frozen=True, slots=True)
class PeriodClaimTemporal:
    valid_from: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        start = normalize_utc(self.valid_from)
        end = normalize_utc(self.valid_until)
        if end < start:
            raise InvariantViolationError("Claim validity end cannot precede its start.")
        object.__setattr__(self, "valid_from", start)
        object.__setattr__(self, "valid_until", end)


@dataclass(frozen=True, slots=True)
class UndatedClaimTemporal:
    reason: TemporalAbsenceReason

    def __post_init__(self) -> None:
        if not isinstance(self.reason, TemporalAbsenceReason):
            raise InvariantViolationError("Claim temporal absence reason is invalid.")


type ClaimTemporal = PointClaimTemporal | PeriodClaimTemporal | UndatedClaimTemporal


@dataclass(frozen=True, slots=True)
class ClaimEvidenceUseDecision:
    outcome: ClaimEvidenceUseOutcome
    reason_code: ClaimEvidenceUseReason
    policy_id: str
    policy_version: int
    purpose: ClaimEvidencePurpose
    controlled_corpus_manifest_version: int
    controlled_corpus_manifest_digest: str
    requested_by: UserId
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ClaimEvidenceUseOutcome) or not isinstance(
            self.reason_code, ClaimEvidenceUseReason
        ):
            raise InvariantViolationError("Claim evidence-use decision vocabulary is invalid.")
        if self.reason_code not in _USE_REASONS_BY_OUTCOME[self.outcome]:
            raise InvariantViolationError("Claim evidence-use outcome and reason are incompatible.")
        _code(self.policy_id, "Claim evidence-use policy ID")
        _positive(self.policy_version, "Claim evidence-use policy version")
        if not isinstance(self.purpose, ClaimEvidencePurpose):
            raise InvariantViolationError("Claim evidence-use purpose is invalid.")
        _positive(
            self.controlled_corpus_manifest_version,
            "Controlled corpus manifest version",
        )
        _digest(self.controlled_corpus_manifest_digest, "Controlled corpus manifest")
        if not isinstance(self.requested_by, UserId):
            raise InvariantViolationError("Claim evidence-use requester must be typed.")
        object.__setattr__(self, "evaluated_at", normalize_utc(self.evaluated_at))


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class Claim:
    id: ClaimId
    series_id: ClaimId
    version: int
    supersedes_claim_id: ClaimId | None
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    subject_company_id: CompanyId
    entity_resolution_decision_id: EntityResolutionDecisionId
    command_id: ClaimCommandId
    command_digest: str
    predicate_code: ClaimPredicate
    predicate_version: int
    value: ClaimValue = field(repr=False)
    temporal: ClaimTemporal
    criticality: ClaimCriticality
    creation_method: ClaimCreationMethod
    creation_method_version: int
    created_by: UserId
    created_at: datetime
    correction_reason: ClaimCorrectionReason | None
    claim_digest: str
    schema_version: int = CLAIM_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _claim_ids(self)
        _positive(self.version, "Claim version")
        if self.version == 1:
            if self.series_id != self.id or self.supersedes_claim_id is not None:
                raise InvariantViolationError("First Claim version must start its own series.")
            if self.correction_reason is not None:
                raise InvariantViolationError(
                    "First Claim version cannot have a correction reason."
                )
        elif self.series_id == self.id or self.supersedes_claim_id is None:
            raise InvariantViolationError("Corrected Claim must identify its prior version.")
        elif not isinstance(self.correction_reason, ClaimCorrectionReason):
            raise InvariantViolationError("Corrected Claim requires a closed correction reason.")
        if self.supersedes_claim_id == self.id:
            raise InvariantViolationError("Claim cannot supersede itself.")
        _digest(self.command_digest, "Claim command")
        _digest(self.claim_digest, "Claim")
        if not isinstance(self.predicate_code, ClaimPredicate):
            raise InvariantViolationError("Claim predicate is invalid.")
        if self.predicate_version != CLAIM_PREDICATE_VERSION:
            raise InvariantViolationError("Claim predicate version is unsupported.")
        _predicate_value(self.predicate_code, self.value)
        if not isinstance(
            self.temporal, (PointClaimTemporal, PeriodClaimTemporal, UndatedClaimTemporal)
        ):
            raise InvariantViolationError("Claim temporal value is invalid.")
        if not isinstance(self.criticality, ClaimCriticality):
            raise InvariantViolationError("Claim criticality is invalid.")
        if not isinstance(self.creation_method, ClaimCreationMethod):
            raise InvariantViolationError("Claim creation method is invalid.")
        _positive(self.creation_method_version, "Claim creation method version")
        object.__setattr__(self, "created_at", normalize_utc(self.created_at))
        if self.schema_version != CLAIM_SCHEMA_VERSION:
            raise InvariantViolationError("Claim schema is unsupported.")
        if self.claim_digest != claim_digest(self):
            raise ClaimIntegrityError("Claim digest verification failed.")

    def __repr__(self) -> str:
        return (
            f"Claim(id={self.id!r}, series_id={self.series_id!r}, version={self.version}, "
            f"workspace_id={self.workspace_id!r}, investigation_id={self.investigation_id!r}, "
            "value=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class ClaimEvidenceLink:
    claim_id: ClaimId
    claim_version: int
    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    subject_company_id: CompanyId
    entity_resolution_decision_id: EntityResolutionDecisionId
    evidence_id: EvidenceId
    evidence_digest: str
    role: ClaimEvidenceRole
    use_decision: ClaimEvidenceUseDecision
    link_digest: str
    schema_version: int = CLAIM_LINK_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for value, expected in (
            (self.claim_id, ClaimId),
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.subject_company_id, CompanyId),
            (self.entity_resolution_decision_id, EntityResolutionDecisionId),
            (self.evidence_id, EvidenceId),
        ):
            if not isinstance(value, expected):
                raise InvariantViolationError("Claim link identifiers must be typed.")
        _positive(self.claim_version, "Claim link version")
        _digest(self.evidence_digest, "Claim link Evidence")
        _digest(self.link_digest, "Claim link")
        if not isinstance(self.role, ClaimEvidenceRole) or not isinstance(
            self.use_decision, ClaimEvidenceUseDecision
        ):
            raise InvariantViolationError("Claim link vocabulary is invalid.")
        if self.schema_version != CLAIM_LINK_SCHEMA_VERSION:
            raise InvariantViolationError("Claim link schema is unsupported.")
        if self.link_digest != claim_link_digest(self):
            raise ClaimIntegrityError("Claim link digest verification failed.")


@dataclass(frozen=True, slots=True)
class ClaimHistory:
    versions: tuple[Claim, ...]
    links: tuple[ClaimEvidenceLink, ...]

    def __post_init__(self) -> None:
        if not self.versions:
            raise ClaimHistoryError("Claim history must contain at least one version.")
        if tuple(item.version for item in self.versions) != tuple(range(1, len(self.versions) + 1)):
            raise ClaimHistoryError("Claim versions must be contiguous and ordered.")
        if len({item.id for item in self.versions}) != len(self.versions) or len(
            {item.command_id for item in self.versions}
        ) != len(self.versions):
            raise ClaimHistoryError("Claim versions must have unique identities and commands.")
        first = self.versions[0]
        for index, version in enumerate(self.versions):
            if (
                version.series_id != first.series_id
                or version.workspace_id != first.workspace_id
                or version.investigation_id != first.investigation_id
                or version.subject_company_id != first.subject_company_id
                or version.entity_resolution_decision_id != first.entity_resolution_decision_id
                or version.predicate_code is not first.predicate_code
                or version.predicate_version != first.predicate_version
            ):
                raise ClaimHistoryError("Claim history scope, subject, or predicate changed.")
            if index and version.supersedes_claim_id != self.versions[index - 1].id:
                raise ClaimHistoryError("Claim supersession chain is broken.")
            if index and version.created_at < self.versions[index - 1].created_at:
                raise ClaimHistoryError("Claim timestamps are regressive.")
        ids = {item.id: item for item in self.versions}
        grouped: dict[ClaimId, list[ClaimEvidenceLink]] = {item.id: [] for item in self.versions}
        seen: set[tuple[ClaimId, EvidenceId]] = set()
        for link in self.links:
            claim = ids.get(link.claim_id)
            if claim is None or link.claim_version != claim.version:
                raise ClaimHistoryError("Claim link targets an unknown Claim version.")
            if (
                link.workspace_id != claim.workspace_id
                or link.investigation_id != claim.investigation_id
                or link.subject_company_id != claim.subject_company_id
                or link.entity_resolution_decision_id != claim.entity_resolution_decision_id
            ):
                raise ClaimHistoryError("Claim link scope or custody changed.")
            if (
                link.use_decision.requested_by != claim.created_by
                or link.use_decision.evaluated_at != claim.created_at
            ):
                raise ClaimHistoryError("Claim link decision provenance changed.")
            identity = (link.claim_id, link.evidence_id)
            if identity in seen:
                raise ClaimHistoryError("Evidence is duplicated within a Claim version.")
            seen.add(identity)
            grouped[link.claim_id].append(link)
        if any(
            not any(link.role is ClaimEvidenceRole.SUPPORTS for link in grouped[claim.id])
            for claim in self.versions
        ):
            raise ClaimHistoryError("Every Claim version requires an explicit support link.")

    @property
    def latest(self) -> Claim:
        return self.versions[-1]

    @property
    def latest_links(self) -> tuple[ClaimEvidenceLink, ...]:
        return tuple(link for link in self.links if link.claim_id == self.latest.id)


@dataclass(frozen=True, slots=True)
class ClaimAssessment:
    outcome: ClaimAssessmentOutcome
    reason: ClaimAssessmentReason
    qualifications: tuple[EvidenceId, ...]


def build_claim(
    *,
    claim_id: ClaimId,
    series_id: ClaimId,
    version: int,
    supersedes_claim_id: ClaimId | None,
    workspace_id: WorkspaceId,
    investigation_id: InvestigationId,
    subject_company_id: CompanyId,
    entity_resolution_decision_id: EntityResolutionDecisionId,
    command_id: ClaimCommandId,
    command_digest: str,
    predicate_code: ClaimPredicate,
    predicate_version: int,
    value: ClaimValue,
    temporal: ClaimTemporal,
    criticality: ClaimCriticality,
    creation_method: ClaimCreationMethod,
    creation_method_version: int,
    created_by: UserId,
    created_at: datetime,
    correction_reason: ClaimCorrectionReason | None,
) -> Claim:
    values: dict[str, object] = {
        "id": claim_id,
        "series_id": series_id,
        "version": version,
        "supersedes_claim_id": supersedes_claim_id,
        "workspace_id": workspace_id,
        "investigation_id": investigation_id,
        "subject_company_id": subject_company_id,
        "entity_resolution_decision_id": entity_resolution_decision_id,
        "command_id": command_id,
        "command_digest": command_digest,
        "predicate_code": predicate_code,
        "predicate_version": predicate_version,
        "value": value,
        "temporal": temporal,
        "criticality": criticality,
        "creation_method": creation_method,
        "creation_method_version": creation_method_version,
        "created_by": created_by,
        "created_at": created_at,
        "correction_reason": correction_reason,
        "schema_version": CLAIM_SCHEMA_VERSION,
    }
    return Claim(**values, claim_digest=_record_digest(values))  # type: ignore[arg-type]


def build_claim_link(
    *,
    claim: Claim,
    evidence_id: EvidenceId,
    evidence_digest: str,
    role: ClaimEvidenceRole,
    use_decision: ClaimEvidenceUseDecision,
) -> ClaimEvidenceLink:
    values: dict[str, object] = {
        "claim_id": claim.id,
        "claim_version": claim.version,
        "workspace_id": claim.workspace_id,
        "investigation_id": claim.investigation_id,
        "subject_company_id": claim.subject_company_id,
        "entity_resolution_decision_id": claim.entity_resolution_decision_id,
        "evidence_id": evidence_id,
        "evidence_digest": evidence_digest,
        "role": role,
        "use_decision": use_decision,
        "schema_version": CLAIM_LINK_SCHEMA_VERSION,
    }
    return ClaimEvidenceLink(**values, link_digest=_record_digest(values))  # type: ignore[arg-type]


def claim_digest(claim: Claim) -> str:
    return _record_digest(
        {
            name: getattr(claim, name)
            for name in Claim.__dataclass_fields__
            if name != "claim_digest"
        }
    )


def claim_link_digest(link: ClaimEvidenceLink) -> str:
    return _record_digest(
        {
            name: getattr(link, name)
            for name in ClaimEvidenceLink.__dataclass_fields__
            if name != "link_digest"
        }
    )


def assess_links(
    links: tuple[ClaimEvidenceLink, ...], valid_evidence_ids: frozenset[EvidenceId]
) -> ClaimAssessment:
    effective = tuple(
        link
        for link in links
        if link.evidence_id in valid_evidence_ids
        and link.use_decision.outcome is ClaimEvidenceUseOutcome.ELIGIBLE
    )
    supports = any(link.role is ClaimEvidenceRole.SUPPORTS for link in effective)
    contradicts = any(link.role is ClaimEvidenceRole.CONTRADICTS for link in effective)
    qualifications = tuple(
        link.evidence_id for link in effective if link.role is ClaimEvidenceRole.QUALIFIES
    )
    if supports and contradicts:
        return ClaimAssessment(
            ClaimAssessmentOutcome.CONFLICTED,
            ClaimAssessmentReason.ELIGIBLE_CONFLICT,
            qualifications,
        )
    if supports:
        return ClaimAssessment(
            ClaimAssessmentOutcome.SUPPORTED,
            ClaimAssessmentReason.ELIGIBLE_SUPPORT,
            qualifications,
        )
    reason = (
        ClaimAssessmentReason.ELIGIBLE_CONTRADICTION_WITHOUT_SUPPORT
        if contradicts
        else ClaimAssessmentReason.NO_ELIGIBLE_SUPPORT
    )
    return ClaimAssessment(ClaimAssessmentOutcome.INSUFFICIENT, reason, qualifications)


def claim_value_to_snapshot(value: ClaimValue) -> tuple[str, dict[str, object]]:
    if isinstance(value, TextClaimValue):
        return "TEXT", {"value": value.value}
    if isinstance(value, RegistrationStatusClaimValue):
        return "REGISTRATION_STATUS", {"status": value.status.value}
    if isinstance(value, DateClaimValue):
        return "DATE", {"value": value.value.isoformat()}
    if isinstance(value, CountryCodeClaimValue):
        return "COUNTRY_CODE", {"country": str(value.country)}
    if isinstance(value, RegistrationIdentifierClaimValue):
        return (
            "REGISTRATION_IDENTIFIER",
            {
                "identifier_type": value.identifier_type,
                "jurisdiction": str(value.jurisdiction),
                "original_value": value.original_value,
            },
        )
    raise InvariantViolationError("Claim value type is unsupported.")


def claim_value_from_snapshot(value_type: str, snapshot: dict[str, object]) -> ClaimValue:
    try:
        if value_type == "TEXT":
            _require_string_snapshot(snapshot, frozenset({"value"}), "Claim value")
            parsed: ClaimValue = TextClaimValue(snapshot["value"])  # type: ignore[arg-type]
        elif value_type == "REGISTRATION_STATUS":
            _require_string_snapshot(snapshot, frozenset({"status"}), "Claim value")
            parsed = RegistrationStatusClaimValue(
                RegistrationStatus(snapshot["status"])  # type: ignore[arg-type]
            )
        elif value_type == "DATE":
            _require_string_snapshot(snapshot, frozenset({"value"}), "Claim value")
            parsed = DateClaimValue(date.fromisoformat(snapshot["value"]))  # type: ignore[arg-type]
        elif value_type == "COUNTRY_CODE":
            _require_string_snapshot(snapshot, frozenset({"country"}), "Claim value")
            parsed = CountryCodeClaimValue(
                CountryCode(snapshot["country"])  # type: ignore[arg-type]
            )
        elif value_type == "REGISTRATION_IDENTIFIER":
            _require_string_snapshot(
                snapshot,
                frozenset({"identifier_type", "original_value", "jurisdiction"}),
                "Claim value",
            )
            parsed = RegistrationIdentifierClaimValue(
                identifier_type=snapshot["identifier_type"],  # type: ignore[arg-type]
                original_value=snapshot["original_value"],  # type: ignore[arg-type]
                jurisdiction=CountryCode(snapshot["jurisdiction"]),  # type: ignore[arg-type]
            )
        else:
            raise ClaimIntegrityError("Persisted Claim value type is unsupported.")
        if claim_value_to_snapshot(parsed) != (value_type, snapshot):
            raise ClaimIntegrityError("Persisted Claim value is not canonical.")
        return parsed
    except (InvariantViolationError, KeyError, TypeError, ValueError) as error:
        raise ClaimIntegrityError("Persisted Claim value is invalid.") from error


def claim_temporal_to_snapshot(value: ClaimTemporal) -> tuple[str, dict[str, object]]:
    if isinstance(value, PointClaimTemporal):
        return "POINT", {"occurred_at": value.occurred_at.isoformat()}
    if isinstance(value, PeriodClaimTemporal):
        return (
            "PERIOD",
            {
                "valid_from": value.valid_from.isoformat(),
                "valid_until": value.valid_until.isoformat(),
            },
        )
    if isinstance(value, UndatedClaimTemporal):
        return "UNDATED", {"reason": value.reason.value}
    raise InvariantViolationError("Claim temporal type is unsupported.")


def claim_temporal_from_snapshot(temporal_type: str, snapshot: dict[str, object]) -> ClaimTemporal:
    try:
        if temporal_type == "POINT":
            _require_string_snapshot(snapshot, frozenset({"occurred_at"}), "Claim temporal")
            parsed: ClaimTemporal = PointClaimTemporal(
                datetime.fromisoformat(snapshot["occurred_at"])  # type: ignore[arg-type]
            )
        elif temporal_type == "PERIOD":
            _require_string_snapshot(
                snapshot,
                frozenset({"valid_from", "valid_until"}),
                "Claim temporal",
            )
            parsed = PeriodClaimTemporal(
                valid_from=datetime.fromisoformat(snapshot["valid_from"]),  # type: ignore[arg-type]
                valid_until=datetime.fromisoformat(snapshot["valid_until"]),  # type: ignore[arg-type]
            )
        elif temporal_type == "UNDATED":
            _require_string_snapshot(snapshot, frozenset({"reason"}), "Claim temporal")
            parsed = UndatedClaimTemporal(
                TemporalAbsenceReason(snapshot["reason"])  # type: ignore[arg-type]
            )
        else:
            raise ClaimIntegrityError("Persisted Claim temporal type is unsupported.")
        if claim_temporal_to_snapshot(parsed) != (temporal_type, snapshot):
            raise ClaimIntegrityError("Persisted Claim temporal value is not canonical.")
        return parsed
    except (InvariantViolationError, KeyError, TypeError, ValueError) as error:
        raise ClaimIntegrityError("Persisted Claim temporal value is invalid.") from error


def _require_string_snapshot(
    snapshot: dict[str, object], expected_keys: frozenset[str], name: str
) -> None:
    if not isinstance(snapshot, dict) or frozenset(snapshot) != expected_keys:
        raise ClaimIntegrityError(f"Persisted {name} fields are invalid.")
    if any(type(snapshot[key]) is not str for key in expected_keys):
        raise ClaimIntegrityError(f"Persisted {name} JSON types are invalid.")


def _claim_ids(claim: Claim) -> None:
    for value, expected in (
        (claim.id, ClaimId),
        (claim.series_id, ClaimId),
        (claim.workspace_id, WorkspaceId),
        (claim.investigation_id, InvestigationId),
        (claim.subject_company_id, CompanyId),
        (claim.entity_resolution_decision_id, EntityResolutionDecisionId),
        (claim.command_id, ClaimCommandId),
        (claim.created_by, UserId),
    ):
        if not isinstance(value, expected):
            raise InvariantViolationError("Claim identifiers must be typed.")
    if claim.supersedes_claim_id is not None and not isinstance(claim.supersedes_claim_id, ClaimId):
        raise InvariantViolationError("Claim superseded identifier must be typed.")


def _predicate_value(predicate: ClaimPredicate, value: ClaimValue) -> None:
    expected: dict[ClaimPredicate, type[object]] = {
        ClaimPredicate.LEGAL_NAME: TextClaimValue,
        ClaimPredicate.REGISTRATION_STATUS: RegistrationStatusClaimValue,
        ClaimPredicate.INCORPORATION_DATE: DateClaimValue,
        ClaimPredicate.COUNTRY_OF_REGISTRATION: CountryCodeClaimValue,
        ClaimPredicate.REGISTRATION_IDENTIFIER: RegistrationIdentifierClaimValue,
    }
    if not isinstance(value, expected[predicate]):
        raise InvariantViolationError("Claim value is incompatible with its predicate.")


def _record_digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_json(value: object) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _canonical(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(
        value,
        (
            WorkspaceId,
            UserId,
            CompanyId,
            InvestigationId,
            ClaimId,
            ClaimCommandId,
            EntityResolutionDecisionId,
            EvidenceId,
        ),
    ):
        return str(value)
    if isinstance(value, datetime):
        return normalize_utc(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if hasattr(value, "__dataclass_fields__"):
        return {name: _canonical(getattr(value, name)) for name in value.__dataclass_fields__}
    return value


def _text(value: str, name: str, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > maximum
        or any(ord(character) < 32 for character in value)
    ):
        raise InvariantViolationError(f"{name} is invalid.")


def _code(value: str, name: str) -> None:
    if not isinstance(value, str) or _CODE_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"{name} is invalid.")


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"{name} digest is invalid.")


def _positive(value: int, name: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise InvariantViolationError(f"{name} must be positive.")


__all__ = [
    "CLAIM_LINK_SCHEMA_VERSION",
    "CLAIM_PREDICATE_VERSION",
    "CLAIM_SCHEMA_VERSION",
    "Claim",
    "ClaimAssessment",
    "ClaimAssessmentOutcome",
    "ClaimAssessmentReason",
    "ClaimCorrectionReason",
    "ClaimCreationMethod",
    "ClaimCriticality",
    "ClaimEvidenceLink",
    "ClaimEvidencePurpose",
    "ClaimEvidenceRole",
    "ClaimEvidenceUseDecision",
    "ClaimEvidenceUseOutcome",
    "ClaimEvidenceUseReason",
    "ClaimHistory",
    "ClaimPredicate",
    "ClaimTemporal",
    "ClaimValue",
    "CountryCodeClaimValue",
    "DateClaimValue",
    "PeriodClaimTemporal",
    "PointClaimTemporal",
    "RegistrationIdentifierClaimValue",
    "RegistrationStatus",
    "RegistrationStatusClaimValue",
    "TemporalAbsenceReason",
    "TextClaimValue",
    "UndatedClaimTemporal",
    "assess_links",
    "build_claim",
    "build_claim_link",
    "claim_digest",
    "claim_link_digest",
    "claim_temporal_from_snapshot",
    "claim_temporal_to_snapshot",
    "claim_value_from_snapshot",
    "claim_value_to_snapshot",
]
