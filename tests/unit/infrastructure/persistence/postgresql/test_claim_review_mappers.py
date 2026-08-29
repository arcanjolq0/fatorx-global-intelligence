"""Fail-closed F5.4 Claim-review relational mapper tests."""

import pytest

from intelligence.infrastructure.persistence.postgresql.claim_review_mappers import (
    claim_review_decision_from_values,
    claim_review_decision_to_values,
)
from tests.unit.application.test_claim_review_service import _command, _setup


def _values() -> dict[str, object]:
    _creator, reviewer, _factory, reviews, claim, _admitted = _setup()
    return claim_review_decision_to_values(reviews.decide(reviewer, _command(claim)).history.latest)


def test_mapper_round_trip_and_rejects_invalid_persisted_values() -> None:
    values = _values()
    assert claim_review_decision_from_values(values).decision_digest == values["decision_digest"]
    for field, invalid in (
        ("supersedes_decision_id", "not-a-uuid"),
        ("outcome", "UNKNOWN"),
        ("claim_version", True),
        ("decided_at", "not-a-datetime"),
    ):
        corrupted = dict(values)
        corrupted[field] = invalid
        with pytest.raises(ValueError, match=r"Persisted Claim-review field|UNKNOWN"):
            claim_review_decision_from_values(corrupted)
