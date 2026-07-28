"""Tests for connector descriptor invariants and explicit coverage."""

from collections.abc import Iterable
from dataclasses import FrozenInstanceError
from typing import cast

import pytest

from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorMode,
    ConnectorOperation,
)
from intelligence.connectors.errors import InvalidConnectorDescriptorError
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import CONNECTOR_CONTRACT_VERSION, SemanticVersion
from intelligence.domain.geography import CountryCode


def descriptor(
    *,
    coverage_kind: ConnectorCoverageKind = ConnectorCoverageKind.COUNTRY_SET,
    countries: Iterable[CountryCode] = (CountryCode("BR"),),
    capabilities: Iterable[ConnectorCapability] = (ConnectorCapability.COMPANY_REGISTRY,),
    operations: Iterable[ConnectorOperation] = (ConnectorOperation.SEARCH,),
    credential_ref_name: str | None = None,
    supports_test_mode: bool = True,
    max_page_size: int | None = 50,
) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        connector_id=ConnectorId("registry.alpha"),
        version=SemanticVersion(1, 2, 0),
        contract_version=CONNECTOR_CONTRACT_VERSION,
        source_id=SourceId("source.alpha"),
        coverage_kind=coverage_kind,
        countries=countries,
        capabilities=capabilities,
        operations=operations,
        access_type=ConnectorAccessType.FILE,
        credential_ref_name=credential_ref_name,
        supports_test_mode=supports_test_mode,
        max_page_size=max_page_size,
    )


def test_country_descriptor_converts_collections_and_supports_declared_matrix() -> None:
    value = descriptor(
        countries=[CountryCode("br")],
        capabilities=[ConnectorCapability.COMPANY_REGISTRY],
        operations=[ConnectorOperation.SEARCH],
        credential_ref_name="REGISTRY_CREDENTIAL_REF",
    )

    assert value.countries == frozenset({CountryCode("BR")})
    assert isinstance(value.capabilities, frozenset)
    assert value.supports(
        country=CountryCode("BR"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.TEST,
    )
    assert not value.supports(
        country=CountryCode("US"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.TEST,
    )
    with pytest.raises(FrozenInstanceError):
        value.max_page_size = 10  # type: ignore[misc]


def test_global_descriptor_has_explicit_empty_country_set() -> None:
    value = descriptor(
        coverage_kind=ConnectorCoverageKind.GLOBAL,
        countries=(),
        supports_test_mode=False,
    )

    assert value.supports(
        country=CountryCode("DE"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.PRODUCTION,
    )
    assert not value.supports(
        country=CountryCode("DE"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.TEST,
    )
    assert not value.supports(
        country=CountryCode("DE"),
        capability=ConnectorCapability.OWNERSHIP,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.PRODUCTION,
    )
    assert not value.supports(
        country=CountryCode("DE"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.FETCH_DETAILS,
        mode=ConnectorMode.PRODUCTION,
    )


@pytest.mark.parametrize(
    ("coverage_kind", "countries"),
    [
        (ConnectorCoverageKind.GLOBAL, (CountryCode("BR"),)),
        (ConnectorCoverageKind.COUNTRY_SET, ()),
    ],
)
def test_descriptor_rejects_contradictory_coverage(
    coverage_kind: ConnectorCoverageKind,
    countries: tuple[CountryCode, ...],
) -> None:
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(coverage_kind=coverage_kind, countries=countries)


@pytest.mark.parametrize(
    ("capabilities", "operations"),
    [
        ((), (ConnectorOperation.SEARCH,)),
        ((ConnectorCapability.COMPANY_REGISTRY,), ()),
        (
            (ConnectorCapability.COMPANY_REGISTRY,),
            (ConnectorOperation.FETCH_DOCUMENT,),
        ),
    ],
)
def test_descriptor_rejects_empty_or_inconsistent_declared_surface(
    capabilities: tuple[ConnectorCapability, ...],
    operations: tuple[ConnectorOperation, ...],
) -> None:
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(capabilities=capabilities, operations=operations)


def test_fetch_document_requires_and_accepts_documents_capability() -> None:
    value = descriptor(
        capabilities=(ConnectorCapability.DOCUMENTS,),
        operations=(ConnectorOperation.FETCH_DOCUMENT,),
    )

    assert ConnectorOperation.FETCH_DOCUMENT in value.operations


@pytest.mark.parametrize("page_size", [0, -1, True])
def test_descriptor_rejects_invalid_page_size(page_size: int) -> None:
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(max_page_size=page_size)


@pytest.mark.parametrize("reference", ["", "credential-ref", "A=B", "a", "A" * 65])
def test_descriptor_rejects_unsafe_credential_reference_name(reference: str) -> None:
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(credential_ref_name=reference)


def test_descriptor_rejects_invalid_runtime_collection_members() -> None:
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(countries=cast(Iterable[CountryCode], ["BR"]))
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(capabilities=cast(Iterable[ConnectorCapability], ["COMPANY_REGISTRY"]))
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(operations=cast(Iterable[ConnectorOperation], ["SEARCH"]))


def test_descriptor_rejects_invalid_runtime_scalar_types() -> None:
    with pytest.raises(InvalidConnectorDescriptorError):
        ConnectorDescriptor(
            connector_id=cast(ConnectorId, "registry.alpha"),
            version=SemanticVersion(1, 0, 0),
            contract_version=CONNECTOR_CONTRACT_VERSION,
            source_id=SourceId("source.alpha"),
            coverage_kind=ConnectorCoverageKind.GLOBAL,
            countries=(),
            capabilities=(ConnectorCapability.COMPANY_REGISTRY,),
            operations=(ConnectorOperation.SEARCH,),
            access_type=ConnectorAccessType.API,
        )
    with pytest.raises(InvalidConnectorDescriptorError):
        descriptor(supports_test_mode=cast(bool, 1))
