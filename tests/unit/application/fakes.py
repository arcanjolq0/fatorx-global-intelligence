"""Controlled in-memory application adapters with explicit transaction semantics."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from types import TracebackType
from typing import Literal, Self

from intelligence.application.collection_execution import (
    CollectionExecutionOwnership,
    CollectionExecutionResultRecord,
)
from intelligence.application.entity_candidate_review import EntityCandidateBatchRecord
from intelligence.application.entity_confirmation import EntityResolutionDecisionRecord
from intelligence.application.errors import PersistenceConflictError, PersistenceError
from intelligence.application.investigation_lifecycle import InvestigationTransitionRecord
from intelligence.claims.models import Claim, ClaimEvidenceLink, ClaimHistory
from intelligence.domain.audit import AuditEvent
from intelligence.domain.companies import Company
from intelligence.domain.identifiers import (
    ClaimCommandId,
    ClaimId,
    CollectionOperationId,
    CollectionRunId,
    CompanyId,
    EntityCandidateBatchId,
    EntityResolutionDecisionId,
    EvidenceCommandId,
    EvidenceId,
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
from intelligence.evidence.models import Artifact, Evidence, EvidenceHistory, EvidenceLifecycleEvent
from intelligence.orchestration.collection_activation import CollectionRun
from intelligence.orchestration.planning import InvestigationPlan


@dataclass(slots=True)
class FakeDatabase:
    workspaces: dict[WorkspaceId, Workspace] = field(default_factory=dict)
    companies: dict[tuple[WorkspaceId, CompanyId], Company] = field(default_factory=dict)
    investigations: dict[tuple[WorkspaceId, InvestigationId], Investigation] = field(
        default_factory=dict
    )
    investigation_transitions: dict[
        tuple[WorkspaceId, InvestigationCommandId], InvestigationTransitionRecord
    ] = field(default_factory=dict)
    entity_candidate_batches: dict[
        tuple[WorkspaceId, EntityCandidateBatchId], EntityCandidateBatchRecord
    ] = field(default_factory=dict)
    entity_resolution_decisions: dict[
        tuple[WorkspaceId, EntityResolutionDecisionId], EntityResolutionDecisionRecord
    ] = field(default_factory=dict)
    investigation_plans: dict[tuple[WorkspaceId, InvestigationPlanId], InvestigationPlan] = field(
        default_factory=dict
    )
    collection_runs: dict[tuple[WorkspaceId, CollectionRunId], CollectionRun] = field(
        default_factory=dict
    )
    collection_execution_ownership: dict[
        tuple[WorkspaceId, InvestigationCommandId], CollectionExecutionOwnership
    ] = field(default_factory=dict)
    collection_execution_results: dict[
        tuple[WorkspaceId, InvestigationCommandId], CollectionExecutionResultRecord
    ] = field(default_factory=dict)
    users: dict[UserId, UserAccount] = field(default_factory=dict)
    memberships: dict[tuple[WorkspaceId, UserId], WorkspaceMembership] = field(default_factory=dict)
    audit_events: list[AuditEvent] = field(default_factory=list)
    evidence_histories: dict[tuple[WorkspaceId, EvidenceId], EvidenceHistory] = field(
        default_factory=dict
    )
    claim_histories: dict[tuple[WorkspaceId, ClaimId], ClaimHistory] = field(default_factory=dict)

    def clone(self) -> FakeDatabase:
        return FakeDatabase(
            workspaces=dict(self.workspaces),
            companies=dict(self.companies),
            investigations=dict(self.investigations),
            investigation_transitions=dict(self.investigation_transitions),
            entity_candidate_batches=dict(self.entity_candidate_batches),
            entity_resolution_decisions=dict(self.entity_resolution_decisions),
            investigation_plans=dict(self.investigation_plans),
            collection_runs=dict(self.collection_runs),
            collection_execution_ownership=dict(self.collection_execution_ownership),
            collection_execution_results=dict(self.collection_execution_results),
            users=dict(self.users),
            memberships=dict(self.memberships),
            audit_events=list(self.audit_events),
            evidence_histories=dict(self.evidence_histories),
            claim_histories=dict(self.claim_histories),
        )

    def replace_with(self, other: FakeDatabase) -> None:
        self.workspaces = dict(other.workspaces)
        self.companies = dict(other.companies)
        self.investigations = dict(other.investigations)
        self.investigation_transitions = dict(other.investigation_transitions)
        self.entity_candidate_batches = dict(other.entity_candidate_batches)
        self.entity_resolution_decisions = dict(other.entity_resolution_decisions)
        self.investigation_plans = dict(other.investigation_plans)
        self.collection_runs = dict(other.collection_runs)
        self.collection_execution_ownership = dict(other.collection_execution_ownership)
        self.collection_execution_results = dict(other.collection_execution_results)
        self.users = dict(other.users)
        self.memberships = dict(other.memberships)
        self.audit_events = list(other.audit_events)
        self.evidence_histories = dict(other.evidence_histories)
        self.claim_histories = dict(other.claim_histories)


class FakeWorkspaceRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def add(self, workspace: Workspace) -> None:
        if workspace.id in self._database.workspaces:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.workspaces[workspace.id] = workspace

    def get(self, workspace_id: WorkspaceId) -> Workspace | None:
        return self._database.workspaces.get(workspace_id)


class FakeCompanyRepository:
    def __init__(self, database: FakeDatabase, *, fail_add: bool = False) -> None:
        self._database = database
        self._fail_add = fail_add
        self.get_calls: list[tuple[WorkspaceId, CompanyId]] = []

    def add(self, company: Company) -> None:
        if self._fail_add:
            raise PersistenceError("Persistence operation failed.")
        key = (company.workspace_id, company.id)
        if key in self._database.companies:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.companies[key] = company

    def get(self, workspace_id: WorkspaceId, company_id: CompanyId) -> Company | None:
        self.get_calls.append((workspace_id, company_id))
        return self._database.companies.get((workspace_id, company_id))


class FakeInvestigationRepository:
    def __init__(self, database: FakeDatabase, *, force_cas_conflict: bool = False) -> None:
        self._database = database
        self._force_cas_conflict = force_cas_conflict
        self.get_calls: list[tuple[WorkspaceId, InvestigationId]] = []
        self.cas_calls: list[tuple[Investigation, int]] = []
        self.get_for_update_calls: list[tuple[WorkspaceId, InvestigationId]] = []

    def add(self, investigation: Investigation) -> None:
        key = (investigation.workspace_id, investigation.id)
        if key in self._database.investigations:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.investigations[key] = investigation

    def get(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        self.get_calls.append((workspace_id, investigation_id))
        return self._database.investigations.get((workspace_id, investigation_id))

    def update_if_version(
        self,
        investigation: Investigation,
        *,
        expected_state_version: int,
    ) -> bool:
        self.cas_calls.append((investigation, expected_state_version))
        key = (investigation.workspace_id, investigation.id)
        current = self._database.investigations.get(key)
        if (
            self._force_cas_conflict
            or current is None
            or current.state_version != expected_state_version
        ):
            return False
        self._database.investigations[key] = investigation
        return True

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> Investigation | None:
        self.get_for_update_calls.append((workspace_id, investigation_id))
        return self._database.investigations.get((workspace_id, investigation_id))


class FakeInvestigationTransitionRepository:
    def __init__(self, database: FakeDatabase, *, fail_add: bool = False) -> None:
        self._database = database
        self._fail_add = fail_add
        self.lock_calls: list[tuple[WorkspaceId, InvestigationCommandId]] = []
        self.get_calls: list[tuple[WorkspaceId, InvestigationCommandId]] = []

    def acquire_command_lock(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> None:
        self.lock_calls.append((workspace_id, command_id))

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> InvestigationTransitionRecord | None:
        self.get_calls.append((workspace_id, command_id))
        return self._database.investigation_transitions.get((workspace_id, command_id))

    def add(self, record: InvestigationTransitionRecord) -> None:
        if self._fail_add:
            raise PersistenceError("Persistence operation failed.")
        key = (record.workspace_id, record.command_id)
        if key in self._database.investigation_transitions:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.investigation_transitions[key] = record


class FakeEntityCandidateBatchRepository:
    def __init__(self, database: FakeDatabase, *, fail_add: bool = False) -> None:
        self._database = database
        self._fail_add = fail_add

    def add(self, record: EntityCandidateBatchRecord) -> None:
        if self._fail_add:
            raise PersistenceError("Persistence operation failed.")
        key = (record.workspace_id, record.id)
        if key in self._database.entity_candidate_batches:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.entity_candidate_batches[key] = record

    def get(
        self,
        workspace_id: WorkspaceId,
        batch_id: EntityCandidateBatchId,
    ) -> EntityCandidateBatchRecord | None:
        return self._database.entity_candidate_batches.get((workspace_id, batch_id))


class FakeEntityResolutionDecisionRepository:
    def __init__(self, database: FakeDatabase, *, fail_add: bool = False) -> None:
        self._database = database
        self._fail_add = fail_add

    def add(self, record: EntityResolutionDecisionRecord) -> None:
        if self._fail_add:
            raise PersistenceError("Persistence operation failed.")
        if any(
            existing.workspace_id == record.workspace_id
            and (
                existing.investigation_id == record.investigation_id
                or existing.command_id == record.command_id
                or existing.company_id == record.company_id
            )
            for existing in self._database.entity_resolution_decisions.values()
        ):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.entity_resolution_decisions[(record.workspace_id, record.id)] = record

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> EntityResolutionDecisionRecord | None:
        return next(
            (
                record
                for record in self._database.entity_resolution_decisions.values()
                if record.workspace_id == workspace_id and record.command_id == command_id
            ),
            None,
        )

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> EntityResolutionDecisionRecord | None:
        return next(
            (
                record
                for record in self._database.entity_resolution_decisions.values()
                if record.workspace_id == workspace_id
                and record.investigation_id == investigation_id
            ),
            None,
        )

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        decision_id: EntityResolutionDecisionId,
    ) -> EntityResolutionDecisionRecord | None:
        return self._database.entity_resolution_decisions.get((workspace_id, decision_id))


class FakeInvestigationPlanRepository:
    def __init__(
        self,
        database: FakeDatabase,
        *,
        fail_plan_add: bool = False,
        fail_capability_add: bool = False,
        fail_option_add: bool = False,
    ) -> None:
        self._database = database
        self._fail_plan_add = fail_plan_add
        self._fail_capability_add = fail_capability_add
        self._fail_option_add = fail_option_add

    def add(self, plan: InvestigationPlan) -> None:
        if self._fail_plan_add:
            raise PersistenceError("Persistence operation failed.")
        if self._fail_capability_add and plan.capabilities:
            raise PersistenceError("Persistence operation failed.")
        if self._fail_option_add and any(item.connector_options for item in plan.capabilities):
            raise PersistenceError("Persistence operation failed.")
        if any(
            existing.workspace_id == plan.workspace_id
            and (
                existing.investigation_id == plan.investigation_id
                or existing.command_id == plan.command_id
            )
            for existing in self._database.investigation_plans.values()
        ):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.investigation_plans[(plan.workspace_id, plan.id)] = plan

    def get_by_command(
        self,
        workspace_id: WorkspaceId,
        command_id: InvestigationCommandId,
    ) -> InvestigationPlan | None:
        return next(
            (
                plan
                for plan in self._database.investigation_plans.values()
                if plan.workspace_id == workspace_id and plan.command_id == command_id
            ),
            None,
        )

    def get_by_investigation(
        self,
        workspace_id: WorkspaceId,
        investigation_id: InvestigationId,
    ) -> InvestigationPlan | None:
        return next(
            (
                plan
                for plan in self._database.investigation_plans.values()
                if plan.workspace_id == workspace_id and plan.investigation_id == investigation_id
            ),
            None,
        )

    def get_by_id(
        self,
        workspace_id: WorkspaceId,
        plan_id: InvestigationPlanId,
    ) -> InvestigationPlan | None:
        return self._database.investigation_plans.get((workspace_id, plan_id))


class FakeCollectionRunRepository:
    def __init__(
        self,
        database: FakeDatabase,
        *,
        fail_run_add: bool = False,
        fail_operation_add: bool = False,
        fail_dependency_add: bool = False,
    ) -> None:
        self._database = database
        self._fail_run_add = fail_run_add
        self._fail_operation_add = fail_operation_add
        self._fail_dependency_add = fail_dependency_add

    def add(self, run: CollectionRun) -> None:
        if self._fail_run_add:
            raise PersistenceError("Persistence operation failed.")
        if self._fail_operation_add and run.operations:
            raise PersistenceError("Persistence operation failed.")
        if self._fail_dependency_add and any(
            operation.dependency_operation_ids for operation in run.operations
        ):
            raise PersistenceError("Persistence operation failed.")
        if any(
            existing.workspace_id == run.workspace_id
            and (
                existing.investigation_id == run.investigation_id
                or existing.plan_id == run.plan_id
                or existing.command_id == run.command_id
            )
            for existing in self._database.collection_runs.values()
        ):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.collection_runs[(run.workspace_id, run.id)] = run

    def get_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionRun | None:
        return next(
            (
                run
                for run in self._database.collection_runs.values()
                if run.workspace_id == workspace_id and run.command_id == command_id
            ),
            None,
        )

    def get_by_investigation(
        self, workspace_id: WorkspaceId, investigation_id: InvestigationId
    ) -> CollectionRun | None:
        return next(
            (
                run
                for run in self._database.collection_runs.values()
                if run.workspace_id == workspace_id and run.investigation_id == investigation_id
            ),
            None,
        )

    def get_by_plan(
        self, workspace_id: WorkspaceId, plan_id: InvestigationPlanId
    ) -> CollectionRun | None:
        return next(
            (
                run
                for run in self._database.collection_runs.values()
                if run.workspace_id == workspace_id and run.plan_id == plan_id
            ),
            None,
        )

    def get_by_id(self, workspace_id: WorkspaceId, run_id: CollectionRunId) -> CollectionRun | None:
        return self._database.collection_runs.get((workspace_id, run_id))


class FakeCollectionExecutionRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database

    def try_add_ownership(self, ownership: CollectionExecutionOwnership) -> bool:
        if (
            ownership.workspace_id,
            ownership.command_id,
        ) in self._database.collection_execution_ownership:
            return False
        if any(
            existing.workspace_id == ownership.workspace_id
            and existing.collection_operation_id == ownership.collection_operation_id
            for existing in self._database.collection_execution_ownership.values()
        ):
            return False
        self._database.collection_execution_ownership[
            (ownership.workspace_id, ownership.command_id)
        ] = ownership
        return True

    def add_result(self, result: CollectionExecutionResultRecord) -> None:
        key = (result.workspace_id, result.command_id)
        if key in self._database.collection_execution_results:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.collection_execution_results[key] = result

    def get_ownership_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionExecutionOwnership | None:
        return self._database.collection_execution_ownership.get((workspace_id, command_id))

    def get_ownership_by_operation(
        self, workspace_id: WorkspaceId, operation_id: CollectionOperationId
    ) -> CollectionExecutionOwnership | None:
        return next(
            (
                item
                for item in self._database.collection_execution_ownership.values()
                if item.workspace_id == workspace_id
                and item.collection_operation_id == operation_id
            ),
            None,
        )

    def get_result_by_command(
        self, workspace_id: WorkspaceId, command_id: InvestigationCommandId
    ) -> CollectionExecutionResultRecord | None:
        return self._database.collection_execution_results.get((workspace_id, command_id))

    def get_result_by_operation(
        self, workspace_id: WorkspaceId, operation_id: CollectionOperationId
    ) -> CollectionExecutionResultRecord | None:
        return next(
            (
                item
                for item in self._database.collection_execution_results.values()
                if item.workspace_id == workspace_id
                and item.collection_operation_id == operation_id
            ),
            None,
        )

    def list_results_by_run(
        self, workspace_id: WorkspaceId, run_id: CollectionRunId
    ) -> tuple[CollectionExecutionResultRecord, ...]:
        return tuple(
            sorted(
                (
                    item
                    for item in self._database.collection_execution_results.values()
                    if item.workspace_id == workspace_id and item.collection_run_id == run_id
                ),
                key=lambda item: str(item.collection_operation_id),
            )
        )


class FakeUserRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.get_calls: list[UserId] = []

    def add(self, user: UserAccount) -> None:
        if user.id in self._database.users or any(
            existing.email == user.email for existing in self._database.users.values()
        ):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.users[user.id] = user

    def get(self, user_id: UserId) -> UserAccount | None:
        self.get_calls.append(user_id)
        return self._database.users.get(user_id)

    def get_by_email(self, email: EmailAddress) -> UserAccount | None:
        return next(
            (user for user in self._database.users.values() if user.email == email),
            None,
        )


class FakeWorkspaceMembershipRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.get_calls: list[tuple[WorkspaceId, UserId]] = []
        self.get_for_update_calls: list[tuple[WorkspaceId, UserId]] = []
        self.owner_lock_calls: list[WorkspaceId] = []

    def add(self, membership: WorkspaceMembership) -> None:
        key = (membership.workspace_id, membership.user_id)
        if key in self._database.memberships:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.memberships[key] = membership

    def get(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        self.get_calls.append((workspace_id, user_id))
        return self._database.memberships.get((workspace_id, user_id))

    def get_for_update(
        self,
        workspace_id: WorkspaceId,
        user_id: UserId,
    ) -> WorkspaceMembership | None:
        self.get_for_update_calls.append((workspace_id, user_id))
        return self._database.memberships.get((workspace_id, user_id))

    def list_active_owners_for_update(
        self,
        workspace_id: WorkspaceId,
    ) -> list[WorkspaceMembership]:
        self.owner_lock_calls.append(workspace_id)
        return sorted(
            (
                membership
                for membership in self._database.memberships.values()
                if membership.workspace_id == workspace_id
                and membership.status is MembershipStatus.ACTIVE
                and membership.role is MembershipRole.OWNER
            ),
            key=lambda membership: membership.id.value,
        )

    def update(self, membership: WorkspaceMembership) -> None:
        key = (membership.workspace_id, membership.user_id)
        current = self._database.memberships.get(key)
        if current is None or current.id != membership.id:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.memberships[key] = membership


class FakeAuditEventRepository:
    def __init__(self, database: FakeDatabase, *, fail_add: bool = False) -> None:
        self._database = database
        self._fail_add = fail_add

    def add(self, event: AuditEvent) -> None:
        if self._fail_add:
            raise PersistenceError("Persistence operation failed.")
        if any(existing.id == event.id for existing in self._database.audit_events):
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.audit_events.append(event)


class FakeEvidenceRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.lock_calls: list[tuple[WorkspaceId, EvidenceCommandId]] = []
        self.history_lock_calls: list[tuple[WorkspaceId, EvidenceId]] = []
        self.add_initial_calls: list[tuple[Artifact, Evidence]] = []
        self.add_correction_calls: list[tuple[Evidence, EvidenceLifecycleEvent]] = []
        self.add_lifecycle_event_calls: list[EvidenceLifecycleEvent] = []

    def acquire_command_lock(
        self, workspace_id: WorkspaceId, command_id: EvidenceCommandId
    ) -> None:
        self.lock_calls.append((workspace_id, command_id))

    def acquire_history_lock(self, workspace_id: WorkspaceId, evidence_id: EvidenceId) -> None:
        self.history_lock_calls.append((workspace_id, evidence_id))

    def add_initial(self, artifact: Artifact, evidence: Evidence) -> None:
        self.add_initial_calls.append((artifact, evidence))
        key = (artifact.workspace_id, evidence.series_id)
        if key in self._database.evidence_histories:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.evidence_histories[key] = EvidenceHistory(
            artifact=artifact, versions=(evidence,), events=()
        )

    def add_correction(self, evidence: Evidence, event: EvidenceLifecycleEvent) -> None:
        self.add_correction_calls.append((evidence, event))
        key = (evidence.workspace_id, evidence.series_id)
        history = self._database.evidence_histories.get(key)
        if history is None:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.evidence_histories[key] = EvidenceHistory(
            artifact=history.artifact,
            versions=(*history.versions, evidence),
            events=(*history.events, event),
        )

    def add_lifecycle_event(self, event: EvidenceLifecycleEvent) -> None:
        self.add_lifecycle_event_calls.append(event)
        found = self.get_history(event.workspace_id, event.evidence_id)
        if found is None:
            raise PersistenceConflictError("Persistence constraint conflict.")
        key = (event.workspace_id, found.latest.series_id)
        self._database.evidence_histories[key] = EvidenceHistory(
            artifact=found.artifact,
            versions=found.versions,
            events=(*found.events, event),
        )

    def get_history(
        self, workspace_id: WorkspaceId, evidence_id: EvidenceId
    ) -> EvidenceHistory | None:
        return next(
            (
                history
                for (scope, _), history in self._database.evidence_histories.items()
                if scope == workspace_id
                and any(item.id == evidence_id for item in history.versions)
            ),
            None,
        )

    def get_history_by_command(
        self, workspace_id: WorkspaceId, command_id: EvidenceCommandId
    ) -> EvidenceHistory | None:
        return next(
            (
                history
                for (scope, _), history in self._database.evidence_histories.items()
                if scope == workspace_id
                and (
                    any(item.command_id == command_id for item in history.versions)
                    or any(item.command_id == command_id for item in history.events)
                )
            ),
            None,
        )


class FakeClaimRepository:
    def __init__(self, database: FakeDatabase) -> None:
        self._database = database
        self.command_lock_calls: list[tuple[WorkspaceId, ClaimCommandId]] = []
        self.history_lock_calls: list[tuple[WorkspaceId, ClaimId]] = []
        self.add_initial_calls: list[tuple[Claim, tuple[ClaimEvidenceLink, ...]]] = []
        self.add_correction_calls: list[tuple[Claim, tuple[ClaimEvidenceLink, ...]]] = []

    def acquire_command_lock(self, workspace_id: WorkspaceId, command_id: ClaimCommandId) -> None:
        self.command_lock_calls.append((workspace_id, command_id))

    def acquire_history_lock(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> None:
        self.history_lock_calls.append((workspace_id, claim_id))

    def add_initial(self, claim: Claim, links: tuple[ClaimEvidenceLink, ...]) -> None:
        self.add_initial_calls.append((claim, links))
        key = (claim.workspace_id, claim.series_id)
        if key in self._database.claim_histories:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.claim_histories[key] = ClaimHistory(versions=(claim,), links=links)

    def add_correction(self, claim: Claim, links: tuple[ClaimEvidenceLink, ...]) -> None:
        self.add_correction_calls.append((claim, links))
        key = (claim.workspace_id, claim.series_id)
        history = self._database.claim_histories.get(key)
        if history is None:
            raise PersistenceConflictError("Persistence constraint conflict.")
        self._database.claim_histories[key] = ClaimHistory(
            versions=(*history.versions, claim),
            links=(*history.links, *links),
        )

    def get_history(self, workspace_id: WorkspaceId, claim_id: ClaimId) -> ClaimHistory | None:
        return next(
            (
                history
                for (scope, _), history in self._database.claim_histories.items()
                if scope == workspace_id and any(item.id == claim_id for item in history.versions)
            ),
            None,
        )

    def get_history_by_command(
        self, workspace_id: WorkspaceId, command_id: ClaimCommandId
    ) -> ClaimHistory | None:
        return next(
            (
                history
                for (scope, _), history in self._database.claim_histories.items()
                if scope == workspace_id
                and any(item.command_id == command_id for item in history.versions)
            ),
            None,
        )


class FakeUnitOfWork:
    def __init__(
        self,
        database: FakeDatabase,
        *,
        fail_commit: bool = False,
        fail_audit: bool = False,
        fail_transition_add: bool = False,
        fail_candidate_batch_add: bool = False,
        fail_company_add: bool = False,
        fail_decision_add: bool = False,
        fail_plan_add: bool = False,
        fail_capability_add: bool = False,
        fail_option_add: bool = False,
        fail_run_add: bool = False,
        fail_operation_add: bool = False,
        fail_dependency_add: bool = False,
        force_cas_conflict: bool = False,
    ) -> None:
        self._committed_database = database
        self._working_database = database.clone()
        self._fail_commit = fail_commit
        self._entered = False
        self._closed = False
        self._committed = False
        self.commit_calls = 0
        self.rollback_calls = 0
        self.workspaces = FakeWorkspaceRepository(self._working_database)
        self.companies = FakeCompanyRepository(
            self._working_database,
            fail_add=fail_company_add,
        )
        self.investigations = FakeInvestigationRepository(
            self._working_database,
            force_cas_conflict=force_cas_conflict,
        )
        self.investigation_transitions = FakeInvestigationTransitionRepository(
            self._working_database,
            fail_add=fail_transition_add,
        )
        self.entity_candidate_batches = FakeEntityCandidateBatchRepository(
            self._working_database,
            fail_add=fail_candidate_batch_add,
        )
        self.entity_resolution_decisions = FakeEntityResolutionDecisionRepository(
            self._working_database,
            fail_add=fail_decision_add,
        )
        self.investigation_plans = FakeInvestigationPlanRepository(
            self._working_database,
            fail_plan_add=fail_plan_add,
            fail_capability_add=fail_capability_add,
            fail_option_add=fail_option_add,
        )
        self.collection_runs = FakeCollectionRunRepository(
            self._working_database,
            fail_run_add=fail_run_add,
            fail_operation_add=fail_operation_add,
            fail_dependency_add=fail_dependency_add,
        )
        self.collection_executions = FakeCollectionExecutionRepository(self._working_database)
        self.evidence = FakeEvidenceRepository(self._working_database)
        self.claims = FakeClaimRepository(self._working_database)
        self.users = FakeUserRepository(self._working_database)
        self.memberships = FakeWorkspaceMembershipRepository(self._working_database)
        self.audit_events = FakeAuditEventRepository(
            self._working_database,
            fail_add=fail_audit,
        )

    def __enter__(self) -> Self:
        if self._entered:
            raise PersistenceError("Unit of Work instances are single-use.")
        self._entered = True
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exception_type, exception, traceback
        if not self._committed:
            self.rollback_calls += 1
        self._closed = True
        return False

    def commit(self) -> None:
        self.commit_calls += 1
        if self._fail_commit:
            raise PersistenceError("Unable to commit the persistence transaction.")
        self._committed_database.replace_with(self._working_database)
        self._committed = True

    def rollback(self) -> None:
        self.rollback_calls += 1
        self._closed = True


class FakeUnitOfWorkFactory:
    def __init__(
        self,
        database: FakeDatabase | None = None,
        *,
        fail_commit: bool = False,
        fail_audit: bool = False,
        fail_transition_add: bool = False,
        fail_candidate_batch_add: bool = False,
        fail_company_add: bool = False,
        fail_decision_add: bool = False,
        fail_plan_add: bool = False,
        fail_capability_add: bool = False,
        fail_option_add: bool = False,
        fail_run_add: bool = False,
        fail_operation_add: bool = False,
        fail_dependency_add: bool = False,
        force_cas_conflict: bool = False,
    ) -> None:
        self.database = database or FakeDatabase()
        self.fail_commit = fail_commit
        self.fail_audit = fail_audit
        self.fail_transition_add = fail_transition_add
        self.fail_candidate_batch_add = fail_candidate_batch_add
        self.fail_company_add = fail_company_add
        self.fail_decision_add = fail_decision_add
        self.fail_plan_add = fail_plan_add
        self.fail_capability_add = fail_capability_add
        self.fail_option_add = fail_option_add
        self.fail_run_add = fail_run_add
        self.fail_operation_add = fail_operation_add
        self.fail_dependency_add = fail_dependency_add
        self.force_cas_conflict = force_cas_conflict
        self.created: list[FakeUnitOfWork] = []

    def __call__(self) -> FakeUnitOfWork:
        unit_of_work = FakeUnitOfWork(
            self.database,
            fail_commit=self.fail_commit,
            fail_audit=self.fail_audit,
            fail_transition_add=self.fail_transition_add,
            fail_candidate_batch_add=self.fail_candidate_batch_add,
            fail_company_add=self.fail_company_add,
            fail_decision_add=self.fail_decision_add,
            fail_plan_add=self.fail_plan_add,
            fail_capability_add=self.fail_capability_add,
            fail_option_add=self.fail_option_add,
            fail_run_add=self.fail_run_add,
            fail_operation_add=self.fail_operation_add,
            fail_dependency_add=self.fail_dependency_add,
            force_cas_conflict=self.force_cas_conflict,
        )
        self.created.append(unit_of_work)
        return unit_of_work


@dataclass(frozen=True, slots=True)
class FakeClock:
    instant: datetime

    def now(self) -> datetime:
        return self.instant


__all__ = [
    "FakeClock",
    "FakeDatabase",
    "FakeUnitOfWork",
    "FakeUnitOfWorkFactory",
]
