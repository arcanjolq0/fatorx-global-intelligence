"""Controlled in-process doubles for connector execution tests."""

import asyncio
from collections.abc import Coroutine
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext, LocaleTag, MonotonicDeadline
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ArtifactRetentionMode,
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorErrorCode,
    ConnectorMode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.execution import (
    ConnectorExecutionPolicy,
    ConnectorExecutionPolicyVersion,
    ConnectorOperationRunner,
    FetchDetailsConnectorOperation,
    FetchDocumentConnectorOperation,
    InMemoryIdempotencyStore,
    SearchConnectorOperation,
)
from intelligence.connectors.identifiers import (
    ArtifactRefId,
    CandidateRefId,
    ConnectorId,
    OperationId,
    OriginReferenceId,
    RequestId,
    SourceId,
)
from intelligence.connectors.observations import (
    CandidateObservation,
    Observation,
    ObservationTypeCode,
)
from intelligence.connectors.outcomes import (
    ConnectorError,
    ConnectorOutcome,
    ConnectorUsage,
    ConnectorWarning,
    ContinuationToken,
    Pagination,
    SourceSnapshot,
)
from intelligence.connectors.queries import (
    CandidateRef,
    CandidateSnapshot,
    CompanyQuery,
)
from intelligence.connectors.versions import (
    CONNECTOR_CONTRACT_VERSION,
    SemanticVersion,
    SourcePolicyVersion,
)
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CorrelationId, InvestigationId, WorkspaceId
from intelligence.domain.money import CurrencyCode, Money
from tests.connectors.synthetic_fixtures import synthetic_query

TEST_CONNECTOR_ID = ConnectorId("controlled.business_registry")
TEST_SOURCE_ID = SourceId("source.synthetic.controlled_registry")
TEST_COUNTRY = CountryCode("BR")
TEST_CURRENCY = CurrencyCode("USD")
TEST_OPERATION_ID = OperationId.from_value("40000000-0000-4000-8000-000000000001")
_DEFAULT_ATTEMPT_COST = Money(Decimal("1.00"), TEST_CURRENCY)
_DEFAULT_BUDGET = Money(Decimal("10.00"), TEST_CURRENCY)


@dataclass(slots=True)
class MutableCancellationSignal:
    cancelled: bool = False

    def is_cancelled(self) -> bool:
        return self.cancelled

    def cancel(self) -> None:
        self.cancelled = True


@dataclass(slots=True)
class ManualClock:
    value: float = 100.0

    def now(self) -> float:
        return self.value


class ControlledSleeper:
    """Record backoff and expose event-driven deadline/backoff completion."""

    def __init__(self, *, block_backoff: bool = False) -> None:
        self.delays: list[timedelta] = []
        self.deadline_waits: list[MonotonicDeadline] = []
        self.deadline_started = asyncio.Event()
        self.deadline_release = asyncio.Event()
        self.backoff_started = asyncio.Event()
        self.backoff_release = asyncio.Event()
        self.block_backoff = block_backoff

    async def sleep(self, delay: timedelta) -> None:
        self.delays.append(delay)
        self.backoff_started.set()
        if self.block_backoff:
            await self.backoff_release.wait()

    async def sleep_until(self, deadline: MonotonicDeadline) -> None:
        self.deadline_waits.append(deadline)
        self.deadline_started.set()
        await self.deadline_release.wait()


@dataclass(frozen=True, slots=True)
class FixedJitter:
    value: timedelta = timedelta(0)

    def jitter(self, *, attempt: int, backoff: timedelta) -> timedelta:
        del attempt, backoff
        return self.value


@dataclass(frozen=True, slots=True)
class CredentialDouble:
    secret: str
    configured_reference: str

    @property
    def reference_name(self) -> str:
        return self.configured_reference

    def __repr__(self) -> str:
        return f"CredentialDouble(secret={self.secret!r})"


