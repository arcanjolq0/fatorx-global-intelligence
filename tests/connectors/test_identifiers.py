"""Tests for strong connector-scoped identifiers."""

from typing import cast
from uuid import UUID

import pytest

from intelligence.connectors.errors import InvalidConnectorIdentifierError
from intelligence.connectors.identifiers import (
    ArtifactRefId,
    CandidateRefId,
    ConnectorId,
    OperationId,
    OriginReferenceId,
    RequestId,
    SourceId,
)


def test_readable_identifiers_remain_distinct_and_hashable() -> None:
    connector_id = ConnectorId("registry.alpha")
    same_connector_id = ConnectorId("registry.alpha")
    source_id = SourceId("registry.alpha")

    assert connector_id == same_connector_id
    assert hash(connector_id) == hash(same_connector_id)
    assert connector_id != cast(object, source_id)
    assert str(connector_id) == "registry.alpha"
    assert repr(connector_id) == "ConnectorId('registry.alpha')"


@pytest.mark.parametrize(
    "value",
    ["", " ", "Registry", "registry alpha", "registry/alpha", "registry..alpha", "a" * 129],
)
def test_readable_identifiers_reject_noncanonical_values(value: str) -> None:
    with pytest.raises(InvalidConnectorIdentifierError):
        ConnectorId(value)


def test_origin_reference_is_logical_and_not_a_url() -> None:
    reference = OriginReferenceId("record_2026-07-28")

    assert str(reference) == "record_2026-07-28"
    with pytest.raises(InvalidConnectorIdentifierError):
        OriginReferenceId("https://source.example/item?token=value")


@pytest.mark.parametrize(
    "identifier_type",
    [OperationId, RequestId, CandidateRefId, ArtifactRefId],
)
def test_uuid_identifiers_round_trip_and_have_safe_repr(
    identifier_type: type[OperationId | RequestId | CandidateRefId | ArtifactRefId],
) -> None:
    value = UUID("11111111-1111-4111-8111-111111111111")
    identifier = identifier_type.from_value(str(value))

    assert identifier.value == value
    assert str(identifier) == str(value)
    assert str(value) in repr(identifier)
    assert identifier_type.from_value(value) == identifier
    assert isinstance(identifier_type.new().value, UUID)


def test_uuid_identifier_types_are_not_interchangeable() -> None:
    value = UUID("11111111-1111-4111-8111-111111111111")

    assert OperationId(value) != cast(object, RequestId(value))


@pytest.mark.parametrize(
    "value",
    [
        UUID(int=0),
        "not-a-uuid",
        "11111111111141118111111111111111",
        "{11111111-1111-4111-8111-111111111111}",
    ],
)
def test_uuid_identifiers_reject_zero_and_noncanonical_values(value: UUID | str) -> None:
    with pytest.raises(InvalidConnectorIdentifierError):
        OperationId.from_value(value)


def test_uuid_identifier_constructor_rejects_wrong_runtime_type() -> None:
    with pytest.raises(InvalidConnectorIdentifierError):
        OperationId("11111111-1111-4111-8111-111111111111")  # type: ignore[arg-type]
