"""SQLAlchemy Core repository adapters using a caller-owned connection."""

from collections.abc import Mapping
from typing import cast
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.sql.elements import ColumnElement

from intelligence.application.collection_activation import validate_collection_activation_history
from intelligence.application.collection_execution import (
    CollectionExecutionOwnership,
    CollectionExecutionResultRecord,
    validate_collection_execution_history,
)
from intelligence.application.entity_candidate_review import EntityCandidateBatchRecord
from intelligence.application.entity_confirmation import (
    EntityResolutionDecisionRecord,
    validate_entity_resolution_decision_context,
)
from intelligence.application.errors import (
    PersistenceConflictError,
    PersistenceDataError,
    PersistenceError,
)
from intelligence.application.investigation_lifecycle import (
    InvestigationCommandType,
    InvestigationTransitionRecord,
)
from intelligence.domain.audit import AuditEvent
from intelligence.domain.companies import Company
from intelligence.domain.errors import DomainError
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
    CompanyId,
    EntityCandidateBatchId,
    EntityResolutionDecisionId,
    InvestigationCommandId,
    InvestigationId,
    InvestigationPlanId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.identities import (
    EmailAddress,
    MembershipRole,
    MembershipStatus,
    UserAccount,
    WorkspaceMembership,
)
from intelligence.domain.investigations import Investigation
from intelligence.domain.workspaces import Workspace
from intelligence.infrastructure.persistence.postgresql.mappers import (
    audit_event_to_values,
    collection_dependency_to_values,
    collection_execution_ownership_from_values,
    collection_execution_ownership_to_values,
    collection_execution_result_from_values,
    collection_execution_result_to_values,
    collection_operation_to_values,
    collection_run_from_values,
    collection_run_to_values,
    company_from_values,
    company_to_values,
    entity_candidate_batch_from_values,
    entity_candidate_batch_to_values,
    entity_candidate_dimension_to_values,
    entity_candidate_to_values,
    entity_resolution_decision_from_values,
    entity_resolution_decision_to_values,
    investigation_from_values,
    investigation_lifecycle_to_values,
    investigation_plan_from_values,
    investigation_plan_to_values,
    investigation_to_values,
    investigation_transition_from_values,
    investigation_transition_to_values,
    planned_capability_to_values,
    planned_connector_option_to_values,
    user_account_from_values,
    user_account_to_values,
    workspace_from_values,
    workspace_membership_from_values,
    workspace_membership_to_values,
    workspace_to_values,
)
from intelligence.infrastructure.persistence.postgresql.tables import (
    audit_event_table,
    collection_operation_dependency_table,
    collection_operation_execution_result_table,
    collection_operation_execution_table,
    collection_operation_table,
    collection_run_table,
    company_table,
    entity_candidate_batch_table,
    entity_candidate_dimension_score_table,
    entity_candidate_table,
    entity_resolution_decision_table,
    investigation_plan_table,
    investigation_table,
    investigation_transition_table,
    planned_capability_table,
    planned_connector_option_table,
    user_account_table,
    workspace_membership_table,
    workspace_table,
)
from intelligence.infrastructure.persistence.postgresql.transaction_guard import (
    PostgreSQLTransactionGuard,
)
from intelligence.orchestration.collection_activation import (
    CollectionRun,
    validate_collection_run_context,
)
from intelligence.orchestration.planning import (
    InvestigationPlan,
    validate_investigation_plan_context,
)


class PostgreSQLWorkspaceRepository:
    """Core adapter for workspace snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, workspace: Workspace) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(workspace_table).values(**workspace_to_values(workspace)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            workspace_table.c.id,
            workspace_table.c.name,
            workspace_table.c.status,
            workspace_table.c.retention_policy_version,
            workspace_table.c.created_at,
            workspace_table.c.updated_at,
        ).where(workspace_table.c.id == workspace_id.value)
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            workspace_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLCompanyRepository:
    """Core adapter for workspace-scoped company snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, company: Company) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(company_table).values(**company_to_values(company)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, workspace_id: WorkspaceId, company_id: CompanyId) -> Company | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            company_table.c.id,
            company_table.c.workspace_id,
            company_table.c.legal_name,
            company_table.c.trade_name,
            company_table.c.country_code,
            company_table.c.legal_form,
            company_table.c.status,
            company_table.c.incorporated_on,
            company_table.c.dissolved_on,
            company_table.c.official_domain,
            company_table.c.created_at,
            company_table.c.updated_at,
        ).where(
            company_table.c.workspace_id == workspace_id.value,
            company_table.c.id == company_id.value,
        )
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            company_from_values(cast(Mapping[str, object], values)) if values is not None else None
        )


