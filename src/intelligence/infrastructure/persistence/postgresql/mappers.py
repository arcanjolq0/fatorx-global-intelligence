"""Pure mappings between domain snapshots and relational values."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from intelligence.application.errors import PersistenceDataError
from intelligence.domain.audit import AuditEvent, AuditOutcome, AuditResourceId, AuditResourceType
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import DomainError
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

RelationalValues = Mapping[str, object]


def workspace_to_values(workspace: Workspace) -> dict[str, object]:
    """Map a workspace snapshot to values accepted by the Core table."""

    return {
        "id": workspace.id.value,
        "name": workspace.name,
        "status": workspace.status.value,
        "retention_policy_version": workspace.retention_policy_version,
        "created_at": workspace.created_at,
        "updated_at": workspace.updated_at,
    }


def workspace_from_values(values: RelationalValues) -> Workspace:
    """Reconstitute a workspace while validating every persisted value."""

    try:
        return Workspace(
            id=WorkspaceId(_required(values, "id", UUID)),
            name=_required(values, "name", str),
            status=_enum(values, "status", WorkspaceStatus),
            retention_policy_version=_required(values, "retention_policy_version", str),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted Workspace data is invalid.") from error


def company_to_values(company: Company) -> dict[str, object]:
    """Map a company snapshot to values accepted by the Core table."""

    return {
        "id": company.id.value,
        "workspace_id": company.workspace_id.value,
        "legal_name": company.legal_name,
        "trade_name": company.trade_name,
        "country_code": company.country_code.value,
        "legal_form": company.legal_form,
        "status": company.status.value,
        "incorporated_on": company.incorporated_on,
        "dissolved_on": company.dissolved_on,
        "official_domain": company.official_domain,
        "created_at": company.created_at,
        "updated_at": company.updated_at,
    }


def company_from_values(values: RelationalValues) -> Company:
    """Reconstitute a company while validating every persisted value."""

    try:
        return Company(
            id=CompanyId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            legal_name=_required(values, "legal_name", str),
            trade_name=_optional(values, "trade_name", str),
            country_code=CountryCode(_required(values, "country_code", str)),
            legal_form=_optional(values, "legal_form", str),
            status=_enum(values, "status", CompanyStatus),
            incorporated_on=_optional_date(values, "incorporated_on"),
            dissolved_on=_optional_date(values, "dissolved_on"),
            official_domain=_optional(values, "official_domain", str),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted Company data is invalid.") from error


def investigation_to_values(investigation: Investigation) -> dict[str, object]:
    """Map an investigation snapshot to values accepted by the Core table."""

    budget_amount: Decimal | None = None
    budget_currency: str | None = None
    if investigation.budget is not None:
        budget_amount = investigation.budget.amount
        budget_currency = investigation.budget.currency.value

    return {
        "id": investigation.id.value,
        "workspace_id": investigation.workspace_id.value,
        "requested_by": investigation.requested_by.value,
        "profile_code": investigation.profile_code,
        "country_code": investigation.country_code.value,
        "state": investigation.state.value,
        "state_version": investigation.state_version,
        "confirmed_company_id": (
            investigation.confirmed_company_id.value
            if investigation.confirmed_company_id is not None
            else None
        ),
        "budget_amount": budget_amount,
        "budget_currency": budget_currency,
        "deadline_at": investigation.deadline_at,
        "started_at": investigation.started_at,
        "completed_at": investigation.completed_at,
        "created_at": investigation.created_at,
    }


def investigation_from_values(values: RelationalValues) -> Investigation:
    """Reconstitute any valid persisted state through the domain contract."""

    try:
        confirmed_company_uuid = _optional(values, "confirmed_company_id", UUID)
        budget_amount = _optional(values, "budget_amount", Decimal)
        budget_currency = _optional(values, "budget_currency", str)
        if (budget_amount is None) != (budget_currency is None):
            raise PersistenceDataError("Persisted Investigation budget data is incomplete.")
        budget = (
            Money(budget_amount, CurrencyCode(budget_currency))
            if budget_amount is not None and budget_currency is not None
            else None
        )

        return Investigation.reconstitute(
            id=InvestigationId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            requested_by=UserId(_required(values, "requested_by", UUID)),
            profile_code=_required(values, "profile_code", str),
            country_code=CountryCode(_required(values, "country_code", str)),
            state=_enum(values, "state", InvestigationState),
            state_version=_required_integer(values, "state_version"),
            confirmed_company_id=(
                CompanyId(confirmed_company_uuid) if confirmed_company_uuid is not None else None
            ),
            budget=budget,
            deadline_at=_optional_datetime(values, "deadline_at"),
            started_at=_optional_datetime(values, "started_at"),
            completed_at=_optional_datetime(values, "completed_at"),
            created_at=_required_datetime(values, "created_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted Investigation data is invalid.") from error


def user_account_to_values(user: UserAccount) -> dict[str, object]:
    """Map an internal identity snapshot to relational values."""

    return {
        "id": user.id.value,
        "email": user.email.value,
        "display_name": user.display_name,
        "status": user.status.value,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
    }


def user_account_from_values(values: RelationalValues) -> UserAccount:
    """Reconstitute an internal identity from validated relational values."""

    try:
        return UserAccount(
            id=UserId(_required(values, "id", UUID)),
            email=EmailAddress(_required(values, "email", str)),
            display_name=_required(values, "display_name", str),
            status=_enum(values, "status", UserAccountStatus),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted UserAccount data is invalid.") from error


def workspace_membership_to_values(
    membership: WorkspaceMembership,
) -> dict[str, object]:
    """Map a membership snapshot to relational values."""

    return {
        "id": membership.id.value,
        "workspace_id": membership.workspace_id.value,
        "user_id": membership.user_id.value,
        "role": membership.role.value,
        "status": membership.status.value,
        "created_at": membership.created_at,
        "updated_at": membership.updated_at,
        "deactivated_at": membership.deactivated_at,
    }


def workspace_membership_from_values(values: RelationalValues) -> WorkspaceMembership:
    """Reconstitute a membership snapshot from relational values."""

    try:
        return WorkspaceMembership(
            id=MembershipId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            user_id=UserId(_required(values, "user_id", UUID)),
            role=_enum(values, "role", MembershipRole),
            status=_enum(values, "status", MembershipStatus),
            created_at=_required_datetime(values, "created_at"),
            updated_at=_required_datetime(values, "updated_at"),
            deactivated_at=_optional_datetime(values, "deactivated_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted WorkspaceMembership data is invalid.") from error


def audit_event_to_values(event: AuditEvent) -> dict[str, object]:
    """Map an append-only audit event to its minimal relational representation."""

    return {
        "id": event.id.value,
        "workspace_id": event.workspace_id.value,
        "actor_user_id": event.actor_user_id.value,
        "action_code": event.action_code,
        "resource_type": event.resource_type.value,
        "resource_id": event.resource_id.value if event.resource_id is not None else None,
        "outcome": event.outcome.value,
        "reason_code": event.reason_code,
        "correlation_id": event.correlation_id.value,
        "occurred_at": event.occurred_at,
    }


def audit_event_from_values(values: RelationalValues) -> AuditEvent:
    """Reconstitute an audit event and its strongly typed resource ID."""

    try:
        resource_type = _enum(values, "resource_type", AuditResourceType)
        resource_uuid = _optional(values, "resource_id", UUID)
        return AuditEvent(
            id=AuditEventId(_required(values, "id", UUID)),
            workspace_id=WorkspaceId(_required(values, "workspace_id", UUID)),
            actor_user_id=UserId(_required(values, "actor_user_id", UUID)),
            action_code=_required(values, "action_code", str),
            resource_type=resource_type,
            resource_id=(
                _audit_resource_id(resource_type, resource_uuid)
                if resource_uuid is not None
                else None
            ),
            outcome=_enum(values, "outcome", AuditOutcome),
            reason_code=_optional(values, "reason_code", str),
            correlation_id=CorrelationId(_required(values, "correlation_id", UUID)),
            occurred_at=_required_datetime(values, "occurred_at"),
        )
    except PersistenceDataError:
        raise
    except (DomainError, TypeError, ValueError) as error:
        raise PersistenceDataError("Persisted AuditEvent data is invalid.") from error


def _audit_resource_id(
    resource_type: AuditResourceType,
    resource_uuid: UUID,
) -> AuditResourceId:
    identifier_types: dict[AuditResourceType, type[AuditResourceId]] = {
        AuditResourceType.WORKSPACE: WorkspaceId,
        AuditResourceType.USER: UserId,
        AuditResourceType.MEMBERSHIP: MembershipId,
        AuditResourceType.COMPANY: CompanyId,
        AuditResourceType.INVESTIGATION: InvestigationId,
    }
    return identifier_types[resource_type](resource_uuid)


def _read(values: RelationalValues, field_name: str) -> object:
    try:
        return values[field_name]
    except KeyError as error:
        raise PersistenceDataError(
            f"Persisted data is missing required field {field_name}."
        ) from error


def _required[Value](
    values: RelationalValues,
    field_name: str,
    expected_type: type[Value],
) -> Value:
    value = _read(values, field_name)
    if not isinstance(value, expected_type):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _optional[Value](
    values: RelationalValues,
    field_name: str,
    expected_type: type[Value],
) -> Value | None:
    value = _read(values, field_name)
    if value is None:
        return None
    if not isinstance(value, expected_type):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _required_integer(values: RelationalValues, field_name: str) -> int:
    value = _read(values, field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _required_datetime(values: RelationalValues, field_name: str) -> datetime:
    return _required(values, field_name, datetime)


def _optional_datetime(values: RelationalValues, field_name: str) -> datetime | None:
    return _optional(values, field_name, datetime)


def _optional_date(values: RelationalValues, field_name: str) -> date | None:
    value = _read(values, field_name)
    if value is None:
        return None
    if not isinstance(value, date) or isinstance(value, datetime):
        raise PersistenceDataError(f"Persisted field {field_name} has an invalid type.")
    return value


def _enum[EnumValue: StrEnum](
    values: RelationalValues,
    field_name: str,
    enum_type: type[EnumValue],
) -> EnumValue:
    return enum_type(_required(values, field_name, str))


__all__ = [
    "RelationalValues",
    "audit_event_from_values",
    "audit_event_to_values",
    "company_from_values",
    "company_to_values",
    "investigation_from_values",
    "investigation_to_values",
    "user_account_from_values",
    "user_account_to_values",
    "workspace_from_values",
    "workspace_membership_from_values",
    "workspace_membership_to_values",
    "workspace_to_values",
]
