"""Fail-closed validation edges for F5.2 Claim reconstitution contracts."""

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import cast

import pytest

from intelligence.claims.errors import ClaimHistoryError, ClaimIntegrityError
from intelligence.claims.models import (
    CLAIM_LINK_SCHEMA_VERSION,
    CLAIM_SCHEMA_VERSION,
    ClaimCorrectionReason,
    ClaimCreationMethod,
    ClaimCriticality,
    ClaimEvidencePurpose,
    ClaimEvidenceRole,
    ClaimEvidenceUseDecision,
    ClaimEvidenceUseOutcome,
    ClaimEvidenceUseReason,
    ClaimHistory,
    ClaimPredicate,
    ClaimTemporal,
    ClaimValue,
    CountryCodeClaimValue,
    DateClaimValue,
    PeriodClaimTemporal,
    PointClaimTemporal,
    RegistrationIdentifierClaimValue,
    RegistrationStatus,
    RegistrationStatusClaimValue,
    TemporalAbsenceReason,
    TextClaimValue,
    UndatedClaimTemporal,
    claim_temporal_from_snapshot,
    claim_temporal_to_snapshot,
    claim_value_from_snapshot,
    claim_value_to_snapshot,
)
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import ClaimId, UserId, WorkspaceId
from tests.claims.synthetic_fixtures import FIXED_TIME
from tests.claims.test_claim_models import _claim, _decision, _link


@pytest.mark.parametrize(
    "factory",
    [
        lambda: RegistrationStatusClaimValue(cast(RegistrationStatus, "ACTIVE")),
        lambda: DateClaimValue(cast(date, datetime(2026, 8, 21, tzinfo=UTC))),
        lambda: CountryCodeClaimValue(cast(CountryCode, "BR")),
        lambda: RegistrationIdentifierClaimValue("SYNTHETIC_ID", "value", cast(CountryCode, "BR")),
        lambda: UndatedClaimTemporal(cast(TemporalAbsenceReason, "NOT_PROVIDED")),
    ],
)
def test_typed_value_and_temporal_constructors_reject_structural_lookalikes(
    factory: Callable[[], object],
) -> None:
    with pytest.raises(InvariantViolationError):
        factory()


def test_use_decision_rejects_invalid_types_metadata_and_reason_pairing() -> None:
    decision = _decision(ClaimEvidenceUseOutcome.ELIGIBLE)
    invalid: tuple[Callable[[], object], ...] = (
        lambda: replace(decision, outcome=cast(ClaimEvidenceUseOutcome, "ELIGIBLE")),
        lambda: replace(
            decision,
            reason_code=cast(ClaimEvidenceUseReason, "CONTROLLED_EVIDENCE_ELIGIBLE"),
        ),
        lambda: replace(
            decision,
            reason_code=ClaimEvidenceUseReason.CONTROLLED_CORPUS_NOT_PROVEN,
        ),
        lambda: replace(decision, policy_id="unsafe policy"),
        lambda: replace(decision, policy_version=0),
        lambda: replace(
            decision,
            purpose=cast(ClaimEvidencePurpose, "INTERNAL_CLAIM_VERIFICATION"),
        ),
        lambda: replace(decision, controlled_corpus_manifest_version=0),
        lambda: replace(decision, controlled_corpus_manifest_digest="invalid"),
        lambda: replace(decision, requested_by=cast(UserId, "user")),
    )
    for build_invalid in invalid:
        with pytest.raises(InvariantViolationError):
            build_invalid()


def test_claim_rejects_invalid_version_shape_vocabulary_and_schema() -> None:
    first = _claim()
    second = _claim(version=2, previous=first)
    invalid_first: tuple[Callable[[], object], ...] = (
        lambda: replace(first, series_id=ClaimId.new()),
        lambda: replace(first, correction_reason=ClaimCorrectionReason.VALUE_CORRECTION),
        lambda: replace(first, predicate_code=cast(ClaimPredicate, "LEGAL_NAME")),
        lambda: replace(first, predicate_version=2),
        lambda: replace(first, temporal=cast(ClaimTemporal, "undated")),
        lambda: replace(first, criticality=cast(ClaimCriticality, "STANDARD")),
        lambda: replace(first, creation_method=cast(ClaimCreationMethod, "MANUAL")),
        lambda: replace(first, creation_method_version=0),
        lambda: replace(first, schema_version=CLAIM_SCHEMA_VERSION + 1),
        lambda: replace(first, workspace_id=cast(WorkspaceId, "workspace")),
    )
    for build_invalid in invalid_first:
        with pytest.raises(InvariantViolationError):
            build_invalid()
    invalid_second: tuple[Callable[[], object], ...] = (
        lambda: replace(second, supersedes_claim_id=None),
        lambda: replace(
            second,
            correction_reason=cast(ClaimCorrectionReason, "VALUE_CORRECTION"),
        ),
        lambda: replace(second, supersedes_claim_id=second.id),
    )
    for build_invalid in invalid_second:
        with pytest.raises(InvariantViolationError):
            build_invalid()


