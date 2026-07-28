"""Identity guard for repositories bound to one explicit root transaction."""

from dataclasses import dataclass

from sqlalchemy.engine import Connection, RootTransaction

from intelligence.application.errors import PersistenceStateError


@dataclass(frozen=True, slots=True)
class PostgreSQLTransactionGuard:
    """Prove that a repository still belongs to its original active transaction."""

    connection: Connection
    transaction: RootTransaction

    def require_active(self) -> Connection:
        """Return the connection only while the original root transaction is active."""

        if (
            self.connection.closed
            or not self.transaction.is_active
            or self.connection.get_transaction() is not self.transaction
        ):
            raise PersistenceStateError("Persistence transaction is not active.")
        return self.connection


__all__ = ["PostgreSQLTransactionGuard"]
