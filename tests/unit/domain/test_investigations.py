"""Tests for investigation initial snapshots and lifecycle vocabulary."""

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest

from intelligence.domain.errors import DomainError, InvalidDateTimeError, InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    EntityCandidateBatchId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.investigation_inputs import (
    BusinessIdentifierInput,
    BusinessIdentifierType,
    CorporateDomainInput,
    IdentificationInput,
    OriginalAndNormalizedText,
)
from intelligence.domain.investigations import (
    INITIAL_STATE_VERSION,
    TERMINAL_INVESTIGATION_STATES,
    Investigation,
    InvestigationState,
)
from intelligence.domain.money import CurrencyCode, Money


def _investigation(**overrides: object) -> Investigation:
    values: dict[str, object] = {
        "id": InvestigationId.new(),
        "workspace_id": WorkspaceId.new(),
        "requested_by": UserId.new(),
        "profile_code": "  SUPPLIER_STANDARD  ",
        "country_code": CountryCode("BR"),
        "created_at": datetime(
            2026,
            7,
            25,
            9,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "confirmed_company_id": None,
        "budget": Money(Decimal("250.00"), CurrencyCode("BRL")),
        "deadline_at": datetime(2026, 7, 30, 12, tzinfo=UTC),
    }
    values.update(overrides)
    return Investigation(**cast(Any, values))


def _reconstituted_investigation(**overrides: object) -> Investigation:
    values: dict[str, object] = {
        "id": InvestigationId.new(),
        "workspace_id": WorkspaceId.new(),
        "requested_by": UserId.new(),
        "profile_code": "  SUPPLIER_STANDARD  ",
        "country_code": CountryCode("BR"),
        "created_at": datetime(2026, 7, 25, 12, tzinfo=UTC),
        "state": InvestigationState.IDENTIFYING,
        "state_version": 2,
        "started_at": datetime(
            2026,
            7,
            25,
            10,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "identification_input": _identification_input(),
    }
    values.update(overrides)
    return Investigation.reconstitute(**cast(Any, values))


def _identification_input() -> IdentificationInput:
    return IdentificationInput(
        legal_name=OriginalAndNormalizedText(
            original_value="Empresa Exemplo S.A.",
            normalized_value="empresa exemplo sa",
        ),
        identifiers=(
            BusinessIdentifierInput(
                identifier_type=BusinessIdentifierType.BUSINESS_REGISTRATION,
                original_value="12.345.678/0001-90",
                normalized_value="12345678000190",
                jurisdiction_country_code=CountryCode("BR"),
            ),
        ),
        corporate_domain=CorporateDomainInput(
            original_value="Empresa.Example",
            normalized_value="empresa.example",
        ),
    )


def test_investigation_starts_created_at_version_one_and_normalizes_time() -> None:
    investigation = _investigation()

    assert investigation.state is InvestigationState.CREATED
    assert investigation.state_version == INITIAL_STATE_VERSION == 1
    assert investigation.profile_code == "SUPPLIER_STANDARD"
    assert investigation.created_at == datetime(2026, 7, 25, 12, tzinfo=UTC)
    assert investigation.completed_at is None


def test_created_investigation_cannot_reference_existing_company() -> None:
    with pytest.raises(InvariantViolationError, match="before confirmation"):
        _investigation(confirmed_company_id=CompanyId.new())


def test_investigation_state_vocabulary_matches_documented_lifecycle() -> None:
    assert {state.value for state in InvestigationState} == {
        "CREATED",
        "IDENTIFYING",
        "WAITING_FOR_ENTITY_CONFIRMATION",
        "PLANNING",
        "COLLECTING",
        "NORMALIZING",
        "VERIFYING",
        "ANALYZING",
        "WAITING_FOR_REVIEW",
        "COMPLETED",
        "PARTIALLY_COMPLETED",
        "FAILED",
        "CANCELLED",
    }
    assert {
        InvestigationState.COMPLETED,
        InvestigationState.PARTIALLY_COMPLETED,
        InvestigationState.FAILED,
        InvestigationState.CANCELLED,
    } == TERMINAL_INVESTIGATION_STATES


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("id", "investigation"),
        ("workspace_id", "workspace"),
        ("requested_by", "user"),
        ("country_code", "BR"),
        ("state", "CREATED"),
        ("confirmed_company_id", "company"),
        ("budget", Decimal("1")),
    ],
)
def test_investigation_rejects_untyped_domain_fields(
    field_name: str,
    invalid_value: object,
) -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(**{field_name: invalid_value})


