"""Explicit deterministic connector registry without discovery or external I/O."""

from collections.abc import Iterable
from dataclasses import dataclass
from inspect import iscoroutinefunction

from intelligence.connectors.descriptor import (
    ConnectorDescriptor,
    validate_connector_descriptor,
)
from intelligence.connectors.enums import (
    ConnectorCapability,
    ConnectorMode,
    ConnectorOperation,
)
from intelligence.connectors.errors import (
    ConnectorNotFoundError,
    DuplicateConnectorError,
    IncompatibleConnectorProtocolError,
    UnsupportedContractVersionError,
)
from intelligence.connectors.identifiers import ConnectorId
from intelligence.connectors.protocol import Connector
from intelligence.connectors.versions import SUPPORTED_CONTRACT_MAJORS
from intelligence.domain.geography import CountryCode


@dataclass(frozen=True, slots=True)
class _RegisteredConnector:
    connector: Connector
    descriptor: ConnectorDescriptor


class ConnectorRegistry:
    """Instance-scoped registry that stores descriptors captured at admission."""

    def __init__(
        self,
        *,
        supported_contract_majors: Iterable[int] = SUPPORTED_CONTRACT_MAJORS,
    ) -> None:
        majors = frozenset(supported_contract_majors)
        if not majors or any(
            isinstance(major, bool) or not isinstance(major, int) or major < 0 for major in majors
        ):
            raise UnsupportedContractVersionError(
                "Registry supported contract majors must be non-negative integers."
            )
        self._supported_contract_majors = majors
        self._entries: dict[ConnectorId, _RegisteredConnector] = {}

    def register(self, connector: Connector) -> None:
        """Validate and register an explicitly supplied connector object."""

        if not isinstance(connector, Connector):
            raise IncompatibleConnectorProtocolError(
                "Connector object does not expose the required protocol surface."
            )
        if any(
            not iscoroutinefunction(getattr(connector, operation_name))
            for operation_name in ("search", "fetch_details", "fetch_document")
        ):
            raise IncompatibleConnectorProtocolError(
                "Connector operations must use the asynchronous protocol surface."
            )
        descriptor = connector.describe()
        validate_connector_descriptor(descriptor)
        if descriptor.contract_version.major not in self._supported_contract_majors:
            raise UnsupportedContractVersionError(
                "Connector contract major is not supported by this registry."
            )
        if descriptor.connector_id in self._entries:
            raise DuplicateConnectorError(
                "Connector identifier is already registered in this registry."
            )
        self._entries[descriptor.connector_id] = _RegisteredConnector(connector, descriptor)

    def get(self, connector_id: ConnectorId) -> Connector:
        """Return a connector by strong identifier."""

        if not isinstance(connector_id, ConnectorId):
            raise ConnectorNotFoundError("Connector identifier was not found in the registry.")
        try:
            return self._entries[connector_id].connector
        except KeyError as error:
            raise ConnectorNotFoundError(
                "Connector identifier was not found in the registry."
            ) from error

    def list_all(self) -> tuple[Connector, ...]:
        """List connectors in stable identifier order."""

        return tuple(
            entry.connector
            for _, entry in sorted(
                self._entries.items(),
                key=lambda item: item[0].value,
            )
        )

    def list_descriptors(self) -> tuple[ConnectorDescriptor, ...]:
        """Return admission-time descriptors without invoking connector objects."""

        return tuple(
            entry.descriptor
            for _, entry in sorted(
                self._entries.items(),
                key=lambda item: item[0].value,
            )
        )

    def select(
        self,
        *,
        country: CountryCode,
        capability: ConnectorCapability,
        operation: ConnectorOperation,
        mode: ConnectorMode,
    ) -> tuple[Connector, ...]:
        """Select declared support deterministically without invoking a connector."""

        return tuple(
            entry.connector
            for _, entry in sorted(
                self._entries.items(),
                key=lambda item: item[0].value,
            )
            if entry.descriptor.supports(
                country=country,
                capability=capability,
                operation=operation,
                mode=mode,
            )
        )


__all__ = ["ConnectorRegistry"]
