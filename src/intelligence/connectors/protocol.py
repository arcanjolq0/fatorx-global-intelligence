"""Asynchronous connector protocol with no base implementation or I/O."""

from typing import Protocol, runtime_checkable

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import ConnectorOutcome
from intelligence.connectors.queries import CandidateRef, CompanyQuery


@runtime_checkable
class Connector(Protocol):
    """Uniform logical connector surface implemented by future adapters."""

    def describe(self) -> ConnectorDescriptor:
        """Return the immutable descriptor without external I/O."""

        ...

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        """Search neutral candidates without confirming identity."""

        ...

    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        """Fetch neutral observations for a connector-scoped candidate."""

        ...

    async def fetch_document(
        self,
        document_ref: ArtifactReference,
        context: ConnectorContext,
    ) -> ConnectorOutcome[ArtifactPayload]:
        """Fetch a declared document; selection rejects unsupported operations first."""

        ...


__all__ = ["Connector"]