def test_investigation_requires_profile_and_initial_state_version() -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(profile_code="  ")
    with pytest.raises(InvariantViolationError):
        _investigation(state=InvestigationState.IDENTIFYING)
    with pytest.raises(InvariantViolationError):
        _investigation(state_version=2)
    with pytest.raises(InvariantViolationError):
        _investigation(state_version=cast(int, True))


def test_investigation_rejects_inconsistent_timestamps() -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(started_at=datetime(2026, 7, 25, 11, tzinfo=UTC))
    with pytest.raises(InvariantViolationError):
        _investigation(
            started_at=None,
            completed_at=datetime(2026, 7, 25, 13, tzinfo=UTC),
        )
    with pytest.raises(InvariantViolationError):
        _investigation(
            started_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
            completed_at=datetime(2026, 7, 25, 13, tzinfo=UTC),
        )
    with pytest.raises(InvariantViolationError):
        _investigation(
            completed_at=datetime(2026, 7, 25, 13, tzinfo=UTC),
        )
    with pytest.raises(InvalidDateTimeError):
        _investigation(deadline_at=datetime(2026, 7, 30, 12))


def test_created_investigation_rejects_started_at_and_expired_deadline() -> None:
    with pytest.raises(InvariantViolationError):
        _investigation(started_at=datetime(2026, 7, 25, 12, 1, tzinfo=UTC))
    with pytest.raises(InvariantViolationError):
        _investigation(deadline_at=datetime(2026, 7, 25, 11, 59, tzinfo=UTC))


def test_reconstitution_accepts_valid_non_initial_snapshot_and_normalizes_it() -> None:
    investigation = _reconstituted_investigation()

    assert investigation.state is InvestigationState.IDENTIFYING
    assert investigation.state_version == 2
    assert investigation.profile_code == "SUPPLIER_STANDARD"
    assert investigation.started_at == datetime(2026, 7, 25, 13, tzinfo=UTC)


@pytest.mark.parametrize("state", sorted(TERMINAL_INVESTIGATION_STATES, key=str))
def test_reconstitution_accepts_every_terminal_state(state: InvestigationState) -> None:
    completed_at = datetime(2026, 7, 25, 14, tzinfo=UTC)

    investigation = _reconstituted_investigation(
        state=state,
        state_version=7,
        completed_at=completed_at,
        confirmed_company_id=(
            CompanyId.new()
            if state in {InvestigationState.COMPLETED, InvestigationState.PARTIALLY_COMPLETED}
            else None
        ),
    )

    assert investigation.state is state
    assert investigation.completed_at == completed_at


def test_reconstitution_accepts_created_snapshot_without_relaxing_creation() -> None:
    investigation = _reconstituted_investigation(
        state=InvestigationState.CREATED,
        state_version=1,
        started_at=None,
        identification_input=None,
    )

    assert investigation.state is InvestigationState.CREATED
    assert investigation.started_at is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"state_version": 0},
        {"state": InvestigationState.CREATED},
        {"started_at": None},
        {"completed_at": datetime(2026, 7, 25, 14, tzinfo=UTC)},
        {
            "state": InvestigationState.COMPLETED,
            "completed_at": None,
        },
        {
            "state": InvestigationState.COMPLETED,
            "completed_at": datetime(2026, 7, 25, 12, 59, tzinfo=UTC),
        },
    ],
)
def test_reconstitution_rejects_inconsistent_persisted_snapshots(
    overrides: dict[str, object],
) -> None:
    with pytest.raises(InvariantViolationError):
        _reconstituted_investigation(**overrides)


def test_start_identification_returns_new_snapshot_and_typed_transition() -> None:
    original = _investigation(confirmed_company_id=None)
    identification_input = _identification_input()
    occurred_at = original.created_at + timedelta(minutes=1)

    result = original.start_identification(
        identification_input=identification_input,
        occurred_at=occurred_at,
    )

    assert original.state is InvestigationState.CREATED
    assert original.state_version == 1
    assert original.started_at is None
    assert original.identification_input is None
    assert result.investigation.state is InvestigationState.IDENTIFYING
    assert result.investigation.state_version == 2
    assert result.investigation.started_at == occurred_at
    assert result.investigation.completed_at is None
    assert result.investigation.identification_input is identification_input
    assert result.transition.state_before is InvestigationState.CREATED
    assert result.transition.state_after is InvestigationState.IDENTIFYING
    assert result.transition.version_before == 1
    assert result.transition.version_after == 2


