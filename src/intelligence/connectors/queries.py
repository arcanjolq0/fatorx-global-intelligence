"""Neutral company query and opaque candidate reference types."""

import re
from dataclasses import dataclass

from intelligence.connectors.errors import InvalidCompanyQueryError
from intelligence.connectors.identifiers import CandidateRefId, ConnectorId
from intelligence.domain.geography import CountryCode

_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.-]*", flags=re.ASCII)
_DOMAIN_LABEL_PATTERN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?")
_MAX_NAME_LENGTH = 512
_MAX_SNAPSHOT_LENGTH = 512


@dataclass(frozen=True, slots=True)
class BusinessIdentifierType:
    """Closed-shape identifier type code interpreted later by country policy."""

    value: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, str)
            or not self.value
            or len(self.value) > 64
            or _CODE_PATTERN.fullmatch(self.value) is None
        ):
            raise InvalidCompanyQueryError("Business identifier type has an invalid format.")


@dataclass(frozen=True, slots=True)
class BusinessIdentifier:
    """Structured identifier signal supplied by the caller, not a confirmed fact."""

    identifier_type: BusinessIdentifierType
    original_value: str
    normalized_value: str

    def __post_init__(self) -> None:
        if not isinstance(self.identifier_type, BusinessIdentifierType):
            raise InvalidCompanyQueryError(
                "BusinessIdentifier identifier_type has an invalid type."
            )
        object.__setattr__(
            self,
            "original_value",
            _required_text(self.original_value, "Business identifier original value", 256),
        )
        object.__setattr__(
            self,
            "normalized_value",
            _required_text(self.normalized_value, "Business identifier normalized value", 256),
        )


@dataclass(frozen=True, slots=True)
class DomainName:
    """Canonical host name without protocol, path, port, query, or credentials."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidCompanyQueryError("DomainName must be text.")
        canonical = self.value.strip().lower()
        labels = canonical.split(".")
        if (
            not canonical
            or len(canonical) > 253
            or canonical.endswith(".")
            or any(character.isspace() for character in canonical)
            or any(character in canonical for character in "/:@?#")
            or any(_DOMAIN_LABEL_PATTERN.fullmatch(label) is None for label in labels)
        ):
            raise InvalidCompanyQueryError(
                "DomainName must contain only a canonical host without URL parts."
            )
        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, kw_only=True)
class SearchAddress:
    """Structured address signal that preserves supplied text components."""

    country: CountryCode
    lines: tuple[str, ...] = ()
    locality: str | None = None
    administrative_area: str | None = None
    postal_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.country, CountryCode):
            raise InvalidCompanyQueryError("SearchAddress country must be a CountryCode.")
        lines = tuple(_required_text(line, "Search address line", 256) for line in self.lines)
        locality = _optional_text(self.locality, "Search address locality", 128)
        administrative_area = _optional_text(
            self.administrative_area,
            "Search address administrative area",
            128,
        )
        postal_code = _optional_text(self.postal_code, "Search address postal code", 32)
        if not lines and locality is None and administrative_area is None and postal_code is None:
            raise InvalidCompanyQueryError(
                "SearchAddress requires at least one supplied component."
            )
        object.__setattr__(self, "lines", lines)
        object.__setattr__(self, "locality", locality)
        object.__setattr__(self, "administrative_area", administrative_area)
        object.__setattr__(self, "postal_code", postal_code)


@dataclass(frozen=True, slots=True, kw_only=True)
class CompanyQuery:
    """Company search input that never constructs or confirms a domain Company."""

    country: CountryCode
    original_name: str
    normalized_name: str
    identifiers: tuple[BusinessIdentifier, ...] = ()
    domain: DomainName | None = None
    address: SearchAddress | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.country, CountryCode):
            raise InvalidCompanyQueryError("CompanyQuery country must be a CountryCode.")
        if any(not isinstance(identifier, BusinessIdentifier) for identifier in self.identifiers):
            raise InvalidCompanyQueryError(
                "CompanyQuery identifiers must contain only BusinessIdentifier values."
            )
        if self.domain is not None and not isinstance(self.domain, DomainName):
            raise InvalidCompanyQueryError("CompanyQuery domain must be a DomainName.")
        if self.address is not None:
            if not isinstance(self.address, SearchAddress):
                raise InvalidCompanyQueryError("CompanyQuery address must be a SearchAddress.")
            if self.address.country != self.country:
                raise InvalidCompanyQueryError(
                    "CompanyQuery address country must match the query country."
                )
        object.__setattr__(
            self,
            "original_name",
            _required_text(self.original_name, "CompanyQuery original_name", _MAX_NAME_LENGTH),
        )
        object.__setattr__(
            self,
            "normalized_name",
            _required_text(
                self.normalized_name,
                "CompanyQuery normalized_name",
                _MAX_NAME_LENGTH,
            ),
        )
        object.__setattr__(self, "identifiers", tuple(self.identifiers))


@dataclass(frozen=True, slots=True)
class CandidateSnapshot:
    """Small human-readable candidate hint, never a raw provider payload."""

    summary: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "summary",
            _required_text(self.summary, "Candidate snapshot", _MAX_SNAPSHOT_LENGTH),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateRef:
    """Opaque connector-scoped candidate that cannot be confused with CompanyId."""

    candidate_ref_id: CandidateRefId
    connector_id: ConnectorId
    snapshot: CandidateSnapshot
    country: CountryCode
    display_name: str
    primary_identifier: BusinessIdentifier | None = None
    domain: DomainName | None = None

    def __post_init__(self) -> None:
        expected_types = (
            (self.candidate_ref_id, CandidateRefId, "candidate_ref_id"),
            (self.connector_id, ConnectorId, "connector_id"),
            (self.snapshot, CandidateSnapshot, "snapshot"),
            (self.country, CountryCode, "country"),
        )
        for value, expected_type, field_name in expected_types:
            if not isinstance(value, expected_type):
                raise InvalidCompanyQueryError(f"CandidateRef {field_name} has an invalid type.")
        if self.primary_identifier is not None and not isinstance(
            self.primary_identifier, BusinessIdentifier
        ):
            raise InvalidCompanyQueryError(
                "CandidateRef primary_identifier must be a BusinessIdentifier."
            )
        if self.domain is not None and not isinstance(self.domain, DomainName):
            raise InvalidCompanyQueryError("CandidateRef domain must be a DomainName.")
        object.__setattr__(
            self,
            "display_name",
            _required_text(self.display_name, "CandidateRef display_name", _MAX_NAME_LENGTH),
        )


def _required_text(value: str, field_name: str, maximum_length: int) -> str:
    if not isinstance(value, str):
        raise InvalidCompanyQueryError(f"{field_name} must be text.")
    canonical = value.strip()
    if (
        not canonical
        or len(canonical) > maximum_length
        or any(character in "\r\n\x00" for character in canonical)
    ):
        raise InvalidCompanyQueryError(f"{field_name} has an invalid value.")
    return canonical


def _optional_text(value: str | None, field_name: str, maximum_length: int) -> str | None:
    if value is None:
        return None
    return _required_text(value, field_name, maximum_length)


__all__ = [
    "BusinessIdentifier",
    "BusinessIdentifierType",
    "CandidateRef",
    "CandidateSnapshot",
    "CompanyQuery",
    "DomainName",
    "SearchAddress",
]
