"""Unit tests for tenant-scoped Company application services."""

import inspect
from datetime import UTC, date, datetime, timedelta

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import AuditActionCode, AuditReasonCode
from intelligence.application.authorization import ContextualAuthorizer
from intelligence.application.errors import (
    AuthorizationDeniedError,
    InvalidOperationError,
    LastOwnerProtectionError,
    MembershipConflictError,
    PersistenceError,
    ResourceNotFoundError,
)
from intelligence.application.services.companies import CompanyService
from intelligence.domain.audit import AuditOutcome
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import (
    CompanyId,
    CorrelationId,
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
from tests.unit.application.fakes import FakeClock, FakeDatabase, FakeUnitOfWorkFactory

NOW = datetime(2026, 7, 28, 15, tzinfo=UTC)


def _setup(
    role: MembershipRole,
) -> tuple[
    ActorContext,
    FakeDatabase,
    FakeUnitOfWorkFactory,
    CompanyService,
]:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    user = UserAccount(
        id=actor.user_id,
        email=EmailAddress(f"{actor.user_id.value}@example.test"),
        display_name="Actor",
        status=UserAccountStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    membership = WorkspaceMembership(
        id=MembershipId.new(),
        workspace_id=actor.workspace_id,
        user_id=actor.user_id,
        role=role,
        status=MembershipStatus.ACTIVE,
        created_at=NOW - timedelta(days=1),
        updated_at=NOW - timedelta(days=1),
    )
    database = FakeDatabase(
        users={actor.user_id: user},
        memberships={(actor.workspace_id, actor.user_id): membership},
    )
    factory = FakeUnitOfWorkFactory(database)
    return (
        actor,
        database,
        factory,
        CompanyService(factory, ContextualAuthorizer(), FakeClock(NOW)),
    )


def _company(workspace_id: WorkspaceId) -> Company:
    return Company(
        id=CompanyId.new(),
        workspace_id=workspace_id,
        legal_name="Existing Company",
        country_code=CountryCode("BR"),
        status=CompanyStatus.ACTIVE,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    "role",
    [MembershipRole.OWNER, MembershipRole.ADMIN, MembershipRole.ANALYST],
)
def test_authorized_roles_create_company_in_actor_workspace_with_success_audit(
    role: MembershipRole,
) -> None:
    actor, database, factory, service = _setup(role)

    company = service.create_company(
        actor,
        legal_name="  Global Company Ltd.  ",
        trade_name=" Global ",
        country_code=CountryCode("br"),
        status=CompanyStatus.ACTIVE,
        incorporated_on=date(2020, 1, 1),
        official_domain=" GLOBAL.EXAMPLE ",
    )

    assert company.workspace_id == actor.workspace_id
    assert company.legal_name == "Global Company Ltd."
    assert company.created_at == NOW == company.updated_at
    assert database.companies[(actor.workspace_id, company.id)] == company
    event = database.audit_events[-1]
    assert event.action_code == AuditActionCode.COMPANY_CREATED.value
    assert event.outcome is AuditOutcome.SUCCESS
    assert event.resource_id == company.id
    assert event.correlation_id == actor.correlation_id
    assert factory.created[0].commit_calls == 1


def test_viewer_cannot_create_company_and_denial_has_no_mutation() -> None:
    actor, database, factory, service = _setup(MembershipRole.VIEWER)

    with pytest.raises(AuthorizationDeniedError):
        service.create_company(
            actor,
            legal_name="Denied Company",
            country_code=CountryCode("BR"),
        )

    assert database.companies == {}
    assert database.audit_events[-1].outcome is AuditOutcome.DENIED
    assert database.audit_events[-1].reason_code == AuditReasonCode.PERMISSION_DENIED.value
    assert factory.created[0].companies.get_calls == []


@pytest.mark.parametrize("role", list(MembershipRole))
def test_all_active_roles_read_company_without_success_read_audit(role: MembershipRole) -> None:
    actor, database, factory, service = _setup(role)
    company = _company(actor.workspace_id)
    database.companies[(actor.workspace_id, company.id)] = company

    restored = service.get_company(actor, company_id=company.id)

    assert restored == company
    assert database.audit_events == []
    assert factory.created[0].companies.get_calls == [(actor.workspace_id, company.id)]
    assert factory.created[0].commit_calls == 1


def test_company_from_another_workspace_looks_absent_and_denial_is_audited() -> None:
    actor, database, factory, service = _setup(MembershipRole.OWNER)
    other = _company(WorkspaceId.new())
    database.companies[(other.workspace_id, other.id)] = other

    with pytest.raises(ResourceNotFoundError, match="not found"):
        service.get_company(actor, company_id=other.id)

    assert factory.created[0].companies.get_calls == [(actor.workspace_id, other.id)]
    event = database.audit_events[-1]
    assert event.action_code == AuditActionCode.COMPANY_READ_DENIED.value
    assert event.outcome is AuditOutcome.DENIED
    assert event.reason_code == AuditReasonCode.RESOURCE_NOT_FOUND.value
    assert event.resource_id is None
    assert str(other.workspace_id) not in str(ResourceNotFoundError())


def test_invalid_company_is_audited_as_failure_without_mutation() -> None:
    actor, database, _, service = _setup(MembershipRole.OWNER)

    with pytest.raises(InvalidOperationError):
        service.create_company(
            actor,
            legal_name="   ",
            country_code=CountryCode("BR"),
        )

    assert database.companies == {}
    assert database.audit_events[-1].outcome is AuditOutcome.FAILURE
    assert database.audit_events[-1].reason_code == AuditReasonCode.VALIDATION_FAILURE.value


def test_commit_failure_rolls_back_company_and_success_audit() -> None:
    actor, database, _, _ = _setup(MembershipRole.OWNER)
    factory = FakeUnitOfWorkFactory(database, fail_commit=True)
    service = CompanyService(factory, ContextualAuthorizer(), FakeClock(NOW))

    with pytest.raises(PersistenceError, match="Unable to commit"):
        service.create_company(
            actor,
            legal_name="Atomic Company",
            country_code=CountryCode("BR"),
        )

    assert database.companies == {}
    assert database.audit_events == []


def test_company_service_signature_has_no_separate_workspace_parameter() -> None:
    for method_name in ("create_company", "get_company"):
        parameters = inspect.signature(getattr(CompanyService, method_name)).parameters
        assert "workspace_id" not in parameters


def test_missing_actor_preserves_safe_denial_when_audit_cannot_reference_user() -> None:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )
    factory = FakeUnitOfWorkFactory(fail_audit=True)
    service = CompanyService(factory, ContextualAuthorizer(), FakeClock(NOW))

    with pytest.raises(AuthorizationDeniedError) as captured:
        service.create_company(
            actor,
            legal_name="Unavailable",
            country_code=CountryCode("BR"),
        )

    assert str(captured.value) == "Operation is not authorized."
    assert factory.database.audit_events == []
    assert factory.database.companies == {}


def test_public_application_errors_are_constant_and_redacted() -> None:
    errors = [
        AuthorizationDeniedError(),
        ResourceNotFoundError(),
        MembershipConflictError(),
        LastOwnerProtectionError(),
        InvalidOperationError(),
    ]

    for error in errors:
        public_message = str(error).lower()
        assert "select " not in public_message
        assert "postgresql" not in public_message
        assert "credential-marker" not in public_message
        assert "technical-marker" not in public_message
