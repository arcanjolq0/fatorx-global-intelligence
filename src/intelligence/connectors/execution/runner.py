"""Controlled runner for exactly one logical operation of one connector."""

import asyncio
import math
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal
from enum import StrEnum
from typing import cast, overload

from intelligence.connectors.artifacts import ArtifactPayload
from intelligence.connectors.context import ConnectorContext
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionControlCode,
    ConnectorExecutionEvent,
    ConnectorExecutionEventKind,
    ConnectorExecutionIdempotencyStatus,
    ConnectorExecutionItem,
    ConnectorExecutionMetadata,
    ConnectorExecutionResult,
    ConnectorOperationRequest,
    FetchDetailsConnectorOperation,
    FetchDocumentConnectorOperation,
    SearchConnectorOperation,
)
from intelligence.connectors.execution.errors import (
    ConnectorExecutionPreflightError,
    IdempotencyConflictError,
)
from intelligence.connectors.execution.fingerprint import (
    connector_execution_digest,
    connector_request_fingerprint,
)
from intelligence.connectors.execution.ports import (
    ExecutionSleeper,
    IdempotencyClaimStatus,
    IdempotencyStore,
    JitterSource,
    MonotonicClock,
    StoredConnectorExecutionResult,
)
from intelligence.connectors.execution.validation import (
    ConnectorDescriptorStabilityError,
    InvalidRuntimeConnectorOutcomeError,
    validate_and_limit_outcome,
    validate_descriptor_stability,
    validate_execution_preflight,
)
from intelligence.connectors.observations import CandidateObservation, Observation
from intelligence.connectors.outcomes import (
    ConnectorError,
    ConnectorOutcome,
    ConnectorUsage,
)
from intelligence.domain.money import CurrencyCode, Money


class _InvocationKind(StrEnum):
    RETURNED = "RETURNED"
    TIMED_OUT = "TIMED_OUT"
    RAISED = "RAISED"
    CANCELLED = "CANCELLED"


class _IdempotencyWaitKind(StrEnum):
    COMPLETED = "COMPLETED"
    RELEASED = "RELEASED"
    TIMED_OUT = "TIMED_OUT"


@dataclass(frozen=True, slots=True)
class _Invocation:
    kind: _InvocationKind
    outcome: object | None = None


@dataclass(frozen=True, slots=True)
class _IdempotencyWait:
    kind: _IdempotencyWaitKind
    result: StoredConnectorExecutionResult | None = None


@dataclass(frozen=True, slots=True)
class _Accounting:
    calls: int = 0
    bytes_received: int = 0
    duration: timedelta = timedelta(0)
    cost: Money | None = None
    cost_kind: UsageCostKind | None = None

    def add(
        self,
        usage: ConnectorUsage | None,
        *,
        estimate: Money | None,
        expected_currency: CurrencyCode | None,
    ) -> tuple[_Accounting, ConnectorUsage, Money | None, bool]:
        reported = usage or ConnectorUsage(
            calls=1,
            bytes_received=0,
            duration=timedelta(0),
        )
        charged = reported.cost
        charged_kind = reported.cost_kind
        currency_invalid = False
        if (
            charged is not None
            and expected_currency is not None
            and charged.currency != expected_currency
        ):
            currency_invalid = True
            charged = estimate
            charged_kind = UsageCostKind.ESTIMATED if estimate is not None else None
        elif charged is None and estimate is not None:
            charged = estimate
            charged_kind = UsageCostKind.ESTIMATED
        if charged is not None and self.cost is not None and charged.currency != self.cost.currency:
            currency_invalid = True
            charged = (
                estimate
                if estimate is not None and estimate.currency == self.cost.currency
                else None
            )
            charged_kind = UsageCostKind.ESTIMATED if charged is not None else None

        total_cost = self.cost
        total_cost_kind = self.cost_kind
        if charged is not None:
            total_cost = charged if total_cost is None else total_cost + charged
            if (
                total_cost_kind is UsageCostKind.ESTIMATED
                or charged_kind is UsageCostKind.ESTIMATED
            ):
                total_cost_kind = UsageCostKind.ESTIMATED
            else:
                total_cost_kind = UsageCostKind.KNOWN
        accounted_attempt = ConnectorUsage(
            calls=reported.calls,
            bytes_received=reported.bytes_received,
            duration=reported.duration,
            cost=charged,
            cost_kind=charged_kind,
        )
        return (
            _Accounting(
                calls=self.calls + reported.calls,
                bytes_received=self.bytes_received + reported.bytes_received,
                duration=self.duration + reported.duration,
                cost=total_cost,
                cost_kind=total_cost_kind,
            ),
            accounted_attempt,
            charged,
            currency_invalid,
        )

    def as_usage(self) -> ConnectorUsage:
        return ConnectorUsage(
            calls=self.calls,
            bytes_received=self.bytes_received,
            duration=self.duration,
            cost=self.cost,
            cost_kind=self.cost_kind,
        )


