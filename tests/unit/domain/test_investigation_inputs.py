"""Tests for the immutable, versioned identification input contract."""

import json
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from intelligence.domain.errors import InvalidIdentificationInputError
from intelligence.domain.geography import CountryCode
from intelligence.domain.investigation_inputs import (
    IDENTIFICATION_INPUT_SCHEMA_VERSION,
    BusinessIdentifierInput,
    BusinessIdentifierType,
    CorporateDomainInput,
    IdentificationAddressInput,
    IdentificationInput,
    OriginalAndNormalizedText,
)


def _text(original: str, normalized: str) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(
        original_value=original,
        normalized_value=normalized,
    )


def _complete_input() -> IdentificationInput:
    return IdentificationInput(
        legal_name=_text("Fábrica Global S.A.", "fabrica global sa"),
        trade_name=_text("Fábrica", "fabrica"),
        identifiers=(
            BusinessIdentifierInput(
                identifier_type=BusinessIdentifierType.TAX_IDENTIFIER,
                original_value="12.345.678/0001-90",
                normalized_value="12345678000190",
                jurisdiction_country_code=CountryCode("BR"),
            ),
            BusinessIdentifierInput(
                identifier_type=BusinessIdentifierType.LEI,
                original_value="529900T8BM49AURSDO55",
                normalized_value="529900T8BM49AURSDO55",
            ),
        ),
        corporate_domain=CorporateDomainInput(
            original_value="Fabrica.Example",
            normalized_value="fabrica.example",
        ),
        address=IdentificationAddressInput(
            country_code=CountryCode("BR"),
            address_line_1=_text("Rua Exemplo, 10", "rua exemplo 10"),
            locality=_text("São Paulo", "sao paulo"),
            administrative_area=_text("SP", "sp"),
            postal_code=_text("01000-000", "01000000"),
        ),
        original_language="pt-BR",
    )


def test_complete_input_is_immutable_redacted_and_versioned() -> None:
    identification_input = _complete_input()

    assert identification_input.schema_version == IDENTIFICATION_INPUT_SCHEMA_VERSION == 1
    assert identification_input.has_usable_signal
    assert identification_input.to_public_redacted().identifier_count == 2
    representation = repr(identification_input)
    for sensitive in ("Fábrica", "529900", "Rua Exemplo", "fabrica.example"):
        assert sensitive not in representation
    with pytest.raises(FrozenInstanceError):
        identification_input.original_language = "en"  # type: ignore[misc]


def test_canonical_serialization_is_deterministic_and_round_trips() -> None:
    identification_input = _complete_input()

    serialized = identification_input.to_canonical_json()
    restored = IdentificationInput.from_canonical_json(serialized)

    assert restored == identification_input
    assert restored.to_canonical_json() == serialized
    assert restored.digest == identification_input.digest


def test_original_text_is_preserved_separately_from_normalized_text() -> None:
    text = _text("  Fábrica Global S.A.  ", "fabrica global sa")
    identification_input = IdentificationInput(legal_name=text)

    restored = IdentificationInput.from_canonical_json(identification_input.to_canonical_json())

    assert text.original_value == "  Fábrica Global S.A.  "
    assert text.normalized_value == "fabrica global sa"
    assert restored.legal_name == text


def test_reconstitution_rejects_noncanonical_or_unknown_schema() -> None:
    canonical = _complete_input().to_canonical_json()

    with pytest.raises(InvalidIdentificationInputError, match="canonical"):
        IdentificationInput.from_canonical_json(canonical.replace(":", ": ", 1))
    with pytest.raises(InvalidIdentificationInputError, match="unsupported fields"):
        IdentificationInput.from_canonical_json(canonical[:-1] + ',"document":"forbidden"}')
    with pytest.raises(InvalidIdentificationInputError, match="version"):
        IdentificationInput(schema_version=2)
    with pytest.raises(InvalidIdentificationInputError, match="version"):
        IdentificationInput(schema_version=True)


@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (lambda: _text(" ", "valid"), "cannot be empty"),
        (lambda: _text("valid", "\n"), "cannot be empty"),
        (
            lambda: CorporateDomainInput(
                original_value="https://example.test/path",
                normalized_value="https://example.test/path",
            ),
            "canonical lowercase host",
        ),
        (
            lambda: IdentificationAddressInput(country_code=CountryCode("BR")),
            "requires at least one",
        ),
        (
            lambda: BusinessIdentifierInput(
                identifier_type=BusinessIdentifierType.TAX_IDENTIFIER,
                original_value="123",
                normalized_value="123",
            ),
            "requires a jurisdiction",
        ),
    ],
)
def test_invalid_empty_domain_address_and_identifier_values_are_rejected(
    factory: object,
    expected: str,
) -> None:
    callable_factory = factory
    assert callable(callable_factory)
    with pytest.raises(InvalidIdentificationInputError, match=expected):
        callable_factory()


def test_empty_input_requires_confirmed_company_and_countries_must_match() -> None:
    empty = IdentificationInput()
    with pytest.raises(InvalidIdentificationInputError, match="usable signal"):
        empty.validate_for(
            investigation_country_code=CountryCode("BR"),
            has_confirmed_company=False,
        )
    empty.validate_for(
        investigation_country_code=CountryCode("BR"),
        has_confirmed_company=True,
    )

    wrong_country = IdentificationInput(
        address=IdentificationAddressInput(
            country_code=CountryCode("US"),
            locality=_text("Austin", "austin"),
        )
    )
    with pytest.raises(InvalidIdentificationInputError, match="must match"):
        wrong_country.validate_for(
            investigation_country_code=CountryCode("BR"),
            has_confirmed_company=False,
        )


