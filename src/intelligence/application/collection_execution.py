"""Typed F4.6 direct execution ownership and redacted completion receipts."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256

from intelligence.application.actor_context import ActorContext
from intelligence.connectors.context import LocaleTag
from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.execution.contracts import (
    ConnectorExecutionControlCode,
    ConnectorExecutionIdempotencyStatus,
    ConnectorExecutionItem,
    ConnectorExecutionResult,
)
from intelligence.connectors.execution.errors import ConnectorExecutionError
from intelligence.connectors.execution.policies import ConnectorExecutionPolicy
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.versions import SemanticVersion, SourcePolicyVersion
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import (
    CollectionOperationId,
    CollectionRunId,
    InvestigationCommandId,
    InvestigationId,
    UserId,
    WorkspaceId,
)
from intelligence.domain.money import Money
from intelligence.domain.time import normalize_utc

COLLECTION_EXECUTION_SCHEMA_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class ExecuteCollectionSearchOperation:
    """Execute one manifest SEARCH operation without accepting connector payload data."""

    command_id: InvestigationCommandId
    collection_run_id: CollectionRunId
    collection_operation_id: CollectionOperationId
    expected_run_digest: str
    expected_operation_digest: str
    source_policy_version: SourcePolicyVersion
    accepted_locales: tuple[LocaleTag, ...]
    execution_policy: ConnectorExecutionPolicy = field(repr=False)
    schema_version: int = COLLECTION_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed = (
            (self.command_id, InvestigationCommandId),
            (self.collection_run_id, CollectionRunId),
            (self.collection_operation_id, CollectionOperationId),
            (self.source_policy_version, SourcePolicyVersion),
            (self.execution_policy, ConnectorExecutionPolicy),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise InvariantViolationError("Collection execution command metadata is invalid.")
        _digest(self.expected_run_digest, "expected run")
        _digest(self.expected_operation_digest, "expected operation")
        if (
            not isinstance(self.accepted_locales, tuple)
            or not self.accepted_locales
            or any(not isinstance(locale, LocaleTag) for locale in self.accepted_locales)
            or len(set(self.accepted_locales)) != len(self.accepted_locales)
        ):
            raise InvariantViolationError("Collection execution locales are invalid.")
        if self.schema_version != COLLECTION_EXECUTION_SCHEMA_VERSION:
            raise InvariantViolationError("Collection execution command schema is unsupported.")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CollectionExecutionOwnership:
    """Immutable durable ownership record created before connector I/O."""

    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    collection_run_id: CollectionRunId
    collection_operation_id: CollectionOperationId
    command_id: InvestigationCommandId
    command_digest: str
    actor_user_id: UserId
    connector_id: ConnectorId
    connector_version: SemanticVersion
    contract_version: SemanticVersion
    source_id: SourceId
    source_policy_version: SourcePolicyVersion
    accepted_locales: tuple[LocaleTag, ...]
    execution_policy_snapshot: str = field(repr=False)
    execution_policy_digest: str
    started_at: datetime
    ownership_digest: str
    schema_version: int = COLLECTION_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed = (
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.collection_run_id, CollectionRunId),
            (self.collection_operation_id, CollectionOperationId),
            (self.command_id, InvestigationCommandId),
            (self.actor_user_id, UserId),
            (self.connector_id, ConnectorId),
            (self.connector_version, SemanticVersion),
            (self.contract_version, SemanticVersion),
            (self.source_id, SourceId),
            (self.source_policy_version, SourcePolicyVersion),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise InvariantViolationError("Collection execution ownership metadata is invalid.")
        if (
            not isinstance(self.accepted_locales, tuple)
            or not self.accepted_locales
            or any(not isinstance(locale, LocaleTag) for locale in self.accepted_locales)
            or len(set(self.accepted_locales)) != len(self.accepted_locales)
        ):
            raise InvariantViolationError("Collection execution ownership locales are invalid.")
        for value, name in (
            (self.command_digest, "command"),
            (self.execution_policy_digest, "execution policy"),
            (self.ownership_digest, "ownership"),
        ):
            _digest(value, name)
        policy = execution_policy_from_snapshot(self.execution_policy_snapshot)
        if execution_policy_digest(policy) != self.execution_policy_digest:
            raise InvariantViolationError("Collection execution policy snapshot is inconsistent.")
        object.__setattr__(self, "started_at", normalize_utc(self.started_at))
        if self.schema_version != COLLECTION_EXECUTION_SCHEMA_VERSION:
            raise InvariantViolationError("Collection execution ownership schema is unsupported.")
        if self.ownership_digest != collection_execution_ownership_digest(self):
            raise InvariantViolationError("Collection execution ownership digest is inconsistent.")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CollectionExecutionResultRecord:
    """Append-only redacted completion; connector items are deliberately absent."""

    workspace_id: WorkspaceId
    investigation_id: InvestigationId
    collection_run_id: CollectionRunId
    collection_operation_id: CollectionOperationId
    command_id: InvestigationCommandId
    command_digest: str
    outcome_status: ConnectorOutcomeStatus
    error_code: ConnectorErrorCode | None
    warning_codes: tuple[ConnectorWarningCode, ...]
    attempts_started: int
    usage_calls: int
    usage_bytes_received: int
    usage_duration_microseconds: int
    usage_cost: Money | None
    usage_cost_kind: UsageCostKind | None
    request_fingerprint: str
    execution_digest: str
    idempotency_status: ConnectorExecutionIdempotencyStatus
    control_code: ConnectorExecutionControlCode | None
    completed_at: datetime
    result_digest: str
    schema_version: int = COLLECTION_EXECUTION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        typed = (
            (self.workspace_id, WorkspaceId),
            (self.investigation_id, InvestigationId),
            (self.collection_run_id, CollectionRunId),
            (self.collection_operation_id, CollectionOperationId),
            (self.command_id, InvestigationCommandId),
            (self.outcome_status, ConnectorOutcomeStatus),
            (self.idempotency_status, ConnectorExecutionIdempotencyStatus),
        )
        if any(not isinstance(value, expected) for value, expected in typed):
            raise InvariantViolationError("Collection execution result metadata is invalid.")
        if self.error_code is not None and not isinstance(self.error_code, ConnectorErrorCode):
            raise InvariantViolationError("Collection execution error code is invalid.")
        if self.control_code is not None and not isinstance(
            self.control_code, ConnectorExecutionControlCode
        ):
            raise InvariantViolationError("Collection execution control code is invalid.")
        if (
            not isinstance(self.warning_codes, tuple)
            or tuple(sorted(set(self.warning_codes), key=lambda item: item.value))
            != self.warning_codes
        ):
            raise InvariantViolationError("Collection execution warning codes are not canonical.")
        for count, name in (
            (self.attempts_started, "attempt count"),
            (self.usage_calls, "usage calls"),
            (self.usage_bytes_received, "usage bytes"),
            (self.usage_duration_microseconds, "usage duration"),
        ):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise InvariantViolationError(f"Collection execution {name} is invalid.")
        if (self.usage_cost is None) != (self.usage_cost_kind is None):
            raise InvariantViolationError("Collection execution cost metadata is incomplete.")
        if self.usage_cost is not None and (
            not isinstance(self.usage_cost, Money) or self.usage_cost.amount < 0
        ):
            raise InvariantViolationError("Collection execution cost is invalid.")
        for digest_value, name in (
            (self.command_digest, "command"),
            (self.request_fingerprint, "request fingerprint"),
            (self.execution_digest, "execution"),
            (self.result_digest, "result"),
        ):
            _digest(digest_value, name)
        object.__setattr__(self, "completed_at", normalize_utc(self.completed_at))
        if self.schema_version != COLLECTION_EXECUTION_SCHEMA_VERSION:
            raise InvariantViolationError("Collection execution result schema is unsupported.")
        if self.result_digest != collection_execution_result_digest(self):
            raise InvariantViolationError("Collection execution result digest is inconsistent.")

    @property
    def is_usable(self) -> bool:
        return self.outcome_status in {
            ConnectorOutcomeStatus.SUCCEEDED,
            ConnectorOutcomeStatus.NO_RESULTS,
            ConnectorOutcomeStatus.PARTIAL,
        }


def digest_execute_collection_command(
    actor: ActorContext, command: ExecuteCollectionSearchOperation
) -> str:
    if not isinstance(actor, ActorContext) or not isinstance(
        command, ExecuteCollectionSearchOperation
    ):
        raise TypeError("Collection execution digest requires typed inputs.")
    return _json_digest(
        {
            "accepted_locales": [locale.value for locale in command.accepted_locales],
            "actor_user_id": str(actor.user_id),
            "collection_operation_id": str(command.collection_operation_id),
            "collection_run_id": str(command.collection_run_id),
            "expected_operation_digest": command.expected_operation_digest,
            "expected_run_digest": command.expected_run_digest,
            "execution_policy": execution_policy_object(command.execution_policy),
            "schema_version": command.schema_version,
            "source_policy_version": str(command.source_policy_version),
            "workspace_id": str(actor.workspace_id),
        }
    )


def build_collection_execution_ownership(
    *,
    actor: ActorContext,
    investigation_id: InvestigationId,
    command: ExecuteCollectionSearchOperation,
    connector_id: ConnectorId,
    connector_version: SemanticVersion,
    contract_version: SemanticVersion,
    source_id: SourceId,
    started_at: datetime,
) -> CollectionExecutionOwnership:
    snapshot = execution_policy_snapshot(command.execution_policy)
    values: dict[str, object] = {
        "workspace_id": actor.workspace_id,
        "investigation_id": investigation_id,
        "collection_run_id": command.collection_run_id,
        "collection_operation_id": command.collection_operation_id,
        "command_id": command.command_id,
        "command_digest": digest_execute_collection_command(actor, command),
        "actor_user_id": actor.user_id,
        "connector_id": connector_id,
        "connector_version": connector_version,
        "contract_version": contract_version,
        "source_id": source_id,
        "source_policy_version": command.source_policy_version,
        "accepted_locales": command.accepted_locales,
        "execution_policy_snapshot": snapshot,
        "execution_policy_digest": _text_digest(snapshot),
        "started_at": normalize_utc(started_at),
        "schema_version": COLLECTION_EXECUTION_SCHEMA_VERSION,
    }
    return CollectionExecutionOwnership(
        ownership_digest=_ownership_digest_from_values(values),
        **values,  # type: ignore[arg-type]
    )


def build_collection_execution_result(
    *,
    ownership: CollectionExecutionOwnership,
    execution: ConnectorExecutionResult[ConnectorExecutionItem],
    completed_at: datetime,
) -> CollectionExecutionResultRecord:
    error_code = execution.outcome.error.code if execution.outcome.error is not None else None
    warning_codes = tuple(
        sorted({item.code for item in execution.outcome.warnings}, key=lambda x: x.value)
    )
    usage = execution.total_usage
    values: dict[str, object] = {
        "workspace_id": ownership.workspace_id,
        "investigation_id": ownership.investigation_id,
        "collection_run_id": ownership.collection_run_id,
        "collection_operation_id": ownership.collection_operation_id,
        "command_id": ownership.command_id,
        "command_digest": ownership.command_digest,
        "outcome_status": execution.outcome.status,
        "error_code": error_code,
        "warning_codes": warning_codes,
        "attempts_started": execution.attempts_started,
        "usage_calls": usage.calls,
        "usage_bytes_received": usage.bytes_received,
        "usage_duration_microseconds": _timedelta_microseconds(usage.duration),
        "usage_cost": usage.cost,
        "usage_cost_kind": usage.cost_kind,
        "request_fingerprint": execution.fingerprint,
        "execution_digest": execution.digest,
        "idempotency_status": execution.idempotency_status,
        "control_code": execution.control_code,
        "completed_at": normalize_utc(completed_at),
        "schema_version": COLLECTION_EXECUTION_SCHEMA_VERSION,
    }
    return CollectionExecutionResultRecord(
        result_digest=_result_digest_from_values(values),
        **values,  # type: ignore[arg-type]
    )


def validate_collection_execution_history(
    ownership: CollectionExecutionOwnership, result: CollectionExecutionResultRecord
) -> None:
    if (
        ownership.workspace_id != result.workspace_id
        or ownership.investigation_id != result.investigation_id
        or ownership.collection_run_id != result.collection_run_id
        or ownership.collection_operation_id != result.collection_operation_id
        or ownership.command_id != result.command_id
        or ownership.command_digest != result.command_digest
        or result.completed_at < ownership.started_at
    ):
        raise InvariantViolationError("Collection execution history is inconsistent.")


def execution_policy_object(policy: ConnectorExecutionPolicy) -> dict[str, object]:
    return {
        "base_backoff_microseconds": _timedelta_microseconds(policy.base_backoff),
        "estimated_attempt_cost": _money_object(policy.estimated_attempt_cost),
        "max_artifacts": policy.max_artifacts,
        "max_attempts": policy.max_attempts,
        "max_backoff_microseconds": _timedelta_microseconds(policy.max_backoff),
        "max_items": policy.max_items,
        "max_jitter_microseconds": _timedelta_microseconds(policy.max_jitter),
        "retriable_codes": sorted(code.value for code in policy.retriable_codes),
        "version": policy.version.value,
    }


def execution_policy_snapshot(policy: ConnectorExecutionPolicy) -> str:
    return json.dumps(execution_policy_object(policy), sort_keys=True, separators=(",", ":"))


def execution_policy_from_snapshot(snapshot: str) -> ConnectorExecutionPolicy:
    from intelligence.connectors.execution.policies import ConnectorExecutionPolicyVersion
    from intelligence.domain.money import CurrencyCode

    try:
        raw = json.loads(snapshot)
        cost_raw = raw["estimated_attempt_cost"]
        cost = (
            Money(Decimal(cost_raw["amount"]), CurrencyCode(cost_raw["currency"]))
            if cost_raw is not None
            else None
        )
        policy = ConnectorExecutionPolicy(
            version=ConnectorExecutionPolicyVersion(raw["version"]),
            max_attempts=raw["max_attempts"],
            retriable_codes=(ConnectorErrorCode(value) for value in raw["retriable_codes"]),
            base_backoff=timedelta(microseconds=raw["base_backoff_microseconds"]),
            max_backoff=timedelta(microseconds=raw["max_backoff_microseconds"]),
            max_jitter=timedelta(microseconds=raw["max_jitter_microseconds"]),
            estimated_attempt_cost=cost,
            max_items=raw["max_items"],
            max_artifacts=raw["max_artifacts"],
        )
    except (
        KeyError,
        TypeError,
        ValueError,
        InvariantViolationError,
        ConnectorExecutionError,
    ) as error:
        raise InvariantViolationError(
            "Persisted collection execution policy is invalid."
        ) from error
    if execution_policy_snapshot(policy) != snapshot:
        raise InvariantViolationError("Persisted collection execution policy is not canonical.")
    return policy


def execution_policy_digest(policy: ConnectorExecutionPolicy) -> str:
    return _text_digest(execution_policy_snapshot(policy))


def collection_execution_ownership_digest(ownership: CollectionExecutionOwnership) -> str:
    values = {
        name: getattr(ownership, name)
        for name in CollectionExecutionOwnership.__dataclass_fields__
        if name != "ownership_digest"
    }
    return _ownership_digest_from_values(values)


def collection_execution_result_digest(result: CollectionExecutionResultRecord) -> str:
    values = {
        name: getattr(result, name)
        for name in CollectionExecutionResultRecord.__dataclass_fields__
        if name != "result_digest"
    }
    return _result_digest_from_values(values)


def _ownership_digest_from_values(values: dict[str, object]) -> str:
    return _json_digest(_canonical(values))


def _result_digest_from_values(values: dict[str, object]) -> str:
    return _json_digest(_canonical(values))


def _canonical(values: dict[str, object]) -> dict[str, object]:
    canonical: dict[str, object] = {}
    for key, value in values.items():
        if isinstance(value, datetime):
            canonical[key] = normalize_utc(value).isoformat()
        elif isinstance(value, Money):
            canonical[key] = _money_object(value)
        elif isinstance(value, SemanticVersion):
            canonical[key] = str(value)
        elif isinstance(value, tuple):
            canonical[key] = [getattr(item, "value", item) for item in value]
        elif hasattr(value, "value"):
            canonical[key] = str(value)
        else:
            canonical[key] = value
    return canonical


def _money_object(value: Money | None) -> dict[str, str] | None:
    return (
        {"amount": str(value.amount), "currency": value.currency.value}
        if value is not None
        else None
    )


def _timedelta_microseconds(value: timedelta) -> int:
    return ((value.days * 86400 + value.seconds) * 1_000_000) + value.microseconds


def _json_digest(value: object) -> str:
    return _text_digest(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def _text_digest(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _digest(value: str, name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"Collection execution {name} digest is invalid.")


__all__ = [
    "COLLECTION_EXECUTION_SCHEMA_VERSION",
    "CollectionExecutionOwnership",
    "CollectionExecutionResultRecord",
    "ExecuteCollectionSearchOperation",
    "build_collection_execution_ownership",
    "build_collection_execution_result",
    "collection_execution_ownership_digest",
    "collection_execution_result_digest",
    "digest_execute_collection_command",
    "execution_policy_digest",
    "execution_policy_from_snapshot",
    "execution_policy_snapshot",
    "validate_collection_execution_history",
]
