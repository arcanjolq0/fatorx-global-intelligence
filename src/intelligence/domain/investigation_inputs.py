"""Closed, versioned identification input for investigation lifecycle commands."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum
from hashlib import sha256
from typing import cast
from unicodedata import category

from intelligence.domain.errors import InvalidIdentificationInputError
from intelligence.domain.geography import CountryCode

IDENTIFICATION_INPUT_SCHEMA_VERSION = 1
IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION = 2
SUPPORTED_IDENTIFICATION_INPUT_SCHEMA_VERSIONS = frozenset(
    {IDENTIFICATION_INPUT_SCHEMA_VERSION, IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION}
)
MAX_INPUT_TEXT_LENGTH = 512
MAX_IDENTIFIER_LENGTH = 256
MAX_LANGUAGE_TAG_LENGTH = 35
MAX_INPUT_ADMINISTRATORS = 50

_DOMAIN_PATTERN = re.compile(
    r"[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?"
    r"(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*",
    flags=re.ASCII,
)
_LANGUAGE_TAG_PATTERN = re.compile(
    r"[A-Za-z]{2,8}(-[A-Za-z0-9]{1,8})*",
    flags=re.ASCII,
)


class BusinessIdentifierType(StrEnum):
    """Closed business identifier vocabulary available in the first schema."""

    BUSINESS_REGISTRATION = "BUSINESS_REGISTRATION"
    TAX_IDENTIFIER = "TAX_IDENTIFIER"
    LEI = "LEI"


@dataclass(frozen=True, slots=True)
class OriginalAndNormalizedText:
    """A bounded original value and its separately supplied normalized form."""

    original_value: str = field(repr=False)
    normalized_value: str = field(repr=False)

    def __post_init__(self) -> None:
        original = _bounded_text(
            self.original_value,
            field_name="original value",
            maximum_length=MAX_INPUT_TEXT_LENGTH,
            preserve_outer_whitespace=True,
        )
        normalized = _bounded_text(
            self.normalized_value,
            field_name="normalized value",
            maximum_length=MAX_INPUT_TEXT_LENGTH,
        )
        object.__setattr__(self, "original_value", original)
        object.__setattr__(self, "normalized_value", normalized)

    def __repr__(self) -> str:
        return "OriginalAndNormalizedText(<redacted>)"


@dataclass(frozen=True, slots=True)
class BusinessIdentifierInput:
    """Typed business identifier preserving original and normalized values."""

    identifier_type: BusinessIdentifierType
    original_value: str = field(repr=False)
    normalized_value: str = field(repr=False)
    jurisdiction_country_code: CountryCode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identifier_type, BusinessIdentifierType):
            raise InvalidIdentificationInputError(
                "Business identifier type must use the closed vocabulary."
            )
        original = _bounded_text(
            self.original_value,
            field_name="business identifier original value",
            maximum_length=MAX_IDENTIFIER_LENGTH,
            preserve_outer_whitespace=True,
        )
        normalized = _bounded_text(
            self.normalized_value,
            field_name="business identifier normalized value",
            maximum_length=MAX_IDENTIFIER_LENGTH,
        )
        if self.jurisdiction_country_code is not None and not isinstance(
            self.jurisdiction_country_code, CountryCode
        ):
            raise InvalidIdentificationInputError(
                "Business identifier jurisdiction must be a CountryCode."
            )
        if (
            self.identifier_type
            in {
                BusinessIdentifierType.BUSINESS_REGISTRATION,
                BusinessIdentifierType.TAX_IDENTIFIER,
            }
            and self.jurisdiction_country_code is None
        ):
            raise InvalidIdentificationInputError(
                "This business identifier type requires a jurisdiction country."
            )
        object.__setattr__(self, "original_value", original)
        object.__setattr__(self, "normalized_value", normalized)

    def __repr__(self) -> str:
        jurisdiction = (
            self.jurisdiction_country_code.value
            if self.jurisdiction_country_code is not None
            else None
        )
        return (
            "BusinessIdentifierInput("
            f"identifier_type={self.identifier_type!r}, "
            f"jurisdiction_country_code={jurisdiction!r}, value=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class CorporateDomainInput:
    """Original corporate host and its canonical lowercase host."""

    original_value: str = field(repr=False)
    normalized_value: str = field(repr=False)

    def __post_init__(self) -> None:
        original = _bounded_text(
            self.original_value,
            field_name="corporate domain original value",
            maximum_length=253,
            preserve_outer_whitespace=True,
        )
        normalized = _bounded_text(
            self.normalized_value,
            field_name="corporate domain normalized value",
            maximum_length=253,
        )
        if normalized != normalized.lower() or _DOMAIN_PATTERN.fullmatch(normalized) is None:
            raise InvalidIdentificationInputError(
                "Corporate domain must be a canonical lowercase host."
            )
        if original.lower() != normalized:
            raise InvalidIdentificationInputError(
                "Corporate domain original and normalized values are inconsistent."
            )
        object.__setattr__(self, "original_value", original)
        object.__setattr__(self, "normalized_value", normalized)

    def __repr__(self) -> str:
        return "CorporateDomainInput(<redacted>)"


@dataclass(frozen=True, slots=True, kw_only=True)
class IdentificationAddressInput:
    """Closed address/locality structure without documents or arbitrary payloads."""

    country_code: CountryCode
    address_line_1: OriginalAndNormalizedText | None = field(default=None, repr=False)
    address_line_2: OriginalAndNormalizedText | None = field(default=None, repr=False)
    locality: OriginalAndNormalizedText | None = field(default=None, repr=False)
    administrative_area: OriginalAndNormalizedText | None = field(default=None, repr=False)
    postal_code: OriginalAndNormalizedText | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.country_code, CountryCode):
            raise InvalidIdentificationInputError(
                "Identification address country must be a CountryCode."
            )
        components = (
            self.address_line_1,
            self.address_line_2,
            self.locality,
            self.administrative_area,
            self.postal_code,
        )
        if not any(component is not None for component in components):
            raise InvalidIdentificationInputError(
                "Identification address requires at least one address or locality component."
            )
        if any(
            component is not None and not isinstance(component, OriginalAndNormalizedText)
            for component in components
        ):
            raise InvalidIdentificationInputError(
                "Identification address components must be typed text values."
            )

    def __repr__(self) -> str:
        return f"IdentificationAddressInput(country_code={self.country_code.value!r}, <redacted>)"


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedIdentificationInput:
    """Allowlisted public description that contains no business values."""

    schema_version: int
    has_legal_name: bool
    has_trade_name: bool
    identifier_count: int
    has_corporate_domain: bool
    has_address: bool
    has_original_language: bool
    administrator_count: int
    has_incorporated_on: bool


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class IdentificationInput:
    """Immutable input snapshot captured when identification starts."""

    schema_version: int = IDENTIFICATION_INPUT_SCHEMA_VERSION
    legal_name: OriginalAndNormalizedText | None = None
    trade_name: OriginalAndNormalizedText | None = None
    identifiers: tuple[BusinessIdentifierInput, ...] = ()
    corporate_domain: CorporateDomainInput | None = None
    address: IdentificationAddressInput | None = None
    original_language: str | None = None
    administrators: tuple[OriginalAndNormalizedText, ...] = ()
    incorporated_on: date | None = None

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or not isinstance(self.schema_version, int)
            or self.schema_version not in SUPPORTED_IDENTIFICATION_INPUT_SCHEMA_VERSIONS
        ):
            raise InvalidIdentificationInputError(
                "Identification input schema version is not supported."
            )
        if self.legal_name is not None and not isinstance(
            self.legal_name, OriginalAndNormalizedText
        ):
            raise InvalidIdentificationInputError("Legal name must be typed text.")
        if self.trade_name is not None and not isinstance(
            self.trade_name, OriginalAndNormalizedText
        ):
            raise InvalidIdentificationInputError("Trade name must be typed text.")
        if not isinstance(self.identifiers, tuple) or any(
            not isinstance(identifier, BusinessIdentifierInput) for identifier in self.identifiers
        ):
            raise InvalidIdentificationInputError(
                "Identification input identifiers must be an immutable typed tuple."
            )
        if self.corporate_domain is not None and not isinstance(
            self.corporate_domain, CorporateDomainInput
        ):
            raise InvalidIdentificationInputError("Corporate domain must be typed.")
        if self.address is not None and not isinstance(self.address, IdentificationAddressInput):
            raise InvalidIdentificationInputError("Identification address must be typed.")
        if (
            not isinstance(self.administrators, tuple)
            or len(self.administrators) > MAX_INPUT_ADMINISTRATORS
            or any(
                not isinstance(administrator, OriginalAndNormalizedText)
                for administrator in self.administrators
            )
        ):
            raise InvalidIdentificationInputError(
                "Identification administrators violate the safe typed limit."
            )
        if self.incorporated_on is not None and (
            not isinstance(self.incorporated_on, date) or isinstance(self.incorporated_on, datetime)
        ):
            raise InvalidIdentificationInputError(
                "Identification incorporation date must be a civil date."
            )
        has_extended_signal = bool(self.administrators) or self.incorporated_on is not None
        if self.schema_version == IDENTIFICATION_INPUT_SCHEMA_VERSION and has_extended_signal:
            raise InvalidIdentificationInputError(
                "Identification schema version 1 cannot contain extended matching fields."
            )
        if (
            self.schema_version == IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION
            and not has_extended_signal
        ):
            raise InvalidIdentificationInputError(
                "Identification schema version 2 requires an extended matching field."
            )
        language = None
        if self.original_language is not None:
            language = _bounded_text(
                self.original_language,
                field_name="original language",
                maximum_length=MAX_LANGUAGE_TAG_LENGTH,
            )
            if _LANGUAGE_TAG_PATTERN.fullmatch(language) is None:
                raise InvalidIdentificationInputError(
                    "Original language must use a BCP 47-shaped language tag."
                )
        object.__setattr__(self, "original_language", language)

    @property
    def has_usable_signal(self) -> bool:
        """Return whether the input contains a company-identification signal."""

        return any(
            (
                self.legal_name is not None,
                self.trade_name is not None,
                bool(self.identifiers),
                self.corporate_domain is not None,
                self.address is not None,
                bool(self.administrators),
                self.incorporated_on is not None,
            )
        )

    def validate_for(
        self,
        *,
        investigation_country_code: CountryCode,
        has_confirmed_company: bool,
    ) -> None:
        """Validate tenant-independent coherence with its investigation snapshot."""

        if not isinstance(investigation_country_code, CountryCode):
            raise InvalidIdentificationInputError("Investigation country must be a CountryCode.")
        if not isinstance(has_confirmed_company, bool):
            raise InvalidIdentificationInputError("Confirmed-company presence must be a boolean.")
        if not self.has_usable_signal and not has_confirmed_company:
            raise InvalidIdentificationInputError(
                "Identification input requires at least one usable signal."
            )
        country_values = [
            identifier.jurisdiction_country_code
            for identifier in self.identifiers
            if identifier.jurisdiction_country_code is not None
        ]
        if self.address is not None:
            country_values.append(self.address.country_code)
        if any(country != investigation_country_code for country in country_values):
            raise InvalidIdentificationInputError(
                "Identification input country must match the investigation country."
            )

    def to_public_redacted(self) -> RedactedIdentificationInput:
        """Return only signal presence and counts, never business values."""

        return RedactedIdentificationInput(
            schema_version=self.schema_version,
            has_legal_name=self.legal_name is not None,
            has_trade_name=self.trade_name is not None,
            identifier_count=len(self.identifiers),
            has_corporate_domain=self.corporate_domain is not None,
            has_address=self.address is not None,
            has_original_language=self.original_language is not None,
            administrator_count=len(self.administrators),
            has_incorporated_on=self.incorporated_on is not None,
        )

    def to_canonical_json(self) -> str:
        """Serialize the closed schema deterministically for JSONB and digests."""

        return json.dumps(
            self._canonical_object(),
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_canonical_json(cls, serialized: str) -> IdentificationInput:
        """Validate and reconstruct the exact supported persisted schema."""

        if not isinstance(serialized, str):
            raise InvalidIdentificationInputError(
                "Persisted identification input must be canonical JSON text."
            )
        try:
            raw = cast(object, json.loads(serialized))
        except (json.JSONDecodeError, TypeError) as error:
            raise InvalidIdentificationInputError(
                "Persisted identification input is invalid."
            ) from error
        if not isinstance(raw, dict):
            raise InvalidIdentificationInputError(
                "Persisted identification input must be an object."
            )
        untyped_root = cast(dict[object, object], raw)
        raw_schema_version = untyped_root.get("schema_version")
        schema_version = _integer(raw_schema_version, "schema_version")
        expected_keys = (
            _ROOT_KEYS_V2
            if schema_version == IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION
            else _ROOT_KEYS_V1
        )
        root = _object(raw, expected_keys=expected_keys, field_name="identification input")
        legal_name = _optional_text_pair(root["legal_name"], "legal_name")
        trade_name = _optional_text_pair(root["trade_name"], "trade_name")
        identifiers_raw = _array(root["identifiers"], "identifiers")
        identifiers = tuple(_identifier(value) for value in identifiers_raw)
        corporate_domain = _optional_domain(root["corporate_domain"])
        address = _optional_address(root["address"])
        language = _optional_string(root["original_language"], "original_language")
        administrators = (
            tuple(
                _required_text_pair(value, "administrator")
                for value in _array(root["administrators"], "administrators")
            )
            if schema_version == IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION
            else ()
        )
        incorporated_on = (
            _optional_date(root["incorporated_on"])
            if schema_version == IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION
            else None
        )
        result = cls(
            schema_version=schema_version,
            legal_name=legal_name,
            trade_name=trade_name,
            identifiers=identifiers,
            corporate_domain=corporate_domain,
            address=address,
            original_language=language,
            administrators=administrators,
            incorporated_on=incorporated_on,
        )
        if result.to_canonical_json() != serialized:
            raise InvalidIdentificationInputError(
                "Persisted identification input is not in canonical form."
            )
        return result

    @property
    def digest(self) -> str:
        """Return a SHA-256 digest of the canonical input representation."""

        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        summary = self.to_public_redacted()
        return (
            "IdentificationInput("
            f"schema_version={summary.schema_version}, "
            f"has_legal_name={summary.has_legal_name}, "
            f"has_trade_name={summary.has_trade_name}, "
            f"identifier_count={summary.identifier_count}, "
            f"has_corporate_domain={summary.has_corporate_domain}, "
            f"has_address={summary.has_address}, "
            f"has_original_language={summary.has_original_language}, "
            f", administrator_count={summary.administrator_count}, "
            f"has_incorporated_on={summary.has_incorporated_on})"
        )

    def _canonical_object(self) -> dict[str, object]:
        result: dict[str, object] = {
            "address": _address_object(self.address),
            "corporate_domain": _domain_object(self.corporate_domain),
            "identifiers": [_identifier_object(identifier) for identifier in self.identifiers],
            "legal_name": _text_pair_object(self.legal_name),
            "original_language": self.original_language,
            "schema_version": self.schema_version,
            "trade_name": _text_pair_object(self.trade_name),
        }
        if self.schema_version == IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION:
            result["administrators"] = [
                _text_pair_object(administrator) for administrator in self.administrators
            ]
            result["incorporated_on"] = (
                self.incorporated_on.isoformat() if self.incorporated_on is not None else None
            )
        return result


_ROOT_KEYS_V1 = frozenset(
    {
        "address",
        "corporate_domain",
        "identifiers",
        "legal_name",
        "original_language",
        "schema_version",
        "trade_name",
    }
)
_ROOT_KEYS_V2 = _ROOT_KEYS_V1 | {"administrators", "incorporated_on"}
_TEXT_PAIR_KEYS = frozenset({"normalized_value", "original_value"})
_IDENTIFIER_KEYS = frozenset(
    {"identifier_type", "jurisdiction_country_code", "normalized_value", "original_value"}
)
_ADDRESS_KEYS = frozenset(
    {
        "address_line_1",
        "address_line_2",
        "administrative_area",
        "country_code",
        "locality",
        "postal_code",
    }
)


def _bounded_text(
    value: str,
    *,
    field_name: str,
    maximum_length: int,
    preserve_outer_whitespace: bool = False,
) -> str:
    if not isinstance(value, str):
        raise InvalidIdentificationInputError(f"Identification {field_name} must be text.")
    if not value.strip():
        raise InvalidIdentificationInputError(f"Identification {field_name} cannot be empty.")
    if len(value) > maximum_length:
        raise InvalidIdentificationInputError(
            f"Identification {field_name} exceeds the maximum length."
        )
    if any(category(character) == "Cc" for character in value):
        raise InvalidIdentificationInputError(
            f"Identification {field_name} cannot contain control characters."
        )
    return value if preserve_outer_whitespace else value.strip()


def _text_pair_object(value: OriginalAndNormalizedText | None) -> object:
    if value is None:
        return None
    return {
        "normalized_value": value.normalized_value,
        "original_value": value.original_value,
    }


def _domain_object(value: CorporateDomainInput | None) -> object:
    if value is None:
        return None
    return {
        "normalized_value": value.normalized_value,
        "original_value": value.original_value,
    }


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


def _address_object(value: IdentificationAddressInput | None) -> object:
    if value is None:
        return None
    return {
        "address_line_1": _text_pair_object(value.address_line_1),
        "address_line_2": _text_pair_object(value.address_line_2),
        "administrative_area": _text_pair_object(value.administrative_area),
        "country_code": value.country_code.value,
        "locality": _text_pair_object(value.locality),
        "postal_code": _text_pair_object(value.postal_code),
    }


def _object(value: object, *, expected_keys: frozenset[str], field_name: str) -> dict[str, object]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise InvalidIdentificationInputError(f"Persisted {field_name} must be an object.")
    typed = cast(dict[str, object], value)
    if frozenset(typed) != expected_keys:
        raise InvalidIdentificationInputError(
            f"Persisted {field_name} contains unsupported fields."
        )
    return typed


def _array(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        raise InvalidIdentificationInputError(f"Persisted {field_name} must be an array.")
    return cast(list[object], value)


def _string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        raise InvalidIdentificationInputError(f"Persisted {field_name} must be text.")
    return value


def _optional_string(value: object, field_name: str) -> str | None:
    return None if value is None else _string(value, field_name)


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidIdentificationInputError(f"Persisted {field_name} must be an integer.")
    return value


def _optional_text_pair(value: object, field_name: str) -> OriginalAndNormalizedText | None:
    if value is None:
        return None
    typed = _object(value, expected_keys=_TEXT_PAIR_KEYS, field_name=field_name)
    return OriginalAndNormalizedText(
        original_value=_string(typed["original_value"], f"{field_name}.original_value"),
        normalized_value=_string(typed["normalized_value"], f"{field_name}.normalized_value"),
    )


def _required_text_pair(value: object, field_name: str) -> OriginalAndNormalizedText:
    result = _optional_text_pair(value, field_name)
    if result is None:
        raise InvalidIdentificationInputError(f"Persisted {field_name} cannot be null.")
    return result


def _optional_date(value: object) -> date | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidIdentificationInputError("Persisted incorporation date must be text.")
    try:
        result = date.fromisoformat(value)
    except ValueError as error:
        raise InvalidIdentificationInputError("Persisted incorporation date is invalid.") from error
    if result.isoformat() != value:
        raise InvalidIdentificationInputError("Persisted incorporation date is not canonical.")
    return result


def _optional_domain(value: object) -> CorporateDomainInput | None:
    if value is None:
        return None
    typed = _object(value, expected_keys=_TEXT_PAIR_KEYS, field_name="corporate_domain")
    return CorporateDomainInput(
        original_value=_string(typed["original_value"], "corporate_domain.original_value"),
        normalized_value=_string(typed["normalized_value"], "corporate_domain.normalized_value"),
    )


def _identifier(value: object) -> BusinessIdentifierInput:
    typed = _object(value, expected_keys=_IDENTIFIER_KEYS, field_name="identifier")
    jurisdiction = _optional_string(
        typed["jurisdiction_country_code"], "identifier.jurisdiction_country_code"
    )
    try:
        identifier_type = BusinessIdentifierType(
            _string(typed["identifier_type"], "identifier.identifier_type")
        )
        country = CountryCode(jurisdiction) if jurisdiction is not None else None
    except ValueError as error:
        raise InvalidIdentificationInputError("Persisted identifier type is invalid.") from error
    return BusinessIdentifierInput(
        identifier_type=identifier_type,
        original_value=_string(typed["original_value"], "identifier.original_value"),
        normalized_value=_string(typed["normalized_value"], "identifier.normalized_value"),
        jurisdiction_country_code=country,
    )


def _optional_address(value: object) -> IdentificationAddressInput | None:
    if value is None:
        return None
    typed = _object(value, expected_keys=_ADDRESS_KEYS, field_name="address")
    country_value = _string(typed["country_code"], "address.country_code")
    return IdentificationAddressInput(
        country_code=CountryCode(country_value),
        address_line_1=_optional_text_pair(typed["address_line_1"], "address.address_line_1"),
        address_line_2=_optional_text_pair(typed["address_line_2"], "address.address_line_2"),
        locality=_optional_text_pair(typed["locality"], "address.locality"),
        administrative_area=_optional_text_pair(
            typed["administrative_area"], "address.administrative_area"
        ),
        postal_code=_optional_text_pair(typed["postal_code"], "address.postal_code"),
    )


__all__ = [
    "IDENTIFICATION_INPUT_EXTENDED_SCHEMA_VERSION",
    "IDENTIFICATION_INPUT_SCHEMA_VERSION",
    "MAX_INPUT_ADMINISTRATORS",
    "SUPPORTED_IDENTIFICATION_INPUT_SCHEMA_VERSIONS",
    "BusinessIdentifierInput",
    "BusinessIdentifierType",
    "CorporateDomainInput",
    "IdentificationAddressInput",
    "IdentificationInput",
    "OriginalAndNormalizedText",
    "RedactedIdentificationInput",
]
