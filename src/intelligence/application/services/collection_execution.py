"""F4.6 direct execution of one admitted manifest SEARCH operation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Never, cast

from intelligence.application.actor_context import ActorContext
from intelligence.application.audit import (
    AuditActionCode,
    AuditReasonCode,
    append_audit_event,
    commit_standalone_outcome,
)
from intelligence.application.authorization import ContextualAuthorizer, Permission
from intelligence.application.collection_execution import (
    CollectionExecutionOwnership,
    CollectionExecutionResultRecord,
    ExecuteCollectionSearchOperation,
    build_collection_execution_ownership,
    build_collection_execution_result,
    digest_execute_collection_command,
    validate_collection_execution_history,
)
from intelligence.application.errors import (
    AuthorizationDeniedError,
    CollectionExecutionAlreadyOwnedError,
    CollectionExecutionDependencyError,
    CollectionExecutionInProgressError,
    InvalidCollectionExecutionError,
    InvestigationCommandCollisionError,
    PersistenceDataError,
    ResourceNotFoundError,
)
from intelligence.application.ports.clock import Clock
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory
from intelligence.connectors.context import CancellationSignal, ConnectorContext, MonotonicDeadline
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import ConnectorMode, ConnectorOperation
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionItem,
    ConnectorExecutionResult,
    SearchConnectorOperation,
)
from intelligence.connectors.execution.runner import ConnectorOperationRunner
from intelligence.connectors.execution.validation import validate_execution_preflight
from intelligence.connectors.identifiers import ConnectorId, OperationId, RequestId
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CompanyQuery, DomainName
from intelligence.domain.audit import AuditOutcome, AuditResourceType
from intelligence.domain.errors import DomainError
from intelligence.domain.money import Money
from intelligence.entity_resolution.matching import normalize_matching_name
from intelligence.orchestration.collection_activation import (
    CollectionOperation,
    CollectionRunStatus,
)


class CollectionExecutionService:
    """Own, execute, and redact one direct TEST-mode manifest operation."""

    def __init__(
        self,
        *,
        unit_of_work_factory: UnitOfWorkFactory,
        authorizer: ContextualAuthorizer,
        clock: Clock,
        runner: ConnectorOperationRunner,
        admitted_connector_ids: frozenset[ConnectorId],
    ) -> None:
        if not admitted_connector_ids or any(
            not isinstance(item, ConnectorId) for item in admitted_connector_ids
        ):
            raise TypeError("Collection execution requires an explicit connector allowlist.")
        self._unit_of_work_factory = unit_of_work_factory
        self._authorizer = authorizer
        self._clock = clock
        self._runner = runner
        self._admitted_connector_ids = admitted_connector_ids

    async def execute_search(
        self,
        actor: ActorContext,
        command: ExecuteCollectionSearchOperation,
        *,
        connector: Connector,
        monotonic_deadline: MonotonicDeadline,
        cancellation_signal: CancellationSignal,
    ) -> CollectionExecutionResultRecord:
        """Execute one SEARCH and persist only structural completion metadata."""

        if not isinstance(command, ExecuteCollectionSearchOperation):
            raise TypeError("command must be an ExecuteCollectionSearchOperation")
        action = AuditActionCode.COLLECTION_OPERATION_EXECUTED
        command_digest = digest_execute_collection_command(actor, command)

        with self._unit_of_work_factory() as unit_of_work:
            self._authorize(unit_of_work, actor, action)
            replay = self._replay_or_none(
                unit_of_work,
                actor=actor,
                action=action,
                command=command,
                command_digest=command_digest,
            )
            if replay is not None:
                unit_of_work.commit()
                return replay
            run = unit_of_work.collection_runs.get_by_id(
                actor.workspace_id, command.collection_run_id
            )
            if run is None:
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    reason=AuditReasonCode.RESOURCE_NOT_FOUND,
                    error=ResourceNotFoundError(),
                )
            operation = next(
                (item for item in run.operations if item.id == command.collection_operation_id),
                None,
            )
            if operation is None:
                self._reject_invalid(unit_of_work, actor=actor, action=action)
            started_at = self._clock.now()
            if (
                run.status is not CollectionRunStatus.PENDING
                or run.run_digest != command.expected_run_digest
                or operation.operation_digest != command.expected_operation_digest
                or (run.deadline_at is not None and started_at >= run.deadline_at)
            ):
                self._reject_invalid(unit_of_work, actor=actor, action=action, at=started_at)

            company = unit_of_work.companies.get(actor.workspace_id, run.company_id)
            if company is None:
                raise PersistenceDataError("Collection execution Company context is missing.")
            completed = unit_of_work.collection_executions.list_results_by_run(
                actor.workspace_id, run.id
            )
            by_operation = {item.collection_operation_id: item for item in completed}
            if any(
                dependency_id not in by_operation or not by_operation[dependency_id].is_usable
                for dependency_id in operation.dependency_operation_ids
            ):
                self._reject(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    reason=AuditReasonCode.COLLECTION_EXECUTION_DEPENDENCY_PENDING,
                    error=CollectionExecutionDependencyError(),
                    occurred_at=started_at,
                )
            budget_remaining = _remaining_budget(run.budget, completed)
            context = ConnectorContext(
                workspace_id=actor.workspace_id,
                investigation_id=run.investigation_id,
                operation_id=OperationId(operation.id.value),
                attempt=1,
                correlation_id=actor.correlation_id,
                request_id=RequestId(command.command_id.value),
                deadline=monotonic_deadline,
                budget_remaining=budget_remaining,
                accepted_locales=command.accepted_locales,
                source_policy_version=command.source_policy_version,
                mode=ConnectorMode.TEST,
                cancellation_signal=cancellation_signal,
            )
            request = SearchConnectorOperation(
                connector=connector,
                capability=operation.capability,
                country=company.country_code,
                query=CompanyQuery(
                    country=company.country_code,
                    original_name=company.legal_name,
                    normalized_name=normalize_matching_name(company.legal_name),
                    domain=(
                        DomainName(company.official_domain)
                        if company.official_domain is not None
                        else None
                    ),
                ),
                context=context,
                policy=command.execution_policy,
            )
            preflight = validate_execution_preflight(request)
            descriptor = preflight.descriptor
            if not self._descriptor_matches_manifest(descriptor, operation):
                self._reject_invalid(unit_of_work, actor=actor, action=action, at=started_at)
            ownership = build_collection_execution_ownership(
                actor=actor,
                investigation_id=run.investigation_id,
                command=command,
                connector_id=descriptor.connector_id,
                connector_version=descriptor.version,
                contract_version=descriptor.contract_version,
                source_id=descriptor.source_id,
                started_at=started_at,
            )
            if not unit_of_work.collection_executions.try_add_ownership(ownership):
                conflict_replay = self._resolve_ownership_conflict(
                    unit_of_work,
                    actor=actor,
                    action=action,
                    command=command,
                    command_digest=command_digest,
                )
                unit_of_work.commit()
                return conflict_replay
            unit_of_work.commit()

        executed = cast(
            ConnectorExecutionResult[ConnectorExecutionItem],
            await self._runner.execute(request, expected_descriptor=descriptor),
        )
        return self._complete(actor, ownership=ownership, execution=executed, action=action)

    def _complete(
        self,
        actor: ActorContext,
        *,
        ownership: CollectionExecutionOwnership,
        execution: ConnectorExecutionResult[ConnectorExecutionItem],
        action: AuditActionCode,
    ) -> CollectionExecutionResultRecord:
        completed_at = self._clock.now()
        result = build_collection_execution_result(
            ownership=ownership, execution=execution, completed_at=completed_at
        )
        with self._unit_of_work_factory() as unit_of_work:
            persisted_ownership = unit_of_work.collection_executions.get_ownership_by_command(
                actor.workspace_id, ownership.command_id
            )
            existing = unit_of_work.collection_executions.get_result_by_command(
                actor.workspace_id, ownership.command_id
            )
            if persisted_ownership != ownership:
                raise PersistenceDataError("Persisted collection execution ownership is invalid.")
            if existing is not None:
                validate_collection_execution_history(ownership, existing)
                if existing.result_digest != result.result_digest:
                    raise PersistenceDataError(
                        "Concurrent collection execution completion diverged."
                    )
                unit_of_work.commit()
                return existing
            unit_of_work.collection_executions.add_result(result)
            append_audit_event(
                unit_of_work,
                actor=actor,
                action=action,
                resource_type=AuditResourceType.INVESTIGATION,
                resource_id=ownership.investigation_id,
                outcome=AuditOutcome.SUCCESS,
                reason=None,
                occurred_at=completed_at,
            )
            unit_of_work.commit()
        return result

    def _replay_or_none(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        action: AuditActionCode,
        command: ExecuteCollectionSearchOperation,
        command_digest: str,
    ) -> CollectionExecutionResultRecord | None:
        ownership = unit_of_work.collection_executions.get_ownership_by_command(
            actor.workspace_id, command.command_id
        )
        if ownership is None:
            return None
        if ownership.command_digest != command_digest:
            self._reject(
                unit_of_work,
                actor=actor,
                action=action,
                reason=AuditReasonCode.COMMAND_ID_COLLISION,
                error=InvestigationCommandCollisionError(),
            )
        if (
            ownership.collection_run_id != command.collection_run_id
            or ownership.collection_operation_id != command.collection_operation_id
        ):
            raise PersistenceDataError("Persisted collection execution ownership is invalid.")
        result = unit_of_work.collection_executions.get_result_by_command(
            actor.workspace_id, command.command_id
        )
        if result is None:
            self._reject(
                unit_of_work,
                actor=actor,
                action=action,
                reason=AuditReasonCode.COLLECTION_EXECUTION_IN_PROGRESS,
                error=CollectionExecutionInProgressError(),
            )
        try:
            validate_collection_execution_history(ownership, result)
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted collection execution history is invalid."
            ) from error
        return result

    def _resolve_ownership_conflict(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        action: AuditActionCode,
        command: ExecuteCollectionSearchOperation,
        command_digest: str,
    ) -> CollectionExecutionResultRecord:
        by_command = unit_of_work.collection_executions.get_ownership_by_command(
            actor.workspace_id, command.command_id
        )
        if by_command is not None and by_command.command_digest != command_digest:
            self._reject(
                unit_of_work,
                actor=actor,
                action=action,
                reason=AuditReasonCode.COMMAND_ID_COLLISION,
                error=InvestigationCommandCollisionError(),
            )
        if by_command is not None:
            if (
                by_command.collection_run_id != command.collection_run_id
                or by_command.collection_operation_id != command.collection_operation_id
            ):
                raise PersistenceDataError("Persisted collection execution ownership is invalid.")
            result = unit_of_work.collection_executions.get_result_by_command(
                actor.workspace_id, command.command_id
            )
            if result is not None:
                try:
                    validate_collection_execution_history(by_command, result)
                except DomainError as error:
                    raise PersistenceDataError(
                        "Persisted collection execution history is invalid."
                    ) from error
                return result
            self._reject(
                unit_of_work,
                actor=actor,
                action=action,
                reason=AuditReasonCode.COLLECTION_EXECUTION_IN_PROGRESS,
                error=CollectionExecutionInProgressError(),
            )
        by_operation = unit_of_work.collection_executions.get_ownership_by_operation(
            actor.workspace_id, command.collection_operation_id
        )
        if by_operation is None:
            raise PersistenceDataError("Collection execution ownership conflict is invalid.")
        self._reject(
            unit_of_work,
            actor=actor,
            action=action,
            reason=AuditReasonCode.COLLECTION_EXECUTION_ALREADY_OWNED,
            error=CollectionExecutionAlreadyOwnedError(),
        )

    def _descriptor_matches_manifest(
        self, descriptor: ConnectorDescriptor, operation: CollectionOperation
    ) -> bool:
        return (
            descriptor.connector_id in self._admitted_connector_ids
            and descriptor.connector_id == operation.connector_id
            and descriptor.version == operation.connector_version
            and descriptor.contract_version == operation.contract_version
            and descriptor.source_id == operation.source_id
            and descriptor.coverage_kind == operation.coverage_kind
            and descriptor.access_type == operation.access_type
            and descriptor.operations == frozenset(operation.connector_operations)
            and descriptor.supports_test_mode
            and ConnectorOperation.SEARCH in operation.connector_operations
        )

    def _authorize(
        self, unit_of_work: UnitOfWork, actor: ActorContext, action: AuditActionCode
    ) -> None:
        decision = self._authorizer.authorize(
            unit_of_work, actor, Permission.COLLECTION_OPERATION_EXECUTE
        )
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

    def _reject_invalid(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        action: AuditActionCode,
        at: datetime | None = None,
    ) -> Never:
        self._reject(
            unit_of_work,
            actor=actor,
            action=action,
            reason=AuditReasonCode.COLLECTION_EXECUTION_INVALID,
            error=InvalidCollectionExecutionError(),
            occurred_at=at,
        )

    def _reject(
        self,
        unit_of_work: UnitOfWork,
        *,
        actor: ActorContext,
        action: AuditActionCode,
        reason: AuditReasonCode,
        error: Exception,
        occurred_at: datetime | None = None,
    ) -> Never:
        commit_standalone_outcome(
            unit_of_work,
            actor=actor,
            action=action,
            resource_type=AuditResourceType.INVESTIGATION,
            resource_id=None,
            outcome=AuditOutcome.FAILURE,
            reason=reason,
            occurred_at=occurred_at if occurred_at is not None else self._clock.now(),
        )
        raise error


def _remaining_budget(
    budget: Money | None, completed: tuple[CollectionExecutionResultRecord, ...]
) -> Money | None:
    if budget is None:
        return None
    spent = Money(Decimal("0"), budget.currency)
    for result in completed:
        cost = result.usage_cost
        if cost is not None:
            if cost.currency != budget.currency:
                raise PersistenceDataError("Persisted collection execution cost currency diverges.")
            spent += cost
    if spent.amount >= budget.amount:
        return Money(Decimal("0"), budget.currency)
    return budget - spent


__all__ = ["CollectionExecutionService"]
