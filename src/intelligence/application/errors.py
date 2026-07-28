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


__all__ = [
    "ApplicationError",
    "PersistenceConflictError",
    "PersistenceDataError",
    "PersistenceError",
    "PersistenceStateError",
]
