"""Immutable, serializable policy for deterministic identity matching."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha256
from typing import cast

from intelligence.entity_resolution.errors import InvalidMatchingPolicyError

BASIS_POINTS_MAX = 10_000
MATCH_POLICY_SCHEMA_VERSION = 1
NAME_NORMALIZATION_V1 = "NAME_NORMALIZATION_V1"
SUPPORTED_NAME_NORMALIZATION_VERSIONS = frozenset({NAME_NORMALIZATION_V1})
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}", flags=re.ASCII)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class MatchDimension(StrEnum):
    """Closed, independently explainable matching dimensions."""

    IDENTIFIER = "IDENTIFIER"
    NAME = "NAME"
    DOMAIN = "DOMAIN"
    GEOGRAPHY = "GEOGRAPHY"
    ADDRESS = "ADDRESS"
    ADMINISTRATORS = "ADMINISTRATORS"
    TEMPORAL = "TEMPORAL"


class MatchClassification(StrEnum):
    """Review classification; no value confirms an entity in F4.2."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    EXCLUDED = "EXCLUDED"


class HardConflictRule(StrEnum):
    """Versioned strong-conflict rules supported by policy schema 1."""

    COMPARABLE_IDENTIFIER_MISMATCH = "COMPARABLE_IDENTIFIER_MISMATCH"
    COUNTRY_MISMATCH = "COUNTRY_MISMATCH"


class MatchExplanationCode(StrEnum):
    """Closed explanations persisted for every dimensional score."""

    IDENTIFIER_EXACT = "IDENTIFIER_EXACT"
    IDENTIFIER_CONFLICT = "IDENTIFIER_CONFLICT"
    IDENTIFIER_UNAVAILABLE = "IDENTIFIER_UNAVAILABLE"
    NAME_LEGAL_EXACT = "NAME_LEGAL_EXACT"
    NAME_TRADE_EXACT = "NAME_TRADE_EXACT"
    NAME_CROSS_EXACT = "NAME_CROSS_EXACT"
    NAME_TOKENS_EQUIVALENT = "NAME_TOKENS_EQUIVALENT"
    NAME_DIFFERENT = "NAME_DIFFERENT"
    NAME_UNAVAILABLE = "NAME_UNAVAILABLE"
    DOMAIN_EXACT = "DOMAIN_EXACT"
    DOMAIN_DIFFERENT = "DOMAIN_DIFFERENT"
    DOMAIN_UNAVAILABLE = "DOMAIN_UNAVAILABLE"
    GEOGRAPHY_EXACT = "GEOGRAPHY_EXACT"
    GEOGRAPHY_CONFLICT = "GEOGRAPHY_CONFLICT"
    ADDRESS_EXACT = "ADDRESS_EXACT"
    ADDRESS_PARTIAL = "ADDRESS_PARTIAL"
    ADDRESS_DIFFERENT = "ADDRESS_DIFFERENT"
    ADDRESS_UNAVAILABLE = "ADDRESS_UNAVAILABLE"
    ADMINISTRATORS_EXACT = "ADMINISTRATORS_EXACT"
    ADMINISTRATORS_PARTIAL = "ADMINISTRATORS_PARTIAL"
    ADMINISTRATORS_DIFFERENT = "ADMINISTRATORS_DIFFERENT"
    ADMINISTRATORS_UNAVAILABLE = "ADMINISTRATORS_UNAVAILABLE"
    TEMPORAL_EXACT = "TEMPORAL_EXACT"
    TEMPORAL_DIFFERENT = "TEMPORAL_DIFFERENT"
    TEMPORAL_UNAVAILABLE = "TEMPORAL_UNAVAILABLE"


