"""F4.5 pure persistence mappings and tamper rejection."""

import pytest

from intelligence.application.errors import PersistenceDataError
from intelligence.infrastructure.persistence.postgresql.mappers import (
    collection_dependency_to_values,
    collection_operation_to_values,
    collection_run_from_values,
    collection_run_to_values,
)
from tests.unit.orchestration.test_collection_activation import _build


def test_collection_manifest_mapper_round_trip_preserves_operations_and_edges() -> None:
    _, _, _, run = _build()
    operation_values = tuple(collection_operation_to_values(item) for item in run.operations)
    dependency_values = tuple(
        collection_dependency_to_values(operation, dependency_id, dependency_order)
        for operation in run.operations
        for dependency_order, dependency_id in enumerate(
            operation.dependency_operation_ids, start=1
        )
    )

    restored = collection_run_from_values(
        collection_run_to_values(run), operation_values, dependency_values
    )

    assert restored == run
    assert restored.operations == run.operations


def test_collection_manifest_mapper_rejects_digest_and_dependency_scope_tampering() -> None:
    _, _, _, run = _build()
    operation_values = tuple(collection_operation_to_values(item) for item in run.operations)
    dependency_values = tuple(
        collection_dependency_to_values(operation, dependency_id, dependency_order)
        for operation in run.operations
        for dependency_order, dependency_id in enumerate(
            operation.dependency_operation_ids, start=1
        )
    )
    with pytest.raises(PersistenceDataError):
        collection_run_from_values(
            collection_run_to_values(run) | {"run_digest": "f" * 64},
            operation_values,
            dependency_values,
        )
    tampered_edges = (
        (dependency_values[0] | {"workspace_id": run.workspace_id.value})
        if dependency_values
        else None
    )
    if tampered_edges is not None:
        with pytest.raises(PersistenceDataError):
            collection_run_from_values(
                collection_run_to_values(run),
                operation_values,
                (
                    tampered_edges | {"collection_run_id": run.operations[0].id.value},
                    *dependency_values[1:],
                ),
            )
