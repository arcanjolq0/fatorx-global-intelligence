"""Pure mapper tests without a database."""

from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from intelligence.application.errors import PersistenceDataError
from intelligence.domain.audit import (
    AuditEvent,
    AuditOutcome,
    AuditResourceId,
    AuditResourceType,
)
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
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
from intelligence.domain.investigations import Investigation, InvestigationState
from intelligence.domain.money import CurrencyCode, Money
from intelligence.domain.workspaces import Workspace, WorkspaceStatus
from intelligence.infrastructure.persistence.postgresql.mappers import (
    audit_event_from_values,
    audit_event_to_values,
    company_from_values,
    company_to_values,
    investigation_from_values,
    investigation_to_values,
    user_account_from_values,
    user_account_to_values,
    workspace_from_values,
    workspace_membership_from_values,
    workspace_membership_to_values,
    workspace_to_values,
)

CREATED_AT = datetime(2026, 7, 28, 12, tzinfo=UTC)


def _workspace(*, status: WorkspaceStatus = WorkspaceStatus.ACTIVE) -> Workspace:
    return Workspace(
        id=WorkspaceId.new(),
        name="Workspace",
        status=status,
        retention_policy_version="2026-01",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _company(workspace_id: WorkspaceId) -> Company:
    return Company(
        id=CompanyId.new(),
        workspace_id=workspace_id,
        legal_name="Empresa Ltda.",
        trade_name="Empresa",
        country_code=CountryCode("BR"),
        legal_form="Limitada",
        status=CompanyStatus.DISSOLVED,
        incorporated_on=date(2020, 1, 2),
        dissolved_on=date(2025, 3, 4),
        official_domain="empresa.example",
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _investigation(workspace_id: WorkspaceId, company_id: CompanyId) -> Investigation:
    return Investigation.reconstitute(
        id=InvestigationId.new(),
        workspace_id=workspace_id,
        requested_by=UserId.new(),
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        state=InvestigationState.COMPLETED,
        state_version=11,
        confirmed_company_id=company_id,
        budget=Money(
            Decimal("12345678901234567890.12345678901234567890"),
            CurrencyCode("BRL"),
        ),
        deadline_at=CREATED_AT + timedelta(days=2),
        started_at=CREATED_AT + timedelta(minutes=1),
        completed_at=CREATED_AT + timedelta(minutes=2),
        created_at=CREATED_AT,
    )


def _user_account(*, status: UserAccountStatus = UserAccountStatus.ACTIVE) -> UserAccount:
    return UserAccount(
        id=UserId.new(),
        email=EmailAddress("analyst@example.com"),
        display_name="Ana Analyst",
        status=status,
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=1),
    )


def _membership(
    *,
    role: MembershipRole = MembershipRole.ANALYST,
    status: MembershipStatus = MembershipStatus.ACTIVE,
) -> WorkspaceMembership:
    deactivated_at = (
        CREATED_AT + timedelta(minutes=2) if status is MembershipStatus.INACTIVE else None
    )
    return WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=WorkspaceId.new(),
        user_id=UserId.new(),
        role=role,
        status=status,
        created_at=CREATED_AT,
        updated_at=CREATED_AT + timedelta(minutes=2),
        deactivated_at=deactivated_at,
    )


def _audit_event(
    *,
    resource_type: AuditResourceType = AuditResourceType.INVESTIGATION,
    resource_id: AuditResourceId | None = None,
    outcome: AuditOutcome = AuditOutcome.SUCCESS,
    reason_code: str | None = "MEMBERSHIP.ACTIVE",
) -> AuditEvent:
    return AuditEvent(
        id=AuditEventId.new(),
        workspace_id=WorkspaceId.new(),
        actor_user_id=UserId.new(),
        action_code="INVESTIGATION.READ",
        resource_type=resource_type,
        resource_id=resource_id,
        outcome=outcome,
        reason_code=reason_code,
        correlation_id=CorrelationId.new(),
        occurred_at=CREATED_AT,
    )


