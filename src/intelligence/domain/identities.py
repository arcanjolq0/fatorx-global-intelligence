"""Internal identities and workspace membership snapshots."""

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum
from unicodedata import category

from intelligence.domain.errors import InvalidEmailAddressError, InvariantViolationError
from intelligence.domain.identifiers import MembershipId, UserId, WorkspaceId
from intelligence.domain.time import normalize_utc

EMAIL_ADDRESS_MAX_LENGTH = 254


@dataclass(frozen=True, slots=True)
class EmailAddress:
    """Minimal canonical email identity without network or full RFC validation."""

    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str):
            raise InvalidEmailAddressError("EmailAddress must be provided as text.")
        if any(category(character) == "Cc" for character in self.value):
            raise InvalidEmailAddressError("EmailAddress cannot contain control characters.")

        canonical = self.value.strip().lower()
        if not canonical:
            raise InvalidEmailAddressError("EmailAddress cannot be empty.")
        if len(canonical) > EMAIL_ADDRESS_MAX_LENGTH:
            raise InvalidEmailAddressError(
                f"EmailAddress cannot exceed {EMAIL_ADDRESS_MAX_LENGTH} characters."
            )
        if any(character.isspace() for character in canonical):
            raise InvalidEmailAddressError("EmailAddress cannot contain internal whitespace.")
        if canonical.count("@") != 1:
            raise InvalidEmailAddressError(
                "EmailAddress must contain one local part and one domain."
            )
        local_part, domain = canonical.split("@", maxsplit=1)
        if not local_part or not domain:
            raise InvalidEmailAddressError(
                "EmailAddress must contain one local part and one domain."
            )

        object.__setattr__(self, "value", canonical)

    def __str__(self) -> str:
        return self.value


class UserAccountStatus(StrEnum):
    """Operational state of an internal identity, not authentication state."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


@dataclass(frozen=True, slots=True, kw_only=True)
class UserAccount:
    """Immutable internal identity without credentials or authentication data."""

    id: UserId
    email: EmailAddress
    display_name: str
    status: UserAccountStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.id, UserId):
            raise InvariantViolationError("UserAccount id must be a UserId.")
        if not isinstance(self.email, EmailAddress):
            raise InvariantViolationError("UserAccount email must be an EmailAddress.")
        if not isinstance(self.status, UserAccountStatus):
            raise InvariantViolationError("UserAccount status must be a UserAccountStatus.")

        display_name = _required_text(self.display_name, field_name="UserAccount display_name")
        created_at = normalize_utc(self.created_at)
        updated_at = normalize_utc(self.updated_at)
        if updated_at < created_at:
            raise InvariantViolationError("UserAccount updated_at cannot precede created_at.")

        object.__setattr__(self, "display_name", display_name)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)


class MembershipRole(StrEnum):
    """Persisted role vocabulary without an applied permission matrix."""

    OWNER = "OWNER"
    ADMIN = "ADMIN"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class MembershipStatus(StrEnum):
    """Lifecycle state represented by a membership snapshot."""

    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


@dataclass(frozen=True, slots=True, kw_only=True)
class WorkspaceMembership:
    """Immutable snapshot linking one internal user to one workspace."""

    id: MembershipId
    workspace_id: WorkspaceId
    user_id: UserId
    role: MembershipRole
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
    deactivated_at: datetime | None = None

    def __post_init__(self) -> None:
        _validate_membership_types(self)
        created_at = normalize_utc(self.created_at)
        updated_at = normalize_utc(self.updated_at)
        deactivated_at = (
            normalize_utc(self.deactivated_at) if self.deactivated_at is not None else None
        )

        if updated_at < created_at:
            raise InvariantViolationError(
                "WorkspaceMembership updated_at cannot precede created_at."
            )
        if deactivated_at is not None and deactivated_at < created_at:
            raise InvariantViolationError(
                "WorkspaceMembership deactivated_at cannot precede created_at."
            )
        if self.status is MembershipStatus.ACTIVE and deactivated_at is not None:
            raise InvariantViolationError(
                "An active WorkspaceMembership cannot define deactivated_at."
            )
        if self.status is MembershipStatus.INACTIVE and deactivated_at is None:
            raise InvariantViolationError(
                "An inactive WorkspaceMembership must define deactivated_at."
            )

        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "updated_at", updated_at)
        object.__setattr__(self, "deactivated_at", deactivated_at)

    def change_role(
        self,
        new_role: MembershipRole,
        *,
        updated_at: datetime,
    ) -> WorkspaceMembership:
        """Return a new snapshot with another role and stable identity."""

        if not isinstance(new_role, MembershipRole):
            raise InvariantViolationError("New membership role must be a MembershipRole.")
        changed_at = _non_regressive_timestamp(updated_at, current=self.updated_at)
        return replace(self, role=new_role, updated_at=changed_at)

    def deactivate(self, *, updated_at: datetime) -> WorkspaceMembership:
        """Return an inactive snapshot without mutating the current one."""

        if self.status is not MembershipStatus.ACTIVE:
            raise InvariantViolationError("Only an active membership can be deactivated.")
        changed_at = _non_regressive_timestamp(updated_at, current=self.updated_at)
        return replace(
            self,
            status=MembershipStatus.INACTIVE,
            updated_at=changed_at,
            deactivated_at=changed_at,
        )

    def reactivate(self, *, updated_at: datetime) -> WorkspaceMembership:
        """Return an active snapshot and clear the previous deactivation timestamp."""

        if self.status is not MembershipStatus.INACTIVE:
            raise InvariantViolationError("Only an inactive membership can be reactivated.")
        changed_at = _non_regressive_timestamp(updated_at, current=self.updated_at)
        return replace(
            self,
            status=MembershipStatus.ACTIVE,
            updated_at=changed_at,
            deactivated_at=None,
        )


def _validate_membership_types(membership: WorkspaceMembership) -> None:
    if not isinstance(membership.id, MembershipId):
        raise InvariantViolationError("WorkspaceMembership id must be a MembershipId.")
    if not isinstance(membership.workspace_id, WorkspaceId):
        raise InvariantViolationError("WorkspaceMembership workspace_id must be a WorkspaceId.")
    if not isinstance(membership.user_id, UserId):
        raise InvariantViolationError("WorkspaceMembership user_id must be a UserId.")
    if not isinstance(membership.role, MembershipRole):
        raise InvariantViolationError("WorkspaceMembership role must be a MembershipRole.")
    if not isinstance(membership.status, MembershipStatus):
        raise InvariantViolationError("WorkspaceMembership status must be a MembershipStatus.")


def _non_regressive_timestamp(value: datetime, *, current: datetime) -> datetime:
    normalized = normalize_utc(value)
    if normalized < current:
        raise InvariantViolationError("Membership transition timestamp cannot regress.")
    return normalized


def _required_text(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvariantViolationError(f"{field_name} must be a non-empty string.")
    return value.strip()


__all__ = [
    "EMAIL_ADDRESS_MAX_LENGTH",
    "EmailAddress",
    "MembershipRole",
    "MembershipStatus",
    "UserAccount",
    "UserAccountStatus",
    "WorkspaceMembership",
]