class ControlledConnector:
    """Sequence-based connector with call counts and optional event blocking."""

    def __init__(
        self,
        *,
        descriptor: ConnectorDescriptor | None = None,
        search_values: tuple[object, ...] | None = None,
        details_values: tuple[object, ...] | None = None,
        document_values: tuple[object, ...] | None = None,
        block_operations: bool = False,
        cancel_signal_after_call: MutableCancellationSignal | None = None,
        descriptor_after_operation: ConnectorDescriptor | None = None,
    ) -> None:
        self.descriptor = descriptor or connector_descriptor()
        self.search_values = search_values or (search_success(),)
        self.details_values = details_values or (details_success(test_candidate()),)
        self.document_values = document_values or (document_success(),)
        self.block_operations = block_operations
        self.cancel_signal_after_call = cancel_signal_after_call
        self.descriptor_after_operation = descriptor_after_operation
        self.describe_calls = 0
        self.operation_calls = 0
        self.search_calls = 0
        self.details_calls = 0
        self.document_calls = 0
        self.contexts: list[ConnectorContext] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.task_cancelled = asyncio.Event()

    def describe(self) -> ConnectorDescriptor:
        self.describe_calls += 1
        if self.operation_calls and self.descriptor_after_operation is not None:
            return self.descriptor_after_operation
        return self.descriptor

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        del query
        self.search_calls += 1
        value = await self._value(self.search_values, context)
        return cast(ConnectorOutcome[CandidateObservation], value)

    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        del candidate_ref
        self.details_calls += 1
        value = await self._value(self.details_values, context)
        return cast(ConnectorOutcome[Observation], value)

    async def fetch_document(
        self,
        document_ref: ArtifactReference,
        context: ConnectorContext,
    ) -> ConnectorOutcome[ArtifactPayload]:
        del document_ref
        self.document_calls += 1
        value = await self._value(self.document_values, context)
        return cast(ConnectorOutcome[ArtifactPayload], value)

    async def _value(self, values: tuple[object, ...], context: ConnectorContext) -> object:
        self.operation_calls += 1
        self.contexts.append(context)
        self.started.set()
        if self.block_operations:
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                self.task_cancelled.set()
                raise
        index = min(self.operation_calls - 1, len(values) - 1)
        value = values[index]
        if self.cancel_signal_after_call is not None:
            self.cancel_signal_after_call.cancel()
        if isinstance(value, Exception):
            raise value
        return value


def run_async[T](coroutine: Coroutine[object, object, T]) -> T:
    """Run one deterministic scenario; tests allow only asyncio's loopback wakeup."""

    with asyncio.Runner() as runner:
        return runner.run(coroutine)


def operation_runner(
    *,
    clock: ManualClock | None = None,
    sleeper: ControlledSleeper | None = None,
    jitter: FixedJitter | None = None,
    store: InMemoryIdempotencyStore | None = None,
) -> ConnectorOperationRunner:
    return ConnectorOperationRunner(
        clock=clock or ManualClock(),
        sleeper=sleeper or ControlledSleeper(),
        jitter=jitter or FixedJitter(),
        idempotency_store=store or InMemoryIdempotencyStore(),
    )


def connector_descriptor(
    *,
    connector_id: ConnectorId = TEST_CONNECTOR_ID,
    source_id: SourceId = TEST_SOURCE_ID,
    countries: tuple[CountryCode, ...] = (TEST_COUNTRY,),
    capabilities: tuple[ConnectorCapability, ...] = (
        ConnectorCapability.COMPANY_REGISTRY,
        ConnectorCapability.DOCUMENTS,
    ),
    operations: tuple[ConnectorOperation, ...] = (
        ConnectorOperation.SEARCH,
        ConnectorOperation.FETCH_DETAILS,
        ConnectorOperation.FETCH_DOCUMENT,
    ),
    supports_test_mode: bool = True,
    credential_ref_name: str | None = None,
    max_page_size: int | None = 3,
) -> ConnectorDescriptor:
    return ConnectorDescriptor(
        connector_id=connector_id,
        version=SemanticVersion(1, 2, 3),
        contract_version=CONNECTOR_CONTRACT_VERSION,
        source_id=source_id,
        coverage_kind=ConnectorCoverageKind.COUNTRY_SET,
        countries=countries,
        capabilities=capabilities,
        operations=operations,
        access_type=ConnectorAccessType.FILE,
        credential_ref_name=credential_ref_name,
        supports_test_mode=supports_test_mode,
        max_page_size=max_page_size,
    )


def execution_policy(
    *,
    max_attempts: int = 3,
    retriable_codes: tuple[ConnectorErrorCode, ...] = (
        ConnectorErrorCode.RATE_LIMITED,
        ConnectorErrorCode.TIMEOUT,
        ConnectorErrorCode.UNAVAILABLE,
    ),
    base_backoff: timedelta = timedelta(seconds=1),
    max_backoff: timedelta = timedelta(seconds=30),
    max_jitter: timedelta = timedelta(0),
    estimated_attempt_cost: Money | None = _DEFAULT_ATTEMPT_COST,
    max_items: int = 10,
    max_artifacts: int = 10,
) -> ConnectorExecutionPolicy:
    return ConnectorExecutionPolicy(
        version=ConnectorExecutionPolicyVersion("test-execution-policy-1"),
        max_attempts=max_attempts,
        retriable_codes=retriable_codes,
        base_backoff=base_backoff,
        max_backoff=max_backoff,
        max_jitter=max_jitter,
        estimated_attempt_cost=estimated_attempt_cost,
        max_items=max_items,
        max_artifacts=max_artifacts,
    )