@dataclass(frozen=True, slots=True, kw_only=True)
class DimensionWeight:
    """One integer basis-point weight for a closed dimension."""

    dimension: MatchDimension
    basis_points: int

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, MatchDimension):
            raise InvalidMatchingPolicyError("Matching dimension must use the closed vocabulary.")
        _basis_points(self.basis_points, field_name="dimension weight")


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class MatchPolicy:
    """Exact policy snapshot required to reproduce one candidate evaluation."""

    policy_id: str
    version: int
    normalization_version: str
    weights: tuple[DimensionWeight, ...]
    high_threshold: int
    medium_threshold: int
    hard_conflict_rules: frozenset[HardConflictRule]
    schema_version: int = MATCH_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != MATCH_POLICY_SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise InvalidMatchingPolicyError("Matching policy schema version is unsupported.")
        _code(self.policy_id, field_name="policy_id")
        _positive_integer(self.version, field_name="policy version")
        _code(self.normalization_version, field_name="normalization_version")
        if self.normalization_version not in SUPPORTED_NAME_NORMALIZATION_VERSIONS:
            raise InvalidMatchingPolicyError(
                "Matching policy normalization version is unsupported."
            )
        if not isinstance(self.weights, tuple) or any(
            not isinstance(weight, DimensionWeight) for weight in self.weights
        ):
            raise InvalidMatchingPolicyError("Matching policy weights must be an immutable tuple.")
        dimensions = tuple(weight.dimension for weight in self.weights)
        if len(dimensions) != len(MatchDimension) or set(dimensions) != set(MatchDimension):
            raise InvalidMatchingPolicyError("Matching policy must weight every dimension once.")
        if sum(weight.basis_points for weight in self.weights) != BASIS_POINTS_MAX:
            raise InvalidMatchingPolicyError("Matching policy weights must total 10,000.")
        _basis_points(self.high_threshold, field_name="high threshold")
        _basis_points(self.medium_threshold, field_name="medium threshold")
        if self.medium_threshold >= self.high_threshold:
            raise InvalidMatchingPolicyError("Matching thresholds must be strictly ordered.")
        if not isinstance(self.hard_conflict_rules, frozenset) or any(
            not isinstance(rule, HardConflictRule) for rule in self.hard_conflict_rules
        ):
            raise InvalidMatchingPolicyError("Hard-conflict rules must use a closed frozenset.")
        required_rules = frozenset(HardConflictRule)
        if self.hard_conflict_rules != required_rules:
            raise InvalidMatchingPolicyError("Policy schema 1 requires both strong-conflict rules.")
        object.__setattr__(
            self,
            "weights",
            tuple(sorted(self.weights, key=lambda item: item.dimension.value)),
        )

    def weight_for(self, dimension: MatchDimension) -> int:
        if not isinstance(dimension, MatchDimension):
            raise InvalidMatchingPolicyError("Matching dimension must use the closed vocabulary.")
        return next(weight.basis_points for weight in self.weights if weight.dimension is dimension)

    def classify(self, score: int, *, has_hard_conflict: bool) -> MatchClassification:
        _basis_points(score, field_name="total score")
        if not isinstance(has_hard_conflict, bool):
            raise InvalidMatchingPolicyError("Hard-conflict indicator must be boolean.")
        if has_hard_conflict:
            return MatchClassification.EXCLUDED
        if score >= self.high_threshold:
            return MatchClassification.HIGH
        if score >= self.medium_threshold:
            return MatchClassification.MEDIUM
        return MatchClassification.LOW

    def to_canonical_json(self) -> str:
        return json.dumps(
            self._canonical_object(),
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def from_canonical_json(cls, serialized: str) -> MatchPolicy:
        if not isinstance(serialized, str):
            raise InvalidMatchingPolicyError("Persisted matching policy must be JSON text.")
        try:
            raw = cast(object, json.loads(serialized))
        except (json.JSONDecodeError, TypeError) as error:
            raise InvalidMatchingPolicyError("Persisted matching policy is invalid.") from error
        if not isinstance(raw, dict) or set(raw) != _POLICY_KEYS:
            raise InvalidMatchingPolicyError("Persisted matching policy has unsupported fields.")
        typed = cast(dict[str, object], raw)
        weights_raw = typed["weights"]
        conflicts_raw = typed["hard_conflict_rules"]
        if not isinstance(weights_raw, list) or not isinstance(conflicts_raw, list):
            raise InvalidMatchingPolicyError("Persisted matching policy collections are invalid.")
        try:
            weights = tuple(
                DimensionWeight(
                    dimension=MatchDimension(_required_string(item, "dimension")),
                    basis_points=_required_integer(item, "basis_points"),
                )
                for item in weights_raw
            )
            result = cls(
                policy_id=_root_string(typed, "policy_id"),
                version=_root_integer(typed, "version"),
                normalization_version=_root_string(typed, "normalization_version"),
                weights=weights,
                high_threshold=_root_integer(typed, "high_threshold"),
                medium_threshold=_root_integer(typed, "medium_threshold"),
                hard_conflict_rules=frozenset(
                    HardConflictRule(_list_string(value)) for value in conflicts_raw
                ),
                schema_version=_root_integer(typed, "schema_version"),
            )
        except ValueError as error:
            raise InvalidMatchingPolicyError(
                "Persisted matching policy vocabulary is invalid."
            ) from error
        if result.to_canonical_json() != serialized:
            raise InvalidMatchingPolicyError("Persisted matching policy is not canonical.")
        return result

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return (
            "MatchPolicy("
            f"policy_id={self.policy_id!r}, version={self.version}, "
            f"normalization_version={self.normalization_version!r}, digest={self.digest!r})"
        )

    def _canonical_object(self) -> dict[str, object]:
        return {
            "hard_conflict_rules": sorted(rule.value for rule in self.hard_conflict_rules),
            "high_threshold": self.high_threshold,
            "medium_threshold": self.medium_threshold,
            "normalization_version": self.normalization_version,
            "policy_id": self.policy_id,
            "schema_version": self.schema_version,
            "version": self.version,
            "weights": [
                {"basis_points": weight.basis_points, "dimension": weight.dimension.value}
                for weight in sorted(self.weights, key=lambda item: item.dimension.value)
            ],
        }


_POLICY_KEYS = {
    "hard_conflict_rules",
    "high_threshold",
    "medium_threshold",
    "normalization_version",
    "policy_id",
    "schema_version",
    "version",
    "weights",
}


def _basis_points(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= BASIS_POINTS_MAX:
        raise InvalidMatchingPolicyError(f"Matching {field_name} must be integer basis points.")


def _positive_integer(value: int, *, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidMatchingPolicyError(f"Matching {field_name} must be a positive integer.")


def _code(value: str, *, field_name: str) -> str:
    if not isinstance(value, str) or _CODE_PATTERN.fullmatch(value) is None:
        raise InvalidMatchingPolicyError(f"Matching {field_name} has an invalid format.")
    return value


def _required_object(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != {"basis_points", "dimension"}:
        raise InvalidMatchingPolicyError("Persisted dimension weight is invalid.")
    return cast(dict[str, object], value)


def _required_string(value: object, field_name: str) -> str:
    item = _required_object(value)[field_name]
    if not isinstance(item, str):
        raise InvalidMatchingPolicyError("Persisted dimension weight type is invalid.")
    return item


def _required_integer(value: object, field_name: str) -> int:
    item = _required_object(value)[field_name]
    if isinstance(item, bool) or not isinstance(item, int):
        raise InvalidMatchingPolicyError("Persisted dimension weight type is invalid.")
    return item


def _root_string(value: dict[str, object], field_name: str) -> str:
    item = value[field_name]
    if not isinstance(item, str):
        raise InvalidMatchingPolicyError("Persisted matching policy field type is invalid.")
    return item


def _root_integer(value: dict[str, object], field_name: str) -> int:
    item = value[field_name]
    if isinstance(item, bool) or not isinstance(item, int):
        raise InvalidMatchingPolicyError("Persisted matching policy field type is invalid.")
    return item


def _list_string(value: object) -> str:
    if not isinstance(value, str):
        raise InvalidMatchingPolicyError("Persisted hard-conflict rule type is invalid.")
    return value


INITIAL_MATCH_POLICY = MatchPolicy(
    policy_id="ENTITY_MATCH_V1",
    version=1,
    normalization_version=NAME_NORMALIZATION_V1,
    weights=(
        DimensionWeight(dimension=MatchDimension.IDENTIFIER, basis_points=3_500),
        DimensionWeight(dimension=MatchDimension.NAME, basis_points=2_500),
        DimensionWeight(dimension=MatchDimension.DOMAIN, basis_points=1_200),
        DimensionWeight(dimension=MatchDimension.GEOGRAPHY, basis_points=1_000),
        DimensionWeight(dimension=MatchDimension.ADDRESS, basis_points=800),
        DimensionWeight(dimension=MatchDimension.ADMINISTRATORS, basis_points=700),
        DimensionWeight(dimension=MatchDimension.TEMPORAL, basis_points=300),
    ),
    high_threshold=8_500,
    medium_threshold=6_000,
    hard_conflict_rules=frozenset(HardConflictRule),
)


__all__ = [
    "BASIS_POINTS_MAX",
    "INITIAL_MATCH_POLICY",
    "MATCH_POLICY_SCHEMA_VERSION",
    "NAME_NORMALIZATION_V1",
    "SUPPORTED_NAME_NORMALIZATION_VERSIONS",
    "DimensionWeight",
    "HardConflictRule",
    "MatchClassification",
    "MatchDimension",
    "MatchExplanationCode",
    "MatchPolicy",
]