def test_input_repr_never_exposes_identifier_values() -> None:
    identifier = BusinessIdentifierInput(
        identifier_type=BusinessIdentifierType.LEI,
        original_value="SENSITIVE-ORIGINAL",
        normalized_value="SENSITIVE-NORMALIZED",
    )
    identification_input = IdentificationInput(identifiers=(identifier,))

    assert "SENSITIVE" not in repr(identifier)
    assert "SENSITIVE" not in repr(identification_input)


def test_public_component_reprs_are_redacted() -> None:
    text = _text("Sensitive", "sensitive")
    domain = CorporateDomainInput(
        original_value="Sensitive.Example",
        normalized_value="sensitive.example",
    )
    address = IdentificationAddressInput(
        country_code=CountryCode("BR"),
        locality=text,
    )

    assert "Sensitive" not in repr(text)
    assert "Sensitive" not in repr(domain)
    assert "Sensitive" not in repr(address)


def test_typed_boundaries_reject_mistyped_components() -> None:
    with pytest.raises(InvalidIdentificationInputError, match="type"):
        BusinessIdentifierInput(
            identifier_type=cast(BusinessIdentifierType, "TAX"),
            original_value="123",
            normalized_value="123",
        )
    with pytest.raises(InvalidIdentificationInputError, match="CountryCode"):
        BusinessIdentifierInput(
            identifier_type=BusinessIdentifierType.LEI,
            original_value="123",
            normalized_value="123",
            jurisdiction_country_code=cast(CountryCode, "BR"),
        )
    with pytest.raises(InvalidIdentificationInputError, match="inconsistent"):
        CorporateDomainInput(
            original_value="different.example",
            normalized_value="expected.example",
        )
    with pytest.raises(InvalidIdentificationInputError, match="CountryCode"):
        IdentificationAddressInput(
            country_code=cast(CountryCode, "BR"),
            locality=_text("City", "city"),
        )
    with pytest.raises(InvalidIdentificationInputError, match="components"):
        IdentificationAddressInput(
            country_code=CountryCode("BR"),
            locality=cast(OriginalAndNormalizedText, "City"),
        )

    invalid_inputs: tuple[dict[str, object], ...] = (
        {"legal_name": "name"},
        {"trade_name": "name"},
        {"identifiers": []},
        {"identifiers": ("identifier",)},
        {"corporate_domain": "example.test"},
        {"address": "city"},
    )
    for values in invalid_inputs:
        with pytest.raises(InvalidIdentificationInputError):
            IdentificationInput(**values)  # type: ignore[arg-type]


def test_text_language_and_validation_boundaries_are_bounded_and_typed() -> None:
    with pytest.raises(InvalidIdentificationInputError, match="must be text"):
        OriginalAndNormalizedText(
            original_value=cast(str, 123),
            normalized_value="valid",
        )
    with pytest.raises(InvalidIdentificationInputError, match="maximum length"):
        _text("x" * 513, "valid")
    with pytest.raises(InvalidIdentificationInputError, match="control"):
        _text("bad\x00value", "valid")
    with pytest.raises(InvalidIdentificationInputError, match="language tag"):
        IdentificationInput(original_language="pt_BR")

    empty = IdentificationInput()
    with pytest.raises(InvalidIdentificationInputError, match="Investigation country"):
        empty.validate_for(
            investigation_country_code=cast(CountryCode, "BR"),
            has_confirmed_company=True,
        )
    with pytest.raises(InvalidIdentificationInputError, match="boolean"):
        empty.validate_for(
            investigation_country_code=CountryCode("BR"),
            has_confirmed_company=cast(bool, 1),
        )


def _canonical(raw: object) -> str:
    return json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@pytest.mark.parametrize(
    "serialized",
    [
        "{",
        _canonical([]),
        _canonical(
            {
                "address": None,
                "corporate_domain": None,
                "identifiers": {},
                "legal_name": None,
                "original_language": None,
                "schema_version": 1,
                "trade_name": None,
            }
        ),
        _canonical(
            {
                "address": None,
                "corporate_domain": None,
                "identifiers": [],
                "legal_name": None,
                "original_language": 1,
                "schema_version": 1,
                "trade_name": None,
            }
        ),
        _canonical(
            {
                "address": None,
                "corporate_domain": None,
                "identifiers": [],
                "legal_name": None,
                "original_language": None,
                "schema_version": True,
                "trade_name": None,
            }
        ),
    ],
)
def test_persisted_input_rejects_invalid_json_shapes(serialized: str) -> None:
    with pytest.raises(InvalidIdentificationInputError):
        IdentificationInput.from_canonical_json(serialized)


def test_persisted_input_rejects_invalid_identifier_vocabulary() -> None:
    raw = json.loads(_complete_input().to_canonical_json())
    raw["identifiers"][0]["identifier_type"] = "UNKNOWN"

    with pytest.raises(InvalidIdentificationInputError, match="identifier type"):
        IdentificationInput.from_canonical_json(_canonical(raw))

    with pytest.raises(InvalidIdentificationInputError, match="JSON text"):
        IdentificationInput.from_canonical_json(cast(str, 123))
