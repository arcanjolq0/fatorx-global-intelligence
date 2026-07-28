"""Minimal authorized investigation creation and tenant-scoped retrieval."""

from datetime import datetime
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
from intelligence.domain.errors import DomainError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CompanyId, InvestigationId
from intelligence.domain.investigations import Investigation
from intelligence.domain.money import Money


class InvestigationService:
    """Create and retrieve investigations under the actor's effective workspace."""

    def __init__(
        self,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock

    def create_investigation(
        self,
        actor: ActorContext,
        *,
        profile_code: str,
        country_code: CountryCode,
        confirmed_company_id: CompanyId | None = None,
        budget: Money | None = None,
        deadline_at: datetime | None = None,
    ) -> Investigation:
        action = AuditActionCode.INVESTIGATION_CREATED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.INVESTIGATION_CREATE, action)
            if (
                confirmed_company_id is not None
                and unit_of_work.companies.get(actor.workspace_id, confirmed_company_id) is None
            ):
                commit_standalone_outcome(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.INVESTIGATION,
                    resource_id=None,
                    outcome=AuditOutcome.FAILURE,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    occurred_at=self._clock.now(),
                )
                raise ResourceNotFoundError()

            occurred_at = self._clock.now()
            try:
                investigation = Investigation(
                    id=InvestigationId.new(),
                    workspace_id=actor.workspace_id,
                    requested_by=actor.user_id,
                    profile_code=profile_code,
                    country_code=country_code,
                    confirmed_company_id=confirmed_company_id,
                    budget=budget,
                    deadline_at=deadline_at,
                    created_at=occurred_at,
                )
            except DomainError as cause:
                error = InvalidOperationError()
                error.__cause__ = cause
                self._fail(unit_of_work, actor, action, error)

            unit_of_work.investigations.add(investigation)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=investigation.id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=occurred_at,
            )
            unit_of_work.commit()
            return investigation

    def get_investigation(
        self,
        actor: ActorContext,
        *,
        investigation_id: InvestigationId,
    ) -> Investigation:
        action = AuditActionCode.INVESTIGATION_READ_DENIED
        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, Permission.INVESTIGATION_READ, action)
            investigation = unit_of_work.investigations.get(
                actor.workspace_id,
                investigation_id,
            )
            if investigation is None:
                commit_standalone_outcome(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    resource_type=AuditResourceType.INVESTIGATION,
                    resource_id=None,
                    outcome=AuditOutcome.DENIED,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    occurred_at=self._clock.now(),
                )
                raise ResourceNotFoundError()
            unit_of_work.commit()
            return investigation

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
            resource_type=AuditResourceType.INVESTIGATION,
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
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.FAILURE,
            reason=AuditReasonCode.VALIDATION_FAILURE,
            occurred_at=self._clock.now(),
        )
        raise error


__all__ = ["InvestigationService"]
