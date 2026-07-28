"""Tests for connector result metadata and outcome status invariants."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import cast

import pytest

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.enums import (
    ArtifactRetentionMode,
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.errors import InvalidConnectorOutcomeError
from intelligence.connectors.identifiers import ArtifactRefId, OriginReferenceId, SourceId
from intelligence.connectors.outcomes import (
    ArtifactResult,
    ConnectorError,
    ConnectorOutcome,
    ConnectorUsage,
    ConnectorWarning,
    ContinuationToken,
    Pagination,
    SourceSnapshot,
)
from intelligence.domain.money import CurrencyCode, Money


def snapshot() -> SourceSnapshot:
    return SourceSnapshot(
        source_id=SourceId("source.alpha"),
        origin_reference=OriginReferenceId("record-1"),
        retrieved_at=datetime(2026, 7, 28, 12, tzinfo=UTC),
        published_at=datetime(2026, 7, 27, 12, tzinfo=UTC),
    )


def usage() -> ConnectorUsage:
    return ConnectorUsage(calls=1, bytes_received=128, duration=timedelta(milliseconds=15))


def payload() -> ArtifactPayload:
    return ArtifactPayload(
        content=b"synthetic",
        media_type="text/plain",
        retention=ArtifactRetentionMode.STORE_ORIGINAL,
        origin_reference=OriginReferenceId("record-1"),
    )


def outcome(
    *,
    status: ConnectorOutcomeStatus,
    items: tuple[str, ...] = (),
    artifacts: tuple[ArtifactResult, ...] = (),
    source_snapshot: SourceSnapshot | None = None,
    pagination: Pagination | None = None,
    warnings: tuple[ConnectorWarning, ...] = (),
    error: ConnectorError | None = None,
    response_digest: str | None = None,
) -> ConnectorOutcome[str]:
    return ConnectorOutcome(
        status=status,
        items=items,
        artifacts=artifacts,
        source_snapshot=source_snapshot,
        pagination=pagination,
        usage=usage(),
        warnings=warnings,
        error=error,
        response_digest=response_digest,
    )


def test_source_snapshot_and_pagination_are_canonical_and_redacted() -> None:
    source = snapshot()
    token = ContinuationToken("opaque-cursor-value")
    pagination = Pagination(returned_count=1, has_more=True, continuation=token)

    assert source.retrieved_at.tzinfo is UTC
    assert "opaque-cursor-value" not in repr(token)
    assert "opaque-cursor-value" not in repr(pagination)
    assert "<redacted>" in repr(pagination)


@pytest.mark.parametrize(
    "builder",
    [
        lambda: Pagination(returned_count=-1, has_more=False),
        lambda: Pagination(returned_count=0, has_more=True),
        lambda: Pagination(
            returned_count=0,
            has_more=False,
            continuation=ContinuationToken("cursor"),
        ),
        lambda: ContinuationToken(""),
        lambda: ContinuationToken("line-1\nline-2"),
    ],
)
def test_pagination_rejects_incoherent_or_unsafe_values(builder: object) -> None:
    callable_builder = cast(Callable[[], object], builder)
    with pytest.raises(InvalidConnectorOutcomeError):
        callable_builder()


def test_usage_supports_exact_known_or_estimated_money() -> None:
    value = ConnectorUsage(
        calls=2,
        bytes_received=1024,
        duration=timedelta(seconds=1),
        cost=Money(Decimal("0.25"), CurrencyCode("USD")),
        cost_kind=UsageCostKind.ESTIMATED,
    )

    assert value.cost == Money(Decimal("0.25"), CurrencyCode("USD"))


@pytest.mark.parametrize(
    "kwargs",
    [
        {"calls": -1, "bytes_received": 0, "duration": timedelta(0)},
        {"calls": 0, "bytes_received": -1, "duration": timedelta(0)},
        {"calls": 0, "bytes_received": 0, "duration": timedelta(seconds=-1)},
        {
            "calls": 0,
            "bytes_received": 0,
            "duration": timedelta(0),
            "cost": Money(Decimal("1"), CurrencyCode("USD")),
        },
        {
            "calls": 0,
            "bytes_received": 0,
            "duration": timedelta(0),
            "cost": Money(Decimal("-1"), CurrencyCode("USD")),
            "cost_kind": UsageCostKind.KNOWN,
        },
    ],
)
def test_usage_rejects_negative_or_incomplete_accounting(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidConnectorOutcomeError):
        ConnectorUsage(**kwargs)  # type: ignore[arg-type]


def test_warning_and_error_are_closed_bounded_public_messages() -> None:
    warning = ConnectorWarning(ConnectorWarningCode.PARTIAL_DATA, "One field unavailable")
    error = ConnectorError(
        code=ConnectorErrorCode.RATE_LIMITED,
        message="Source is temporarily limited",
        retry_after=timedelta(seconds=30),
    )

    assert warning.code is ConnectorWarningCode.PARTIAL_DATA
    assert error.retry_after == timedelta(seconds=30)


@pytest.mark.parametrize(
    "builder",
    [
        lambda: ConnectorWarning(cast(ConnectorWarningCode, "PARTIAL_DATA"), "Message"),
        lambda: ConnectorWarning(ConnectorWarningCode.PARTIAL_DATA, "line 1\nline 2"),
        lambda: ConnectorError(
            code=ConnectorErrorCode.INTERNAL_ERROR,
            message="https://internal.example/failure",
        ),
        lambda: ConnectorError(
            code=ConnectorErrorCode.INTERNAL_ERROR,
            message="Authorization header was rejected",
        ),
        lambda: ConnectorError(
            code=ConnectorErrorCode.RATE_LIMITED,
            message="Limited",
            retry_after=timedelta(seconds=-1),
        ),
    ],
)
def test_warning_and_error_reject_unsafe_or_invalid_shapes(builder: object) -> None:
    callable_builder = cast(Callable[[], object], builder)
    with pytest.raises(InvalidConnectorOutcomeError):
        callable_builder()


def test_all_valid_outcome_statuses_store_immutable_tuples() -> None:
    warning = ConnectorWarning(ConnectorWarningCode.PARTIAL_DATA, "One field unavailable")
    gap = ConnectorError(
        code=ConnectorErrorCode.UNAVAILABLE,
        message="One source section unavailable",
    )
    cancelled_error = ConnectorError(
        code=ConnectorErrorCode.CANCELLED,
        message="Operation was cancelled",
    )
    valid = (
        outcome(
            status=ConnectorOutcomeStatus.SUCCEEDED,
            items=("item",),
            source_snapshot=snapshot(),
            pagination=Pagination(returned_count=1, has_more=False),
            response_digest="a" * 64,
        ),
        outcome(
            status=ConnectorOutcomeStatus.SUCCEEDED,
            artifacts=(payload(),),
            source_snapshot=snapshot(),
        ),
        outcome(
            status=ConnectorOutcomeStatus.NO_RESULTS,
            source_snapshot=snapshot(),
            pagination=Pagination(returned_count=0, has_more=False),
        ),
        outcome(
            status=ConnectorOutcomeStatus.PARTIAL,
            items=("item",),
            source_snapshot=snapshot(),
            warnings=(warning,),
        ),
        outcome(
            status=ConnectorOutcomeStatus.PARTIAL,
            artifacts=(payload(),),
            source_snapshot=snapshot(),
            error=gap,
        ),
        outcome(
            status=ConnectorOutcomeStatus.FAILED,
            error=gap,
        ),
        outcome(
            status=ConnectorOutcomeStatus.FAILED,
            artifacts=(payload(),),
            source_snapshot=snapshot(),
            pagination=Pagination(returned_count=0, has_more=False),
            error=gap,
        ),
        outcome(status=ConnectorOutcomeStatus.CANCELLED),
        outcome(status=ConnectorOutcomeStatus.CANCELLED, error=cancelled_error),
    )

    assert all(isinstance(value.items, tuple) for value in valid)
    assert all(isinstance(value.artifacts, tuple) for value in valid)
    assert all(isinstance(value.warnings, tuple) for value in valid)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": ConnectorOutcomeStatus.SUCCEEDED, "source_snapshot": snapshot()},
        {
            "status": ConnectorOutcomeStatus.SUCCEEDED,
            "items": ("item",),
            "source_snapshot": snapshot(),
            "error": ConnectorError(
                code=ConnectorErrorCode.UNAVAILABLE,
                message="Unavailable",
            ),
        },
        {
            "status": ConnectorOutcomeStatus.NO_RESULTS,
            "items": ("item",),
            "source_snapshot": snapshot(),
        },
        {
            "status": ConnectorOutcomeStatus.PARTIAL,
            "items": ("item",),
            "source_snapshot": snapshot(),
        },
        {"status": ConnectorOutcomeStatus.FAILED},
        {
            "status": ConnectorOutcomeStatus.FAILED,
            "items": ("item",),
            "error": ConnectorError(
                code=ConnectorErrorCode.UNAVAILABLE,
                message="Unavailable",
            ),
        },
        {
            "status": ConnectorOutcomeStatus.CANCELLED,
            "items": ("late",),
        },
        {
            "status": ConnectorOutcomeStatus.CANCELLED,
            "error": ConnectorError(
                code=ConnectorErrorCode.TIMEOUT,
                message="Timed out",
            ),
        },
        {
            "status": ConnectorOutcomeStatus.PARTIAL,
            "items": ("item",),
            "source_snapshot": snapshot(),
            "error": ConnectorError(
                code=ConnectorErrorCode.CANCELLED,
                message="Operation was cancelled",
            ),
        },
    ],
)
def test_outcome_rejects_contradictory_status_combinations(kwargs: dict[str, object]) -> None:
    with pytest.raises(InvalidConnectorOutcomeError):
        outcome(**kwargs)  # type: ignore[arg-type]


def test_outcome_rejects_invalid_digest_pagination_count_and_field_types() -> None:
    with pytest.raises(InvalidConnectorOutcomeError):
        outcome(
            status=ConnectorOutcomeStatus.SUCCEEDED,
            items=("item",),
            source_snapshot=snapshot(),
            response_digest="A" * 64,
        )
    with pytest.raises(InvalidConnectorOutcomeError):
        outcome(
            status=ConnectorOutcomeStatus.SUCCEEDED,
            items=("item",),
            source_snapshot=snapshot(),
            pagination=Pagination(returned_count=0, has_more=False),
        )
    with pytest.raises(InvalidConnectorOutcomeError):
        ConnectorOutcome[str](
            status=ConnectorOutcomeStatus.SUCCEEDED,
            items=("item",),
            artifacts=cast(tuple[ArtifactResult, ...], ("artifact",)),
            source_snapshot=snapshot(),
            pagination=None,
            usage=usage(),
        )


def test_artifact_reference_is_a_usable_outcome_artifact() -> None:
    reference = ArtifactReference(
        artifact_ref_id=ArtifactRefId.new(),
        media_type="application/pdf",
        retention=ArtifactRetentionMode.REFERENCE_ONLY,
        origin_reference=OriginReferenceId("record-2"),
    )
    value = outcome(
        status=ConnectorOutcomeStatus.SUCCEEDED,
        artifacts=(reference,),
        source_snapshot=snapshot(),
    )

    assert value.artifacts == (reference,)
