"""Framework-neutral errors exposed by the application boundary."""


class ApplicationError(Exception):
    """Base class for expected application-layer failures."""


class PersistenceError(ApplicationError):
    """A database operation failed without exposing adapter details."""


class PersistenceConflictError(PersistenceError):
    """A key, foreign-key, or other integrity constraint was rejected."""


class PersistenceDataError(PersistenceError):
    """Persisted values cannot be reconstituted as a valid domain snapshot."""


class PersistenceStateError(PersistenceError):
    """A persistence operation was attempted outside an active transaction."""


class AuthorizationDeniedError(ApplicationError):
    """The authenticated actor cannot perform the requested operation."""

    def __init__(self) -> None:
        super().__init__("Operation is not authorized.")


class ResourceNotFoundError(ApplicationError):
    """A tenant-scoped resource is absent without revealing another tenant."""

    def __init__(self) -> None:
        super().__init__("Requested resource was not found.")


class MembershipConflictError(ApplicationError):
    """A membership operation conflicts with its current state."""

    def __init__(self) -> None:
        super().__init__("Membership operation conflicts with current state.")


class LastOwnerProtectionError(ApplicationError):
    """An operation would remove the final active owner of a workspace."""

    def __init__(self) -> None:
        super().__init__("The workspace must retain an active owner.")


class InvalidOperationError(ApplicationError):
    """A known application operation is invalid in the current state."""

    def __init__(self) -> None:
        super().__init__("Operation is invalid in the current state.")


__all__ = [
    "ApplicationError",
    "AuthorizationDeniedError",
    "InvalidOperationError",
    "LastOwnerProtectionError",
    "MembershipConflictError",
    "PersistenceConflictError",
    "PersistenceDataError",
    "PersistenceError",
    "PersistenceStateError",
    "ResourceNotFoundError",
]
