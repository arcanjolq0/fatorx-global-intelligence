"""Tests for connector call context contracts without execution controls."""

from dataclasses import FrozenInstanceError
from decimal import Decimal
from typing import cast

import pytest

from intelligence.connectors.context import (
    ConnectorContext,
    LocaleTag,
    MonotonicDeadline,
)
from intelligence.connectors.enums import ConnectorMode
from intelligence.connectors.errors import InvalidConnectorContextError
from intelligence.connectors.identifiers import OperationId, RequestId
from intelligence.connectors.versions import SourcePolicyVersion
from intelligence.domain.identifiers import CorrelationId, InvestigationId, WorkspaceId
from intelligence.domain.money import CurrencyCode, Money


class CredentialStub:
    def __init__(self, marker: str) -> None:
        self.marker = marker

    @property
    def reference_name(self) -> str:
        return "REGISTRY_CREDENTIAL_REF"

    def __repr__(self) -> str:
        return f"CredentialStub(marker={self.marker!r})"


class CancellationStub:
    def __init__(self, cancelled: bool = False) -> None:
        self.cancelled = cancelled

    def is_cancelled(self) -> bool:
        return self.cancelled


def context(**overrides: object) -> ConnectorContext:
    values: dict[str, object] = {
        "workspace_id": WorkspaceId.new(),
        "investigation_id": InvestigationId.new(),
        "operation_id": OperationId.new(),
        "attempt": 1,
        "correlation_id": CorrelationId.new(),
        "request_id": RequestId.new(),
        "deadline": MonotonicDeadline(123.5),
        "budget_remaining": Money(Decimal("12.50"), CurrencyCode("BRL")),
        "accepted_locales": [LocaleTag("pt-BR"), LocaleTag("en")],
        "source_policy_version": SourcePolicyVersion("policy-1"),
        "mode": ConnectorMode.TEST,
        "credential_handle": CredentialStub("secret-marker"),
        "cancellation_signal": CancellationStub(),
    }
    values.update(overrides)
    return ConnectorContext(
        workspace_id=cast(WorkspaceId, values["workspace_id"]),
        investigation_id=cast(InvestigationId, values["investigation_id"]),
        operation_id=cast(OperationId, values["operation_id"]),
        attempt=cast(int, values["attempt"]),
        correlation_id=cast(CorrelationId, values["correlation_id"]),
        request_id=cast(RequestId, values["request_id"]),
        deadline=cast(MonotonicDeadline, values["deadline"]),
        budget_remaining=cast(Money | None, values["budget_remaining"]),
        accepted_locales=cast(list[LocaleTag], values["accepted_locales"]),
        source_policy_version=cast(SourcePolicyVersion, values["source_policy_version"]),
        mode=cast(ConnectorMode, values["mode"]),
        credential_handle=cast(CredentialStub | None, values["credential_handle"]),
        cancellation_signal=cast(CancellationStub, values["cancellation_signal"]),
    )


def test_context_is_immutable_typed_and_redacts_handles() -> None:
    value = context()

    assert value.attempt == 1
    assert value.accepted_locales == (LocaleTag("pt-BR"), LocaleTag("en"))
    assert "secret-marker" not in repr(value)
    assert "CancellationStub" not in repr(value)
    assert value.cancellation_signal.is_cancelled() is False
    with pytest.raises(FrozenInstanceError):
        value.attempt = 2  # type: ignore[misc]


def test_locale_tag_normalizes_supported_bcp47_shape() -> None:
    assert LocaleTag("PT-br").value == "pt-BR"
    assert LocaleTag("zh-hant-tw").value == "zh-Hant-TW"


@pytest.mark.parametrize("value", ["", "p", "pt_BR", "pt-Brazil", " pt-BR"])
def test_locale_tag_rejects_invalid_forms(value: str) -> None:
    with pytest.raises(InvalidConnectorContextError):
        LocaleTag(value)


@pytest.mark.parametrize("value", [-1.0, float("inf"), float("nan"), 1, True])
def test_monotonic_deadline_rejects_invalid_values(value: object) -> None:
    with pytest.raises(InvalidConnectorContextError):
        MonotonicDeadline(cast(float, value))


@pytest.mark.parametrize("attempt", [0, -1, True])
def test_context_rejects_invalid_attempt(attempt: int) -> None:
    with pytest.raises(InvalidConnectorContextError):
        context(attempt=attempt)


def test_context_rejects_wrong_strong_identifier_type() -> None:
    with pytest.raises(InvalidConnectorContextError):
        context(workspace_id=InvestigationId.new())


def test_context_rejects_float_or_negative_budget() -> None:
    with pytest.raises(InvalidConnectorContextError):
        context(budget_remaining=12.5)
    with pytest.raises(InvalidConnectorContextError):
        context(budget_remaining=Money(Decimal("-0.01"), CurrencyCode("BRL")))


def test_context_rejects_empty_duplicate_or_untyped_locales() -> None:
    with pytest.raises(InvalidConnectorContextError):
        context(accepted_locales=[])
    with pytest.raises(InvalidConnectorContextError):
        context(accepted_locales=[LocaleTag("pt-BR"), LocaleTag("pt-br")])
    with pytest.raises(InvalidConnectorContextError):
        context(accepted_locales=["pt-BR"])


def test_context_rejects_incompatible_credential_and_cancellation_protocols() -> None:
    with pytest.raises(InvalidConnectorContextError):
        context(credential_handle=object())
    with pytest.raises(InvalidConnectorContextError):
        context(cancellation_signal=object())