def test_start_identification_requires_created_and_non_regressive_time() -> None:
    started = _reconstituted_investigation()

    with pytest.raises(InvariantViolationError):
        started.start_identification(
            identification_input=_identification_input(),
            occurred_at=started.started_at or started.created_at,
        )
    original = _investigation(confirmed_company_id=None)
    with pytest.raises(DomainError):
        original.start_identification(
            identification_input=_identification_input(),
            occurred_at=original.created_at - timedelta(microseconds=1),
        )


def test_identification_without_company_requires_a_usable_input() -> None:
    original = _investigation()

    with pytest.raises(DomainError):
        original.start_identification(
            identification_input=IdentificationInput(),
            occurred_at=original.created_at,
        )


def test_cancel_created_sets_equal_start_and_completion_timestamps() -> None:
    original = _investigation(confirmed_company_id=None)
    occurred_at = original.created_at + timedelta(minutes=1)

    result = original.cancel(occurred_at=occurred_at)

    assert original.state is InvestigationState.CREATED
    assert result.investigation.state is InvestigationState.CANCELLED
    assert result.investigation.state_version == 2
    assert result.investigation.started_at == occurred_at
    assert result.investigation.completed_at == occurred_at
    assert result.investigation.identification_input is None


def test_cancel_started_preserves_start_and_frozen_input() -> None:
    started = _reconstituted_investigation()
    occurred_at = (started.started_at or started.created_at) + timedelta(minutes=1)

    result = started.cancel(occurred_at=occurred_at)

    assert result.investigation.state is InvestigationState.CANCELLED
    assert result.investigation.state_version == started.state_version + 1
    assert result.investigation.started_at == started.started_at
    assert result.investigation.completed_at == occurred_at
    assert result.investigation.identification_input is started.identification_input


def test_request_entity_confirmation_is_specific_immutable_and_preserves_input() -> None:
    started = _reconstituted_investigation(confirmed_company_id=None)
    batch_id = EntityCandidateBatchId.new()
    occurred_at = (started.started_at or started.created_at) + timedelta(minutes=1)

    result = started.request_entity_confirmation(
        candidate_batch_id=batch_id,
        occurred_at=occurred_at,
    )

    assert started.state is InvestigationState.IDENTIFYING
    assert started.active_candidate_batch_id is None
    assert result.investigation.state is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
    assert result.investigation.state_version == started.state_version + 1
    assert result.investigation.active_candidate_batch_id == batch_id
    assert result.investigation.identification_input is started.identification_input
    assert result.investigation.started_at == started.started_at
    assert result.investigation.completed_at is None
    assert result.investigation.confirmed_company_id is None
    assert result.transition.state_before is InvestigationState.IDENTIFYING
    assert result.transition.state_after is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION


def test_candidate_batch_state_consistency_and_source_state_are_enforced() -> None:
    batch_id = EntityCandidateBatchId.new()
    with pytest.raises(InvariantViolationError):
        _reconstituted_investigation(
            state=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
            active_candidate_batch_id=None,
        )
    with pytest.raises(InvariantViolationError):
        _reconstituted_investigation(active_candidate_batch_id=batch_id)
    with pytest.raises(InvariantViolationError):
        _reconstituted_investigation().request_entity_confirmation(
            candidate_batch_id=cast(EntityCandidateBatchId, "batch"),
            occurred_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
        )

    waiting = _reconstituted_investigation(
        state=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
        active_candidate_batch_id=batch_id,
    )
    with pytest.raises(InvariantViolationError):
        waiting.request_entity_confirmation(
            candidate_batch_id=EntityCandidateBatchId.new(),
            occurred_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
        )


def test_confirm_entity_is_specific_immutable_and_preserves_frozen_context() -> None:
    batch_id = EntityCandidateBatchId.new()
    company_id = CompanyId.new()
    waiting = _reconstituted_investigation(
        state=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
        state_version=3,
        active_candidate_batch_id=batch_id,
    )
    occurred_at = (waiting.started_at or waiting.created_at) + timedelta(minutes=2)

    result = waiting.confirm_entity(
        company_id=company_id,
        candidate_batch_id=batch_id,
        occurred_at=occurred_at,
    )

    assert waiting.state is InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION
    assert waiting.active_candidate_batch_id == batch_id
    assert result.investigation.state is InvestigationState.PLANNING
    assert result.investigation.state_version == 4
    assert result.investigation.confirmed_company_id == company_id
    assert result.investigation.active_candidate_batch_id is None
    assert result.investigation.started_at == waiting.started_at
    assert result.investigation.identification_input is waiting.identification_input
    assert result.investigation.budget == waiting.budget
    assert result.investigation.deadline_at == waiting.deadline_at
    assert result.investigation.completed_at is None


