"""F2.4.1 repository and transaction tests against real PostgreSQL."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError

from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceError,
    PersistenceStateError,
)
from intelligence.domain.audit import AuditEvent, AuditOutcome, AuditResourceType
from intelligence.domain.identifiers import (
    AuditEventId,
    CompanyId,
    CorrelationId,
    InvestigationId,
    MembershipId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.engine import (
    create_postgresql_engine,
)
from intelligence.infrastructure.persistence.postgresql.mappers import (
    audit_event_from_values,
)
from intelligence.infrastructure.persistence.postgresql.tables import audit_event_table
from intelligence.infrastructure.persistence.postgresql.unit_of_work import (
    PostgreSQLUnitOfWork,
)
from tests.support.destructive_database import require_safe_destructive_database_url

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
CREATED_AT = datetime(2026, 7, 28, 12, 0, 0, 123456, tzinfo=UTC)


@pytest.fixture()
def engine() -> Iterator[Engine]:
    database_url = require_safe_destructive_database_url()
    config = Config(str(REPOSITORY_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(REPOSITORY_ROOT / "migrations"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    database_engine = create_postgresql_engine({"DATABASE_URL": database_url})
    try:
        yield database_engine
    finally:
        database_engine.dispose()
        command.downgrade(config, "base")


def _workspace(workspace_id: WorkspaceId | None = None) -> Workspace:
    return Workspace(
        id=workspace_id or WorkspaceId.new(),
        name="Workspace F2.4.1",
        status=WorkspaceStatus.ACTIVE,
        retention_policy_version="2026-01",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _user(
    *,
    user_id: UserId | None = None,
    email: str | None = None,
    status: UserAccountStatus = UserAccountStatus.ACTIVE,
) -> UserAccount:
    resolved_id = user_id or UserId.new()
    return UserAccount(
        id=resolved_id,
        email=EmailAddress(email or f" ANALYST-{resolved_id.value}@Example.Test "),
        display_name="  Analista Internacional  ",
        status=status,
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _membership(
    workspace_id: WorkspaceId,
    user_id: UserId,
    *,
    membership_id: MembershipId | None = None,
    role: MembershipRole = MembershipRole.ANALYST,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> WorkspaceMembership:
    inactive = status is MembershipStatus.INACTIVE
    return WorkspaceMembership(
        id=membership_id or MembershipId.new(),
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        status=status,
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=2),
        deactivated_at=CREATED_AT + timedelta(minutes=2) if inactive else None,
    )


def _resource_id(
    resource_type: AuditResourceType,
    *,
    workspace_id: WorkspaceId,
    user_id: UserId,
) -> WorkspaceId | UserId | MembershipId | CompanyId | InvestigationId:
    match resource_type:
        case AuditResourceType.WORKSPACE:
            return workspace_id
        case AuditResourceType.USER:
            return user_id
        case AuditResourceType.MEMBERSHIP:
            return MembershipId.new()
        case AuditResourceType.COMPANY:
            return CompanyId.new()
        case AuditResourceType.INVESTIGATION:
            return InvestigationId.new()


def _audit_event(
    workspace_id: WorkspaceId,
    actor_user_id: UserId,
    *,
    event_id: AuditEventId | None = None,
    resource_type: AuditResourceType = AuditResourceType.MEMBERSHIP,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    include_resource: bool = True,
    include_reason: bool = True,
) -> AuditEvent:
    return AuditEvent(
        id=event_id or AuditEventId.new(),
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        action_code=" membership.read ",
        resource_type=resource_type,
        resource_id=(
            _resource_id(resource_type, workspace_id=workspace_id, user_id=actor_user_id)
            if include_resource
            else None
        ),
        outcome=outcome,
        reason_code=" policy.allowed " if include_reason else None,
        correlation_id=CorrelationId.new(),
        occurred_at=CREATED_AT,
    )


def _seed_workspace_and_user(engine: Engine) -> tuple[Workspace, UserAccount]:
    workspace = _workspace()
    user = _user()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.users.add(user)
        unit_of_work.commit()
    return workspace, user


def _fetch_audit_event(engine: Engine, event_id: AuditEventId) -> AuditEvent | None:
    statement = sa.select(audit_event_table).where(audit_event_table.c.id == event_id.value)
    with engine.connect() as connection:
        values = connection.execute(statement).mappings().first()
    return (
        audit_event_from_values(cast(Mapping[str, object], values)) if values is not None else None
    )


def _terminate_unit_of_work_backend(
    engine: Engine,
    unit_of_work: PostgreSQLUnitOfWork,
) -> None:
    connection = unit_of_work._connection
    assert connection is not None
    backend_pid = connection.execute(sa.text("SELECT pg_backend_pid() ")).scalar_one()
    with engine.begin() as controller:
        terminated = controller.execute(
            sa.text("SELECT pg_terminate_backend(:backend_pid)"),
            {"backend_pid": backend_pid},
        ).scalar_one()
    assert terminated is True


@pytest.mark.parametrize("status", list(UserAccountStatus))
def test_user_round_trip_covers_statuses_email_name_and_timestamps(
    engine: Engine,
    status: UserAccountStatus,
) -> None:
    user = _user(status=status)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.users.add(user)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored_by_id = unit_of_work.users.get(user.id)
        restored_by_email = unit_of_work.users.get_by_email(user.email)

    assert restored_by_id == user
    assert restored_by_email == user
    assert restored_by_id is not None
    assert restored_by_id.email.value == str(user.email)
    assert restored_by_id.display_name == "Analista Internacional"
    assert restored_by_id.created_at == CREATED_AT
    assert restored_by_id.created_at.tzinfo is UTC


@pytest.mark.parametrize("role", list(MembershipRole))
def test_membership_round_trip_covers_every_role(
    engine: Engine,
    role: MembershipRole,
) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    membership = _membership(workspace.id, user.id, role=role)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.memberships.add(membership)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.memberships.get(workspace.id, user.id)

    assert restored == membership
    assert restored is not None
    assert restored.workspace_id == workspace.id
    assert restored.user_id == user.id
    assert restored.status is MembershipStatus.ACTIVE
    assert restored.deactivated_at is None


def test_inactive_membership_round_trip_preserves_deactivation_snapshot(
    engine: Engine,
) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    membership = _membership(
        workspace.id,
        user.id,
        status=MembershipStatus.INACTIVE,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.memberships.add(membership)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        restored = unit_of_work.memberships.get(workspace.id, user.id)

    assert restored == membership
    assert restored is not None
    assert restored.status is MembershipStatus.INACTIVE
    assert restored.deactivated_at == CREATED_AT + timedelta(minutes=2)


@pytest.mark.parametrize("outcome", list(AuditOutcome))
def test_audit_round_trip_covers_every_outcome(
    engine: Engine,
    outcome: AuditOutcome,
) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    event = _audit_event(workspace.id, user.id, outcome=outcome)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.audit_events
        repository.add(event)
        assert not any(
            hasattr(repository, operation) for operation in ("update", "delete", "save", "replace")
        )
        unit_of_work.commit()

    restored = _fetch_audit_event(engine, event.id)
    assert restored == event
    assert restored is not None
    assert restored.correlation_id == event.correlation_id
    assert restored.occurred_at == CREATED_AT
    assert restored.occurred_at.microsecond == 123456
    with pytest.raises(FrozenInstanceError):
        setattr(restored, "action_code", "CHANGED")  # noqa: B010


@pytest.mark.parametrize("resource_type", list(AuditResourceType))
def test_audit_round_trip_restores_every_strong_resource_id(
    engine: Engine,
    resource_type: AuditResourceType,
) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    event = _audit_event(workspace.id, user.id, resource_type=resource_type)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.audit_events.add(event)
        unit_of_work.commit()

    restored = _fetch_audit_event(engine, event.id)
    assert restored == event
    assert restored is not None
    assert type(restored.resource_id) is type(event.resource_id)
    assert restored.reason_code == "POLICY.ALLOWED"


def test_audit_round_trip_preserves_absent_resource_and_reason(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    event = _audit_event(
        workspace.id,
        user.id,
        include_resource=False,
        include_reason=False,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.audit_events.add(event)
        unit_of_work.commit()

    restored = _fetch_audit_event(engine, event.id)
    assert restored == event
    assert restored is not None
    assert restored.resource_id is None
    assert restored.reason_code is None


def test_rollback_leaves_no_partial_user(engine: Engine) -> None:
    user = _user()

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.users.add(user)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.users.get(user.id) is None


def test_rollback_leaves_no_partial_membership(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    membership = _membership(workspace.id, user.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.memberships.add(membership)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.memberships.get(workspace.id, user.id) is None


def test_rollback_leaves_no_partial_audit_event(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    event = _audit_event(workspace.id, user.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.audit_events.add(event)

    assert _fetch_audit_event(engine, event.id) is None


def test_user_and_membership_share_one_unit_of_work(engine: Engine) -> None:
    workspace = _workspace()
    user = _user()
    membership = _membership(workspace.id, user.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        unit_of_work.users.add(user)
        unit_of_work.memberships.add(membership)
        assert unit_of_work.users.get(user.id) == user
        assert unit_of_work.memberships.get(workspace.id, user.id) == membership
        unit_of_work.commit()


def test_membership_and_audit_event_share_one_unit_of_work(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    membership = _membership(workspace.id, user.id)
    event = _audit_event(
        workspace.id,
        user.id,
        resource_type=AuditResourceType.MEMBERSHIP,
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        guard = unit_of_work._transaction_guard
        connection = unit_of_work._connection
        transaction = unit_of_work._transaction
        assert unit_of_work.memberships._transaction_guard is guard
        assert unit_of_work.audit_events._transaction_guard is guard
        assert connection is not None
        assert transaction is not None
        unit_of_work.memberships.add(membership)
        unit_of_work.audit_events.add(event)
        assert connection.get_transaction() is transaction
        unit_of_work.commit()

    assert _fetch_audit_event(engine, event.id) == event


def test_duplicate_email_conflict_is_translated_without_details(engine: Engine) -> None:
    first = _user(email="duplicate@example.test")
    duplicate = _user(email=" DUPLICATE@EXAMPLE.TEST ")

    with (
        pytest.raises(PersistenceConflictError) as captured,
        PostgreSQLUnitOfWork(engine) as unit_of_work,
    ):
        unit_of_work.users.add(first)
        unit_of_work.users.add(duplicate)

    assert str(captured.value) == "Persistence constraint conflict."
    assert isinstance(captured.value.__cause__, IntegrityError)
    assert "duplicate@example.test" not in str(captured.value)


def test_duplicate_membership_conflict_is_translated(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    first = _membership(workspace.id, user.id)
    duplicate = _membership(workspace.id, user.id, role=MembershipRole.VIEWER)

    with (
        pytest.raises(PersistenceConflictError) as captured,
        PostgreSQLUnitOfWork(engine) as unit_of_work,
    ):
        unit_of_work.memberships.add(first)
        unit_of_work.memberships.add(duplicate)

    assert str(captured.value) == "Persistence constraint conflict."
    assert isinstance(captured.value.__cause__, IntegrityError)


def test_membership_queries_are_isolated_by_workspace(engine: Engine) -> None:
    first_workspace = _workspace()
    second_workspace = _workspace()
    unrelated_workspace = _workspace()
    user = _user()
    first = _membership(first_workspace.id, user.id, role=MembershipRole.OWNER)
    second = _membership(second_workspace.id, user.id, role=MembershipRole.VIEWER)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(first_workspace)
        unit_of_work.workspaces.add(second_workspace)
        unit_of_work.workspaces.add(unrelated_workspace)
        unit_of_work.users.add(user)
        unit_of_work.memberships.add(first)
        unit_of_work.memberships.add(second)
        unit_of_work.commit()
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.memberships.get(first_workspace.id, user.id) == first
        assert unit_of_work.memberships.get(second_workspace.id, user.id) == second
        assert unit_of_work.memberships.get(unrelated_workspace.id, user.id) is None


def test_absence_returns_none(engine: Engine) -> None:
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        assert unit_of_work.users.get(UserId.new()) is None
        assert unit_of_work.users.get_by_email(EmailAddress("absent@example.test")) is None
        assert unit_of_work.memberships.get(WorkspaceId.new(), UserId.new()) is None


def test_captured_new_repositories_reject_operations_after_commit_without_autobegin(
    engine: Engine,
) -> None:
    workspace = _workspace()
    user = _user()
    membership = _membership(workspace.id, user.id)
    event = _audit_event(workspace.id, user.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        users = unit_of_work.users
        memberships = unit_of_work.memberships
        audit_events = unit_of_work.audit_events
        connection = unit_of_work._connection
        transaction = unit_of_work._transaction
        assert connection is not None
        assert transaction is not None
        unit_of_work.workspaces.add(workspace)
        users.add(user)
        memberships.add(membership)
        audit_events.add(event)
        unit_of_work.commit()

        assert not transaction.is_active
        assert connection.get_transaction() is None
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            users.get(user.id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            memberships.get(workspace.id, user.id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            audit_events.add(_audit_event(workspace.id, user.id))
        assert connection.get_transaction() is None


def test_captured_new_repositories_reject_operations_after_rollback_without_autobegin(
    engine: Engine,
) -> None:
    workspace = _workspace()
    user = _user()
    membership = _membership(workspace.id, user.id)
    event = _audit_event(workspace.id, user.id)

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        users = unit_of_work.users
        memberships = unit_of_work.memberships
        audit_events = unit_of_work.audit_events
        connection = unit_of_work._connection
        transaction = unit_of_work._transaction
        assert connection is not None
        assert transaction is not None
        unit_of_work.workspaces.add(workspace)
        users.add(user)
        memberships.add(membership)
        audit_events.add(event)
        unit_of_work.rollback()

        assert not transaction.is_active
        assert connection.get_transaction() is None
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            users.get(user.id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            memberships.get(workspace.id, user.id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            audit_events.add(event)
        assert connection.get_transaction() is None


def test_commit_failure_poisons_all_new_repositories(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    unit_of_work = PostgreSQLUnitOfWork(engine)

    with pytest.raises(PersistenceError), unit_of_work:
        users = unit_of_work.users
        memberships = unit_of_work.memberships
        audit_events = unit_of_work.audit_events
        guard = unit_of_work._transaction_guard
        assert users._transaction_guard is guard
        assert memberships._transaction_guard is guard
        assert audit_events._transaction_guard is guard
        _terminate_unit_of_work_backend(engine, unit_of_work)
        unit_of_work.commit()

    assert guard is not None
    assert guard.is_invalidated
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        users.get(user.id)
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        memberships.get(workspace.id, user.id)
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        audit_events.add(_audit_event(workspace.id, user.id))


def test_rollback_failure_poisons_all_new_repositories(engine: Engine) -> None:
    workspace, user = _seed_workspace_and_user(engine)
    unit_of_work = PostgreSQLUnitOfWork(engine)

    with pytest.raises(PersistenceError), unit_of_work:
        users = unit_of_work.users
        memberships = unit_of_work.memberships
        audit_events = unit_of_work.audit_events
        guard = unit_of_work._transaction_guard
        assert users._transaction_guard is guard
        assert memberships._transaction_guard is guard
        assert audit_events._transaction_guard is guard
        _terminate_unit_of_work_backend(engine, unit_of_work)
        unit_of_work.rollback()

    assert guard is not None
    assert guard.is_invalidated
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        users.get(user.id)
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        memberships.get(workspace.id, user.id)
    with pytest.raises(PersistenceStateError, match="transaction is not active"):
        audit_events.add(_audit_event(workspace.id, user.id))
