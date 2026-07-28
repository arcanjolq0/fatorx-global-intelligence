"""Tests for internal identities and workspace membership snapshots."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from intelligence.domain.errors import (
    InvalidDateTimeError,
    InvalidEmailAddressError,
    InvariantViolationError,
)
from intelligence.domain.identifiers import MembershipId, UserId, WorkspaceId
from intelligence.domain.identities import (
    EMAIL_ADDRESS_MAX_LENGTH,
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    UserAccountStatus,
    WorkspaceMembership,
)


def _user_account(**overrides: object) -> UserAccount:
    values: dict[str, object] = {
        "id": UserId.new(),
        "email": EmailAddress("analyst@example.com"),
        "display_name": "  Ana Analyst  ",
        "status": UserAccountStatus.ACTIVE,
        "created_at": datetime(
            2026,
            7,
            28,
            9,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "updated_at": datetime(2026, 7, 28, 13, tzinfo=UTC),
    }
    values.update(overrides)
    return UserAccount(**cast(Any, values))


def _membership(**overrides: object) -> WorkspaceMembership:
    values: dict[str, object] = {
        "id": MembershipId.new(),
        "workspace_id": WorkspaceId.new(),
        "user_id": UserId.new(),
        "role": MembershipRole.ANALYST,
        "status": MembershipStatus.ACTIVE,
        "created_at": datetime(
            2026,
            7,
            28,
            9,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "updated_at": datetime(2026, 7, 28, 13, tzinfo=UTC),
        "deactivated_at": None,
    }
    values.update(overrides)
    return WorkspaceMembership(**cast(Any, values))


def test_email_address_normalizes_case_and_external_spaces() -> None:
    email = EmailAddress("  Analyst.Example+Tag@Example.COM  ")

    assert email.value == "analyst.example+tag@example.com"
    assert str(email) == "analyst.example+tag@example.com"


def test_email_address_accepts_the_explicit_maximum_length() -> None:
    raw_email = f"{'a' * 246}@example"

    email = EmailAddress(raw_email)

    assert len(email.value) == EMAIL_ADDRESS_MAX_LENGTH == 254


@pytest.mark.parametrize(
    "invalid_value",
    [
        "",
        "   ",
        "analyst.example.com",
        "@example.com",
        "analyst@",
        "analyst@@example.com",
        "analyst name@example.com",
        "analyst@exam ple.com",
        " analyst\t@example.com ",
        "analyst@example.com\n",
        f"{'a' * 247}@example",
    ],
)
def test_email_address_rejects_invalid_shape_controls_or_size(invalid_value: str) -> None:
    with pytest.raises(InvalidEmailAddressError):
        EmailAddress(invalid_value)


def test_email_address_rejects_a_non_text_runtime_value() -> None:
    with pytest.raises(InvalidEmailAddressError):
        EmailAddress(cast(str, 42))


@pytest.mark.parametrize("status", list(UserAccountStatus))
def test_user_account_accepts_every_status_and_normalizes_fields(
    status: UserAccountStatus,
) -> None:
    account = _user_account(status=status)

    assert account.status is status
    assert account.display_name == "Ana Analyst"
    assert account.created_at == datetime(2026, 7, 28, 12, tzinfo=UTC)
    assert account.updated_at == datetime(2026, 7, 28, 13, tzinfo=UTC)


def test_user_account_status_vocabulary_is_closed() -> None:
    assert {status.value for status in UserAccountStatus} == {"ACTIVE", "DISABLED"}


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("id", "user"),
        ("email", "analyst@example.com"),
        ("display_name", "  "),
        ("status", "ACTIVE"),
    ],
)
def test_user_account_rejects_invalid_fields(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(InvariantViolationError):
        _user_account(**{field_name: invalid_value})


def test_user_account_rejects_inconsistent_or_naive_timestamps() -> None:
    with pytest.raises(InvariantViolationError):
        _user_account(updated_at=datetime(2026, 7, 28, 11, 59, tzinfo=UTC))
    with pytest.raises(InvalidDateTimeError):
        _user_account(created_at=datetime(2026, 7, 28, 12))


def test_user_account_is_immutable() -> None:
    account = _user_account()

    with pytest.raises(FrozenInstanceError):
        account.__setattr__("display_name", "Changed")


def test_membership_vocabularies_are_closed() -> None:
    assert {role.value for role in MembershipRole} == {
        "OWNER",
        "ADMIN",
        "ANALYST",
        "VIEWER",
    }
    assert {status.value for status in MembershipStatus} == {"ACTIVE", "INACTIVE"}


@pytest.mark.parametrize("role", list(MembershipRole))
def test_active_membership_accepts_every_role(role: MembershipRole) -> None:
    membership = _membership(role=role)

    assert membership.role is role
    assert membership.status is MembershipStatus.ACTIVE
    assert membership.deactivated_at is None
    assert membership.created_at == datetime(2026, 7, 28, 12, tzinfo=UTC)


def test_inactive_membership_preserves_tenant_and_normalizes_deactivation() -> None:
    workspace_id = WorkspaceId.new()
    user_id = UserId.new()

    membership = _membership(
        workspace_id=workspace_id,
        user_id=user_id,
        status=MembershipStatus.INACTIVE,
        updated_at=datetime(2026, 7, 28, 14, tzinfo=UTC),
        deactivated_at=datetime(
            2026,
            7,
            28,
            10,
            30,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
    )

    assert membership.workspace_id == workspace_id
    assert membership.user_id == user_id
    assert membership.deactivated_at == datetime(2026, 7, 28, 13, 30, tzinfo=UTC)


def test_membership_snapshots_preserve_workspace_isolation() -> None:
    user_id = UserId.new()
    first = _membership(workspace_id=WorkspaceId.new(), user_id=user_id)
    second = _membership(workspace_id=WorkspaceId.new(), user_id=user_id)

    assert first.user_id == second.user_id
    assert first.workspace_id != second.workspace_id


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("id", "membership"),
        ("workspace_id", "workspace"),
        ("user_id", "user"),
        ("role", "ANALYST"),
        ("status", "ACTIVE"),
    ],
)
def test_membership_rejects_untyped_fields(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(InvariantViolationError):
        _membership(**{field_name: invalid_value})


def test_membership_rejects_invalid_deactivation_combinations() -> None:
    with pytest.raises(InvariantViolationError):
        _membership(
            status=MembershipStatus.ACTIVE,
            deactivated_at=datetime(2026, 7, 28, 13, tzinfo=UTC),
        )
    with pytest.raises(InvariantViolationError):
        _membership(status=MembershipStatus.INACTIVE, deactivated_at=None)


def test_membership_rejects_inconsistent_or_naive_timestamps() -> None:
    with pytest.raises(InvariantViolationError):
        _membership(updated_at=datetime(2026, 7, 28, 11, 59, tzinfo=UTC))
    with pytest.raises(InvariantViolationError):
        _membership(
            status=MembershipStatus.INACTIVE,
            deactivated_at=datetime(2026, 7, 28, 11, 59, tzinfo=UTC),
        )
    with pytest.raises(InvalidDateTimeError):
        _membership(updated_at=datetime(2026, 7, 28, 13))
    with pytest.raises(InvalidDateTimeError):
        _membership(
            status=MembershipStatus.INACTIVE,
            deactivated_at=datetime(2026, 7, 28, 13),
        )


def test_membership_is_immutable() -> None:
    membership = _membership()

    with pytest.raises(FrozenInstanceError):
        membership.__setattr__("role", MembershipRole.VIEWER)


def test_change_role_returns_new_snapshot_and_preserves_identity_and_state() -> None:
    membership = _membership()
    changed_at = datetime(2026, 7, 28, 14, tzinfo=UTC)

    changed = membership.change_role(MembershipRole.VIEWER, updated_at=changed_at)

    assert changed is not membership
    assert changed.id == membership.id
    assert changed.workspace_id == membership.workspace_id
    assert changed.user_id == membership.user_id
    assert changed.role is MembershipRole.VIEWER
    assert changed.status is membership.status
    assert changed.deactivated_at is membership.deactivated_at
    assert changed.updated_at == changed_at
    assert membership.role is MembershipRole.ANALYST


def test_change_role_preserves_inactive_deactivation_snapshot() -> None:
    deactivated_at = datetime(2026, 7, 28, 14, tzinfo=UTC)
    membership = _membership(
        status=MembershipStatus.INACTIVE,
        updated_at=deactivated_at,
        deactivated_at=deactivated_at,
    )

    changed = membership.change_role(
        MembershipRole.VIEWER,
        updated_at=deactivated_at + timedelta(minutes=1),
    )

    assert changed.status is MembershipStatus.INACTIVE
    assert changed.deactivated_at == deactivated_at


def test_deactivate_and_reactivate_return_new_consistent_snapshots() -> None:
    membership = _membership()
    deactivated_at = datetime(2026, 7, 28, 14, tzinfo=UTC)

    inactive = membership.deactivate(updated_at=deactivated_at)
    active = inactive.reactivate(updated_at=deactivated_at + timedelta(minutes=1))

    assert inactive.id == membership.id == active.id
    assert inactive.status is MembershipStatus.INACTIVE
    assert inactive.deactivated_at == deactivated_at
    assert active.status is MembershipStatus.ACTIVE
    assert active.deactivated_at is None
    assert active.updated_at == deactivated_at + timedelta(minutes=1)


def test_membership_transitions_reject_invalid_state_role_and_regressive_time() -> None:
    membership = _membership()
    changed_at = datetime(2026, 7, 28, 14, tzinfo=UTC)
    inactive = membership.deactivate(updated_at=changed_at)

    with pytest.raises(InvariantViolationError, match="MembershipRole"):
        membership.change_role(cast(MembershipRole, "VIEWER"), updated_at=changed_at)
    with pytest.raises(InvariantViolationError, match="cannot regress"):
        membership.change_role(
            MembershipRole.VIEWER,
            updated_at=membership.updated_at - timedelta(seconds=1),
        )
    with pytest.raises(InvariantViolationError, match="active membership"):
        inactive.deactivate(updated_at=changed_at + timedelta(minutes=1))
    with pytest.raises(InvariantViolationError, match="inactive membership"):
        membership.reactivate(updated_at=changed_at)
    with pytest.raises(InvalidDateTimeError):
        membership.deactivate(updated_at=datetime(2026, 7, 28, 14))
