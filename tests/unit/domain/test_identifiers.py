"""Tests for strongly typed domain identifiers."""

from dataclasses import FrozenInstanceError
from typing import cast
from uuid import UUID

import pytest

from intelligence.domain.errors import InvalidIdentifierError
from intelligence.domain.identifiers import (
    CompanyId,
    InvestigationId,
    UserId,
    WorkspaceId,
)


@pytest.mark.parametrize(
    "identifier_type",
    [WorkspaceId, UserId, CompanyId, InvestigationId],
)
def test_identifier_can_be_created_and_reconstructed(
    identifier_type: type[WorkspaceId] | type[UserId] | type[CompanyId] | type[InvestigationId],
) -> None:
    identifier = identifier_type.new()

    assert identifier.value.int != 0
    assert identifier_type.from_value(identifier.value) == identifier
    assert identifier_type.from_value(str(identifier)) == identifier
    assert identifier_type.from_value(str(identifier).upper()) == identifier
    assert identifier_type.__name__ in repr(identifier)


def test_identifier_types_remain_distinct_for_the_same_uuid() -> None:
    value = UUID("63592cee-39bc-436a-8031-08d1c902239f")
    workspace_id = WorkspaceId(value)
    company_id = CompanyId(value)

    assert cast(object, workspace_id) != company_id
    assert len({workspace_id, company_id}) == 2


@pytest.mark.parametrize(
    "invalid_value",
    [
        "not-a-uuid",
        "{63592cee-39bc-436a-8031-08d1c902239f}",
        "63592cee39bc436a803108d1c902239f",
    ],
)
def test_identifier_rejects_malformed_or_noncanonical_text(invalid_value: str) -> None:
    with pytest.raises(InvalidIdentifierError):
        WorkspaceId.from_value(invalid_value)


def test_identifier_rejects_nil_uuid_and_wrong_runtime_type() -> None:
    with pytest.raises(InvalidIdentifierError):
        WorkspaceId(UUID(int=0))

    with pytest.raises(InvalidIdentifierError):
        WorkspaceId(cast(UUID, "63592cee-39bc-436a-8031-08d1c902239f"))


def test_identifier_is_immutable() -> None:
    identifier = WorkspaceId.new()

    with pytest.raises(FrozenInstanceError):
        identifier.__setattr__(
            "value",
            UUID("63592cee-39bc-436a-8031-08d1c902239f"),
        )
