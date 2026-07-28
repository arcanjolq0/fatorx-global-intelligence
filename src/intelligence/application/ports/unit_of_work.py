"""Transaction boundary port for application use cases."""

from types import TracebackType
from typing import Literal, Protocol, Self

from intelligence.application.ports.repositories import (
    CompanyRepository,
    InvestigationRepository,
    WorkspaceRepository,
)


class UnitOfWork(Protocol):
    """One explicit transaction shared by all persistence ports."""

    @property
    def workspaces(self) -> WorkspaceRepository:
        """Return the workspace repository bound to the active transaction."""

    @property
    def companies(self) -> CompanyRepository:
        """Return the company repository bound to the active transaction."""

    @property
    def investigations(self) -> InvestigationRepository:
        """Return the investigation repository bound to the active transaction."""

    def __enter__(self) -> Self:
        """Open the transaction and bind all repositories."""

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        """Roll back uncommitted work and close the connection."""

    def commit(self) -> None:
        """Commit the active transaction exactly once."""

    def rollback(self) -> None:
        """Roll back the active transaction explicitly."""


__all__ = ["UnitOfWork"]
