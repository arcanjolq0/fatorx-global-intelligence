"""F2.4.2 membership locks and last-owner races against real PostgreSQL."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, BrokenBarrierError, Event, Thread

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine

from intelligence.application.actor_context import ActorContext
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import LastOwnerProtectionError, PersistenceStateError
from intelligence.application.services.memberships import MembershipService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.identifiers import CorrelationId, MembershipId, UserId, WorkspaceId
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.engine import create_postgresql_engine
from intelligence.infrastructure.persistence.postgresql.repositories import (
    PostgreSQLWorkspaceMembershipRepository,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    workspace_membership_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from intelligence.infrastructure.persistence.postgresql.unit_of_work import PostgreSQLUnitOfWork
from tests.support.destructive_database import require_safe_destructive_database_url
from tests.unit.application.fakes import FakeClock

pytestmark = pytest.mark.allow_hosts(["127.0.0.1", "::1", "localhost"])

REPOSITORY_ROOT = Path(__file__).parents[3]
NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)
THREAD_TIMEOUT_SECONDS = 10.0


@pytest.fixture(scope="module")
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


@pytest.fixture(autouse=True)
def clean_database(engine: Engine) -> Iterator[None]:
    yield
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "TRUNCATE TABLE audit_event, workspace_membership, user_account, "
                "investigation, company, workspace CASCADE"
            )
        )


def _workspace() -> Workspace:
    return Workspace(
        id=WorkspaceId.new(),
        name="Concurrent Workspace",
        status=WorkspaceStatus.ACTIVE,
        retention_policy_version="2026-01",
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=2),
    )


def _user(user_id: UserId, label: str) -> UserAccount:
    return UserAccount(
        id=user_id,
        email=EmailAddress(f"{label}-{user_id.value}@example.test"),
        display_name=label,
        status=UserAccountStatus.ACTIVE,
        created_at=NOW - timedelta(days=2),
        updated_at=NOW - timedelta(days=2),
    )


def _membership(
    workspace_id: WorkspaceId,
    user_id: UserId,
    role: MembershipRole,
    *,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> WorkspaceMembership:
    timestamp = NOW - timedelta(days=1)
    return WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=workspace_id,
        user_id=user_id,
        role=role,
        status=status,
        created_at=timestamp,
        updated_at=timestamp,
        deactivated_at=timestamp if status is MembershipStatus.INACTIVE else None,
    )


def _seed_memberships(
    engine: Engine,
    roles: list[tuple[MembershipRole, MembershipStatus]],
) -> tuple[Workspace, list[ActorContext], list[WorkspaceMembership]]:
    workspace = _workspace()
    actors: list[ActorContext] = []
    memberships: list[WorkspaceMembership] = []
    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        unit_of_work.workspaces.add(workspace)
        for index, (role, status) in enumerate(roles):
            user_id = UserId.new()
            actor = ActorContext(
                user_id=user_id,
                workspace_id=workspace.id,
                correlation_id=CorrelationId.new(),
            )
            membership = _membership(workspace.id, user_id, role, status=status)
            actors.append(actor)
            memberships.append(membership)
            unit_of_work.users.add(_user(user_id, f"user-{index}"))
            unit_of_work.memberships.add(membership)
        unit_of_work.commit()
    return workspace, actors, memberships


class BarrierMembershipRepository(PostgreSQLWorkspaceMembershipRepository):
    def __init__(self, delegate_guard: PostgreSQLTransactionGuard, barrier: Barrier) -> None:
        super().__init__(delegate_guard)
        self._barrier = barrier
        self._synchronized = False

    def get(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        if not self._synchronized:
            self._synchronized = True
            try:
                self._barrier.wait(timeout=THREAD_TIMEOUT_SECONDS)
            except BrokenBarrierError as error:
                raise RuntimeError("Concurrent authorization barrier failed.") from error
        return super().get(workspace_id, user_id)


class BarrierUnitOfWork(PostgreSQLUnitOfWork):
    def __init__(self, engine: Engine, barrier: Barrier) -> None:
        super().__init__(engine)
        self._barrier = barrier

    def __enter__(self) -> BarrierUnitOfWork:
        super().__enter__()
        guard = self._transaction_guard
        assert guard is not None
        self._memberships = BarrierMembershipRepository(guard, self._barrier)
        return self


class BarrierFactory:
    def __init__(self, engine: Engine, barrier: Barrier) -> None:
        self._engine = engine
        self._barrier = barrier

    def __call__(self) -> BarrierUnitOfWork:
        return BarrierUnitOfWork(self._engine, self._barrier)


def _run_thread(target: Callable[[], None], errors: list[BaseException]) -> None:
    try:
        target()
    except BaseException as error:
        errors.append(error)


def test_get_for_update_blocks_target_and_rechecks_snapshot_after_commit(engine: Engine) -> None:
    workspace, _, memberships = _seed_memberships(
        engine,
        [(MembershipRole.ANALYST, MembershipStatus.ACTIVE)],
    )
    target = memberships[0]
    started = Event()
    acquired = Event()
    errors: list[BaseException] = []
    restored: list[WorkspaceMembership | None] = []

    def contender() -> None:
        with PostgreSQLUnitOfWork(engine) as unit_of_work:
            connection = unit_of_work._connection
            assert connection is not None
            connection.execute(sa.text("SET LOCAL lock_timeout = '5s'"))
            started.set()
            restored.append(unit_of_work.memberships.get_for_update(workspace.id, target.user_id))
            acquired.set()
            unit_of_work.commit()

    with PostgreSQLUnitOfWork(engine) as holder:
        locked = holder.memberships.get_for_update(workspace.id, target.user_id)
        assert locked == target
        thread = Thread(target=_run_thread, args=(contender, errors), daemon=True)
        thread.start()
        assert started.wait(timeout=THREAD_TIMEOUT_SECONDS)
        assert not acquired.wait(timeout=0.25)
        holder.memberships.update(target.deactivate(updated_at=NOW))
        holder.commit()

    assert acquired.wait(timeout=THREAD_TIMEOUT_SECONDS)
    thread.join(timeout=THREAD_TIMEOUT_SECONDS)
    assert not thread.is_alive()
    assert errors == []
    assert restored[0] is not None
    assert restored[0].status is MembershipStatus.INACTIVE


def test_active_owner_lock_returns_only_current_owners_in_stable_id_order(
    engine: Engine,
) -> None:
    workspace, _, memberships = _seed_memberships(
        engine,
        [
            (MembershipRole.OWNER, MembershipStatus.ACTIVE),
            (MembershipRole.OWNER, MembershipStatus.ACTIVE),
            (MembershipRole.OWNER, MembershipStatus.INACTIVE),
            (MembershipRole.ADMIN, MembershipStatus.ACTIVE),
        ],
    )

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        owners = unit_of_work.memberships.list_active_owners_for_update(workspace.id)
        original_transaction = unit_of_work._transaction
        connection = unit_of_work._connection
        assert connection is not None
        assert connection.get_transaction() is original_transaction
        unit_of_work.commit()

    expected = sorted(
        (
            membership
            for membership in memberships
            if membership.role is MembershipRole.OWNER
            and membership.status is MembershipStatus.ACTIVE
        ),
        key=lambda membership: membership.id.value,
    )
    assert owners == expected


def test_new_membership_repository_operations_share_guard_and_reject_autobegin(
    engine: Engine,
) -> None:
    workspace, _, memberships = _seed_memberships(
        engine,
        [(MembershipRole.OWNER, MembershipStatus.ACTIVE)],
    )
    original = memberships[0]

    with PostgreSQLUnitOfWork(engine) as unit_of_work:
        repository = unit_of_work.memberships
        guard = unit_of_work._transaction_guard
        connection = unit_of_work._connection
        transaction = unit_of_work._transaction
        assert guard is not None
        assert connection is not None
        assert transaction is not None
        assert repository._transaction_guard is guard
        locked = repository.get_for_update(workspace.id, original.user_id)
        assert locked == original
        changed = original.change_role(MembershipRole.ADMIN, updated_at=NOW)
        repository.update(changed)
        assert repository.list_active_owners_for_update(workspace.id) == []
        assert connection.get_transaction() is transaction
        unit_of_work.commit()

        assert connection.get_transaction() is None
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.get_for_update(workspace.id, original.user_id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.list_active_owners_for_update(workspace.id)
        with pytest.raises(PersistenceStateError, match="transaction is not active"):
            repository.update(changed)
        assert connection.get_transaction() is None

    with PostgreSQLUnitOfWork(engine) as observer:
        assert observer.memberships.get(workspace.id, original.user_id) == changed


@pytest.mark.parametrize("operation", ["deactivate", "demote"])
def test_concurrent_owner_removal_preserves_one_owner_after_waiter_rechecks(
    engine: Engine,
    operation: str,
) -> None:
    workspace, actors, _ = _seed_memberships(
        engine,
        [
            (MembershipRole.OWNER, MembershipStatus.ACTIVE),
            (MembershipRole.OWNER, MembershipStatus.ACTIVE),
        ],
    )
    barrier = Barrier(2)
    factory = BarrierFactory(engine, barrier)
    services = [
        MembershipService(factory, ContextualAuthorizer(), FakeClock(NOW)),
        MembershipService(factory, ContextualAuthorizer(), FakeClock(NOW)),
    ]
    successes: list[WorkspaceMembership] = []
    errors: list[BaseException] = []

    def remove(index: int) -> None:
        actor = actors[index]
        if operation == "deactivate":
            successes.append(services[index].deactivate_member(actor, user_id=actor.user_id))
        else:
            successes.append(
                services[index].change_role(
                    actor,
                    user_id=actor.user_id,
                    new_role=MembershipRole.ADMIN,
                )
            )

    threads = [
        Thread(target=_run_thread, args=(lambda index=index: remove(index), errors), daemon=True)
        for index in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=THREAD_TIMEOUT_SECONDS)

    assert all(not thread.is_alive() for thread in threads)
    assert len(successes) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], LastOwnerProtectionError)
    with engine.connect() as connection:
        active_owner_count = connection.execute(
            sa.select(sa.func.count())
            .select_from(workspace_membership_table)
            .where(
                workspace_membership_table.c.workspace_id == workspace.id.value,
                workspace_membership_table.c.role == MembershipRole.OWNER.value,
                workspace_membership_table.c.status == MembershipStatus.ACTIVE.value,
            )
        ).scalar_one()
        outcomes = (
            connection.execute(
                sa.select(audit_event_table.c.outcome).order_by(audit_event_table.c.id)
            )
            .scalars()
            .all()
        )

    assert active_owner_count == 1
    assert sorted(outcomes) == sorted([AuditOutcome.SUCCESS.value, AuditOutcome.DENIED.value])
