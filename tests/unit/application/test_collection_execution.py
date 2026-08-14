"""F4.6 immutable command, policy snapshot, history, and mapper tests."""

from dataclasses import replace

import pytest

from intelligence.application.collection_execution import (
    collection_execution_ownership_digest,
    collection_execution_result_digest,
    digest_execute_collection_command,
    execution_policy_from_snapshot,
    execution_policy_snapshot,
    validate_collection_execution_history,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.infrastructure.persistence.postgresql.mappers import (
    collection_execution_ownership_from_values,
    collection_execution_ownership_to_values,
    collection_execution_result_from_values,
    collection_execution_result_to_values,
)
from tests.unit.application.test_collection_execution_service import _execute, _setup

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_policy_snapshot_and_ownership_result_digests_are_deterministic() -> None:
    actor, _, database, _, connector, command, service = _setup()
    result = _execute(service, actor, command, connector)
    ownership = database.collection_execution_ownership[(actor.workspace_id, command.command_id)]

    assert execution_policy_from_snapshot(execution_policy_snapshot(command.execution_policy)) == (
        command.execution_policy
    )
    assert collection_execution_ownership_digest(ownership) == ownership.ownership_digest
    assert collection_execution_result_digest(result) == result.result_digest
    assert digest_execute_collection_command(actor, command) == ownership.command_digest


def test_ownership_and_redacted_result_round_trip_through_relational_mappers() -> None:
    actor, _, database, _, connector, command, service = _setup()
    result = _execute(service, actor, command, connector)
    ownership = database.collection_execution_ownership[(actor.workspace_id, command.command_id)]

    assert (
        collection_execution_ownership_from_values(
            collection_execution_ownership_to_values(ownership)
        )
        == ownership
    )
    assert (
        collection_execution_result_from_values(collection_execution_result_to_values(result))
        == result
    )


def test_noncanonical_or_tampered_policy_snapshot_is_rejected() -> None:
    actor, _, database, _, connector, command, service = _setup()
    _execute(service, actor, command, connector)
    ownership = database.collection_execution_ownership[(actor.workspace_id, command.command_id)]

    with pytest.raises(InvariantViolationError):
        replace(ownership, execution_policy_snapshot='{"version":"changed"}')
    with pytest.raises(InvariantViolationError):
        execution_policy_from_snapshot('{"max_attempts":1}')


def test_tampered_result_digest_and_cross_operation_history_are_rejected() -> None:
    actor, _, database, _, connector, command, service = _setup()
    result = _execute(service, actor, command, connector)
    ownership = database.collection_execution_ownership[(actor.workspace_id, command.command_id)]

    with pytest.raises(InvariantViolationError):
        replace(result, result_digest="f" * 64)
    actor2, _, database2, _, connector2, command2, service2 = _setup()
    result2 = _execute(service2, actor2, command2, connector2)
    assert database2.collection_execution_ownership
    with pytest.raises(InvariantViolationError):
        validate_collection_execution_history(ownership, result2)
