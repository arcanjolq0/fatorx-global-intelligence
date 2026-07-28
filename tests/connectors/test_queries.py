"""Tests for neutral company queries and opaque candidate references."""

from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from intelligence.connectors.errors import InvalidCompanyQueryError
from intelligence.connectors.identifiers import CandidateRefId, ConnectorId
from intelligence.connectors.queries import (
    BusinessIdentifier,
    BusinessIdentifierType,
    CandidateRef,
    CandidateSnapshot,
    CompanyQuery,
    DomainName,
    SearchAddress,
)
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CompanyId


def identifier() -> BusinessIdentifier:
    return BusinessIdentifier(
        BusinessIdentifierType("TAX_ID"),
        original_value=" 12.345 ",
        normalized_value="12345",
    )


def candidate() -> CandidateRef:
    return CandidateRef(
        candidate_ref_id=CandidateRefId.new(),
        connector_id=ConnectorId("registry.alpha"),
        snapshot=CandidateSnapshot("Registry Alpha — record hint"),
        country=CountryCode("BR"),
        display_name="Example Comércio Ltda.",
        primary_identifier=identifier(),
        domain=DomainName("Example.COM"),
    )


def test_company_query_preserves_typed_structured_signals() -> None:
    address = SearchAddress(
        country=CountryCode("BR"),
        lines=("Avenida Exemplo, 10",),
        locality="São Paulo",
        administrative_area="SP",
        postal_code="01000-000",
    )
    query = CompanyQuery(
        country=CountryCode("br"),
        original_name=" Example Comércio Ltda. ",
        normalized_name="example comercio ltda",
        identifiers=(identifier(),),
        domain=DomainName("Example.COM"),
        address=address,
    )

    assert query.country == CountryCode("BR")
    assert query.original_name == "Example Comércio Ltda."
    assert query.domain == DomainName("example.com")
    assert query.identifiers[0].normalized_value == "12345"
    with pytest.raises(FrozenInstanceError):
        query.original_name = "Changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "example.com/record",
        "https://example.com",
        "user@example.com",
        "example.com:443",
        "example.com?x=1",
        "example..com",
        "-example.com",
    ],
)
def test_domain_name_rejects_url_parts_and_invalid_hosts(value: str) -> None:
    with pytest.raises(InvalidCompanyQueryError):
        DomainName(value)


@pytest.mark.parametrize("value", ["", "tax id", "tax:id", "a", "TAX/ID"])
def test_business_identifier_type_rejects_noncanonical_code(value: str) -> None:
    with pytest.raises(InvalidCompanyQueryError):
        BusinessIdentifierType(value)


def test_business_identifier_rejects_empty_values_and_wrong_type() -> None:
    with pytest.raises(InvalidCompanyQueryError):
        BusinessIdentifier(
            cast(BusinessIdentifierType, "TAX_ID"),
            original_value="123",
            normalized_value="123",
        )
    with pytest.raises(InvalidCompanyQueryError):
        BusinessIdentifier(
            BusinessIdentifierType("TAX_ID"),
            original_value=" ",
            normalized_value="123",
        )


def test_search_address_requires_components_and_query_country_match() -> None:
    with pytest.raises(InvalidCompanyQueryError):
        SearchAddress(country=CountryCode("BR"))

    address = SearchAddress(country=CountryCode("US"), locality="Austin")
    with pytest.raises(InvalidCompanyQueryError):
        CompanyQuery(
            country=CountryCode("BR"),
            original_name="Example",
            normalized_name="example",
            address=address,
        )


@pytest.mark.parametrize("field", ["original_name", "normalized_name"])
def test_company_query_rejects_empty_names(field: str) -> None:
    values = {"original_name": "Example", "normalized_name": "example"}
    values[field] = " "
    with pytest.raises(InvalidCompanyQueryError):
        CompanyQuery(
            country=CountryCode("BR"),
            original_name=values["original_name"],
            normalized_name=values["normalized_name"],
        )


def test_company_query_rejects_untyped_identifier_domain_and_address() -> None:
    with pytest.raises(InvalidCompanyQueryError):
        CompanyQuery(
            country=CountryCode("BR"),
            original_name="Example",
            normalized_name="example",
            identifiers=cast(tuple[BusinessIdentifier, ...], ("123",)),
        )
    with pytest.raises(InvalidCompanyQueryError):
        CompanyQuery(
            country=CountryCode("BR"),
            original_name="Example",
            normalized_name="example",
            domain=cast(DomainName, "example.com"),
        )


def test_candidate_is_connector_scoped_and_not_a_company_id() -> None:
    value = candidate()

    assert isinstance(value.candidate_ref_id, CandidateRefId)
    assert not isinstance(cast(object, value.candidate_ref_id), CompanyId)
    assert value.connector_id == ConnectorId("registry.alpha")
    assert len(value.snapshot.summary) <= 512


def test_candidate_snapshot_and_reference_reject_invalid_values() -> None:
    with pytest.raises(InvalidCompanyQueryError):
        CandidateSnapshot("x" * 513)
    with pytest.raises(InvalidCompanyQueryError):
        CandidateRef(
            candidate_ref_id=CandidateRefId.new(),
            connector_id=ConnectorId("registry.alpha"),
            snapshot=CandidateSnapshot("hint"),
            country=CountryCode("BR"),
            display_name=" ",
        )
    with pytest.raises(InvalidCompanyQueryError):
        CandidateRef(
            candidate_ref_id=cast(CandidateRefId, CompanyId.new()),
            connector_id=ConnectorId("registry.alpha"),
            snapshot=CandidateSnapshot("hint"),
            country=CountryCode("BR"),
            display_name="Example",
        )
