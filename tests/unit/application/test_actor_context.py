"""Tests for the immutable, strongly typed actor context."""

from dataclasses import FrozenInstanceError
from datetime import UTC
from typing import Any, cast

import pytest

from intelligence.application.actor_context import ActorContext
from intelligence.application.clock import SystemClock
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import CorrelationId, UserId, WorkspaceId


def test_actor_context_preserves_only_strong_identity_scope_and_correlation() -> None:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )

    assert isinstance(actor.user_id, UserId)
    assert isinstance(actor.workspace_id, WorkspaceId)
    assert isinstance(actor.correlation_id, CorrelationId)
    assert set(actor.__dataclass_fields__) == {"user_id", "workspace_id", "correlation_id"}


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("user_id", "user"),
        ("workspace_id", "workspace"),
        ("correlation_id", "correlation"),
    ],
)
def test_actor_context_rejects_untyped_values(field_name: str, value: str) -> None:
    fields: dict[str, object] = {
        "user_id": UserId.new(),
        "workspace_id": WorkspaceId.new(),
        "correlation_id": CorrelationId.new(),
    }
    fields[field_name] = value

    with pytest.raises(InvariantViolationError):
        ActorContext(**cast(Any, fields))


def test_actor_context_is_immutable() -> None:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )

    with pytest.raises(FrozenInstanceError):
        actor.__setattr__("workspace_id", WorkspaceId.new())


def test_actor_context_representation_contains_no_credential_fields() -> None:
    actor = ActorContext(
        user_id=UserId.new(),
        workspace_id=WorkspaceId.new(),
        correlation_id=CorrelationId.new(),
    )

    representation = repr(actor).lower()
    assert "password" not in representation
    assert "token" not in representation
    assert "session" not in representation


def test_system_clock_returns_timezone_aware_utc() -> None:
    instant = SystemClock().now()

    assert instant.tzinfo is UTC
