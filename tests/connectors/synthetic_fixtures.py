"""Fixed synthetic inputs shared by connector contract tests."""

from collections.abc import Coroutine
from dataclasses import dataclass
from decimal import Decimal
from typing import cast

from intelligence.connectors.context import (
    ConnectorContext,
    LocaleTag,
    MonotonicDeadline,
)
from intelligence.connectors.enums import ConnectorMode
from intelligence.connectors.identifiers import CandidateRefId, ConnectorId, OperationId, RequestId
from intelligence.connectors.queries import (
    BusinessIdentifier,
    BusinessIdentifierType,
    CandidateRef,
    CandidateSnapshot,
    CompanyQuery,
    DomainName,
    SearchAddress,
)
from intelligence.connectors.versions import SourcePolicyVersion
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CorrelationId, InvestigationId, WorkspaceId
from intelligence.domain.money import CurrencyCode, Money


@dataclass(frozen=True, slots=True)
class FixedCancellationSignal:
    """Non-blocking cancellation fixture with no mutable or clock-dependent state."""

    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled


def run_immediate[T](coroutine: Coroutine[object, object, T]) -> T:
    """Drive a non-suspending synthetic coroutine without creating an event loop."""

    try:
        coroutine.send(None)
    except StopIteration as completed:
        return cast(T, completed.value)
    finally:
        coroutine.close()
    raise AssertionError("Synthetic F3.2 coroutine unexpectedly suspended")


def synthetic_query() -> CompanyQuery:
    """Return one wholly synthetic, immutable company query."""

    return CompanyQuery(
        country=CountryCode("BR"),
        original_name="Synthetic Alpha Registry Test Ltd.",
        normalized_name="synthetic alpha registry test ltd",
        identifiers=(
            BusinessIdentifier(
                BusinessIdentifierType("SYNTHETIC_REGISTRY_ID"),
                original_value="TEST-REG-0001",
                normalized_value="TESTREG0001",
            ),
        ),
        domain=DomainName("synthetic-alpha.test"),
        address=SearchAddress(
            country=CountryCode("BR"),
            lines=("100 Synthetic Test Avenue",),
            locality="Synthetic Test City",
            administrative_area="TS",
            postal_code="00000-000",
        ),
    )


def synthetic_context() -> ConnectorContext:
    """Return a fixed context that never reads time, environment, or random state."""

    return ConnectorContext(
        workspace_id=WorkspaceId.from_value("20000000-0000-4000-8000-000000000001"),
        investigation_id=InvestigationId.from_value("20000000-0000-4000-8000-000000000002"),
        operation_id=OperationId.from_value("20000000-0000-4000-8000-000000000003"),
        attempt=1,
        correlation_id=CorrelationId.from_value("20000000-0000-4000-8000-000000000004"),
        request_id=RequestId.from_value("20000000-0000-4000-8000-000000000005"),
        deadline=MonotonicDeadline(10_000.0),
        budget_remaining=Money(Decimal("100.00"), CurrencyCode("USD")),
        accepted_locales=(LocaleTag("en"), LocaleTag("pt-BR")),
        source_policy_version=SourcePolicyVersion("synthetic-policy-1"),
        mode=ConnectorMode.TEST,
        cancellation_signal=FixedCancellationSignal(),
    )


def synthetic_candidate(connector_id: ConnectorId) -> CandidateRef:
    """Return a fixed candidate scoped to the connector under test."""

    return CandidateRef(
        candidate_ref_id=CandidateRefId.from_value("10000000-0000-4000-8000-000000000001"),
        connector_id=connector_id,
        snapshot=CandidateSnapshot("Synthetic registry test record Alpha"),
        country=CountryCode("BR"),
        display_name="Synthetic Alpha Registry Test Ltd.",
        primary_identifier=BusinessIdentifier(
            BusinessIdentifierType("SYNTHETIC_REGISTRY_ID"),
            original_value="TEST-REG-0001",
            normalized_value="TESTREG0001",
        ),
        domain=DomainName("synthetic-alpha.test"),
    )


__all__ = [
    "FixedCancellationSignal",
    "run_immediate",
    "synthetic_candidate",
    "synthetic_context",
    "synthetic_query",
]