class PostgreSQLInvestigationRepository:
    """Core adapter for workspace-scoped investigation snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, investigation: Investigation) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(investigation_table).values(**investigation_to_values(investigation))
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            investigation_table.c.id,
            investigation_table.c.workspace_id,
            investigation_table.c.requested_by,
            investigation_table.c.profile_code,
            investigation_table.c.country_code,
            investigation_table.c.state,
            investigation_table.c.state_version,
            investigation_table.c.input_snapshot,
            investigation_table.c.input_schema_version,
            investigation_table.c.input_digest,
            investigation_table.c.active_candidate_batch_id,
            investigation_table.c.confirmed_company_id,
            investigation_table.c.budget_amount,
            investigation_table.c.budget_currency,
            investigation_table.c.deadline_at,
            investigation_table.c.started_at,
            investigation_table.c.completed_at,
            investigation_table.c.created_at,
        ).where(
            investigation_table.c.workspace_id == workspace_id.value,
            investigation_table.c.id == investigation_id.value,
        )
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            investigation_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )

    def update_if_version(
        self,
        investigation: Investigation,
        *,
        expected_state_version: int,
    ) -> bool:
        """Compare and swap only lifecycle-owned fields under tenant scope."""

        connection = self._transaction_guard.require_active()
        if investigation.state_version != expected_state_version + 1:
            raise PersistenceConflictError("Persistence constraint conflict.")
        statement = (
            sa.update(investigation_table)
            .where(
                investigation_table.c.workspace_id == investigation.workspace_id.value,
                investigation_table.c.id == investigation.id.value,
                investigation_table.c.state_version == expected_state_version,
            )
            .values(**investigation_lifecycle_to_values(investigation))
        )
        try:
            result = connection.execute(statement)
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return result.rowcount == 1

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        """Lock one tenant-scoped Investigation for cross-command serialization."""

        connection = self._transaction_guard.require_active()
        statement = (
            sa.select(investigation_table)
            .where(
                investigation_table.c.workspace_id == workspace_id.value,
                investigation_table.c.id == investigation_id.value,
            )
            .with_for_update()
        )
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            investigation_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLInvestigationTransitionRepository:
    """Append-only adapter for durable lifecycle command records."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def acquire_command_lock(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> None:
        connection = self._transaction_guard.require_active()
        lock_key = f"{workspace_id.value}:{command_id.value}"
        statement = sa.select(
            sa.func.pg_advisory_xact_lock(
                sa.func.hashtextextended(sa.bindparam("command_lock_key"), 0)
            )
        )
        try:
            connection.execute(statement, {"command_lock_key": lock_key}).scalar_one()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> InvestigationTransitionRecord | None:
        connection = self._transaction_guard.require_active()
        statement = self._select_record().where(
            investigation_transition_table.c.workspace_id == workspace_id.value,
            investigation_transition_table.c.command_id == command_id.value,
        )
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            investigation_transition_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )

    def add(self, record: InvestigationTransitionRecord) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(investigation_transition_table).values(
                    **investigation_transition_to_values(record)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    @staticmethod
    def _select_record() -> sa.Select[tuple[object, ...]]:
        return sa.select(
            investigation_transition_table.c.id,
            investigation_transition_table.c.workspace_id,
            investigation_transition_table.c.investigation_id,
            investigation_transition_table.c.command_id,
            investigation_transition_table.c.command_type,
            investigation_transition_table.c.state_before,
            investigation_transition_table.c.version_before,
            investigation_transition_table.c.state_after,
            investigation_transition_table.c.version_after,
            investigation_transition_table.c.actor_user_id,
            investigation_transition_table.c.reason_code,
            investigation_transition_table.c.occurred_at,
            investigation_transition_table.c.command_digest,
            investigation_transition_table.c.correlation_id,
            investigation_transition_table.c.candidate_batch_id,
            investigation_transition_table.c.candidate_count,
            investigation_transition_table.c.top_classification,
            investigation_transition_table.c.policy_id,
            investigation_transition_table.c.policy_version,
            investigation_transition_table.c.confirmation_decision_id,
            investigation_transition_table.c.confirmed_company_id,
            investigation_transition_table.c.confirmed_candidate_batch_id,
            investigation_transition_table.c.confirmed_candidate_id,
            investigation_transition_table.c.confirmation_reason_code,
            investigation_transition_table.c.confirmed_candidate_classification,
            investigation_transition_table.c.confirmed_candidate_rank,
            investigation_transition_table.c.matching_policy_id,
            investigation_transition_table.c.matching_policy_version,
            investigation_transition_table.c.materialization_policy_id,
            investigation_transition_table.c.materialization_policy_version,
            investigation_transition_table.c.collection_run_id,
            investigation_transition_table.c.collection_company_id,
            investigation_transition_table.c.collection_plan_id,
            investigation_transition_table.c.collection_operation_count,
            investigation_transition_table.c.collection_activation_policy_id,
            investigation_transition_table.c.collection_activation_policy_version,
        )


class PostgreSQLEntityCandidateBatchRepository:
    """Append-only adapter for complete candidate batches and dimensional scores."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, record: EntityCandidateBatchRecord) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(entity_candidate_batch_table).values(
                    **entity_candidate_batch_to_values(record)
                )
            )
            for candidate in record.candidates:
                connection.execute(
                    sa.insert(entity_candidate_table).values(
                        **entity_candidate_to_values(candidate)
                    )
                )
                connection.execute(
                    sa.insert(entity_candidate_dimension_score_table),
                    [
                        entity_candidate_dimension_to_values(dimension)
                        for dimension in candidate.dimensions
                    ],
                )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(
        self,
        workspace_id: WorkspaceId,
        batch_id: EntityCandidateBatchId,
    ) -> EntityCandidateBatchRecord | None:
        connection = self._transaction_guard.require_active()
        batch_statement = sa.select(entity_candidate_batch_table).where(
            entity_candidate_batch_table.c.workspace_id == workspace_id.value,
            entity_candidate_batch_table.c.id == batch_id.value,
        )
        candidate_statement = (
            sa.select(entity_candidate_table)
            .where(
                entity_candidate_table.c.workspace_id == workspace_id.value,
                entity_candidate_table.c.batch_id == batch_id.value,
            )
            .order_by(entity_candidate_table.c.rank)
        )
        dimension_statement = (
            sa.select(entity_candidate_dimension_score_table)
            .where(
                entity_candidate_dimension_score_table.c.workspace_id == workspace_id.value,
                entity_candidate_dimension_score_table.c.batch_id == batch_id.value,
            )
            .order_by(
                entity_candidate_dimension_score_table.c.candidate_id,
                entity_candidate_dimension_score_table.c.dimension,
            )
        )
        try:
            batch_values = connection.execute(batch_statement).mappings().first()
            if batch_values is None:
                return None
            candidate_values = connection.execute(candidate_statement).mappings().all()
            dimension_values = connection.execute(dimension_statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return entity_candidate_batch_from_values(
            cast(Mapping[str, object], batch_values),
            tuple(cast(Mapping[str, object], row) for row in candidate_values),
            tuple(cast(Mapping[str, object], row) for row in dimension_values),
        )


class PostgreSQLEntityResolutionDecisionRepository:
    """Append-only adapter that reconstitutes decisions fail closed."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, record: EntityResolutionDecisionRecord) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(entity_resolution_decision_table).values(
                    **entity_resolution_decision_to_values(record)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> EntityResolutionDecisionRecord | None:
        return self._find(
            workspace_id,
            entity_resolution_decision_table.c.command_id == command_id.value,
        )

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> EntityResolutionDecisionRecord | None:
        return self._find(
            workspace_id,
            entity_resolution_decision_table.c.investigation_id == investigation_id.value,
        )

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        decision_id: EntityResolutionDecisionId,
    ) -> EntityResolutionDecisionRecord | None:
        return self._find(
            workspace_id,
            entity_resolution_decision_table.c.id == decision_id.value,
        )

    def _find(
        self,
        workspace_id: WorkspaceId,
        predicate: ColumnElement[bool],
    ) -> EntityResolutionDecisionRecord | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(entity_resolution_decision_table).where(
            entity_resolution_decision_table.c.workspace_id == workspace_id.value,
            predicate,
        )
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if values is None:
            return None
        record = entity_resolution_decision_from_values(cast(Mapping[str, object], values))
        transition = PostgreSQLInvestigationTransitionRepository(
            self._transaction_guard
        ).get_by_command(workspace_id, record.command_id)
        investigation = PostgreSQLInvestigationRepository(self._transaction_guard).get(
            workspace_id,
            record.investigation_id,
        )
        batch = PostgreSQLEntityCandidateBatchRepository(self._transaction_guard).get(
            workspace_id,
            record.candidate_batch_id,
        )
        company = PostgreSQLCompanyRepository(self._transaction_guard).get(
            workspace_id,
            record.company_id,
        )
        if transition is None or investigation is None or batch is None or company is None:
            raise PersistenceDataError(
                "Persisted entity resolution decision references missing context."
            )
        try:
            validate_entity_resolution_decision_context(
                record,
                transition=transition,
                investigation=investigation,
                batch=batch,
                company=company,
            )
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted entity resolution decision context is invalid."
            ) from error
        return record