class ConnectorOperationRunner:
    """Execute one explicitly supplied connector operation under local controls."""

    def __init__(
        self,
        *,
        clock: MonotonicClock,
        sleeper: ExecutionSleeper,
        jitter: JitterSource,
        idempotency_store: IdempotencyStore,
    ) -> None:
        if not isinstance(clock, MonotonicClock):
            raise TypeError("Runner clock does not implement MonotonicClock.")
        if not isinstance(sleeper, ExecutionSleeper):
            raise TypeError("Runner sleeper does not implement ExecutionSleeper.")
        if not isinstance(jitter, JitterSource):
            raise TypeError("Runner jitter does not implement JitterSource.")
        if not isinstance(idempotency_store, IdempotencyStore):
            raise TypeError("Runner idempotency store does not implement IdempotencyStore.")
        self._clock = clock
        self._sleeper = sleeper
        self._jitter = jitter
        self._idempotency_store = idempotency_store

    @overload
    async def execute(
        self,
        request: SearchConnectorOperation,
        *,
        expected_descriptor: ConnectorDescriptor | None = None,
    ) -> ConnectorExecutionResult[CandidateObservation]: ...

    @overload
    async def execute(
        self,
        request: FetchDetailsConnectorOperation,
        *,
        expected_descriptor: ConnectorDescriptor | None = None,
    ) -> ConnectorExecutionResult[Observation]: ...

    @overload
    async def execute(
        self,
        request: FetchDocumentConnectorOperation,
        *,
        expected_descriptor: ConnectorDescriptor | None = None,
    ) -> ConnectorExecutionResult[ArtifactPayload]: ...

    @overload
    async def execute(
        self,
        request: ConnectorOperationRequest,
        *,
        expected_descriptor: ConnectorDescriptor | None = None,
    ) -> ConnectorExecutionResult[ConnectorExecutionItem]: ...

    async def execute(
        self,
        request: ConnectorOperationRequest,
        *,
        expected_descriptor: ConnectorDescriptor | None = None,
    ) -> ConnectorExecutionResult[ConnectorExecutionItem]:
        """Validate, reserve, and execute exactly the request's one declared operation."""

        preflight = validate_execution_preflight(request)
        if expected_descriptor is not None and preflight.descriptor != expected_descriptor:
            raise ConnectorExecutionPreflightError(
                ConnectorErrorCode.INVALID_REQUEST,
                "Connector descriptor differs from the expected persisted descriptor",
            )
        try:
            fingerprint = connector_request_fingerprint(
                request,
                preflight.descriptor,
                credential_reference=preflight.credential_reference,
            )
        except Exception as error:
            raise ConnectorExecutionPreflightError(
                ConnectorErrorCode.INVALID_REQUEST,
                "Connector request fingerprint could not be calculated",
            ) from error
        metadata = _metadata(request, preflight.descriptor)
        if _cancelled(request.context):
            return self._control_result(
                metadata=metadata,
                fingerprint=fingerprint,
                code=ConnectorErrorCode.CANCELLED,
                message="Connector operation was cancelled",
                event_kind=ConnectorExecutionEventKind.CANCELLED,
                control_code=ConnectorExecutionControlCode.CANCELLATION_OBSERVED,
            )
        if self._deadline_expired(request.context):
            return self._control_result(
                metadata=metadata,
                fingerprint=fingerprint,
                code=ConnectorErrorCode.TIMEOUT,
                message="Connector operation deadline expired",
                event_kind=ConnectorExecutionEventKind.TIMED_OUT,
                control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
            )

        operation_id = request.context.operation_id
        while True:
            try:
                claim = await self._idempotency_store.reserve(operation_id, fingerprint)
            except IdempotencyConflictError:
                return self._conflict_result(metadata=metadata, fingerprint=fingerprint)
            if claim.status is IdempotencyClaimStatus.COMPLETED:
                if claim.result is None:
                    raise RuntimeError("Completed idempotency claim has no result.")
                return self._replay(claim.result)
            if claim.status is IdempotencyClaimStatus.WAIT:
                try:
                    waited = await self._wait_for_idempotency(request.context, fingerprint)
                except IdempotencyConflictError:
                    return self._conflict_result(metadata=metadata, fingerprint=fingerprint)
                if waited.kind is _IdempotencyWaitKind.RELEASED:
                    continue
                if waited.kind is _IdempotencyWaitKind.TIMED_OUT:
                    return self._control_result(
                        metadata=metadata,
                        fingerprint=fingerprint,
                        code=ConnectorErrorCode.TIMEOUT,
                        message="Connector operation deadline expired",
                        event_kind=ConnectorExecutionEventKind.TIMED_OUT,
                        control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
                    )
                completed = waited.result
                if completed is None:
                    raise RuntimeError("Completed idempotency wait has no result.")
                if _cancelled(request.context):
                    return self._control_result(
                        metadata=metadata,
                        fingerprint=fingerprint,
                        code=ConnectorErrorCode.CANCELLED,
                        message="Connector operation was cancelled",
                        event_kind=ConnectorExecutionEventKind.CANCELLED,
                        control_code=ConnectorExecutionControlCode.CANCELLATION_OBSERVED,
                    )
                if self._deadline_expired(request.context):
                    return self._control_result(
                        metadata=metadata,
                        fingerprint=fingerprint,
                        code=ConnectorErrorCode.TIMEOUT,
                        message="Connector operation deadline expired",
                        event_kind=ConnectorExecutionEventKind.TIMED_OUT,
                        control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
                    )
                return self._replay(completed)
            break

        try:
            result = await self._execute_owner(
                request=request,
                descriptor=preflight.descriptor,
                metadata=metadata,
                fingerprint=fingerprint,
            )
            await self._idempotency_store.complete(
                operation_id,
                fingerprint,
                result,
            )
            return result
        except asyncio.CancelledError:
            await self._idempotency_store.release(operation_id, fingerprint)
            raise
        except Exception:
            await self._idempotency_store.release(operation_id, fingerprint)
            raise

    async def _wait_for_idempotency(
        self,
        context: ConnectorContext,
        fingerprint: str,
    ) -> _IdempotencyWait:
        wait_task = asyncio.create_task(
            self._idempotency_store.wait(context.operation_id, fingerprint)
        )
        deadline_task = asyncio.create_task(self._sleeper.sleep_until(context.deadline))
        try:
            done, _ = await asyncio.wait(
                {wait_task, deadline_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            await _cancel_task(wait_task)
            await _cancel_task(deadline_task)
            raise
        if deadline_task in done and self._deadline_expired(context):
            await _cancel_task(wait_task)
            await _consume_task(deadline_task)
            return _IdempotencyWait(_IdempotencyWaitKind.TIMED_OUT)
        if wait_task not in done:
            await _cancel_task(wait_task)
            await _consume_task(deadline_task)
            raise RuntimeError("Execution sleeper returned before the monotonic deadline.")
        await _cancel_task(deadline_task)
        completed = wait_task.result()
        if completed is None:
            return _IdempotencyWait(_IdempotencyWaitKind.RELEASED)
        return _IdempotencyWait(_IdempotencyWaitKind.COMPLETED, completed)

    async def _execute_owner(
        self,
        *,
        request: ConnectorOperationRequest,
        descriptor: ConnectorDescriptor,
        metadata: ConnectorExecutionMetadata,
        fingerprint: str,
    ) -> ConnectorExecutionResult[ConnectorExecutionItem]:
        events = [
            _event(
                ConnectorExecutionEventKind.RESERVED,
                metadata,
                fingerprint,
            )
        ]
        accounting = _Accounting()
        remaining = request.context.budget_remaining
        estimate = request.policy.estimated_attempt_cost
        expected_currency = _expected_currency(remaining, estimate)
        attempts_started = 0

        for attempt in range(1, request.policy.max_attempts + 1):
            if _cancelled(request.context):
                events.append(
                    _event(
                        ConnectorExecutionEventKind.CANCELLED,
                        metadata,
                        fingerprint,
                        attempt=attempt,
                        error_code=ConnectorErrorCode.CANCELLED,
                    )
                )
                return _build_result(
                    outcome=_cancelled_outcome(_zero_usage()),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=ConnectorExecutionControlCode.CANCELLATION_OBSERVED,
                )
            if self._deadline_expired(request.context):
                events.append(
                    _event(
                        ConnectorExecutionEventKind.TIMED_OUT,
                        metadata,
                        fingerprint,
                        attempt=attempt,
                        error_code=ConnectorErrorCode.TIMEOUT,
                    )
                )
                return _build_result(
                    outcome=_failed_outcome(
                        ConnectorErrorCode.TIMEOUT,
                        "Connector operation deadline expired",
                        _zero_usage(),
                    ),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
                )
            if not _budget_allows(remaining, estimate):
                events.append(
                    _event(
                        ConnectorExecutionEventKind.BUDGET_BLOCKED,
                        metadata,
                        fingerprint,
                        attempt=attempt,
                        error_code=ConnectorErrorCode.BUDGET_EXCEEDED,
                        total_cost=accounting.cost,
                    )
                )
                return _build_result(
                    outcome=_failed_outcome(
                        ConnectorErrorCode.BUDGET_EXCEEDED,
                        "Connector operation budget is insufficient",
                        _zero_usage(),
                    ),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=ConnectorExecutionControlCode.BUDGET_BLOCKED,
                )

            attempt_context = _attempt_context(request.context, attempt, remaining)
            attempts_started = attempt
            events.append(
                _event(
                    ConnectorExecutionEventKind.ATTEMPT_STARTED,
                    metadata,
                    fingerprint,
                    attempt=attempt,
                    total_cost=accounting.cost,
                )
            )
            invocation = await self._invoke_with_deadline(request, attempt_context)
            raw_usage = _safe_usage(invocation.outcome)
            accounting, attempt_usage, charged, currency_invalid = accounting.add(
                raw_usage,
                estimate=estimate,
                expected_currency=expected_currency,
            )
            remaining, overrun = _apply_charge(remaining, charged)

            if invocation.kind is _InvocationKind.TIMED_OUT:
                outcome = _failed_outcome(
                    ConnectorErrorCode.TIMEOUT,
                    "Connector operation deadline expired",
                    attempt_usage,
                )
                events.append(
                    _event(
                        ConnectorExecutionEventKind.TIMED_OUT,
                        metadata,
                        fingerprint,
                        attempt=attempt,
                        status=outcome.status,
                        error_code=ConnectorErrorCode.TIMEOUT,
                        total_cost=accounting.cost,
                    )
                )
                return _build_result(
                    outcome=outcome,
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
                )
            if invocation.kind is _InvocationKind.CANCELLED or _cancelled(request.context):
                outcome = _cancelled_outcome(attempt_usage)
                events.append(
                    _event(
                        ConnectorExecutionEventKind.CANCELLED,
                        metadata,
                        fingerprint,
                        attempt=attempt,
                        status=outcome.status,
                        error_code=ConnectorErrorCode.CANCELLED,
                        total_cost=accounting.cost,
                    )
                )
                return _build_result(
                    outcome=outcome,
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=ConnectorExecutionControlCode.CANCELLATION_OBSERVED,
                )
            descriptor_unstable = False
            if invocation.kind is _InvocationKind.RAISED:
                outcome = _failed_outcome(
                    ConnectorErrorCode.INTERNAL_ERROR,
                    "Connector operation failed internally",
                    attempt_usage,
                )
                attempt_control_code: ConnectorExecutionControlCode | None = (
                    ConnectorExecutionControlCode.CONNECTOR_EXCEPTION
                )
            else:
                try:
                    validate_descriptor_stability(request.connector, descriptor)
                    outcome = validate_and_limit_outcome(
                        request=request,
                        descriptor=descriptor,
                        outcome=invocation.outcome,
                        expected_cost_currency=expected_currency,
                    )
                    attempt_control_code = None
                except ConnectorDescriptorStabilityError:
                    descriptor_unstable = True
                    outcome = _failed_outcome(
                        ConnectorErrorCode.INVALID_RESPONSE,
                        "Connector identity changed during execution",
                        attempt_usage,
                    )
                    attempt_control_code = ConnectorExecutionControlCode.INVALID_CONNECTOR_RESPONSE
                except InvalidRuntimeConnectorOutcomeError:
                    outcome = _failed_outcome(
                        ConnectorErrorCode.INVALID_RESPONSE,
                        "Connector returned an incompatible response",
                        attempt_usage,
                    )
                    attempt_control_code = ConnectorExecutionControlCode.INVALID_CONNECTOR_RESPONSE
            if currency_invalid and (
                outcome.error is None
                or outcome.error.code is not ConnectorErrorCode.INVALID_RESPONSE
            ):
                outcome = _failed_outcome(
                    ConnectorErrorCode.INVALID_RESPONSE,
                    "Connector returned incompatible usage accounting",
                    attempt_usage,
                )
                attempt_control_code = ConnectorExecutionControlCode.INVALID_CONNECTOR_RESPONSE
            if overrun:
                outcome = _failed_outcome(
                    ConnectorErrorCode.BUDGET_EXCEEDED,
                    "Connector operation exceeded the available budget",
                    attempt_usage,
                )
                attempt_control_code = ConnectorExecutionControlCode.BUDGET_BLOCKED
                events.append(
                    _event(
                        ConnectorExecutionEventKind.BUDGET_BLOCKED,
                        metadata,
                        fingerprint,
                        attempt=attempt,
                        status=outcome.status,
                        error_code=ConnectorErrorCode.BUDGET_EXCEEDED,
                        total_cost=accounting.cost,
                    )
                )

            events.append(
                _event(
                    ConnectorExecutionEventKind.ATTEMPT_COMPLETED,
                    metadata,
                    fingerprint,
                    attempt=attempt,
                    status=outcome.status,
                    error_code=outcome.error.code if outcome.error is not None else None,
                    warning_codes=tuple(warning.code for warning in outcome.warnings),
                    total_cost=accounting.cost,
                )
            )
            if descriptor_unstable or overrun or not _should_retry(outcome, request, attempt):
                return _build_result(
                    outcome=outcome,
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=attempt_control_code,
                )
            if not _budget_allows(remaining, estimate):
                events.append(
                    _event(
                        ConnectorExecutionEventKind.BUDGET_BLOCKED,
                        metadata,
                        fingerprint,
                        attempt=attempt + 1,
                        error_code=ConnectorErrorCode.BUDGET_EXCEEDED,
                        total_cost=accounting.cost,
                    )
                )
                return _build_result(
                    outcome=_failed_outcome(
                        ConnectorErrorCode.BUDGET_EXCEEDED,
                        "Connector operation budget cannot fund a retry",
                        _zero_usage(),
                    ),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=events,
                    control_code=ConnectorExecutionControlCode.BUDGET_BLOCKED,
                )
            delay = self._retry_delay(request, outcome, attempt)
            if _cancelled(request.context):
                return _build_result(
                    outcome=_cancelled_outcome(_zero_usage()),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=[
                        *events,
                        _event(
                            ConnectorExecutionEventKind.CANCELLED,
                            metadata,
                            fingerprint,
                            attempt=attempt,
                            error_code=ConnectorErrorCode.CANCELLED,
                            total_cost=accounting.cost,
                        ),
                    ],
                    control_code=ConnectorExecutionControlCode.CANCELLATION_OBSERVED,
                )
            remaining_time = request.context.deadline.value - self._now()
            if remaining_time <= 0 or delay.total_seconds() >= remaining_time:
                return _build_result(
                    outcome=_failed_outcome(
                        ConnectorErrorCode.TIMEOUT,
                        "Connector operation deadline prevents retry",
                        _zero_usage(),
                    ),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=[
                        *events,
                        _event(
                            ConnectorExecutionEventKind.TIMED_OUT,
                            metadata,
                            fingerprint,
                            attempt=attempt,
                            error_code=ConnectorErrorCode.TIMEOUT,
                            total_cost=accounting.cost,
                        ),
                    ],
                    control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
                )
            events.append(
                _event(
                    ConnectorExecutionEventKind.RETRY_SCHEDULED,
                    metadata,
                    fingerprint,
                    attempt=attempt,
                    error_code=outcome.error.code if outcome.error is not None else None,
                    delay=delay,
                    total_cost=accounting.cost,
                )
            )
            await self._sleeper.sleep(delay)
            if _cancelled(request.context):
                return _build_result(
                    outcome=_cancelled_outcome(_zero_usage()),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=[
                        *events,
                        _event(
                            ConnectorExecutionEventKind.CANCELLED,
                            metadata,
                            fingerprint,
                            attempt=attempt,
                            error_code=ConnectorErrorCode.CANCELLED,
                            total_cost=accounting.cost,
                        ),
                    ],
                    control_code=ConnectorExecutionControlCode.CANCELLATION_OBSERVED,
                )
            if self._deadline_expired(request.context):
                return _build_result(
                    outcome=_failed_outcome(
                        ConnectorErrorCode.TIMEOUT,
                        "Connector operation deadline expired during retry delay",
                        _zero_usage(),
                    ),
                    attempts_started=attempts_started,
                    accounting=accounting,
                    fingerprint=fingerprint,
                    metadata=metadata,
                    events=[
                        *events,
                        _event(
                            ConnectorExecutionEventKind.TIMED_OUT,
                            metadata,
                            fingerprint,
                            attempt=attempt,
                            error_code=ConnectorErrorCode.TIMEOUT,
                            total_cost=accounting.cost,
                        ),
                    ],
                    control_code=ConnectorExecutionControlCode.DEADLINE_EXPIRED,
                )
        raise AssertionError("Execution attempts loop ended unexpectedly")

    async def _invoke_with_deadline(
        self,
        request: ConnectorOperationRequest,
        context: ConnectorContext,
    ) -> _Invocation:
        connector_task = asyncio.create_task(_invoke_connector(request, context))
        deadline_task = asyncio.create_task(self._sleeper.sleep_until(context.deadline))
        try:
            done, _ = await asyncio.wait(
                {connector_task, deadline_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        except asyncio.CancelledError:
            await _cancel_task(connector_task)
            await _cancel_task(deadline_task)
            raise
        if deadline_task in done and self._deadline_expired(context):
            await _cancel_task(connector_task)
            await _consume_task(deadline_task)
            return _Invocation(_InvocationKind.TIMED_OUT)
        if connector_task not in done:
            await _cancel_task(connector_task)
            await _consume_task(deadline_task)
            return _Invocation(_InvocationKind.RAISED)
        await _cancel_task(deadline_task)
        try:
            outcome = connector_task.result()
        except asyncio.CancelledError:
            return _Invocation(_InvocationKind.CANCELLED)
        except Exception:
            return _Invocation(_InvocationKind.RAISED)
        if self._deadline_expired(context):
            return _Invocation(_InvocationKind.TIMED_OUT)
        return _Invocation(_InvocationKind.RETURNED, outcome)

    def _retry_delay(
        self,
        request: ConnectorOperationRequest,
        outcome: ConnectorOutcome[ConnectorExecutionItem],
        attempt: int,
    ) -> timedelta:
        multiplier = 2 ** (attempt - 1)
        backoff = min(request.policy.base_backoff * multiplier, request.policy.max_backoff)
        jitter = self._jitter.jitter(attempt=attempt, backoff=backoff)
        if (
            not isinstance(jitter, timedelta)
            or jitter < timedelta(0)
            or jitter > request.policy.max_jitter
        ):
            raise ValueError("Injected jitter exceeded the execution policy bound.")
        calculated = cast(
            timedelta,
            min(backoff + jitter, request.policy.max_backoff + request.policy.max_jitter),
        )
        retry_after = outcome.error.retry_after if outcome.error is not None else None
        if retry_after is not None and retry_after > calculated:
            return retry_after
        return calculated

    def _now(self) -> float:
        value = self._clock.now()
        if (
            isinstance(value, bool)
            or not isinstance(value, float)
            or not math.isfinite(value)
            or value < 0
        ):
            raise ValueError("Monotonic clock returned an invalid value.")
        return value

    def _deadline_expired(self, context: ConnectorContext) -> bool:
        return self._now() >= context.deadline.value

    def _control_result(
        self,
        *,
        metadata: ConnectorExecutionMetadata,
        fingerprint: str,
        code: ConnectorErrorCode,
        message: str,
        event_kind: ConnectorExecutionEventKind,
        control_code: ConnectorExecutionControlCode,
    ) -> ConnectorExecutionResult[ConnectorExecutionItem]:
        outcome = (
            _cancelled_outcome(_zero_usage())
            if code is ConnectorErrorCode.CANCELLED
            else _failed_outcome(code, message, _zero_usage())
        )
        return _build_result(
            outcome=outcome,
            attempts_started=0,
            accounting=_Accounting(),
            fingerprint=fingerprint,
            metadata=metadata,
            events=[
                _event(
                    event_kind,
                    metadata,
                    fingerprint,
                    status=outcome.status,
                    error_code=code,
                )
            ],
            control_code=control_code,
            idempotency_status=ConnectorExecutionIdempotencyStatus.NOT_RESERVED,
        )

    def _conflict_result(
        self,
        *,
        metadata: ConnectorExecutionMetadata,
        fingerprint: str,
    ) -> ConnectorExecutionResult[ConnectorExecutionItem]:
        outcome = _failed_outcome(
            ConnectorErrorCode.INVALID_REQUEST,
            "Operation identifier conflicts with a different request",
            _zero_usage(),
        )
        return _build_result(
            outcome=outcome,
            attempts_started=0,
            accounting=_Accounting(),
            fingerprint=fingerprint,
            metadata=metadata,
            events=[
                _event(
                    ConnectorExecutionEventKind.IDEMPOTENCY_CONFLICT,
                    metadata,
                    fingerprint,
                    status=outcome.status,
                    error_code=ConnectorErrorCode.INVALID_REQUEST,
                )
            ],
            control_code=ConnectorExecutionControlCode.IDEMPOTENCY_CONFLICT,
            idempotency_status=ConnectorExecutionIdempotencyStatus.CONFLICT,
        )

    def _replay(
        self,
        stored: StoredConnectorExecutionResult,
    ) -> ConnectorExecutionResult[ConnectorExecutionItem]:
        replay_event = _event(
            ConnectorExecutionEventKind.REPLAYED,
            stored.metadata,
            stored.fingerprint,
            status=stored.outcome.status,
            error_code=stored.outcome.error.code if stored.outcome.error is not None else None,
            warning_codes=tuple(warning.code for warning in stored.outcome.warnings),
            total_cost=stored.total_usage.cost,
            digest=stored.digest,
        )
        completed_event = _event(
            ConnectorExecutionEventKind.COMPLETED,
            stored.metadata,
            stored.fingerprint,
            status=stored.outcome.status,
            error_code=stored.outcome.error.code if stored.outcome.error is not None else None,
            warning_codes=tuple(warning.code for warning in stored.outcome.warnings),
            total_cost=stored.total_usage.cost,
            digest=stored.digest,
        )
        return replace(
            stored,
            idempotency_status=ConnectorExecutionIdempotencyStatus.REPLAYED,
            events=(replay_event, completed_event),
        )


async def _invoke_connector(
    request: ConnectorOperationRequest,
    context: ConnectorContext,
) -> object:
    if isinstance(request, SearchConnectorOperation):
        return await request.connector.search(request.query, context)
    if isinstance(request, FetchDetailsConnectorOperation):
        return await request.connector.fetch_details(request.candidate, context)
    return await request.connector.fetch_document(request.document, context)


async def _cancel_task[T](task: asyncio.Task[T]) -> None:
    if not task.done():
        task.cancel()
    await _consume_task(task)


async def _consume_task[T](task: asyncio.Task[T]) -> None:
    try:
        await task
    except asyncio.CancelledError:
        return
    except Exception:
        return


def _attempt_context(
    base: ConnectorContext,
    attempt: int,
    remaining: Money | None,
) -> ConnectorContext:
    return ConnectorContext(
        workspace_id=base.workspace_id,
        investigation_id=base.investigation_id,
        operation_id=base.operation_id,
        attempt=attempt,
        correlation_id=base.correlation_id,
        request_id=base.request_id,
        deadline=base.deadline,
        budget_remaining=remaining,
        accepted_locales=base.accepted_locales,
        source_policy_version=base.source_policy_version,
        mode=base.mode,
        cancellation_signal=base.cancellation_signal,
        credential_handle=base.credential_handle,
    )


def _metadata(
    request: ConnectorOperationRequest,
    descriptor: ConnectorDescriptor,
) -> ConnectorExecutionMetadata:
    return ConnectorExecutionMetadata(
        connector_id=descriptor.connector_id,
        connector_version=descriptor.version,
        contract_version=descriptor.contract_version,
        operation_id=request.context.operation_id,
        operation=request.operation,
        capability=request.capability,
        country=request.country,
    )


def _cancelled(context: ConnectorContext) -> bool:
    try:
        return context.cancellation_signal.is_cancelled()
    except Exception:
        return True


def _expected_currency(
    budget: Money | None,
    estimate: Money | None,
) -> CurrencyCode | None:
    if budget is not None:
        return budget.currency
    if estimate is not None:
        return estimate.currency
    return None


def _budget_allows(remaining: Money | None, estimate: Money | None) -> bool:
    if remaining is None:
        return True
    return estimate is not None and remaining.amount >= estimate.amount


def _apply_charge(
    remaining: Money | None,
    charged: Money | None,
) -> tuple[Money | None, bool]:
    if remaining is None or charged is None:
        return remaining, False
    if charged.currency != remaining.currency:
        return remaining, False
    if charged.amount > remaining.amount:
        return Money(Decimal(0), remaining.currency), True
    return remaining - charged, False


def _safe_usage(outcome: object | None) -> ConnectorUsage | None:
    if not isinstance(outcome, ConnectorOutcome):
        return None
    try:
        usage = outcome.usage
    except Exception:
        return None
    return usage if isinstance(usage, ConnectorUsage) else None


def _should_retry(
    outcome: ConnectorOutcome[ConnectorExecutionItem],
    request: ConnectorOperationRequest,
    attempt: int,
) -> bool:
    return (
        attempt < request.policy.max_attempts
        and outcome.status is ConnectorOutcomeStatus.FAILED
        and outcome.error is not None
        and outcome.error.code in request.policy.retriable_codes
    )


def _failed_outcome(
    code: ConnectorErrorCode,
    message: str,
    usage: ConnectorUsage,
) -> ConnectorOutcome[ConnectorExecutionItem]:
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.FAILED,
        items=(),
        artifacts=(),
        source_snapshot=None,
        pagination=None,
        usage=usage,
        error=ConnectorError(code=code, message=message),
    )


def _cancelled_outcome(usage: ConnectorUsage) -> ConnectorOutcome[ConnectorExecutionItem]:
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.CANCELLED,
        items=(),
        artifacts=(),
        source_snapshot=None,
        pagination=None,
        usage=usage,
        error=ConnectorError(
            code=ConnectorErrorCode.CANCELLED,
            message="Connector operation was cancelled",
        ),
    )


def _zero_usage() -> ConnectorUsage:
    return ConnectorUsage(calls=0, bytes_received=0, duration=timedelta(0))


def _event(
    kind: ConnectorExecutionEventKind,
    metadata: ConnectorExecutionMetadata,
    fingerprint: str,
    *,
    attempt: int | None = None,
    status: ConnectorOutcomeStatus | None = None,
    error_code: ConnectorErrorCode | None = None,
    warning_codes: tuple[ConnectorWarningCode, ...] = (),
    delay: timedelta | None = None,
    total_cost: Money | None = None,
    digest: str | None = None,
) -> ConnectorExecutionEvent:
    return ConnectorExecutionEvent(
        kind=kind,
        metadata=metadata,
        fingerprint=fingerprint,
        attempt=attempt,
        status=status,
        error_code=error_code,
        warning_codes=warning_codes,
        delay=delay,
        total_cost=total_cost,
        digest=digest,
    )


def _build_result(
    *,
    outcome: ConnectorOutcome[ConnectorExecutionItem],
    attempts_started: int,
    accounting: _Accounting,
    fingerprint: str,
    metadata: ConnectorExecutionMetadata,
    events: list[ConnectorExecutionEvent],
    control_code: ConnectorExecutionControlCode | None,
    idempotency_status: ConnectorExecutionIdempotencyStatus = (
        ConnectorExecutionIdempotencyStatus.EXECUTED
    ),
) -> ConnectorExecutionResult[ConnectorExecutionItem]:
    total_usage = accounting.as_usage()
    digest = connector_execution_digest(
        fingerprint=fingerprint,
        metadata=metadata,
        outcome=outcome,
        attempts_started=attempts_started,
        total_usage=total_usage,
    )
    completed = _event(
        ConnectorExecutionEventKind.COMPLETED,
        metadata,
        fingerprint,
        status=outcome.status,
        error_code=outcome.error.code if outcome.error is not None else None,
        warning_codes=tuple(warning.code for warning in outcome.warnings),
        total_cost=total_usage.cost,
        digest=digest,
    )
    return ConnectorExecutionResult(
        outcome=outcome,
        attempts_started=attempts_started,
        total_usage=total_usage,
        fingerprint=fingerprint,
        digest=digest,
        idempotency_status=idempotency_status,
        metadata=metadata,
        events=(*events, completed),
        control_code=control_code,
    )


__all__ = ["ConnectorOperationRunner"]
