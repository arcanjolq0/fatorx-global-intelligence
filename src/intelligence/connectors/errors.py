"""Safe contract errors raised before any connector I/O."""


class ConnectorContractError(Exception):
    """Base class for programming and configuration errors in connector contracts."""


class InvalidConnectorIdentifierError(ConnectorContractError):
    """An integration identifier is missing, malformed, or of the wrong kind."""


class InvalidSemanticVersionError(ConnectorContractError):
    """A semantic version is not in the supported canonical form."""


class InvalidConnectorDescriptorError(ConnectorContractError):
    """A connector descriptor violates a structural invariant."""


class InvalidConnectorContextError(ConnectorContractError):
    """A connector call context violates a structural invariant."""


class InvalidCompanyQueryError(ConnectorContractError):
    """A neutral company query is malformed."""


class InvalidConnectorObservationError(ConnectorContractError):
    """A candidate observation or neutral observation is malformed."""


class InvalidConnectorArtifactError(ConnectorContractError):
    """An inline artifact or opaque artifact reference is malformed."""


class InvalidConnectorOutcomeError(ConnectorContractError):
    """A connector outcome contains a contradictory state."""


class DuplicateConnectorError(ConnectorContractError):
    """A registry already contains the declared connector identifier."""


class UnsupportedContractVersionError(ConnectorContractError):
    """A connector declares a contract major unknown to the registry."""


class ConnectorNotFoundError(ConnectorContractError):
    """A connector identifier is not present in the registry."""


class IncompatibleConnectorProtocolError(ConnectorContractError):
    """An object does not expose the required connector protocol surface."""


__all__ = [
    "ConnectorContractError",
    "ConnectorNotFoundError",
    "DuplicateConnectorError",
    "IncompatibleConnectorProtocolError",
    "InvalidCompanyQueryError",
    "InvalidConnectorArtifactError",
    "InvalidConnectorContextError",
    "InvalidConnectorDescriptorError",
    "InvalidConnectorIdentifierError",
    "InvalidConnectorObservationError",
    "InvalidConnectorOutcomeError",
    "InvalidSemanticVersionError",
    "UnsupportedContractVersionError",
]