class PostgreSQLInvestigationPlanRepository:
    """Append-only adapter for complete plans and their command ledger fields."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, plan: InvestigationPlan) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(investigation_plan_table).values(**investigation_plan_to_values(plan))
            )
            for capability in plan.capabilities:
                connection.execute(
                    sa.insert(planned_capability_table).values(
                        **planned_capability_to_values(capability, plan=plan)
                    )
                )
                for option in capability.connector_options:
                    connection.execute(
                        sa.insert(planned_connector_option_table).values(
                            **planned_connector_option_to_values(option, plan=plan)
                        )
                    )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> InvestigationPlan | None:
        return self._find(
            workspace_id,
            investigation_plan_table.c.command_id == command_id.value,
        )

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> InvestigationPlan | None:
        return self._find(
            workspace_id,
            investigation_plan_table.c.investigation_id == investigation_id.value,
        )

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        plan_id: InvestigationPlanId,
    ) -> InvestigationPlan | None:
        return self._find(
            workspace_id,
            investigation_plan_table.c.id == plan_id.value,
        )

    def _find(
        self,
        workspace_id: WorkspaceId,
        predicate: ColumnElement[bool],
    ) -> InvestigationPlan | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(investigation_plan_table).where(
            investigation_plan_table.c.workspace_id == workspace_id.value,
            predicate,
        )
        try:
            plan_values = connection.execute(statement).mappings().first()
            if plan_values is None:
                return None
            plan_id = cast(UUID, plan_values["id"])
            capability_values = (
                connection.execute(
                    sa.select(planned_capability_table)
                    .where(
                        planned_capability_table.c.workspace_id == workspace_id.value,
                        planned_capability_table.c.plan_id == plan_id,
                    )
                    .order_by(
                        planned_capability_table.c.priority,
                        planned_capability_table.c.capability,
                    )
                )
                .mappings()
                .all()
            )
            option_values = (
                connection.execute(
                    sa.select(planned_connector_option_table)
                    .where(
                        planned_connector_option_table.c.workspace_id == workspace_id.value,
                        planned_connector_option_table.c.plan_id == plan_id,
                    )
                    .order_by(
                        planned_connector_option_table.c.planned_capability_id,
                        planned_connector_option_table.c.eligibility_rank,
                    )
                )
                .mappings()
                .all()
            )
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        plan = investigation_plan_from_values(
            cast(Mapping[str, object], plan_values),
            tuple(cast(Mapping[str, object], row) for row in capability_values),
            tuple(cast(Mapping[str, object], row) for row in option_values),
        )
        investigation = PostgreSQLInvestigationRepository(self._transaction_guard).get(
            workspace_id,
            plan.investigation_id,
        )
        company = PostgreSQLCompanyRepository(self._transaction_guard).get(
            workspace_id,
            plan.company_id,
        )
        if investigation is None or company is None:
            raise PersistenceDataError("Persisted investigation plan references missing context.")
        try:
            validate_investigation_plan_context(
                plan,
                investigation=investigation,
                company=company,
            )
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted investigation plan context is invalid."
            ) from error
        return plan


class PostgreSQLCollectionRunRepository:
    """Append-only adapter for complete collection activation manifests."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, run: CollectionRun) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(collection_run_table).values(**collection_run_to_values(run))
            )
            for operation in run.operations:
                connection.execute(
                    sa.insert(collection_operation_table).values(
                        **collection_operation_to_values(operation)
                    )
                )
                for dependency_order, dependency_id in enumerate(
                    operation.dependency_operation_ids, start=1
                ):
                    connection.execute(
                        sa.insert(collection_operation_dependency_table).values(
                            **collection_dependency_to_values(
                                operation, dependency_id, dependency_order
                            )
                        )
                    )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> CollectionRun | None:
        return self._find(
            workspace_id,
            collection_run_table.c.command_id == command_id.value,
            investigation_transition_table.c.command_id == command_id.value,
        )

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> CollectionRun | None:
        return self._find(
            workspace_id,
            collection_run_table.c.investigation_id == investigation_id.value,
            investigation_transition_table.c.investigation_id == investigation_id.value,
        )

    def get_by_plan(
        self,
        workspace_id: WorkspaceId,
        plan_id: InvestigationPlanId,
    ) -> CollectionRun | None:
        return self._find(
            workspace_id,
            collection_run_table.c.plan_id == plan_id.value,
            investigation_transition_table.c.collection_plan_id == plan_id.value,
        )

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        run_id: CollectionRunId,
    ) -> CollectionRun | None:
        return self._find(
            workspace_id,
            collection_run_table.c.id == run_id.value,
            investigation_transition_table.c.collection_run_id == run_id.value,
        )

    def _find(
        self,
        workspace_id: WorkspaceId,
        predicate: ColumnElement[bool],
        orphan_transition_predicate: ColumnElement[bool],
    ) -> CollectionRun | None:
        connection = self._transaction_guard.require_active()
        try:
            run_values = (
                connection.execute(
                    sa.select(collection_run_table).where(
                        collection_run_table.c.workspace_id == workspace_id.value,
                        predicate,
                    )
                )
                .mappings()
                .first()
            )
            if run_values is None:
                orphan_transition = connection.execute(
                    sa.select(investigation_transition_table.c.id)
                    .where(
                        investigation_transition_table.c.workspace_id == workspace_id.value,
                        investigation_transition_table.c.command_type
                        == InvestigationCommandType.START_COLLECTION.value,
                        orphan_transition_predicate,
                    )
                    .limit(1)
                ).first()
                if orphan_transition is not None:
                    raise PersistenceDataError(
                        "Persisted collection transition references a missing run."
                    )
                return None
            run_id = cast(UUID, run_values["id"])
            operation_values = (
                connection.execute(
                    sa.select(collection_operation_table)
                    .where(
                        collection_operation_table.c.workspace_id == workspace_id.value,
                        collection_operation_table.c.collection_run_id == run_id,
                    )
                    .order_by(
                        collection_operation_table.c.priority,
                        collection_operation_table.c.capability,
                    )
                )
                .mappings()
                .all()
            )
            dependency_values = (
                connection.execute(
                    sa.select(collection_operation_dependency_table)
                    .where(
                        collection_operation_dependency_table.c.workspace_id == workspace_id.value,
                        collection_operation_dependency_table.c.collection_run_id == run_id,
                    )
                    .order_by(
                        collection_operation_dependency_table.c.operation_id,
                        collection_operation_dependency_table.c.dependency_order,
                    )
                )
                .mappings()
                .all()
            )
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        run = collection_run_from_values(
            cast(Mapping[str, object], run_values),
            tuple(cast(Mapping[str, object], row) for row in operation_values),
            tuple(cast(Mapping[str, object], row) for row in dependency_values),
        )
        plan = PostgreSQLInvestigationPlanRepository(self._transaction_guard).get_by_id(
            workspace_id, run.plan_id
        )
        investigation = PostgreSQLInvestigationRepository(self._transaction_guard).get(
            workspace_id, run.investigation_id
        )
        company = PostgreSQLCompanyRepository(self._transaction_guard).get(
            workspace_id, run.company_id
        )
        transition = PostgreSQLInvestigationTransitionRepository(
            self._transaction_guard
        ).get_by_command(workspace_id, run.command_id)
        if plan is None or investigation is None or company is None or transition is None:
            raise PersistenceDataError("Persisted collection run references missing context.")
        try:
            validate_collection_run_context(
                run, investigation=investigation, company=company, plan=plan
            )
            validate_collection_activation_history(run, transition)
        except DomainError as error:
            raise PersistenceDataError("Persisted collection run context is invalid.") from error
        return run


