"""Investigation entity creation and persisted-snapshot invariants."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Self

from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.money import Money
from intelligence.domain.time import normalize_utc


class InvestigationState(StrEnum):
    """States defined by the investigation lifecycle specification."""

    CREATED = "CREATED"
    IDENTIFYING = "IDENTIFYING"
    WAITING_FOR_ENTITY_CONFIRMATION = "WAITING_FOR_ENTITY_CONFIRMATION"
    PLANNING = "PLANNING"
    COLLECTING = "COLLECTING"
    NORMALIZING = "NORMALIZING"
    VERIFYING = "VERIFYING"
    ANALYZING = "ANALYZING"
    WAITING_FOR_REVIEW = "WAITING_FOR_REVIEW"
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_INVESTIGATION_STATES = frozenset(
    {
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    }
)
INITIAL_STATE_VERSION = 1


@dataclass(frozen=True, slots=True, kw_only=True)
class Investigation:
    """Immutable investigation snapshot with an initial-only public constructor."""

    id: InvestigationId
    workspace_id: WorkspaceId
    requested_by: UserId
    profile_code: str
    country_code: CountryCode
    created_at: datetime
    state: InvestigationState = InvestigationState.CREATED
    state_version: int = INITIAL_STATE_VERSION
    confirmed_company_id: CompanyId | None = None
    budget: Money | None = None
    deadline_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        self._validate_and_normalize(is_reconstitution=False)

    @classmethod
    def reconstitute(
        cls,
        *,
        id: InvestigationId,
        workspace_id: WorkspaceId,
        requested_by: UserId,
        profile_code: str,
        country_code: CountryCode,
        created_at: datetime,
        state: InvestigationState,
        state_version: int,
        confirmed_company_id: CompanyId | None = None,
        budget: Money | None = None,
        deadline_at: datetime | None = None,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> Self:
        """Reconstitute a validated persisted snapshot without executing a transition.

        This is the only contract persistence adapters may use for non-initial states.
        The ordinary constructor remains restricted to a new ``CREATED`` snapshot.
        """

        snapshot = object.__new__(cls)
        values: dict[str, object] = {
            "id": id,
            "workspace_id": workspace_id,
            "requested_by": requested_by,
            "profile_code": profile_code,
            "country_code": country_code,
            "created_at": created_at,
            "state": state,
            "state_version": state_version,
            "confirmed_company_id": confirmed_company_id,
            "budget": budget,
            "deadline_at": deadline_at,
            "started_at": started_at,
            "completed_at": completed_at,
        }
        for field_name, value in values.items():
            object.__setattr__(snapshot, field_name, value)
        snapshot._validate_and_normalize(is_reconstitution=True)
        return snapshot

    def _validate_and_normalize(self, *, is_reconstitution: bool) -> None:
        _validate_types(self)
        profile_code = _required_text(self.profile_code)
        created_at = normalize_utc(self.created_at)
        deadline_at = _normalize_optional(self.deadline_at)
        started_at = _normalize_optional(self.started_at)
        completed_at = _normalize_optional(self.completed_at)

        if deadline_at is not None and deadline_at < created_at:
            raise InvariantViolationError("Investigation deadline_at cannot precede created_at.")
        if started_at is not None and started_at < created_at:
            raise InvariantViolationError("Investigation started_at cannot precede created_at.")
        if completed_at is not None:
            if started_at is None:
                raise InvariantViolationError("Investigation completed_at requires started_at.")
            if completed_at < started_at:
                raise InvariantViolationError(
                    "Investigation completed_at cannot precede started_at."
                )
        if self.state_version < INITIAL_STATE_VERSION:
            raise InvariantViolationError("Investigation state_version must be positive.")

        if is_reconstitution:
            _validate_persisted_state_timestamps(
                state=self.state,
                started_at=started_at,
                completed_at=completed_at,
            )
        else:
            if self.state is not InvestigationState.CREATED:
                raise InvariantViolationError(
                    "A new Investigation snapshot must start in the CREATED state."
                )
            if self.state_version != INITIAL_STATE_VERSION:
                raise InvariantViolationError(
                    "A new Investigation snapshot must start at state_version 1."
                )
            if completed_at is not None:
                raise InvariantViolationError(
                    "A new Investigation snapshot cannot define completed_at."
                )
            if started_at is not None:
                raise InvariantViolationError(
                    "An Investigation in CREATED state cannot define started_at."
                )

        object.__setattr__(self, "profile_code", profile_code)
        object.__setattr__(self, "created_at", created_at)
        object.__setattr__(self, "deadline_at", deadline_at)
        object.__setattr__(self, "started_at", started_at)
        object.__setattr__(self, "completed_at", completed_at)


def _validate_types(investigation: Investigation) -> None:
    expected_identifiers = (
        (investigation.id, InvestigationId, "id", "InvestigationId"),
        (investigation.workspace_id, WorkspaceId, "workspace_id", "WorkspaceId"),
        (investigation.requested_by, UserId, "requested_by", "UserId"),
    )
    for value, expected_type, field_name, type_name in expected_identifiers:
        if not isinstance(value, expected_type):
            raise InvariantViolationError(f"Investigation {field_name} must be a {type_name}.")
    if not isinstance(investigation.country_code, CountryCode):
        raise InvariantViolationError("Investigation country_code must be a CountryCode.")
    if not isinstance(investigation.state, InvestigationState):
        raise InvariantViolationError("Investigation state must be an InvestigationState.")
    if isinstance(investigation.state_version, bool) or not isinstance(
        investigation.state_version, int
    ):
        raise InvariantViolationError("Investigation state_version must be an integer.")
    if investigation.confirmed_company_id is not None and not isinstance(
        investigation.confirmed_company_id, CompanyId
    ):
        raise InvariantViolationError("Investigation confirmed_company_id must be a CompanyId.")
    if investigation.budget is not None and not isinstance(investigation.budget, Money):
        raise InvariantViolationError("Investigation budget must be Money.")


def _validate_persisted_state_timestamps(
    *,
    state: InvestigationState,
    started_at: datetime | None,
    completed_at: datetime | None,
) -> None:
    if state is InvestigationState.CREATED and started_at is not None:
        raise InvariantViolationError(
            "A persisted Investigation in CREATED state cannot define started_at."
        )
    if state is not InvestigationState.CREATED and started_at is None:
        raise InvariantViolationError(
            "A persisted Investigation outside CREATED state requires started_at."
        )

    is_terminal = state in TERMINAL_INVESTIGATION_STATES
    if is_terminal and completed_at is None:
        raise InvariantViolationError("A persisted terminal Investigation requires completed_at.")
    if not is_terminal and completed_at is not None:
        raise InvariantViolationError(
            "A persisted non-terminal Investigation cannot define completed_at."
        )


def _required_text(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvariantViolationError("Investigation profile_code must be a non-empty string.")
    return value.strip()


def _normalize_optional(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return normalize_utc(value)


__all__ = [
    "INITIAL_STATE_VERSION",
    "TERMINAL_INVESTIGATION_STATES",
    "Investigation",
    "InvestigationState",
]
