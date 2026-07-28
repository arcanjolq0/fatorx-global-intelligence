"""Lifecycle guard for repositories bound to one explicit root transaction."""

from sqlalchemy.engine import Connection, RootTransaction

from intelligence.application.errors import PersistenceStateError


class PostgreSQLTransactionGuard:
    """Prove transaction identity and retain explicit terminal invalidation."""

    __slots__ = ("_connection", "_invalidated", "_transaction")

    def __init__(self, connection: Connection, transaction: RootTransaction) -> None:
        self._connection = connection
        self._transaction = transaction
        self._invalidated = False

    @property
    def connection(self) -> Connection:
        """Return the connection captured when the Unit of Work was entered."""

        return self._connection

    @property
    def transaction(self) -> RootTransaction:
        """Return the root transaction captured when the Unit of Work was entered."""

        return self._transaction

    @property
    def is_invalidated(self) -> bool:
        """Report whether the Unit of Work made this guard terminal."""

        return self._invalidated

    def invalidate(self) -> None:
        """Permanently reject future repository and public finalization operations."""

        self._invalidated = True

    def require_active(self) -> Connection:
        """Return the connection only while the original root transaction is active."""

        if (
            self._invalidated
            or self._connection.closed
            or not self._transaction.is_active
            or self._connection.get_transaction() is not self._transaction
        ):
            raise PersistenceStateError("Persistence transaction is not active.")
        return self._connection


__all__ = ["PostgreSQLTransactionGuard"]