class PostgreSQLCollectionExecutionRepository:
    """Append-only durable ownership and redacted completions for F4.6."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def try_add_ownership(self, ownership: CollectionExecutionOwnership) -> bool:
        connection = self._transaction_guard.require_active()
        statement = (
            postgresql_insert(collection_operation_execution_table)
            .values(**collection_execution_ownership_to_values(ownership))
            .on_conflict_do_nothing()
            .returning(collection_operation_execution_table.c.command_id)
        )
        try:
            return connection.execute(statement).scalar_one_or_none() is not None
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def add_result(self, result: CollectionExecutionResultRecord) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(collection_operation_execution_result_table).values(
                    **collection_execution_result_to_values(result)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get_ownership_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionExecutionOwnership | None:
        return self._ownership(
            workspace_id, collection_operation_execution_table.c.command_id == command_id.value
        )

    def get_ownership_by_operation(
        self, workspace_id: WorkspaceId, operation_id: CollectionOperationId
    ) -> CollectionExecutionOwnership | None:
        return self._ownership(
            workspace_id,
            collection_operation_execution_table.c.collection_operation_id == operation_id.value,
        )

    def get_result_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionExecutionResultRecord | None:
        return self._result(
            workspace_id,
            collection_operation_execution_result_table.c.command_id == command_id.value,
        )

    def get_result_by_operation(
        self, workspace_id: WorkspaceId, operation_id: CollectionOperationId
    ) -> CollectionExecutionResultRecord | None:
        return self._result(
            workspace_id,
            collection_operation_execution_result_table.c.collection_operation_id
            == operation_id.value,
        )

    def list_results_by_run(
        self, workspace_id: WorkspaceId, run_id: CollectionRunId
    ) -> tuple[CollectionExecutionResultRecord, ...]:
        connection = self._transaction_guard.require_active()
        try:
            rows = (
                connection.execute(
                    sa.select(collection_operation_execution_result_table)
                    .where(
                        collection_operation_execution_result_table.c.workspace_id
                        == workspace_id.value,
                        collection_operation_execution_result_table.c.collection_run_id
                        == run_id.value,
                    )
                    .order_by(collection_operation_execution_result_table.c.collection_operation_id)
                )
                .mappings()
                .all()
            )
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        results = tuple(
            collection_execution_result_from_values(cast(Mapping[str, object], row)) for row in rows
        )
        for result in results:
            ownership = self.get_ownership_by_command(workspace_id, result.command_id)
            self._validate_result(ownership, result)
        return results

    def _ownership(
        self, workspace_id: WorkspaceId, predicate: ColumnElement[bool]
    ) -> CollectionExecutionOwnership | None:
        connection = self._transaction_guard.require_active()
        try:
            row = (
                connection.execute(
                    sa.select(collection_operation_execution_table).where(
                        collection_operation_execution_table.c.workspace_id == workspace_id.value,
                        predicate,
                    )
                )
                .mappings()
                .first()
            )
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            collection_execution_ownership_from_values(cast(Mapping[str, object], row))
            if row is not None
            else None
        )

    def _result(
        self, workspace_id: WorkspaceId, predicate: ColumnElement[bool]
    ) -> CollectionExecutionResultRecord | None:
        connection = self._transaction_guard.require_active()
        try:
            row = (
                connection.execute(
                    sa.select(collection_operation_execution_result_table).where(
                        collection_operation_execution_result_table.c.workspace_id
                        == workspace_id.value,
                        predicate,
                    )
                )
                .mappings()
                .first()
            )
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if row is None:
            return None
        result = collection_execution_result_from_values(cast(Mapping[str, object], row))
        self._validate_result(
            self.get_ownership_by_command(workspace_id, result.command_id), result
        )
        return result

    @staticmethod
    def _validate_result(
        ownership: CollectionExecutionOwnership | None,
        result: CollectionExecutionResultRecord,
    ) -> None:
        if ownership is None:
            raise PersistenceDataError("Persisted collection execution result lacks its ownership.")
        try:
            validate_collection_execution_history(ownership, result)
        except DomainError as error:
            raise PersistenceDataError(
                "Persisted collection execution history is invalid."
            ) from error


class PostgreSQLUserRepository:
    """Core adapter for internal user identity snapshots."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, user: UserAccount) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(user_account_table).values(**user_account_to_values(user)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(self, user_id: UserId) -> UserAccount | None:
        return self._find(user_account_table.c.id == user_id.value)

    def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        return self._find(user_account_table.c.email == email.value)

    def _find(self, predicate: sa.ColumnElement[bool]) -> UserAccount | None:
        connection = self._transaction_guard.require_active()
        statement = sa.select(
            user_account_table.c.id,
            user_account_table.c.email,
            user_account_table.c.display_name,
            user_account_table.c.status,
            user_account_table.c.created_at,
            user_account_table.c.updated_at,
        ).where(predicate)
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            user_account_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )


