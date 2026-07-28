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