def test_link_and_history_reject_unknown_scope_schema_and_ordering() -> None:
    first = _claim()
    second = _claim(version=2, previous=first)
    first_link = _link(first, ClaimEvidenceRole.SUPPORTS, ClaimEvidenceUseOutcome.ELIGIBLE)
    second_link = _link(second, ClaimEvidenceRole.SUPPORTS, ClaimEvidenceUseOutcome.ELIGIBLE)
    invalid_links: tuple[Callable[[], object], ...] = (
        lambda: replace(first_link, claim_id=cast(ClaimId, "claim")),
        lambda: replace(first_link, claim_version=0),
        lambda: replace(first_link, role=cast(ClaimEvidenceRole, "SUPPORTS")),
        lambda: replace(
            first_link,
            use_decision=cast(ClaimEvidenceUseDecision, "decision"),
        ),
        lambda: replace(first_link, schema_version=CLAIM_LINK_SCHEMA_VERSION + 1),
        lambda: replace(first_link, evidence_digest="invalid"),
    )
    for build_invalid in invalid_links:
        with pytest.raises(InvariantViolationError):
            build_invalid()

    with pytest.raises(ClaimHistoryError, match="at least one"):
        ClaimHistory((), ())

    object.__setattr__(second, "supersedes_claim_id", ClaimId.new())
    with pytest.raises(ClaimHistoryError, match="supersession"):
        ClaimHistory((first, second), (first_link, second_link))
    object.__setattr__(second, "supersedes_claim_id", first.id)
    object.__setattr__(second, "created_at", first.created_at - timedelta(seconds=1))
    with pytest.raises(ClaimHistoryError, match="regressive"):
        ClaimHistory((first, second), (first_link, second_link))
    object.__setattr__(second, "created_at", first.created_at)
    object.__setattr__(second_link, "claim_id", ClaimId.new())
    with pytest.raises(ClaimHistoryError, match="unknown"):
        ClaimHistory((first, second), (first_link, second_link))
    object.__setattr__(second_link, "claim_id", second.id)
    object.__setattr__(second_link, "workspace_id", WorkspaceId.new())
    with pytest.raises(ClaimHistoryError, match="scope"):
        ClaimHistory((first, second), (first_link, second_link))


def test_all_snapshots_round_trip_and_malformed_snapshots_fail_closed() -> None:
    values: tuple[ClaimValue, ...] = (
        TextClaimValue("Synthetic"),
        RegistrationStatusClaimValue(RegistrationStatus.ACTIVE),
        DateClaimValue(date(2020, 1, 15)),
        CountryCodeClaimValue(CountryCode("BR")),
        RegistrationIdentifierClaimValue("SYNTHETIC_ID", "TEST-1", CountryCode("BR")),
    )
    for value in values:
        value_type, snapshot = claim_value_to_snapshot(value)
        assert claim_value_from_snapshot(value_type, snapshot) == value
    temporals: tuple[ClaimTemporal, ...] = (
        PointClaimTemporal(FIXED_TIME),
        PeriodClaimTemporal(FIXED_TIME, FIXED_TIME + timedelta(days=1)),
        UndatedClaimTemporal(TemporalAbsenceReason.NOT_APPLICABLE),
    )
    for temporal in temporals:
        temporal_type, snapshot = claim_temporal_to_snapshot(temporal)
        assert claim_temporal_from_snapshot(temporal_type, snapshot) == temporal

    with pytest.raises(InvariantViolationError, match="unsupported"):
        claim_value_to_snapshot(cast(ClaimValue, object()))
    with pytest.raises(InvariantViolationError, match="unsupported"):
        claim_temporal_to_snapshot(cast(ClaimTemporal, object()))
    with pytest.raises(ClaimIntegrityError):
        claim_value_from_snapshot("UNKNOWN", {})
    with pytest.raises(ClaimIntegrityError):
        claim_value_from_snapshot("DATE", {"value": "not-a-date"})
    with pytest.raises(ClaimIntegrityError):
        claim_temporal_from_snapshot("UNKNOWN", {})
    with pytest.raises(ClaimIntegrityError):
        claim_temporal_from_snapshot("POINT", {"occurred_at": "not-a-datetime"})