@pytest.mark.parametrize("status", list(WorkspaceStatus))
def test_workspace_mapper_round_trip_preserves_strong_types_and_status(
    status: WorkspaceStatus,
) -> None:
    workspace = _workspace(status=status)

    restored = workspace_from_values(workspace_to_values(workspace))

    assert restored == workspace
    assert isinstance(restored.id, WorkspaceId)
    assert restored.status is status


def test_workspace_mapper_normalizes_aware_timestamps_to_utc() -> None:
    workspace = _workspace()
    values = workspace_to_values(workspace)
    values["created_at"] = datetime(
        2026,
        7,
        28,
        9,
        tzinfo=timezone(-timedelta(hours=3)),
    )

    restored = workspace_from_values(values)

    assert restored.created_at == CREATED_AT


def test_company_mapper_round_trip_preserves_all_optional_fields() -> None:
    company = _company(WorkspaceId.new())

    restored = company_from_values(company_to_values(company))

    assert restored == company
    assert isinstance(restored.id, CompanyId)
    assert isinstance(restored.workspace_id, WorkspaceId)
    assert restored.incorporated_on == date(2020, 1, 2)


def test_investigation_mapper_round_trip_preserves_decimal_and_persisted_state() -> None:
    investigation = _investigation(WorkspaceId.new(), CompanyId.new())

    restored = investigation_from_values(investigation_to_values(investigation))

    assert restored == investigation
    assert isinstance(restored.id, InvestigationId)
    assert isinstance(restored.requested_by, UserId)
    assert restored.state is InvestigationState.COMPLETED
    assert restored.state_version == 11
    assert restored.budget is not None
    assert restored.budget.amount == Decimal("12345678901234567890.12345678901234567890")


@pytest.mark.parametrize("status", list(UserAccountStatus))
def test_user_account_mapper_round_trip_preserves_email_id_and_status(
    status: UserAccountStatus,
) -> None:
    user = _user_account(status=status)

    restored = user_account_from_values(user_account_to_values(user))

    assert restored == user
    assert isinstance(restored.id, UserId)
    assert isinstance(restored.email, EmailAddress)
    assert restored.status is status


def test_user_account_mapper_normalizes_aware_timestamps_to_utc() -> None:
    values = user_account_to_values(_user_account())
    values["created_at"] = datetime(
        2026,
        7,
        28,
        9,
        tzinfo=timezone(-timedelta(hours=3)),
    )

    restored = user_account_from_values(values)

    assert restored.created_at == CREATED_AT


@pytest.mark.parametrize("role", list(MembershipRole))
def test_membership_mapper_round_trip_preserves_every_role_and_strong_ids(
    role: MembershipRole,
) -> None:
    membership = _membership(role=role)

    restored = workspace_membership_from_values(workspace_membership_to_values(membership))

    assert restored == membership
    assert isinstance(restored.id, MembershipId)
    assert isinstance(restored.workspace_id, WorkspaceId)
    assert isinstance(restored.user_id, UserId)
    assert restored.role is role


def test_membership_mapper_preserves_inactive_snapshot_and_optional_timestamp() -> None:
    membership = _membership(status=MembershipStatus.INACTIVE)

    restored = workspace_membership_from_values(workspace_membership_to_values(membership))

    assert restored == membership
    assert restored.status is MembershipStatus.INACTIVE
    assert restored.deactivated_at == CREATED_AT + timedelta(minutes=2)


@pytest.mark.parametrize("outcome", list(AuditOutcome))
def test_audit_event_mapper_round_trip_preserves_every_outcome(
    outcome: AuditOutcome,
) -> None:
    event = _audit_event(outcome=outcome)

    restored = audit_event_from_values(audit_event_to_values(event))

    assert restored == event
    assert restored.outcome is outcome
    assert isinstance(restored.id, AuditEventId)
    assert isinstance(restored.correlation_id, CorrelationId)


