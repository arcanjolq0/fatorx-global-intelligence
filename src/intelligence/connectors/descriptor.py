"""Immutable connector descriptors with explicit coverage semantics."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorMode,
    ConnectorOperation,
)
from intelligence.connectors.errors import InvalidConnectorDescriptorError
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import SemanticVersion
from intelligence.domain.geography import CountryCode

_CREDENTIAL_REFERENCE_PATTERN = re.compile(r"[A-Z][A-Z0-9_]*", flags=re.ASCII)


@dataclass(frozen=True, slots=True, kw_only=True, init=False)
class ConnectorDescriptor:
    """Validated declaration of one connector's implemented surface."""

    connector_id: ConnectorId
    version: SemanticVersion
    contract_version: SemanticVersion
    source_id: SourceId
    coverage_kind: ConnectorCoverageKind
    countries: frozenset[CountryCode]
    capabilities: frozenset[ConnectorCapability]
    operations: frozenset[ConnectorOperation]
    access_type: ConnectorAccessType
    credential_ref_name: str | None
    supports_test_mode: bool
    max_page_size: int | None

    def __init__(
        self,
        *,
        connector_id: ConnectorId,
        version: SemanticVersion,
        contract_version: SemanticVersion,
        source_id: SourceId,
        coverage_kind: ConnectorCoverageKind,
        countries: Iterable[CountryCode],
        capabilities: Iterable[ConnectorCapability],
        operations: Iterable[ConnectorOperation],
        access_type: ConnectorAccessType,
        credential_ref_name: str | None = None,
        supports_test_mode: bool = False,
        max_page_size: int | None = None,
    ) -> None:
        object.__setattr__(self, "connector_id", connector_id)
        object.__setattr__(self, "version", version)
        object.__setattr__(self, "contract_version", contract_version)
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "coverage_kind", coverage_kind)
        object.__setattr__(self, "countries", frozenset(countries))
        object.__setattr__(self, "capabilities", frozenset(capabilities))
        object.__setattr__(self, "operations", frozenset(operations))
        object.__setattr__(self, "access_type", access_type)
        object.__setattr__(self, "credential_ref_name", credential_ref_name)
        object.__setattr__(self, "supports_test_mode", supports_test_mode)
        object.__setattr__(self, "max_page_size", max_page_size)
        validate_connector_descriptor(self)

    def supports(
        self,
        *,
        country: CountryCode,
        capability: ConnectorCapability,
        operation: ConnectorOperation,
        mode: ConnectorMode,
    ) -> bool:
        """Check the declared matrix without invoking connector code."""

        country_supported = (
            self.coverage_kind is ConnectorCoverageKind.GLOBAL or country in self.countries
        )
        mode_supported = mode is ConnectorMode.PRODUCTION or self.supports_test_mode
        return (
            country_supported
            and capability in self.capabilities
            and operation in self.operations
            and mode_supported
        )


def validate_connector_descriptor(descriptor: ConnectorDescriptor) -> None:
    """Recheck a descriptor at registry admission, including runtime types."""

    if not isinstance(descriptor, ConnectorDescriptor):
        raise InvalidConnectorDescriptorError(
            "Connector describe() must return a ConnectorDescriptor."
        )
    expected_types = (
        (descriptor.connector_id, ConnectorId, "connector_id"),
        (descriptor.version, SemanticVersion, "version"),
        (descriptor.contract_version, SemanticVersion, "contract_version"),
        (descriptor.source_id, SourceId, "source_id"),
        (descriptor.coverage_kind, ConnectorCoverageKind, "coverage_kind"),
        (descriptor.access_type, ConnectorAccessType, "access_type"),
    )
    for value, expected_type, field_name in expected_types:
        if not isinstance(value, expected_type):
            raise InvalidConnectorDescriptorError(
                f"ConnectorDescriptor {field_name} has an invalid type."
            )
    if not isinstance(descriptor.countries, frozenset) or any(
        not isinstance(country, CountryCode) for country in descriptor.countries
    ):
        raise InvalidConnectorDescriptorError(
            "ConnectorDescriptor countries must contain only CountryCode values."
        )
    if descriptor.coverage_kind is ConnectorCoverageKind.GLOBAL and descriptor.countries:
        raise InvalidConnectorDescriptorError(
            "Global connector coverage cannot also declare countries."
        )
    if descriptor.coverage_kind is ConnectorCoverageKind.COUNTRY_SET and not descriptor.countries:
        raise InvalidConnectorDescriptorError(
            "Country-set connector coverage requires at least one country."
        )
    if (
        not isinstance(descriptor.capabilities, frozenset)
        or not descriptor.capabilities
        or any(
            not isinstance(capability, ConnectorCapability)
            for capability in descriptor.capabilities
        )
    ):
        raise InvalidConnectorDescriptorError(
            "ConnectorDescriptor capabilities must be a non-empty closed set."
        )
    if (
        not isinstance(descriptor.operations, frozenset)
        or not descriptor.operations
        or any(not isinstance(operation, ConnectorOperation) for operation in descriptor.operations)
    ):
        raise InvalidConnectorDescriptorError(
            "ConnectorDescriptor operations must be a non-empty closed set."
        )
    if (
        ConnectorOperation.FETCH_DOCUMENT in descriptor.operations
        and ConnectorCapability.DOCUMENTS not in descriptor.capabilities
    ):
        raise InvalidConnectorDescriptorError("FETCH_DOCUMENT requires the DOCUMENTS capability.")
    if descriptor.credential_ref_name is not None and (
        not isinstance(descriptor.credential_ref_name, str)
        or len(descriptor.credential_ref_name) > 64
        or _CREDENTIAL_REFERENCE_PATTERN.fullmatch(descriptor.credential_ref_name) is None
    ):
        raise InvalidConnectorDescriptorError(
            "Credential reference must be a canonical non-secret configuration name."
        )
    if not isinstance(descriptor.supports_test_mode, bool):
        raise InvalidConnectorDescriptorError(
            "ConnectorDescriptor supports_test_mode must be boolean."
        )
    if descriptor.max_page_size is not None and (
        isinstance(descriptor.max_page_size, bool)
        or not isinstance(descriptor.max_page_size, int)
        or descriptor.max_page_size <= 0
    ):
        raise InvalidConnectorDescriptorError(
            "ConnectorDescriptor max_page_size must be a positive integer."
        )


__all__ = ["ConnectorDescriptor", "validate_connector_descriptor"]