class PostgreSQLWorkspaceMembershipRepository:
    """Core adapter for the unique user membership within a workspace."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, membership: WorkspaceMembership) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(
                sa.insert(workspace_membership_table).values(
                    **workspace_membership_to_values(membership)
                )
            )
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error

    def get(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        return self._find(workspace_id, user_id, for_update=False)

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        """Lock the requested membership inside the original UoW transaction."""

        return self._find(workspace_id, user_id, for_update=True)

    def list_active_owners_for_update(
        self,
        workspace_id: WorkspaceId,
    ) -> list[WorkspaceMembership]:
        """Lock active owners by stable membership ID order."""

        connection = self._transaction_guard.require_active()
        statement = (
            self._select_membership()
            .where(
                workspace_membership_table.c.workspace_id == workspace_id.value,
                workspace_membership_table.c.status == MembershipStatus.ACTIVE.value,
                workspace_membership_table.c.role == MembershipRole.OWNER.value,
            )
            .order_by(workspace_membership_table.c.id)
            .with_for_update()
        )
        try:
            values = connection.execute(statement).mappings().all()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return [workspace_membership_from_values(cast(Mapping[str, object], row)) for row in values]

    def update(self, membership: WorkspaceMembership) -> None:
        """Update mutable snapshot fields while matching all stable identity fields."""

        connection = self._transaction_guard.require_active()
        statement = (
            sa.update(workspace_membership_table)
            .where(
                workspace_membership_table.c.workspace_id == membership.workspace_id.value,
                workspace_membership_table.c.user_id == membership.user_id.value,
                workspace_membership_table.c.id == membership.id.value,
            )
            .values(
                role=membership.role.value,
                status=membership.status.value,
                updated_at=membership.updated_at,
                deactivated_at=membership.deactivated_at,
            )
        )
        try:
            result = connection.execute(statement)
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        if result.rowcount != 1:
            raise PersistenceConflictError("Persistence constraint conflict.")

    def _find(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
        *,
        for_update: bool,
    ) -> WorkspaceMembership | None:
        connection = self._transaction_guard.require_active()
        statement = self._select_membership().where(
            workspace_membership_table.c.workspace_id == workspace_id.value,
            workspace_membership_table.c.user_id == user_id.value,
        )
        if for_update:
            statement = statement.with_for_update()
        try:
            values = connection.execute(statement).mappings().first()
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error
        return (
            workspace_membership_from_values(cast(Mapping[str, object], values))
            if values is not None
            else None
        )

    @staticmethod
    def _select_membership() -> sa.Select[tuple[object, ...]]:
        return sa.select(
            workspace_membership_table.c.id,
            workspace_membership_table.c.workspace_id,
            workspace_membership_table.c.user_id,
            workspace_membership_table.c.role,
            workspace_membership_table.c.status,
            workspace_membership_table.c.created_at,
            workspace_membership_table.c.updated_at,
            workspace_membership_table.c.deactivated_at,
        )


class PostgreSQLAuditEventRepository:
    """Core append-only adapter for minimal audit events."""

    def __init__(self, transaction_guard: PostgreSQLTransactionGuard) -> None:
        self._transaction_guard = transaction_guard

    def add(self, event: AuditEvent) -> None:
        connection = self._transaction_guard.require_active()
        try:
            connection.execute(sa.insert(audit_event_table).values(**audit_event_to_values(event)))
        except IntegrityError as error:
            raise PersistenceConflictError("Persistence constraint conflict.") from error
        except DBAPIError as error:
            raise PersistenceError("Persistence operation failed.") from error


__all__ = [
    "PostgreSQLAuditEventRepository",
    "PostgreSQLCollectionExecutionRepository",
    "PostgreSQLCollectionRunRepository",
    "PostgreSQLCompanyRepository",
    "PostgreSQLEntityCandidateBatchRepository",
    "PostgreSQLEntityResolutionDecisionRepository",
    "PostgreSQLInvestigationRepository",
    "PostgreSQLInvestigationTransitionRepository",
    "PostgreSQLUserRepository",
    "PostgreSQLWorkspaceMembershipRepository",
    "PostgreSQLWorkspaceRepository",
]
