"""Controlled in-memory application adapters with explicit transaction semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Literal, Self

from intelligence.application.errors import PersistenceConflictError, PersistenceError
from intelligence.domain.audit import AuditEvent
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import CompanyId, InvestigationId, UserId, WorkspaceId
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    WorkspaceMembership,
)
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace


@dataclass(slots=True)
class FakeDatabase:
    workspaces: dict[WorkspaceId, Workspace] = field(default_factory=dict)
    companies: dict[tuple[WorkspaceId, CompanyId], Company] = field(default_factory=dict)
    investigations: dict[tuple[WorkspaceId, InvestigationId], Investigation] = field(
        default_factory=dict
    )
    users: dict[UserId, UserAccount] = field(default_factory=dict)
    memberships: dict[tuple[WorkspaceId, UserId], WorkspaceMembership] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)

    def clone(self) -> FakeDatabase:
        return FakeDatabase(
            workspaces=dict(self.workspaces),
            companies=dict(self.companies),
            investigations=dict(self.investigations),
            users=dict(self.users),
            memberships=dict(self.memberships),
            audit_events=list(self.audit_events),
        )

    def replace_with(self, other: FakeDatabase) -> None:
        self.workspaces = dict(other.workspaces)
        self.companies = dict(other.companies)
        self.investigations = dict(other.investigations)
        self.users = dict(other.users)
        self.memberships = dict(other.memberships)
        self.audit_events = list(other.audit_events)


class FakeWorkspaceRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def add(self, workspace: Workspace) -> None:
        if workspace.id in self._database.workspaces:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.workspaces[workspace.id] = workspace

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        return self._database.workspaces.get(workspace_id)


class FakeCompanyRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.get_calls: list[tuple[WorkspaceId, CompanyId]] = []

    def add(self, company: Company) -> None:
        key = (company.workspace_id, company.id)
        if key in self._database.companies:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.companies[key] = company

    def get(self, workspace_id: WorkspaceId, company_id: CompanyId) -> Company | None:
        self.get_calls.append((workspace_id, company_id))
        return self._database.companies.get((workspace_id, company_id))


class FakeInvestigationRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.get_calls: list[tuple[WorkspaceId, InvestigationId]] = []

    def add(self, investigation: Investigation) -> None:
        key = (investigation.workspace_id, investigation.id)
        if key in self._database.investigations:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.investigations[key] = investigation

    def get(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        self.get_calls.append((workspace_id, investigation_id))
        return self._database.investigations.get((workspace_id, investigation_id))


class FakeUserRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.get_calls: list[UserId] = []

    def add(self, user: UserAccount) -> None:
        if user.id in self._database.users or any(
            existing.email == user.email for existing in self._database.users.values()
        ):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.users[user.id] = user

    def get(self, user_id: UserId) -> UserAccount | None:
        self.get_calls.append(user_id)
        return self._database.users.get(user_id)

    def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        return next(
            (user for user in self._database.users.values() if user.email == email),
            None,
        )


class FakeWorkspaceMembershipRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.get_calls: list[tuple[WorkspaceId, UserId]] = []
        self.get_for_update_calls: list[tuple[WorkspaceId, UserId]] = []
        self.owner_lock_calls: list[WorkspaceId] = []

    def add(self, membership: WorkspaceMembership) -> None:
        key = (membership.workspace_id, membership.user_id)
        if key in self._database.memberships:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.memberships[key] = membership

    def get(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        self.get_calls.append((workspace_id, user_id))
        return self._database.memberships.get((workspace_id, user_id))

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        self.get_for_update_calls.append((workspace_id, user_id))
        return self._database.memberships.get((workspace_id, user_id))

    def list_active_owners_for_update(
        self,
        workspace_id: WorkspaceId,
    ) -> list[WorkspaceMembership]:
        self.owner_lock_calls.append(workspace_id)
        return sorted(
            (
                membership
                for membership in self._database.memberships.values()
                if membership.workspace_id == workspace_id
                and membership.status is MembershipStatus.ACTIVE
                and membership.role is MembershipRole.OWNER
            ),
            key=lambda membership: membership.id.value,
        )

    def update(self, membership: WorkspaceMembership) -> None:
        key = (membership.workspace_id, membership.user_id)
        current = self._database.memberships.get(key)
        if current is None or current.id != membership.id:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.memberships[key] = membership


class FakeAuditEventRepository:
    def __init__(self, database: FakeDatabase, *, fail_add: bool = False) -> None:
        self._database = database
        self._fail_add = fail_add

    def add(self, event: AuditEvent) -> None:
        if self._fail_add:
            raise PersistenceError("Persistence operation failed.")
        if any(existing.id == event.id for existing in self._database.audit_events):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.audit_events.append(event)


class FakeUnitOfWork:
    def __init__(
        self,
        database: FakeDatabase,
        *,
        fail_commit: bool = False,
        fail_audit: bool = False,
    ) -> None:
        self._committed_database = database
        self._working_database = database.clone()
        self._fail_commit = fail_commit
        self._entered = False
        self._closed = False
        self._committed = False
        self.commit_calls = 0
        self.rollback_calls = 0
        self.workspaces = FakeWorkspaceRepository(self._working_database)
        self.companies = FakeCompanyRepository(self._working_database)
        self.investigations = FakeInvestigationRepository(self._working_database)
        self.users = FakeUserRepository(self._working_database)
        self.memberships = FakeWorkspaceMembershipRepository(self._working_database)
        self.audit_events = FakeAuditEventRepository(
            self._working_database,
            fail_add=fail_audit,
        )

    def __enter__(self) -> Self:
        if self._entered:
            raise PersistenceError("Unit of Work instances are single-use.")
        self._entered = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exception_type, exception, traceback
        if not self._committed:
            self.rollback_calls += 1
        self._closed = True
        return False

    def commit(self) -> None:
        self.commit_calls += 1
        if self._fail_commit:
            raise PersistenceError("Unable to commit the persistence transaction.")
        self._committed_database.replace_with(self._working_database)
        self._committed = True

    def rollback(self) -> None:
        self.rollback_calls += 1
        self._closed = True


class FakeUnitOfWorkFactory:
    def __init__(
        self,
        database: FakeDatabase | None = None,
        *,
        fail_commit: bool = False,
        fail_audit: bool = False,
    ) -> None:
        self.database = database or FakeDatabase()
        self.fail_commit = fail_commit
        self.fail_audit = fail_audit
        self.created: list[FakeUnitOfWork] = []

    def __call__(self) -> FakeUnitOfWork:
        unit_of_work = FakeUnitOfWork(
            self.database,
            fail_commit=self.fail_commit,
            fail_audit=self.fail_audit,
        )
        self.created.append(unit_of_work)
        return unit_of_work


@dataclass(frozen=True, slots=True)
class FakeClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


__all__ = [
    "FakeClock",
    "FakeDatabase",
    "FakeUnitOfWork",
    "FakeUnitOfWorkFactory",
]
