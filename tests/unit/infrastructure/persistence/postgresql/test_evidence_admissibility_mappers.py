"""Strict F5.3 admissibility relational mapper tests."""

import pytest

from intelligence.evidence.errors import EvidenceAdmissibilityIntegrityError
from intelligence.infrastructure.persistence.postgresql.evidence_admissibility_mappers import (
    evidence_admissibility_decision_from_values,
    evidence_admissibility_decision_to_values,
)
from tests.unit.evidence.test_evidence_admissibility import _decision


def test_decision_mapper_round_trips_initial_and_predecessor() -> None:
    first = _decision()
    second = _decision(sequence=2, predecessor=first.id)
    assert (
        evidence_admissibility_decision_from_values(
            evidence_admissibility_decision_to_values(first)
        )
        == first
    )
    assert (
        evidence_admissibility_decision_from_values(
            evidence_admissibility_decision_to_values(second)
        )
        == second
    )


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("policy_id", "F5_3_OTHER_POLICY_V1"),
        ("policy_version", 2),
        ("controlled_trust_root_digest", "0" * 64),
        ("purpose", "UNKNOWN"),
        ("admission_basis", "UNKNOWN"),
    ],
)
def test_mapper_rejects_noncanonical_policy_snapshot(field: str, invalid: object) -> None:
    values = evidence_admissibility_decision_to_values(_decision())
    values[field] = invalid
    with pytest.raises((EvidenceAdmissibilityIntegrityError, ValueError, TypeError)):
        evidence_admissibility_decision_from_values(values)


def test_mapper_rejects_missing_wrong_optional_and_boolean_integer_fields() -> None:
    values = evidence_admissibility_decision_to_values(_decision())
    del values["id"]
    with pytest.raises(ValueError):
        evidence_admissibility_decision_from_values(values)
    values = evidence_admissibility_decision_to_values(_decision())
    values["valid_until"] = "not-a-datetime"
    with pytest.raises(ValueError):
        evidence_admissibility_decision_from_values(values)
    values = evidence_admissibility_decision_to_values(_decision())
    values["schema_version"] = True
    with pytest.raises(ValueError):
        evidence_admissibility_decision_from_values(values)
