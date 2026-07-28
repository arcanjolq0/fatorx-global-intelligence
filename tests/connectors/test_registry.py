"""Tests for deterministic explicit connector registration and selection."""

from typing import cast

import pytest

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorMode,
    ConnectorOperation,
)
from intelligence.connectors.errors import (
    ConnectorNotFoundError,
    DuplicateConnectorError,
    IncompatibleConnectorProtocolError,
    InvalidConnectorDescriptorError,
    UnsupportedContractVersionError,
)
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CandidateRef, CompanyQuery
from intelligence.connectors.registry import ConnectorRegistry
from intelligence.connectors.versions import CONNECTOR_CONTRACT_VERSION, SemanticVersion
from intelligence.domain.geography import CountryCode


class DeclaredConnector:
    def __init__(self, descriptor: ConnectorDescriptor) -> None:
        self.descriptor = descriptor
        self.describe_calls = 0
        self.operation_calls = 0

    def describe(self) -> ConnectorDescriptor:
        self.describe_calls += 1
        return self.descriptor

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        del query, context
        self.operation_calls += 1
        raise AssertionError("Registry selection must not execute search")

    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        del candidate_ref, context
        self.operation_calls += 1
        raise AssertionError("Registry selection must not execute fetch_details")

    async def fetch_document(
        self,
        document_ref: ArtifactReference,
        context: ConnectorContext,
    ) -> ConnectorOutcome[ArtifactPayload]:
        del document_ref, context
        self.operation_calls += 1
        raise AssertionError("Registry selection must not execute fetch_document")


class IncompleteConnector:
    def describe(self) -> ConnectorDescriptor:
        raise AssertionError("Incomplete object must be rejected before describe")


class InvalidDescriptorConnector(DeclaredConnector):
    def describe(self) -> ConnectorDescriptor:
        self.describe_calls += 1
        return cast(ConnectorDescriptor, "invalid")


class SynchronousOperationConnector(DeclaredConnector):
    def search(  # type: ignore[override]
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        del query, context
        raise AssertionError("Synchronous operation must be rejected before execution")


def descriptor(
    connector_id: str,
    *,
    contract_version: SemanticVersion = CONNECTOR_CONTRACT_VERSION,
    coverage_kind: ConnectorCoverageKind = ConnectorCoverageKind.COUNTRY_SET,
    countries: tuple[CountryCode, ...] = (CountryCode("BR"),),
    capabilities: tuple[ConnectorCapability, ...] = (ConnectorCapability.COMPANY_REGISTRY,),
    operations: tuple[ConnectorOperation, ...] = (ConnectorOperation.SEARCH,),
    supports_test_mode: bool = True,
) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        connector_id=ConnectorId(connector_id),
        version=SemanticVersion(1, 0, 0),
        contract_version=contract_version,
        source_id=SourceId(f"source.{connector_id}"),
        coverage_kind=coverage_kind,
        countries=countries,
        capabilities=capabilities,
        operations=operations,
        access_type=ConnectorAccessType.FILE,
        supports_test_mode=supports_test_mode,
    )


def test_register_get_and_list_are_explicit_and_stably_sorted() -> None:
    registry = ConnectorRegistry()
    second = DeclaredConnector(descriptor("registry.zeta"))
    first = DeclaredConnector(descriptor("registry.alpha"))

    registry.register(second)
    registry.register(first)

    assert registry.get(ConnectorId("registry.alpha")) is first
    assert registry.list_all() == (first, second)
    assert first.describe_calls == 1
    assert second.describe_calls == 1


def test_registry_rejects_duplicate_unknown_or_incompatible_connector() -> None:
    registry = ConnectorRegistry()
    first = DeclaredConnector(descriptor("registry.alpha"))
    registry.register(first)

    with pytest.raises(DuplicateConnectorError):
        registry.register(DeclaredConnector(descriptor("registry.alpha")))
    with pytest.raises(ConnectorNotFoundError):
        registry.get(ConnectorId("registry.missing"))
    with pytest.raises(ConnectorNotFoundError):
        registry.get(cast(ConnectorId, "registry.alpha"))
    with pytest.raises(IncompatibleConnectorProtocolError):
        registry.register(cast(DeclaredConnector, IncompleteConnector()))
    with pytest.raises(IncompatibleConnectorProtocolError):
        registry.register(
            cast(Connector, SynchronousOperationConnector(descriptor("registry.sync")))
        )


def test_registry_rejects_unknown_contract_major_and_invalid_descriptor() -> None:
    registry = ConnectorRegistry()
    with pytest.raises(UnsupportedContractVersionError):
        registry.register(
            DeclaredConnector(
                descriptor("registry.future", contract_version=SemanticVersion(2, 0, 0))
            )
        )
    with pytest.raises(InvalidConnectorDescriptorError):
        registry.register(InvalidDescriptorConnector(descriptor("registry.invalid")))


@pytest.mark.parametrize("majors", [(), (-1,), (True,)])
def test_registry_requires_explicit_valid_supported_majors(majors: tuple[int, ...]) -> None:
    with pytest.raises(UnsupportedContractVersionError):
        ConnectorRegistry(supported_contract_majors=majors)


def test_select_filters_country_capability_operation_and_mode_without_calls() -> None:
    registry = ConnectorRegistry()
    country = DeclaredConnector(descriptor("registry.country"))
    global_connector = DeclaredConnector(
        descriptor(
            "registry.global",
            coverage_kind=ConnectorCoverageKind.GLOBAL,
            countries=(),
            capabilities=(ConnectorCapability.COMPANY_REGISTRY, ConnectorCapability.DOCUMENTS),
            operations=(ConnectorOperation.SEARCH, ConnectorOperation.FETCH_DOCUMENT),
            supports_test_mode=False,
        )
    )
    registry.register(global_connector)
    registry.register(country)

    selected = registry.select(
        country=CountryCode("BR"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.PRODUCTION,
    )
    test_selected = registry.select(
        country=CountryCode("BR"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.TEST,
    )
    unsupported_country = registry.select(
        country=CountryCode("US"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.TEST,
    )
    unsupported_capability = registry.select(
        country=CountryCode("BR"),
        capability=ConnectorCapability.OWNERSHIP,
        operation=ConnectorOperation.SEARCH,
        mode=ConnectorMode.PRODUCTION,
    )
    unsupported_operation = registry.select(
        country=CountryCode("BR"),
        capability=ConnectorCapability.COMPANY_REGISTRY,
        operation=ConnectorOperation.FETCH_DETAILS,
        mode=ConnectorMode.PRODUCTION,
    )

    assert selected == (country, global_connector)
    assert test_selected == (country,)
    assert unsupported_country == ()
    assert unsupported_capability == ()
    assert unsupported_operation == ()
    assert country.operation_calls == 0
    assert global_connector.operation_calls == 0
    assert country.describe_calls == 1
    assert global_connector.describe_calls == 1
