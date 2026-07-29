"""Safe errors raised by connector execution controls before external I/O."""

from intelligence.connectors.enums import ConnectorErrorCode


class ConnectorExecutionError(Exception):
    """Base class for execution policy, preflight, and idempotency errors."""


class InvalidConnectorExecutionPolicyError(ConnectorExecutionError):
    """An immutable execution policy contains an incoherent value."""


class ConnectorExecutionPreflightError(ConnectorExecutionError):
    """A request was rejected before a connector operation could start."""

    __slots__ = ("code",)

    def __init__(self, code: ConnectorErrorCode, message: str) -> None:
        self.code = code
        super().__init__(message)


class IdempotencyConflictError(ConnectorExecutionError):
    """An operation identifier is already bound to another fingerprint."""


class IdempotencyStoreError(ConnectorExecutionError):
    """The in-memory idempotency state violated its atomic protocol."""


__all__ = [
    "ConnectorExecutionError",
    "ConnectorExecutionPreflightError",
    "IdempotencyConflictError",
    "IdempotencyStoreError",
    "InvalidConnectorExecutionPolicyError",
]
