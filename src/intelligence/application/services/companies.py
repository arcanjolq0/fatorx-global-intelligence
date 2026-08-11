"""Minimal authorized company creation and tenant-scoped retrieval."""

from datetime import date
from typing import Never

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    AuditReasonCode,
    append_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.authorization import ContextualAuthorizer, Permission
from intelligence.application.errors import (
    AuthorizationDeniedError,
    InvalidOperationError,
    ResourceNotFoundError,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import DomainError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CompanyId


class CompanyService:
    """Create and retrieve companies using only the trusted actor tenant scope."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def create_company(
        self,
        actor: ActorContext,
        *,
        legal_name: str,
        country_code: CountryCode,
        status: CompanyStatus = CompanyStatus.ACTIVE,
        trade_name: str | None = None,
        legal_form: str | None = None,
        incorporated_on: date | None = None,
        dissolved_on: date | None = None,
        official_domain: str | None = None,
    ) -> Company:
        action = AuditActionCode.COMPANY_CREATED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.COMPANY_CREATE, action)
            occurred_at = self._clock.now()
            try:
                company = Company(
                    id=CompanyId.new(),
                    workspace_id=actor.workspace_id,
                    legal_name=legal_name.strip(),
                    trade_name=trade_name.strip() if trade_name is not None else None,
                    country_code=country_code,
                    legal_form=legal_form,
                    status=status,
                    incorporated_on=incorporated_on,
                    dissolved_on=dissolved_on,
                    official_domain=official_domain,
                    created_at=occurred_at,
                    updated_at=occurred_at,
                )
            except DomainError as cause:
                error = InvalidOperationError()
                error.__cause__ = cause
                self._fail(unit_of_work, actor, action, error)

            unit_of_work.companies.add(company)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.COMPANY,
                resource_id=company.id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return company

    def get_company(self, actor: ActorContext, *, company_id: CompanyId) -> Company:
        action = AuditActionCode.COMPANY_READ_DENIED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.COMPANY_READ, action)
            company = unit_of_work.companies.get(actor.workspace_id, company_id)
            if company is None:
                commit_standalone_outcome(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.COMPANY,
                    resource_id=None,
                    outcome=AuditOutcome.DENIED,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    occurred_at=self._clock.now(),
                )
                raise ResourceNotFoundError()
            unit_of_work.commit()
            return company

    def _authorize(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        permission: Permission,
        action: AuditActionCode,
    ) -> None:
        decision = self._authorizer.authorize(unit_of_work, actor, permission)
        if decision.is_allowed:
            return
        reason = decision.denial_reason
        if reason is None:
            raise RuntimeError("A denied authorization decision requires a reason.")
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.DENIED,
            reason=reason,
            occurred_at=self._clock.now(),
        )
        raise AuthorizationDeniedError()

    def _fail(
        self,
        unit_of_work: UnitOfWork,
        actor: ActorContext,
        action: AuditActionCode,
        error: Exception,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.COMPANY,
            resource_id=None,
            outcome=AuditOutcome.FAILURE,
            reason=AuditReasonCode.VALIDATION_FAILURE,
            occurred_at=self._clock.now(),
        )
        raise error


__all__ = ["CompanyService"]
