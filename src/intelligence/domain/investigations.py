"""Investigation snapshots, persisted invariants, and explicit lifecycle transitions."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Self

from intelligence.domain.errors import (
    InvalidInvestigationTransitionError,
    InvariantViolationError,
)
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    EntityCandidateBatchId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import IdentificationInput
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
    identification_input: IdentificationInput | None = field(default=None, repr=False)
    active_candidate_batch_id: EntityCandidateBatchId | None = None

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
        identification_input: IdentificationInput | None = None,
        active_candidate_batch_id: EntityCandidateBatchId | None = None,
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
            "identification_input": identification_input,
            "active_candidate_batch_id": active_candidate_batch_id,
        }
        for field_name, value in values.items():
            object.__setattr__(snapshot, field_name, value)
        snapshot._validate_and_normalize(is_reconstitution=True)
        return snapshot

    def start_identification(
        self,
        *,
        identification_input: IdentificationInput,
        occurred_at: datetime,
    ) -> InvestigationTransitionResult:
        """Return the immutable ``CREATED -> IDENTIFYING`` transition result."""

        if self.state is not InvestigationState.CREATED:
            raise InvalidInvestigationTransitionError(
                "Identification can start only from the CREATED state."
            )
        if not isinstance(identification_input, IdentificationInput):
            raise InvalidInvestigationTransitionError(
                "Identification input must use the supported typed contract."
            )
        identification_input.validate_for(
            investigation_country_code=self.country_code,
            has_confirmed_company=self.confirmed_company_id is not None,
        )
        transition_at = _non_regressive_transition_time(
            occurred_at,
            created_at=self.created_at,
            started_at=None,
        )
        updated = Investigation.reconstitute(
            id=self.id,
            workspace_id=self.workspace_id,
            requested_by=self.requested_by,
            profile_code=self.profile_code,
            country_code=self.country_code,
            created_at=self.created_at,
            state=InvestigationState.IDENTIFYING,
            state_version=self.state_version + 1,
            confirmed_company_id=self.confirmed_company_id,
            budget=self.budget,
            deadline_at=self.deadline_at,
            started_at=transition_at,
            completed_at=None,
            identification_input=identification_input,
            active_candidate_batch_id=None,
        )
        return _transition_result(previous=self, current=updated, occurred_at=transition_at)

    def request_entity_confirmation(
        self,
        *,
        candidate_batch_id: EntityCandidateBatchId,
        occurred_at: datetime,
    ) -> InvestigationTransitionResult:
        """Pause an identifying investigation for a future human decision."""

        if self.state is not InvestigationState.IDENTIFYING:
            raise InvalidInvestigationTransitionError(
                "Entity confirmation can be requested only from the IDENTIFYING state."
            )
        if not isinstance(candidate_batch_id, EntityCandidateBatchId):
            raise InvalidInvestigationTransitionError("Candidate batch ID must be typed.")
        if self.identification_input is None:
            raise InvalidInvestigationTransitionError(
                "Entity confirmation requires the persisted identification input."
            )
        if self.confirmed_company_id is not None:
            raise InvalidInvestigationTransitionError(
                "Entity confirmation cannot be requested for a confirmed company."
            )
        transition_at = _non_regressive_transition_time(
            occurred_at,
            created_at=self.created_at,
            started_at=self.started_at,
        )
        updated = Investigation.reconstitute(
            id=self.id,
            workspace_id=self.workspace_id,
            requested_by=self.requested_by,
            profile_code=self.profile_code,
            country_code=self.country_code,
            created_at=self.created_at,
            state=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
            state_version=self.state_version + 1,
            confirmed_company_id=None,
            budget=self.budget,
            deadline_at=self.deadline_at,
            started_at=self.started_at,
            completed_at=None,
            identification_input=self.identification_input,
            active_candidate_batch_id=candidate_batch_id,
        )
        return _transition_result(previous=self, current=updated, occurred_at=transition_at)

    def confirm_entity(
        self,
        *,
        company_id: CompanyId,
        candidate_batch_id: EntityCandidateBatchId,
        occurred_at: datetime,
    ) -> InvestigationTransitionResult:
        """Return the explicit human-confirmation transition to ``PLANNING``."""

        if self.state is not InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION:
            raise InvalidInvestigationTransitionError(
                "An entity can be confirmed only while confirmation is pending."
            )
        if not isinstance(company_id, CompanyId):
            raise InvalidInvestigationTransitionError("Confirmed company ID must be typed.")
        if not isinstance(candidate_batch_id, EntityCandidateBatchId):
            raise InvalidInvestigationTransitionError("Candidate batch ID must be typed.")
        if self.active_candidate_batch_id is None:
            raise InvalidInvestigationTransitionError(
                "Entity confirmation requires an active candidate batch."
            )
        if candidate_batch_id != self.active_candidate_batch_id:
            raise InvalidInvestigationTransitionError(
                "Entity confirmation must target the active candidate batch."
            )
        if self.confirmed_company_id is not None:
            raise InvalidInvestigationTransitionError(
                "The Investigation already has a confirmed company."
            )
        transition_at = _non_regressive_transition_time(
            occurred_at,
            created_at=self.created_at,
            started_at=self.started_at,
        )
        updated = Investigation.reconstitute(
            id=self.id,
            workspace_id=self.workspace_id,
            requested_by=self.requested_by,
            profile_code=self.profile_code,
            country_code=self.country_code,
            created_at=self.created_at,
            state=InvestigationState.PLANNING,
            state_version=self.state_version + 1,
            confirmed_company_id=company_id,
            budget=self.budget,
            deadline_at=self.deadline_at,
            started_at=self.started_at,
            completed_at=None,
            identification_input=self.identification_input,
            active_candidate_batch_id=None,
        )
        return _transition_result(previous=self, current=updated, occurred_at=transition_at)

    def cancel(self, *, occurred_at: datetime) -> InvestigationTransitionResult:
        """Return a terminal cancellation from any non-terminal state."""

        if self.state in TERMINAL_INVESTIGATION_STATES:
            raise InvalidInvestigationTransitionError(
                "A terminal Investigation cannot be cancelled or reopened."
            )
        transition_at = _non_regressive_transition_time(
            occurred_at,
            created_at=self.created_at,
            started_at=self.started_at,
        )
        started_at = self.started_at if self.started_at is not None else transition_at
        updated = Investigation.reconstitute(
            id=self.id,
            workspace_id=self.workspace_id,
            requested_by=self.requested_by,
            profile_code=self.profile_code,
            country_code=self.country_code,
            created_at=self.created_at,
            state=InvestigationState.CANCELLED,
            state_version=self.state_version + 1,
            confirmed_company_id=self.confirmed_company_id,
            budget=self.budget,
            deadline_at=self.deadline_at,
            started_at=started_at,
            completed_at=transition_at,
            identification_input=self.identification_input,
            active_candidate_batch_id=None,
        )
        return _transition_result(previous=self, current=updated, occurred_at=transition_at)

    def start_collection(self, *, occurred_at: datetime) -> InvestigationTransitionResult:
        """Return the explicit ``PLANNING -> COLLECTING`` activation transition."""

        if self.state is not InvestigationState.PLANNING:
            raise InvalidInvestigationTransitionError(
                "Collection can start only from the PLANNING state."
            )
        if self.confirmed_company_id is None:
            raise InvalidInvestigationTransitionError("Collection requires a confirmed Company.")
        if self.active_candidate_batch_id is not None:
            raise InvalidInvestigationTransitionError(
                "Collection cannot start with an active candidate batch."
            )
        transition_at = _non_regressive_transition_time(
            occurred_at,
            created_at=self.created_at,
            started_at=self.started_at,
        )
        updated = Investigation.reconstitute(
            id=self.id,
            workspace_id=self.workspace_id,
            requested_by=self.requested_by,
            profile_code=self.profile_code,
            country_code=self.country_code,
            created_at=self.created_at,
            state=InvestigationState.COLLECTING,
            state_version=self.state_version + 1,
            confirmed_company_id=self.confirmed_company_id,
            budget=self.budget,
            deadline_at=self.deadline_at,
            started_at=self.started_at,
            completed_at=None,
            identification_input=self.identification_input,
            active_candidate_batch_id=None,
        )
        return _transition_result(previous=self, current=updated, occurred_at=transition_at)

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

        if self.identification_input is not None:
            self.identification_input.validate_for(
                investigation_country_code=self.country_code,
                has_confirmed_company=self.confirmed_company_id is not None,
            )
        if self.state is InvestigationState.CREATED and self.identification_input is not None:
            raise InvariantViolationError(
                "An Investigation in CREATED state cannot define identification input."
            )
        if (
            self.state is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
            and self.active_candidate_batch_id is None
        ):
            raise InvariantViolationError(
                "An Investigation waiting for entity confirmation requires an active batch."
            )
        if (
            self.state is not InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
            and self.active_candidate_batch_id is not None
        ):
            raise InvariantViolationError(
                "Only an Investigation waiting for entity confirmation can reference a batch."
            )
        _validate_entity_confirmation_state(
            state=self.state,
            confirmed_company_id=self.confirmed_company_id,
        )
        if (
            not is_reconstitution
            and self.state not in {InvestigationState.CREATED, InvestigationState.CANCELLED}
            and self.identification_input is None
            and self.confirmed_company_id is None
        ):
            raise InvariantViolationError(
                "A started Investigation requires identification input or a confirmed company."
            )

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
    if investigation.identification_input is not None and not isinstance(
        investigation.identification_input, IdentificationInput
    ):
        raise InvariantViolationError(
            "Investigation identification_input must be an IdentificationInput."
        )
    if investigation.active_candidate_batch_id is not None and not isinstance(
        investigation.active_candidate_batch_id, EntityCandidateBatchId
    ):
        raise InvariantViolationError(
            "Investigation active_candidate_batch_id must be an EntityCandidateBatchId."
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class InvestigationTransition:
    """Pure domain event describing one effective state-version change."""

    investigation_id: InvestigationId
    state_before: InvestigationState
    version_before: int
    state_after: InvestigationState
    version_after: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.investigation_id, InvestigationId):
            raise InvariantViolationError(
                "InvestigationTransition investigation_id must be an InvestigationId."
            )
        if not isinstance(self.state_before, InvestigationState) or not isinstance(
            self.state_after, InvestigationState
        ):
            raise InvariantViolationError(
                "InvestigationTransition states must use InvestigationState."
            )
        if (
            isinstance(self.version_before, bool)
            or not isinstance(self.version_before, int)
            or isinstance(self.version_after, bool)
            or not isinstance(self.version_after, int)
            or self.version_before < INITIAL_STATE_VERSION
            or self.version_after != self.version_before + 1
        ):
            raise InvariantViolationError(
                "InvestigationTransition must increment state_version exactly once."
            )
        object.__setattr__(self, "occurred_at", normalize_utc(self.occurred_at))


@dataclass(frozen=True, slots=True, kw_only=True)
class InvestigationTransitionResult:
    """New immutable aggregate snapshot paired with its typed domain event."""

    investigation: Investigation
    transition: InvestigationTransition

    def __post_init__(self) -> None:
        if not isinstance(self.investigation, Investigation) or not isinstance(
            self.transition, InvestigationTransition
        ):
            raise InvariantViolationError(
                "InvestigationTransitionResult requires typed snapshot and transition."
            )
        if (
            self.investigation.id != self.transition.investigation_id
            or self.investigation.state is not self.transition.state_after
            or self.investigation.state_version != self.transition.version_after
        ):
            raise InvariantViolationError(
                "InvestigationTransitionResult snapshot and event are inconsistent."
            )


def _transition_result(
    *,
    previous: Investigation,
    current: Investigation,
    occurred_at: datetime,
) -> InvestigationTransitionResult:
    return InvestigationTransitionResult(
        investigation=current,
        transition=InvestigationTransition(
            investigation_id=previous.id,
            state_before=previous.state,
            version_before=previous.state_version,
            state_after=current.state,
            version_after=current.state_version,
            occurred_at=occurred_at,
        ),
    )


def _non_regressive_transition_time(
    value: datetime,
    *,
    created_at: datetime,
    started_at: datetime | None,
) -> datetime:
    occurred_at = normalize_utc(value)
    if occurred_at < created_at or (started_at is not None and occurred_at < started_at):
        raise InvalidInvestigationTransitionError(
            "Investigation transition timestamp cannot regress."
        )
    return occurred_at


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


def _validate_entity_confirmation_state(
    *,
    state: InvestigationState,
    confirmed_company_id: CompanyId | None,
) -> None:
    before_confirmation = {
        InvestigationState.CREATED,
        InvestigationState.IDENTIFYING,
        InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
    }
    after_confirmation = {
        InvestigationState.PLANNING,
        InvestigationState.COLLECTING,
        InvestigationState.NORMALIZING,
        InvestigationState.VERIFYING,
        InvestigationState.ANALYZING,
        InvestigationState.WAITING_FOR_REVIEW,
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
    }
    if state in before_confirmation and confirmed_company_id is not None:
        raise InvariantViolationError(
            "An Investigation cannot reference a confirmed company before confirmation."
        )
    if state in after_confirmation and confirmed_company_id is None:
        raise InvariantViolationError(
            "An Investigation after entity confirmation requires a confirmed company."
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
    "InvestigationTransition",
    "InvestigationTransitionResult",
]