def connector_context(
    *,
    operation_id: OperationId = TEST_OPERATION_ID,
    deadline: float = 1_000.0,
    budget: Money | None = _DEFAULT_BUDGET,
    signal: MutableCancellationSignal | None = None,
    attempt: int = 1,
    credential: CredentialDouble | None = None,
) -> ConnectorContext:
    return ConnectorContext(
        workspace_id=WorkspaceId.from_value("40000000-0000-4000-8000-000000000002"),
        investigation_id=InvestigationId.from_value("40000000-0000-4000-8000-000000000003"),
        operation_id=operation_id,
        attempt=attempt,
        correlation_id=CorrelationId.from_value("40000000-0000-4000-8000-000000000004"),
        request_id=RequestId.from_value("40000000-0000-4000-8000-000000000005"),
        deadline=MonotonicDeadline(deadline),
        budget_remaining=budget,
        accepted_locales=(LocaleTag("en"), LocaleTag("pt-BR")),
        source_policy_version=SourcePolicyVersion("synthetic-source-policy-1"),
        mode=ConnectorMode.TEST,
        cancellation_signal=signal or MutableCancellationSignal(),
        credential_handle=credential,
    )


def search_request(
    connector: ControlledConnector,
    *,
    context: ConnectorContext | None = None,
    policy: ConnectorExecutionPolicy | None = None,
    country: CountryCode = TEST_COUNTRY,
    capability: ConnectorCapability = ConnectorCapability.COMPANY_REGISTRY,
    query: CompanyQuery | None = None,
) -> SearchConnectorOperation:
    return SearchConnectorOperation(
        connector=connector,
        capability=capability,
        country=country,
        query=query or synthetic_query(),
        context=context or connector_context(),
        policy=policy or execution_policy(),
    )


def details_request(
    connector: ControlledConnector,
    *,
    candidate: CandidateRef | None = None,
    context: ConnectorContext | None = None,
    policy: ConnectorExecutionPolicy | None = None,
) -> FetchDetailsConnectorOperation:
    return FetchDetailsConnectorOperation(
        connector=connector,
        capability=ConnectorCapability.COMPANY_REGISTRY,
        country=TEST_COUNTRY,
        candidate=candidate or test_candidate(),
        context=context or connector_context(),
        policy=policy or execution_policy(),
    )


def document_request(
    connector: ControlledConnector,
    *,
    context: ConnectorContext | None = None,
    policy: ConnectorExecutionPolicy | None = None,
) -> FetchDocumentConnectorOperation:
    return FetchDocumentConnectorOperation(
        connector=connector,
        capability=ConnectorCapability.DOCUMENTS,
        country=TEST_COUNTRY,
        document=test_document_reference(),
        context=context or connector_context(),
        policy=policy or execution_policy(),
    )


def test_candidate(
    *,
    connector_id: ConnectorId = TEST_CONNECTOR_ID,
    country: CountryCode = TEST_COUNTRY,
    index: int = 1,
) -> CandidateRef:
    return CandidateRef(
        candidate_ref_id=CandidateRefId.from_value(f"50000000-0000-4000-8000-{index:012d}"),
        connector_id=connector_id,
        snapshot=CandidateSnapshot(f"Synthetic execution candidate {index}"),
        country=country,
        display_name=f"Synthetic Execution Candidate {index} Ltd.",
    )


def test_document_reference() -> ArtifactReference:
    return ArtifactReference(
        artifact_ref_id=ArtifactRefId.from_value("60000000-0000-4000-8000-000000000001"),
        media_type="application/pdf",
        retention=ArtifactRetentionMode.REFERENCE_ONLY,
        origin_reference=OriginReferenceId("synthetic-document-1"),
        sha256="d" * 64,
        logical_name="synthetic-document.pdf",
    )


def source_snapshot(*, source_id: SourceId = TEST_SOURCE_ID) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=source_id,
        origin_reference=OriginReferenceId("synthetic-execution-response"),
        retrieved_at=datetime(2026, 7, 29, 12, tzinfo=UTC),
    )


