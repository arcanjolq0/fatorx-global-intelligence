"""Unit tests for tenant-scoped Investigation application services."""

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode, AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    InvalidOperationError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.services.investigations import InvestigationService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
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
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)


def _setup(
    role: MembershipRole,
) -> tuple[
    ActorContext,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    InvestigationService,
]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    database = FakeDatabase(
        users={
            actor.user_id: UserAccount(
                id=actor.user_id,
                email=EmailAddress(f"{actor.user_id.value}@example.test"),
                display_name="Actor",
                status=UserAccountStatus.ACTIVE,
                created_at=NOW - timedelta(days=1),
                updated_at=NOW - timedelta(days=1),
            )
        },
        memberships={
            (actor.workspace_id, actor.user_id): WorkspaceMembership(
                id=MembershipId.new(),
                workspace_id=actor.workspace_id,
                user_id=actor.user_id,
                role=role,
                status=MembershipStatus.ACTIVE,
                created_at=NOW - timedelta(days=1),
                updated_at=NOW - timedelta(days=1),
            )
        },
    )
    factory = FakeUnitOfWorkFactory(database)
    return (
        actor,
        database,
        factory,
        InvestigationService(factory, ContextualAuthorizer(), FakeClock(NOW)),
    )


def _investigation(actor: ActorContext) -> Investigation:
    return Investigation(
        id=InvestigationId.new(),
        workspace_id=actor.workspace_id,
        requested_by=actor.user_id,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        created_at=NOW,
    )


@pytest.mark.parametrize(
    "role",
    [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.ANALYST],
)
def test_authorized_roles_create_initial_investigation_for_actor(
    role: MembershipRole,
) -> None:
    actor, database, factory, service = _setup(role)

    investigation = service.create_investigation(
        actor,
        profile_code=" SUPPLIER_STANDARD ",
        country_code=CountryCode("br"),
        budget=Money(Decimal("1000.50"), CurrencyCode("brl")),
        deadline_at=NOW + timedelta(days=2),
    )

    assert investigation.workspace_id == actor.workspace_id
    assert investigation.requested_by == actor.user_id
    assert investigation.state is InvestigationState.CREATED
    assert investigation.state_version == 1
    assert investigation.created_at == NOW
    assert database.investigations[(actor.workspace_id, investigation.id)] == investigation
    event = database.audit_events[-1]
    assert event.action_code == AuditActionCode.INVESTIGATION_CREATED.value
    assert event.outcome is AuditOutcome.SUCCESS
    assert event.resource_id == investigation.id
    assert event.correlation_id == actor.correlation_id
    assert factory.created[0].commit_calls == 1


def test_viewer_cannot_create_investigation_and_denial_is_audited() -> None:
    actor, database, _, service = _setup(MembershipRole.VIEWER)

    with pytest.raises(AuthorizationDeniedError):
        service.create_investigation(
            actor,
            profile_code="SUPPLIER_STANDARD",
            country_code=CountryCode("BR"),
        )

    assert database.investigations == {}
    assert database.audit_events[-1].reason_code == AuditReasonCode.PERMISSION_DENIED.value


def test_confirmed_company_must_exist_in_actor_workspace() -> None:
    actor, database, factory, service = _setup(MembershipRole.OWNER)
    other_company = Company(
        id=CompanyId.new(),
        workspace_id=WorkspaceId.new(),
        legal_name="Other Tenant",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    database.companies[(other_company.workspace_id, other_company.id)] = other_company

    with pytest.raises(ResourceNotFoundError):
        service.create_investigation(
            actor,
            profile_code="SUPPLIER_STANDARD",
            country_code=CountryCode("BR"),
            confirmed_company_id=other_company.id,
        )

    assert factory.created[0].companies.get_calls == [(actor.workspace_id, other_company.id)]
    assert database.investigations == {}
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE


def test_create_with_company_from_same_workspace_preserves_reference() -> None:
    actor, database, _, service = _setup(MembershipRole.OWNER)
    company = Company(
        id=CompanyId.new(),
        workspace_id=actor.workspace_id,
        legal_name="Same Tenant",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )
    database.companies[(actor.workspace_id, company.id)] = company

    investigation = service.create_investigation(
        actor,
        profile_code="SUPPLIER_STANDARD",
        country_code=CountryCode("BR"),
        confirmed_company_id=company.id,
    )

    assert investigation.confirmed_company_id == company.id


@pytest.mark.parametrize("role", list(MembershipRole))
def test_all_active_roles_read_investigation_without_success_read_audit(
    role: MembershipRole,
) -> None:
    actor, database, factory, service = _setup(role)
    investigation = _investigation(actor)
    database.investigations[(actor.workspace_id, investigation.id)] = investigation

    restored = service.get_investigation(actor, investigation_id=investigation.id)

    assert restored == investigation
    assert database.audit_events == []
    assert factory.created[0].investigations.get_calls == [(actor.workspace_id, investigation.id)]
    assert factory.created[0].commit_calls == 1


def test_investigation_from_other_workspace_looks_absent_and_is_audited() -> None:
    actor, database, factory, service = _setup(MembershipRole.OWNER)
    other_actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    investigation = _investigation(other_actor)
    database.investigations[(other_actor.workspace_id, investigation.id)] = investigation

    with pytest.raises(ResourceNotFoundError):
        service.get_investigation(actor, investigation_id=investigation.id)

    assert factory.created[0].investigations.get_calls == [(actor.workspace_id, investigation.id)]
    event = database.audit_events[-1]
    assert event.action_code == AuditActionCode.INVESTIGATION_READ_DENIED.value
    assert event.reason_code == AuditReasonCode.RESOURCE_NOT_FOUND.value
    assert event.resource_id is None


def test_invalid_investigation_is_failure_audited_without_mutation() -> None:
    actor, database, _, service = _setup(MembershipRole.OWNER)

    with pytest.raises(InvalidOperationError):
        service.create_investigation(
            actor,
            profile_code="   ",
            country_code=CountryCode("BR"),
        )

    assert database.investigations == {}
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE
    assert database.audit_events[-1].reason_code == AuditReasonCode.VALIDATION_FAILURE.value


def test_commit_failure_rolls_back_investigation_and_success_audit() -> None:
    actor, database, _, _ = _setup(MembershipRole.OWNER)
    factory = FakeUnitOfWorkFactory(database, fail_commit=True)
    service = InvestigationService(factory, ContextualAuthorizer(), FakeClock(NOW))

    with pytest.raises(PersistenceError, match="Unable to commit"):
        service.create_investigation(
            actor,
            profile_code="SUPPLIER_STANDARD",
            country_code=CountryCode("BR"),
        )

    assert database.investigations == {}
    assert database.audit_events == []


def test_investigation_service_signature_has_no_separate_workspace_or_requester() -> None:
    create_parameters = inspect.signature(InvestigationService.create_investigation).parameters
    get_parameters = inspect.signature(InvestigationService.get_investigation).parameters

    assert "workspace_id" not in create_parameters
    assert "requested_by" not in create_parameters
    assert "workspace_id" not in get_parameters