@pytest.mark.parametrize(
    ("value_type", "snapshot"),
    [
        ("TEXT", {"value": 123}),
        ("TEXT", {"value": True}),
        ("TEXT", {"value": None}),
        ("TEXT", {"value": "123", "unexpected": "payload"}),
        ("REGISTRATION_STATUS", {"status": 1}),
        ("REGISTRATION_STATUS", {"status": True}),
        ("REGISTRATION_STATUS", {"status": None}),
        ("REGISTRATION_STATUS", {"status": "ACTIVE", "unexpected": "payload"}),
        ("REGISTRATION_STATUS", {}),
        ("DATE", {"value": 20200115}),
        ("DATE", {"value": True}),
        ("DATE", {"value": None}),
        ("DATE", {"value": "2020-01-15", "unexpected": "payload"}),
        ("DATE", {"value": "20200115"}),
        ("COUNTRY_CODE", {"country": 1}),
        ("COUNTRY_CODE", {"country": True}),
        ("COUNTRY_CODE", {"country": None}),
        ("COUNTRY_CODE", {"country": "BR", "unexpected": "payload"}),
        ("COUNTRY_CODE", {}),
        (
            "REGISTRATION_IDENTIFIER",
            {"identifier_type": 1, "original_value": "TEST-1", "jurisdiction": "BR"},
        ),
        (
            "REGISTRATION_IDENTIFIER",
            {"identifier_type": "SYNTHETIC_ID", "original_value": 1, "jurisdiction": "BR"},
        ),
        (
            "REGISTRATION_IDENTIFIER",
            {"identifier_type": "SYNTHETIC_ID", "original_value": "TEST-1", "jurisdiction": 1},
        ),
        (
            "REGISTRATION_IDENTIFIER",
            {
                "identifier_type": "SYNTHETIC_ID",
                "original_value": "TEST-1",
                "jurisdiction": "BR",
                "unexpected": "payload",
            },
        ),
        (
            "REGISTRATION_IDENTIFIER",
            {"original_value": "TEST-1", "jurisdiction": "BR"},
        ),
        (
            "REGISTRATION_IDENTIFIER",
            {"identifier_type": "SYNTHETIC_ID", "jurisdiction": "BR"},
        ),
        (
            "REGISTRATION_IDENTIFIER",
            {"identifier_type": "SYNTHETIC_ID", "original_value": "TEST-1"},
        ),
    ],
)
def test_claim_value_snapshots_reject_noncanonical_json(
    value_type: str, snapshot: dict[str, object]
) -> None:
    with pytest.raises(ClaimIntegrityError):
        claim_value_from_snapshot(value_type, snapshot)


@pytest.mark.parametrize(
    ("temporal_type", "snapshot"),
    [
        ("POINT", {"occurred_at": 1}),
        ("POINT", {"occurred_at": True}),
        ("POINT", {"occurred_at": None}),
        ("POINT", {"occurred_at": FIXED_TIME.isoformat(), "unexpected": "payload"}),
        ("POINT", {}),
        ("POINT", {"occurred_at": "2026-08-21T12:00:00Z"}),
        ("PERIOD", {"valid_from": 1, "valid_until": FIXED_TIME.isoformat()}),
        ("PERIOD", {"valid_from": FIXED_TIME.isoformat(), "valid_until": True}),
        ("PERIOD", {"valid_from": FIXED_TIME.isoformat()}),
        ("PERIOD", {"valid_until": FIXED_TIME.isoformat()}),
        (
            "PERIOD",
            {
                "valid_from": FIXED_TIME.isoformat(),
                "valid_until": (FIXED_TIME + timedelta(days=1)).isoformat(),
                "unexpected": "payload",
            },
        ),
        ("UNDATED", {"reason": 1}),
        ("UNDATED", {"reason": True}),
        ("UNDATED", {"reason": None}),
        ("UNDATED", {"reason": "NOT_APPLICABLE", "unexpected": "payload"}),
        ("UNDATED", {}),
    ],
)
def test_claim_temporal_snapshots_reject_noncanonical_json(
    temporal_type: str, snapshot: dict[str, object]
) -> None:
    with pytest.raises(ClaimIntegrityError):
        claim_temporal_from_snapshot(temporal_type, snapshot)


def test_rejected_decision_uses_only_explicit_prohibition_reason() -> None:
    eligible = _decision(ClaimEvidenceUseOutcome.ELIGIBLE)
    rejected = replace(
        eligible,
        outcome=ClaimEvidenceUseOutcome.REJECTED,
        reason_code=ClaimEvidenceUseReason.USE_EXPLICITLY_PROHIBITED,
    )
    assert rejected.outcome is ClaimEvidenceUseOutcome.REJECTED
