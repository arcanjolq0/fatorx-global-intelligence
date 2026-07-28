"""Tests for the asynchronous structural connector protocol."""

import inspect
from typing import cast

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome
from intelligence.connectors.protocol import Connector
from intelligence.connectors.queries import CandidateRef, CompanyQuery


class CompleteConnectorShape:
    def describe(self) -> ConnectorDescriptor:
        raise AssertionError("Shape-only object is never executed")

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        del query, context
        raise AssertionError("Shape-only object is never executed")

    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        del candidate_ref, context
        raise AssertionError("Shape-only object is never executed")

    async def fetch_document(
        self,
        document_ref: ArtifactReference,
        context: ConnectorContext,
    ) -> ConnectorOutcome[ArtifactPayload]:
        del document_ref, context
        raise AssertionError("Shape-only object is never executed")


class IncompleteConnectorShape:
    def describe(self) -> ConnectorDescriptor:
        return cast(ConnectorDescriptor, object())


def test_protocol_is_runtime_checkable_for_registry_admission() -> None:
    assert isinstance(CompleteConnectorShape(), Connector)
    assert not isinstance(IncompleteConnectorShape(), Connector)


def test_protocol_operations_are_asynchronous_except_description() -> None:
    assert not inspect.iscoroutinefunction(Connector.describe)
    assert inspect.iscoroutinefunction(Connector.search)
    assert inspect.iscoroutinefunction(Connector.fetch_details)
    assert inspect.iscoroutinefunction(Connector.fetch_document)
