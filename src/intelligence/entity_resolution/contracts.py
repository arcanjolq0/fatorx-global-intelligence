"""Closed immutable candidate, origin, and submission-batch contracts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import cast

from intelligence.domain.errors import DomainError
from intelligence.domain.geography import CountryCode
from intelligence.domain.investigation_inputs import (
    BusinessIdentifierInput,
    BusinessIdentifierType,
    CorporateDomainInput,
    IdentificationAddressInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.time import normalize_utc
from intelligence.entity_resolution.errors import (
    InvalidCandidateBatchError,
    InvalidCandidateError,
)
from intelligence.entity_resolution.policy import MatchClassification

CANDIDATE_IDENTITY_SCHEMA_VERSION = 1
CANDIDATE_ORIGIN_SCHEMA_VERSION = 1
CANDIDATE_BATCH_SCHEMA_VERSION = 1
MAX_CANDIDATES_PER_BATCH = 100
MAX_IDENTIFIERS_PER_CANDIDATE = 20
MAX_ADMINISTRATORS_PER_CANDIDATE = 50
MAX_CANDIDATE_KEY_LENGTH = 128
MAX_ORIGIN_REFERENCE_LENGTH = 256

_STABLE_KEY_PATTERN = re.compile(
    rf"[A-Za-z0-9][A-Za-z0-9._:-]{{0,{MAX_CANDIDATE_KEY_LENGTH - 1}}}",
    flags=re.ASCII,
)
_SOURCE_CODE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}", flags=re.ASCII)
_SEMVER_PATTERN = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", flags=re.ASCII)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class SourceRegistrationStatus(StrEnum):
    """Closed source status value without importing connector contracts."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISSOLVED = "DISSOLVED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedCandidateIdentity:
    """Safe candidate summary containing no business values."""

    schema_version: int
    identifier_count: int
    administrator_count: int
    has_trade_name: bool
    has_domain: bool
    has_address: bool
    has_incorporated_on: bool
    has_registry_status: bool


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CandidateIdentitySnapshot:
    """Closed source candidate identity, never a canonical Company."""

    legal_name: OriginalAndNormalizedText
    country_code: CountryCode
    trade_name: OriginalAndNormalizedText | None = None
    identifiers: tuple[BusinessIdentifierInput, ...] = ()
    corporate_domain: CorporateDomainInput | None = None
    address: IdentificationAddressInput | None = None
    incorporated_on: date | None = None
    administrators: tuple[OriginalAndNormalizedText, ...] = ()
    registry_status: SourceRegistrationStatus | None = None
    schema_version: int = CANDIDATE_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != CANDIDATE_IDENTITY_SCHEMA_VERSION
        ):
            raise InvalidCandidateError("Candidate identity schema version is unsupported.")
        if not isinstance(self.legal_name, OriginalAndNormalizedText):
            raise InvalidCandidateError("Candidate legal name must be typed text.")
        if not isinstance(self.country_code, CountryCode):
            raise InvalidCandidateError("Candidate country must be a CountryCode.")
        if self.trade_name is not None and not isinstance(
            self.trade_name, OriginalAndNormalizedText
        ):
            raise InvalidCandidateError("Candidate trade name must be typed text.")
        if (
            not isinstance(self.identifiers, tuple)
            or len(self.identifiers) > MAX_IDENTIFIERS_PER_CANDIDATE
            or any(not isinstance(value, BusinessIdentifierInput) for value in self.identifiers)
        ):
            raise InvalidCandidateError("Candidate identifiers violate the safe typed limit.")
        if self.corporate_domain is not None and not isinstance(
            self.corporate_domain, CorporateDomainInput
        ):
            raise InvalidCandidateError("Candidate corporate domain must be typed.")
        if self.address is not None and not isinstance(self.address, IdentificationAddressInput):
            raise InvalidCandidateError("Candidate address must be typed.")
        if self.address is not None and self.address.country_code != self.country_code:
            raise InvalidCandidateError("Candidate address country must match candidate country.")
        if any(
            identifier.jurisdiction_country_code is not None
            and identifier.jurisdiction_country_code != self.country_code
            for identifier in self.identifiers
        ):
            raise InvalidCandidateError("Candidate identifier jurisdiction must match its country.")
        if self.incorporated_on is not None and (
            not isinstance(self.incorporated_on, date) or isinstance(self.incorporated_on, datetime)
        ):
            raise InvalidCandidateError("Candidate incorporation date must be a civil date.")
        if (
            not isinstance(self.administrators, tuple)
            or len(self.administrators) > MAX_ADMINISTRATORS_PER_CANDIDATE
            or any(
                not isinstance(value, OriginalAndNormalizedText) for value in self.administrators
            )
        ):
            raise InvalidCandidateError("Candidate administrators violate the safe typed limit.")
        if self.registry_status is not None and not isinstance(
            self.registry_status, SourceRegistrationStatus
        ):
            raise InvalidCandidateError("Candidate registry status must use the closed vocabulary.")

    def to_public_redacted(self) -> RedactedCandidateIdentity:
        return RedactedCandidateIdentity(
            schema_version=self.schema_version,
            identifier_count=len(self.identifiers),
            administrator_count=len(self.administrators),
            has_trade_name=self.trade_name is not None,
            has_domain=self.corporate_domain is not None,
            has_address=self.address is not None,
            has_incorporated_on=self.incorporated_on is not None,
            has_registry_status=self.registry_status is not None,
        )

    def to_canonical_json(self) -> str:
        return _canonical_json(self._canonical_object())

    @classmethod
    def from_canonical_json(cls, serialized: str) -> CandidateIdentitySnapshot:
        raw = _parse_object(serialized, _IDENTITY_KEYS, "candidate identity")
        try:
            result = cls(
                legal_name=_text_pair(raw["legal_name"], "legal_name"),
                country_code=CountryCode(_string(raw["country_code"], "country_code")),
                trade_name=_optional_text_pair(raw["trade_name"], "trade_name"),
                identifiers=tuple(
                    _identifier(value) for value in _array(raw["identifiers"], "identifiers")
                ),
                corporate_domain=_optional_domain(raw["corporate_domain"]),
                address=_optional_address(raw["address"]),
                incorporated_on=_optional_date(raw["incorporated_on"]),
                administrators=tuple(
                    _text_pair(value, "administrator")
                    for value in _array(raw["administrators"], "administrators")
                ),
                registry_status=(
                    SourceRegistrationStatus(_string(raw["registry_status"], "registry_status"))
                    if raw["registry_status"] is not None
                    else None
                ),
                schema_version=_integer(raw["schema_version"], "schema_version"),
            )
        except (DomainError, ValueError, TypeError) as error:
            raise InvalidCandidateError("Persisted candidate identity is invalid.") from error
        if result.to_canonical_json() != serialized:
            raise InvalidCandidateError("Persisted candidate identity is not canonical.")
        return result

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        summary = self.to_public_redacted()
        return (
            "CandidateIdentitySnapshot("
            f"schema_version={summary.schema_version}, country_code={self.country_code.value!r}, "
            f"identifier_count={summary.identifier_count}, "
            f"administrator_count={summary.administrator_count}, <redacted>)"
        )

    def _canonical_object(self) -> dict[str, object]:
        return {
            "address": _address_object(self.address),
            "administrators": [_text_object(value) for value in self.administrators],
            "corporate_domain": _domain_object(self.corporate_domain),
            "country_code": self.country_code.value,
            "identifiers": [_identifier_object(value) for value in self.identifiers],
            "incorporated_on": (
                self.incorporated_on.isoformat() if self.incorporated_on is not None else None
            ),
            "legal_name": _text_object(self.legal_name),
            "registry_status": str(self.registry_status)
            if self.registry_status is not None
            else None,
            "schema_version": self.schema_version,
            "trade_name": _text_object(self.trade_name),
        }


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CandidateOriginSnapshot:
    """Minimal typed provenance for a candidate, without URL or source payload."""

    source_id: str
    connector_id: str
    connector_version: str
    source_candidate_reference: str = field(repr=False)
    collected_at: datetime
    collection_operation_reference: str | None = field(default=None, repr=False)
    original_result_digest: str | None = None
    schema_version: int = CANDIDATE_ORIGIN_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != CANDIDATE_ORIGIN_SCHEMA_VERSION
        ):
            raise InvalidCandidateError("Candidate origin schema version is unsupported.")
        _source_code(self.source_id, "source_id")
        _source_code(self.connector_id, "connector_id")
        if (
            not isinstance(self.connector_version, str)
            or _SEMVER_PATTERN.fullmatch(self.connector_version) is None
        ):
            raise InvalidCandidateError("Candidate connector version must be canonical SemVer.")
        _opaque_reference(self.source_candidate_reference, "source candidate reference")
        operation_reference = self.collection_operation_reference
        if operation_reference is not None:
            _opaque_reference(operation_reference, "collection operation reference")
        if self.original_result_digest is not None:
            _digest(self.original_result_digest, "original result digest")
        object.__setattr__(self, "collected_at", normalize_utc(self.collected_at))

    def to_canonical_json(self) -> str:
        return _canonical_json(self._canonical_object())

    @classmethod
    def from_canonical_json(cls, serialized: str) -> CandidateOriginSnapshot:
        raw = _parse_object(serialized, _ORIGIN_KEYS, "candidate origin")
        try:
            result = cls(
                source_id=_string(raw["source_id"], "source_id"),
                connector_id=_string(raw["connector_id"], "connector_id"),
                connector_version=_string(raw["connector_version"], "connector_version"),
                source_candidate_reference=_string(
                    raw["source_candidate_reference"], "source_candidate_reference"
                ),
                collected_at=_datetime(raw["collected_at"]),
                collection_operation_reference=_optional_string(
                    raw["collection_operation_reference"], "collection_operation_reference"
                ),
                original_result_digest=_optional_string(
                    raw["original_result_digest"], "original_result_digest"
                ),
                schema_version=_integer(raw["schema_version"], "schema_version"),
            )
        except (DomainError, ValueError, TypeError) as error:
            raise InvalidCandidateError("Persisted candidate origin is invalid.") from error
        if result.to_canonical_json() != serialized:
            raise InvalidCandidateError("Persisted candidate origin is not canonical.")
        return result

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return (
            "CandidateOriginSnapshot("
            f"source_id={self.source_id!r}, connector_id={self.connector_id!r}, "
            f"connector_version={self.connector_version!r}, collected_at={self.collected_at!r}, "
            "references=<redacted>)"
        )

    def _canonical_object(self) -> dict[str, object]:
        return {
            "collected_at": _datetime_text(self.collected_at),
            "collection_operation_reference": self.collection_operation_reference,
            "connector_id": self.connector_id,
            "connector_version": self.connector_version,
            "original_result_digest": self.original_result_digest,
            "schema_version": self.schema_version,
            "source_candidate_reference": self.source_candidate_reference,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class EntityCandidateInput:
    """Neutral candidate submitted internally for deterministic evaluation."""

    candidate_key: str = field(repr=False)
    identity: CandidateIdentitySnapshot = field(repr=False)
    origin: CandidateOriginSnapshot = field(repr=False)

    def __post_init__(self) -> None:
        if (
            not isinstance(self.candidate_key, str)
            or _STABLE_KEY_PATTERN.fullmatch(self.candidate_key) is None
        ):
            raise InvalidCandidateError("Candidate key has an invalid stable format.")
        if not isinstance(self.identity, CandidateIdentitySnapshot):
            raise InvalidCandidateError("Candidate identity must use the closed snapshot.")
        if not isinstance(self.origin, CandidateOriginSnapshot):
            raise InvalidCandidateError("Candidate origin must use the closed snapshot.")

    def to_canonical_json(self) -> str:
        return _canonical_json(self._canonical_object())

    @classmethod
    def from_canonical_json(cls, serialized: str) -> EntityCandidateInput:
        raw = _parse_object(serialized, _CANDIDATE_KEYS, "entity candidate")
        identity = _object(raw["identity"], _IDENTITY_KEYS, "candidate identity")
        origin = _object(raw["origin"], _ORIGIN_KEYS, "candidate origin")
        result = cls(
            candidate_key=_string(raw["candidate_key"], "candidate_key"),
            identity=CandidateIdentitySnapshot.from_canonical_json(_canonical_json(identity)),
            origin=CandidateOriginSnapshot.from_canonical_json(_canonical_json(origin)),
        )
        if result.to_canonical_json() != serialized:
            raise InvalidCandidateError("Persisted entity candidate is not canonical.")
        return result

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return (
            "EntityCandidateInput(candidate_key=<redacted>, identity=<redacted>, origin=<redacted>)"
        )

    def _canonical_object(self) -> dict[str, object]:
        return {
            "candidate_key": self.candidate_key,
            "identity": json.loads(self.identity.to_canonical_json()),
            "origin": json.loads(self.origin.to_canonical_json()),
        }


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CandidateSubmissionBatch:
    """Bounded immutable candidates tied to one persisted identification input digest."""

    input_digest: str
    candidates: tuple[EntityCandidateInput, ...] = field(repr=False)
    batch_version: int = CANDIDATE_BATCH_SCHEMA_VERSION

    def __post_init__(self) -> None:
        _digest(self.input_digest, "candidate batch input digest")
        if (
            isinstance(self.batch_version, bool)
            or self.batch_version != CANDIDATE_BATCH_SCHEMA_VERSION
        ):
            raise InvalidCandidateBatchError("Candidate batch version is unsupported.")
        if (
            not isinstance(self.candidates, tuple)
            or not self.candidates
            or len(self.candidates) > MAX_CANDIDATES_PER_BATCH
            or any(not isinstance(value, EntityCandidateInput) for value in self.candidates)
        ):
            raise InvalidCandidateBatchError("Candidate batch must contain one to 100 candidates.")
        candidate_keys = tuple(value.candidate_key for value in self.candidates)
        if len(set(candidate_keys)) != len(candidate_keys):
            raise InvalidCandidateBatchError("Candidate keys cannot repeat within a batch.")

    def to_canonical_json(self) -> str:
        return _canonical_json(
            {
                "batch_version": self.batch_version,
                "candidates": [
                    json.loads(value.to_canonical_json())
                    for value in sorted(self.candidates, key=lambda item: item.candidate_key)
                ],
                "input_digest": self.input_digest,
            }
        )

    @classmethod
    def from_canonical_json(cls, serialized: str) -> CandidateSubmissionBatch:
        raw = _parse_object(serialized, _BATCH_KEYS, "candidate batch")
        result = cls(
            input_digest=_string(raw["input_digest"], "input_digest"),
            candidates=tuple(
                EntityCandidateInput.from_canonical_json(_canonical_json(value))
                for value in _array(raw["candidates"], "candidates")
            ),
            batch_version=_integer(raw["batch_version"], "batch_version"),
        )
        if result.to_canonical_json() != serialized:
            raise InvalidCandidateBatchError("Persisted candidate batch is not canonical.")
        return result

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return (
            "CandidateSubmissionBatch("
            f"batch_version={self.batch_version}, candidate_count={len(self.candidates)}, "
            f"input_digest={self.input_digest!r}, candidates=<redacted>)"
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedCandidateBatchResult:
    """Allowlisted batch summary suitable for audit metadata."""

    candidate_count: int
    top_classification: MatchClassification


_TEXT_KEYS = {"normalized_value", "original_value"}
_IDENTIFIER_KEYS = {
    "identifier_type",
    "jurisdiction_country_code",
    "normalized_value",
    "original_value",
}
_ADDRESS_KEYS = {
    "address_line_1",
    "address_line_2",
    "administrative_area",
    "country_code",
    "locality",
    "postal_code",
}
_IDENTITY_KEYS = {
    "address",
    "administrators",
    "corporate_domain",
    "country_code",
    "identifiers",
    "incorporated_on",
    "legal_name",
    "registry_status",
    "schema_version",
    "trade_name",
}
_ORIGIN_KEYS = {
    "collected_at",
    "collection_operation_reference",
    "connector_id",
    "connector_version",
    "original_result_digest",
    "schema_version",
    "source_candidate_reference",
    "source_id",
}
_CANDIDATE_KEYS = {"candidate_key", "identity", "origin"}
_BATCH_KEYS = {"batch_version", "candidates", "input_digest"}


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
    )


def _parse_object(serialized: str, keys: set[str], field_name: str) -> dict[str, object]:
    if not isinstance(serialized, str):
        raise InvalidCandidateError(f"Persisted {field_name} must be JSON text.")
    try:
        raw = cast(object, json.loads(serialized))
    except (json.JSONDecodeError, TypeError) as error:
        raise InvalidCandidateError(f"Persisted {field_name} is invalid.") from error
    return _object(raw, keys, field_name)


def _object(value: object, keys: set[str], field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise InvalidCandidateError(f"Persisted {field_name} has unsupported fields.")
    return cast(dict[str, object], value)


def _array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise InvalidCandidateError(f"Persisted {field_name} must be an array.")
    return cast(list[object], value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidCandidateError(f"Persisted {field_name} must be text.")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    return None if value is None else _string(value, field_name)


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidCandidateError(f"Persisted {field_name} must be an integer.")
    return value


def _text_object(value: OriginalAndNormalizedText | None) -> object:
    if value is None:
        return None
    return {"normalized_value": value.normalized_value, "original_value": value.original_value}


def _text_pair(value: object, field_name: str) -> OriginalAndNormalizedText:
    typed = _object(value, _TEXT_KEYS, field_name)
    return OriginalAndNormalizedText(
        original_value=_string(typed["original_value"], f"{field_name}.original_value"),
        normalized_value=_string(typed["normalized_value"], f"{field_name}.normalized_value"),
    )


def _optional_text_pair(value: object, field_name: str) -> OriginalAndNormalizedText | None:
    return None if value is None else _text_pair(value, field_name)


def _identifier_object(value: BusinessIdentifierInput) -> dict[str, object]:
    return {
        "identifier_type": value.identifier_type.value,
        "jurisdiction_country_code": (
            value.jurisdiction_country_code.value
            if value.jurisdiction_country_code is not None
            else None
        ),
        "normalized_value": value.normalized_value,
        "original_value": value.original_value,
    }


def _identifier(value: object) -> BusinessIdentifierInput:
    typed = _object(value, _IDENTIFIER_KEYS, "identifier")
    jurisdiction = _optional_string(typed["jurisdiction_country_code"], "jurisdiction")
    return BusinessIdentifierInput(
        identifier_type=BusinessIdentifierType(
            _string(typed["identifier_type"], "identifier_type")
        ),
        original_value=_string(typed["original_value"], "identifier.original_value"),
        normalized_value=_string(typed["normalized_value"], "identifier.normalized_value"),
        jurisdiction_country_code=CountryCode(jurisdiction) if jurisdiction is not None else None,
    )


def _domain_object(value: CorporateDomainInput | None) -> object:
    if value is None:
        return None
    return {
        "normalized_value": value.normalized_value,
        "original_value": value.original_value,
    }


def _optional_domain(value: object) -> CorporateDomainInput | None:
    if value is None:
        return None
    typed = _object(value, _TEXT_KEYS, "corporate_domain")
    return CorporateDomainInput(
        original_value=_string(typed["original_value"], "corporate_domain.original_value"),
        normalized_value=_string(typed["normalized_value"], "corporate_domain.normalized_value"),
    )


def _address_object(value: IdentificationAddressInput | None) -> object:
    if value is None:
        return None
    return {
        "address_line_1": _text_object(value.address_line_1),
        "address_line_2": _text_object(value.address_line_2),
        "administrative_area": _text_object(value.administrative_area),
        "country_code": value.country_code.value,
        "locality": _text_object(value.locality),
        "postal_code": _text_object(value.postal_code),
    }


def _optional_address(value: object) -> IdentificationAddressInput | None:
    if value is None:
        return None
    typed = _object(value, _ADDRESS_KEYS, "address")
    return IdentificationAddressInput(
        country_code=CountryCode(_string(typed["country_code"], "address.country_code")),
        address_line_1=_optional_text_pair(typed["address_line_1"], "address_line_1"),
        address_line_2=_optional_text_pair(typed["address_line_2"], "address_line_2"),
        administrative_area=_optional_text_pair(
            typed["administrative_area"], "administrative_area"
        ),
        locality=_optional_text_pair(typed["locality"], "locality"),
        postal_code=_optional_text_pair(typed["postal_code"], "postal_code"),
    )


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidCandidateError("Persisted incorporation date must be text.")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise InvalidCandidateError("Persisted incorporation date is invalid.") from error
    if parsed.isoformat() != value:
        raise InvalidCandidateError("Persisted incorporation date is not canonical.")
    return parsed


def _datetime_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _datetime(value: object) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InvalidCandidateError("Persisted collection timestamp must be canonical UTC.")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as error:
        raise InvalidCandidateError("Persisted collection timestamp is invalid.") from error
    normalized = normalize_utc(parsed)
    if _datetime_text(normalized) != value:
        raise InvalidCandidateError("Persisted collection timestamp is not canonical UTC.")
    return normalized


def _source_code(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SOURCE_CODE_PATTERN.fullmatch(value) is None:
        raise InvalidCandidateError(f"Candidate {field_name} has an invalid format.")


def _opaque_reference(value: str, field_name: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_ORIGIN_REFERENCE_LENGTH
        or any(character in "\r\n\x00" for character in value)
        or "://" in value
    ):
        raise InvalidCandidateError(f"Candidate {field_name} is invalid.")


def _digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        error_type = InvalidCandidateBatchError if "batch" in field_name else InvalidCandidateError
        raise error_type(f"{field_name} must be a lowercase SHA-256 digest.")


__all__ = [
    "CANDIDATE_BATCH_SCHEMA_VERSION",
    "CANDIDATE_IDENTITY_SCHEMA_VERSION",
    "CANDIDATE_ORIGIN_SCHEMA_VERSION",
    "MAX_ADMINISTRATORS_PER_CANDIDATE",
    "MAX_CANDIDATES_PER_BATCH",
    "MAX_IDENTIFIERS_PER_CANDIDATE",
    "CandidateIdentitySnapshot",
    "CandidateOriginSnapshot",
    "CandidateSubmissionBatch",
    "EntityCandidateInput",
    "RedactedCandidateBatchResult",
    "RedactedCandidateIdentity",
    "SourceRegistrationStatus",
]
