"""Tests for workspace entity invariants."""

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from intelligence.domain.errors import InvalidDateTimeError, InvariantViolationError
from intelligence.domain.identifiers import WorkspaceId
from intelligence.domain.workspaces import Workspace, WorkspaceStatus


def _workspace(**overrides: object) -> Workspace:
    values: dict[str, object] = {
        "id": WorkspaceId.new(),
        "name": "  Equipe Brasil  ",
        "status": WorkspaceStatus.ACTIVE,
        "retention_policy_version": "  2026-01  ",
        "created_at": datetime(
            2026,
            7,
            25,
            9,
            tzinfo=timezone(-timedelta(hours=3)),
        ),
        "updated_at": datetime(2026, 7, 25, 13, tzinfo=UTC),
    }
    values.update(overrides)
    return Workspace(**cast(Any, values))


def test_workspace_normalizes_text_and_timestamps() -> None:
    workspace = _workspace()

    assert workspace.name == "Equipe Brasil"
    assert workspace.retention_policy_version == "2026-01"
    assert workspace.created_at == datetime(2026, 7, 25, 12, tzinfo=UTC)
    assert workspace.updated_at == datetime(2026, 7, 25, 13, tzinfo=UTC)


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [("name", "  "), ("retention_policy_version", "")],
)
def test_workspace_requires_meaningful_text(field_name: str, invalid_value: str) -> None:
    with pytest.raises(InvariantViolationError):
        _workspace(**{field_name: invalid_value})


def test_workspace_rejects_invalid_types_and_timestamp_order() -> None:
    with pytest.raises(InvariantViolationError):
        _workspace(id=cast(WorkspaceId, "workspace"))
    with pytest.raises(InvariantViolationError):
        _workspace(status=cast(WorkspaceStatus, "ACTIVE"))
    with pytest.raises(InvariantViolationError):
        _workspace(updated_at=datetime(2026, 7, 25, 11, tzinfo=UTC))
    with pytest.raises(InvalidDateTimeError):
        _workspace(created_at=datetime(2026, 7, 25, 12))


def test_workspace_is_immutable() -> None:
    workspace = _workspace()

    with pytest.raises(FrozenInstanceError):
        workspace.__setattr__("name", "Outro nome")
