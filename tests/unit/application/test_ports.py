"""Tests for framework-neutral application persistence ports."""

import pytest

from intelligence.application.ports.clock import Clock
from intelligence.application.ports.repositories import (
    AuditEventRepository,
    CompanyRepository,
    InvestigationRepository,
    InvestigationTransitionRepository,
    UserRepository,
    WorkspaceMembershipRepository,
    WorkspaceRepository,
)
from intelligence.application.ports.unit_of_work import UnitOfWork, UnitOfWorkFactory


@pytest.mark.parametrize(
    "port_type",
    [
        WorkspaceRepository,
        CompanyRepository,
        InvestigationRepository,
        InvestigationTransitionRepository,
        UserRepository,
        WorkspaceMembershipRepository,
        AuditEventRepository,
        Clock,
        UnitOfWork,
        UnitOfWorkFactory,
    ],
)
def test_persistence_ports_are_protocols_not_technical_implementations(
    port_type: type[object],
) -> None:
    with pytest.raises(TypeError):
        port_type()


def test_protocol_types_accept_structural_adapters_without_base_classes() -> None:
    class StructuralWorkspaceRepository:
        def add(self, workspace: object) -> None:
            del workspace

        def get(self, workspace_id: object) -> None:
            del workspace_id

    repository = StructuralWorkspaceRepository()

    assert _workspace_repository(repository) is repository


def test_audit_event_repository_is_an_append_only_protocol() -> None:
    public_operations = {
        name
        for name, member in AuditEventRepository.__dict__.items()
        if not name.startswith("_") and callable(member)
    }

    assert public_operations == {"add"}


def test_investigation_transition_repository_is_append_only_with_command_lookup() -> None:
    public_operations = {
        name
        for name, member in InvestigationTransitionRepository.__dict__.items()
        if not name.startswith("_") and callable(member)
    }

    assert public_operations == {"acquire_command_lock", "add", "get_by_command"}


def test_audit_event_protocol_accepts_add_only_structural_adapter() -> None:
    class StructuralAuditEventRepository:
        def add(self, event: object) -> None:
            del event

    repository = StructuralAuditEventRepository()

    assert _audit_event_repository(repository) is repository


def test_clock_and_unit_of_work_factory_accept_structural_adapters() -> None:
    class StructuralClock:
        def now(self) -> object:
            return object()

    class StructuralFactory:
        def __call__(self) -> object:
            return object()

    clock: Clock = StructuralClock()  # type: ignore[assignment]
    factory: UnitOfWorkFactory = StructuralFactory()  # type: ignore[assignment]

    assert clock.now() is not None
    assert factory() is not None


def _workspace_repository(repository: WorkspaceRepository) -> WorkspaceRepository:
    return repository


def _audit_event_repository(repository: AuditEventRepository) -> AuditEventRepository:
    return repository
