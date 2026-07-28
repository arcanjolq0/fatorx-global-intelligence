"""Tests for framework-neutral application persistence ports."""

import pytest

from intelligence.application.ports.repositories import (
    CompanyRepository,
    InvestigationRepository,
    WorkspaceRepository,
)
from intelligence.application.ports.unit_of_work import UnitOfWork


@pytest.mark.parametrize(
    "port_type",
    [WorkspaceRepository, CompanyRepository, InvestigationRepository, UnitOfWork],
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


def _workspace_repository(repository: WorkspaceRepository) -> WorkspaceRepository:
    return repository