def connector_usage(
    *,
    cost: Money | None = _DEFAULT_ATTEMPT_COST,
    calls: int = 1,
) -> ConnectorUsage:
    return ConnectorUsage(
        calls=calls,
        bytes_received=128,
        duration=timedelta(milliseconds=10),
        cost=cost,
        cost_kind=UsageCostKind.KNOWN if cost is not None else None,
    )


def search_success(
    *,
    count: int = 1,
    usage: ConnectorUsage | None = None,
    source_id: SourceId = TEST_SOURCE_ID,
    has_more: bool = False,
    cursor: str = "synthetic-secret-cursor",
    warning_message: str | None = None,
) -> ConnectorOutcome[CandidateObservation]:
    items = tuple(
        CandidateObservation(candidate=test_candidate(index=index + 1)) for index in range(count)
    )
    warnings = (
        (ConnectorWarning(ConnectorWarningCode.PARTIAL_DATA, warning_message),)
        if warning_message is not None
        else ()
    )
    status = ConnectorOutcomeStatus.PARTIAL if warnings else ConnectorOutcomeStatus.SUCCEEDED
    return ConnectorOutcome(
        status=status,
        items=items,
        artifacts=(),
        source_snapshot=source_snapshot(source_id=source_id),
        pagination=Pagination(
            returned_count=len(items),
            has_more=has_more,
            continuation=ContinuationToken(cursor) if has_more else None,
        ),
        usage=usage or connector_usage(),
        warnings=warnings,
        response_digest="a" * 64,
    )


def details_success(
    candidate: CandidateRef,
    *,
    usage: ConnectorUsage | None = None,
) -> ConnectorOutcome[Observation]:
    item = Observation(
        observation_type=ObservationTypeCode("COMPANY.SYNTHETIC_NAME", SemanticVersion(1, 0, 0)),
        subject_candidate_ref=candidate,
        original_value="Synthetic execution value",
    )
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.SUCCEEDED,
        items=(item,),
        artifacts=(),
        source_snapshot=source_snapshot(),
        pagination=Pagination(returned_count=1, has_more=False),
        usage=usage or connector_usage(),
        response_digest="b" * 64,
    )


def document_success(
    *,
    artifact_count: int = 1,
    usage: ConnectorUsage | None = None,
) -> ConnectorOutcome[ArtifactPayload]:
    items = tuple(
        ArtifactPayload(
            content=f"synthetic document {index}".encode(),
            media_type="text/plain",
            retention=ArtifactRetentionMode.STORE_ORIGINAL,
            origin_reference=OriginReferenceId(f"synthetic-document-payload-{index}"),
        )
        for index in range(artifact_count)
    )
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.SUCCEEDED,
        items=items,
        artifacts=(),
        source_snapshot=source_snapshot(),
        pagination=Pagination(returned_count=len(items), has_more=False),
        usage=usage or connector_usage(),
        response_digest="c" * 64,
    )


def failed_outcome(
    code: ConnectorErrorCode,
    *,
    retry_after: timedelta | None = None,
    usage: ConnectorUsage | None = None,
) -> ConnectorOutcome[CandidateObservation]:
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.FAILED,
        items=(),
        artifacts=(),
        source_snapshot=None,
        pagination=None,
        usage=usage or connector_usage(),
        error=ConnectorError(
            code=code,
            message="Synthetic connector failure",
            retry_after=retry_after,
        ),
        response_digest="e" * 64,
    )


def changed_descriptor(descriptor: ConnectorDescriptor) -> ConnectorDescriptor:
    return replace(descriptor, version=SemanticVersion(1, 2, 4))


__all__ = [
    "TEST_CONNECTOR_ID",
    "TEST_COUNTRY",
    "TEST_CURRENCY",
    "TEST_OPERATION_ID",
    "TEST_SOURCE_ID",
    "ControlledConnector",
    "ControlledSleeper",
    "CredentialDouble",
    "FixedJitter",
    "ManualClock",
    "MutableCancellationSignal",
    "changed_descriptor",
    "connector_context",
    "connector_descriptor",
    "connector_usage",
    "details_request",
    "details_success",
    "document_request",
    "document_success",
    "execution_policy",
    "failed_outcome",
    "operation_runner",
    "run_async",
    "search_request",
    "search_success",
    "source_snapshot",
    "test_candidate",
    "test_document_reference",
]