def test_confirm_entity_rejects_wrong_batch_untyped_company_and_invalid_state() -> None:
    batch_id = EntityCandidateBatchId.new()
    waiting = _reconstituted_investigation(
        state=InvestigationState.WAITING_FOR_ENTITY_CONFIRMATION,
        state_version=3,
        active_candidate_batch_id=batch_id,
    )
    for company_id, candidate_batch_id in (
        (CompanyId.new(), EntityCandidateBatchId.new()),
        (cast(CompanyId, "company"), batch_id),
    ):
        with pytest.raises(InvariantViolationError):
            waiting.confirm_entity(
                company_id=company_id,
                candidate_batch_id=candidate_batch_id,
                occurred_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
            )
    with pytest.raises(InvariantViolationError):
        _reconstituted_investigation().confirm_entity(
            company_id=CompanyId.new(),
            candidate_batch_id=batch_id,
            occurred_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
        )


def test_start_collection_is_specific_immutable_and_preserves_confirmed_context() -> None:
    planning = _reconstituted_investigation(
        state=InvestigationState.PLANNING,
        state_version=4,
        confirmed_company_id=CompanyId.new(),
    )
    occurred_at = datetime(2026, 7, 25, 15, tzinfo=UTC)

    result = planning.start_collection(occurred_at=occurred_at)

    assert planning.state is InvestigationState.PLANNING
    assert result.investigation.state is InvestigationState.COLLECTING
    assert result.investigation.state_version == 5
    assert result.investigation.confirmed_company_id == planning.confirmed_company_id
    assert result.investigation.started_at == planning.started_at
    assert result.investigation.completed_at is None
    assert result.transition.state_before is InvestigationState.PLANNING
    assert result.transition.state_after is InvestigationState.COLLECTING


def test_start_collection_rejects_missing_company_active_batch_or_wrong_state() -> None:
    occurred_at = datetime(2026, 7, 25, 15, tzinfo=UTC)
    missing_company = _reconstituted_investigation(
        state=InvestigationState.PLANNING,
        state_version=4,
        confirmed_company_id=CompanyId.new(),
    )
    active_batch = _reconstituted_investigation(
        state=InvestigationState.PLANNING,
        state_version=4,
        confirmed_company_id=CompanyId.new(),
    )
    object.__setattr__(missing_company, "confirmed_company_id", None)
    object.__setattr__(active_batch, "active_candidate_batch_id", EntityCandidateBatchId.new())
    invalid = (missing_company, active_batch, _reconstituted_investigation())
    for investigation in invalid:
        with pytest.raises(InvariantViolationError):
            investigation.start_collection(occurred_at=occurred_at)


@pytest.mark.parametrize("state", sorted(TERMINAL_INVESTIGATION_STATES, key=str))
def test_terminal_investigation_cannot_cancel_or_reopen(state: InvestigationState) -> None:
    terminal = _reconstituted_investigation(
        state=state,
        completed_at=datetime(2026, 7, 25, 14, tzinfo=UTC),
        confirmed_company_id=(
            CompanyId.new()
            if state in {InvestigationState.COMPLETED, InvestigationState.PARTIALLY_COMPLETED}
            else None
        ),
    )

    with pytest.raises(InvariantViolationError):
        terminal.cancel(occurred_at=datetime(2026, 7, 25, 15, tzinfo=UTC))


def test_cancel_rejects_timestamp_before_existing_start() -> None:
    started = _reconstituted_investigation()
    assert started.started_at is not None

    with pytest.raises(InvariantViolationError):
        started.cancel(occurred_at=started.started_at - timedelta(microseconds=1))


def test_reconstitution_preserves_legacy_started_snapshot_without_input() -> None:
    legacy = _reconstituted_investigation(
        identification_input=None,
        confirmed_company_id=None,
    )
    assert legacy.identification_input is None

    with pytest.raises(InvariantViolationError, match="before confirmation"):
        _reconstituted_investigation(
            identification_input=None,
            confirmed_company_id=CompanyId.new(),
        )