@pytest.mark.parametrize(
    ("resource_type", "resource_id", "expected_identifier_type"),
    [
        (AuditResourceType.WORKSPACE, WorkspaceId.new(), WorkspaceId),
        (AuditResourceType.USER, UserId.new(), UserId),
        (AuditResourceType.MEMBERSHIP, MembershipId.new(), MembershipId),
        (AuditResourceType.COMPANY, CompanyId.new(), CompanyId),
        (AuditResourceType.INVESTIGATION, InvestigationId.new(), InvestigationId),
    ],
)
def test_audit_event_mapper_restores_resource_id_according_to_resource_type(
    resource_type: AuditResourceType,
    resource_id: AuditResourceId,
    expected_identifier_type: type[AuditResourceId],
) -> None:
    event = _audit_event(resource_type=resource_type, resource_id=resource_id)

    restored = audit_event_from_values(audit_event_to_values(event))

    assert restored == event
    assert restored.resource_type is resource_type
    assert isinstance(restored.resource_id, expected_identifier_type)


def test_audit_event_mapper_preserves_absent_resource_and_reason() -> None:
    event = _audit_event(
        resource_type=AuditResourceType.WORKSPACE,
        resource_id=None,
        reason_code=None,
    )

    restored = audit_event_from_values(audit_event_to_values(event))

    assert restored == event
    assert restored.resource_id is None
    assert restored.reason_code is None


@pytest.mark.parametrize(
    ("mapper", "values"),
    [
        (workspace_from_values, {}),
        (
            workspace_from_values,
            {**workspace_to_values(_workspace()), "id": "not-a-native-uuid"},
        ),
        (
            company_from_values,
            {
                **company_to_values(_company(WorkspaceId.new())),
                "incorporated_on": CREATED_AT,
            },
        ),
        (
            investigation_from_values,
            {
                **investigation_to_values(_investigation(WorkspaceId.new(), CompanyId.new())),
                "budget_currency": None,
            },
        ),
        (
            investigation_from_values,
            {
                **investigation_to_values(_investigation(WorkspaceId.new(), CompanyId.new())),
                "state": "IDENTIFYING",
                "started_at": None,
                "completed_at": None,
            },
        ),
    ],
)
def test_mappers_reject_missing_mistyped_or_inconsistent_rows(
    mapper: object,
    values: dict[str, object],
) -> None:
    with pytest.raises(PersistenceDataError):
        if mapper is workspace_from_values:
            workspace_from_values(values)
        elif mapper is company_from_values:
            company_from_values(values)
        else:
            investigation_from_values(values)


@pytest.mark.parametrize(
    ("mapper", "values"),
    [
        (user_account_from_values, {}),
        (
            user_account_from_values,
            {**user_account_to_values(_user_account()), "email": "not-an-email"},
        ),
        (
            user_account_from_values,
            {**user_account_to_values(_user_account()), "status": "UNKNOWN"},
        ),
        (
            workspace_membership_from_values,
            {
                **workspace_membership_to_values(_membership(status=MembershipStatus.INACTIVE)),
                "deactivated_at": None,
            },
        ),
        (
            workspace_membership_from_values,
            {**workspace_membership_to_values(_membership()), "role": "UNKNOWN"},
        ),
        (
            audit_event_from_values,
            {**audit_event_to_values(_audit_event()), "resource_type": "UNKNOWN"},
        ),
        (
            audit_event_from_values,
            {**audit_event_to_values(_audit_event()), "outcome": "UNKNOWN"},
        ),
        (
            audit_event_from_values,
            {**audit_event_to_values(_audit_event()), "resource_id": "not-a-native-uuid"},
        ),
        (
            audit_event_from_values,
            {
                **audit_event_to_values(_audit_event()),
                "occurred_at": datetime(2026, 7, 28, 12),
            },
        ),
    ],
)
def test_new_mappers_reject_missing_mistyped_or_inconsistent_rows(
    mapper: Callable[[Mapping[str, object]], object],
    values: dict[str, object],
) -> None:
    with pytest.raises(PersistenceDataError):
        mapper(values)
