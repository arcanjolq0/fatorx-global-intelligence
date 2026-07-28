"""Neutral, non-canonical observations produced by future connectors."""

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from intelligence.connectors.context import LocaleTag
from intelligence.connectors.enums import ArtifactLocatorKind, ParsingWarningCode
from intelligence.connectors.errors import InvalidConnectorObservationError
from intelligence.connectors.identifiers import ArtifactRefId
from intelligence.connectors.queries import CandidateRef
from intelligence.connectors.versions import SemanticVersion
from intelligence.domain.errors import InvalidDateTimeError
from intelligence.domain.money import CurrencyCode
from intelligence.domain.time import normalize_utc

_OBSERVATION_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.-]*", flags=re.ASCII)
type ObservationScalar = str | int | bool | Decimal | date | datetime


@dataclass(frozen=True, slots=True)
class ObservationTypeCode:
    """Versioned neutral observation schema code, not a claim predicate."""

    code: str
    schema_version: SemanticVersion

    def __post_init__(self) -> None:
        if (
            not isinstance(self.code, str)
            or not self.code
            or len(self.code) > 64
            or _OBSERVATION_CODE_PATTERN.fullmatch(self.code) is None
        ):
            raise InvalidConnectorObservationError(
                "ObservationTypeCode code has an invalid format."
            )
        if not isinstance(self.schema_version, SemanticVersion):
            raise InvalidConnectorObservationError(
                "ObservationTypeCode schema_version must be SemanticVersion."
            )


@dataclass(frozen=True, slots=True)
class ObservationPeriod:
    """Optional civil-date period associated with one observed value."""

    start: date | None = None
    end: date | None = None

    def __post_init__(self) -> None:
        for value in (self.start, self.end):
            if value is not None and (not isinstance(value, date) or isinstance(value, datetime)):
                raise InvalidConnectorObservationError(
                    "ObservationPeriod boundaries must be civil dates."
                )
        if self.start is None and self.end is None:
            raise InvalidConnectorObservationError(
                "ObservationPeriod requires at least one boundary."
            )
        if self.start is not None and self.end is not None and self.end < self.start:
            raise InvalidConnectorObservationError("ObservationPeriod end cannot precede start.")


@dataclass(frozen=True, slots=True)
class ArtifactLocator:
    """Non-canonical location inside an artifact reference."""

    artifact_ref_id: ArtifactRefId
    kind: ArtifactLocatorKind
    value: str = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_ref_id, ArtifactRefId):
            raise InvalidConnectorObservationError(
                "ArtifactLocator artifact_ref_id must be an ArtifactRefId."
            )
        if not isinstance(self.kind, ArtifactLocatorKind):
            raise InvalidConnectorObservationError(
                "ArtifactLocator kind must be an ArtifactLocatorKind."
            )
        _safe_text(self.value, field_name="Artifact locator", maximum_length=512)

    def __repr__(self) -> str:
        return (
            "ArtifactLocator(artifact_ref_id="
            f"{self.artifact_ref_id!r}, kind={self.kind!r}, value=<redacted>)"
        )


@dataclass(frozen=True, slots=True)
class ParsingWarning:
    """Closed parsing warning with a bounded public message."""

    code: ParsingWarningCode
    message: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, ParsingWarningCode):
            raise InvalidConnectorObservationError(
                "ParsingWarning code must be a ParsingWarningCode."
            )
        object.__setattr__(
            self,
            "message",
            _safe_text(self.message, field_name="Parsing warning", maximum_length=256),
        )


@dataclass(frozen=True, slots=True, kw_only=True)
class CandidateObservation:
    """Candidate returned by a connector without an entity-match decision."""

    candidate: CandidateRef
    observed_at: datetime | None = None
    extraction_confidence: Decimal | None = None
    parsing_warnings: tuple[ParsingWarning, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, CandidateRef):
            raise InvalidConnectorObservationError(
                "CandidateObservation candidate must be a CandidateRef."
            )
        object.__setattr__(self, "observed_at", _optional_utc(self.observed_at))
        _validate_confidence(self.extraction_confidence)
        _validate_parsing_warnings(self.parsing_warnings)
        object.__setattr__(self, "parsing_warnings", tuple(self.parsing_warnings))


@dataclass(frozen=True, slots=True, kw_only=True)
class Observation:
    """Typed connector observation that is neither evidence nor a claim."""

    observation_type: ObservationTypeCode
    subject_candidate_ref: CandidateRef
    original_value: ObservationScalar
    normalized_value: ObservationScalar | None = None
    currency: CurrencyCode | None = None
    unit: str | None = None
    period: ObservationPeriod | None = None
    language: LocaleTag | None = None
    locator: ArtifactLocator | None = None
    observed_at: datetime | None = None
    published_at: datetime | None = None
    extraction_confidence: Decimal | None = None
    parsing_warnings: tuple[ParsingWarning, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.observation_type, ObservationTypeCode):
            raise InvalidConnectorObservationError(
                "Observation observation_type must be an ObservationTypeCode."
            )
        if not isinstance(self.subject_candidate_ref, CandidateRef):
            raise InvalidConnectorObservationError(
                "Observation subject_candidate_ref must be a CandidateRef."
            )
        object.__setattr__(self, "original_value", _observation_scalar(self.original_value))
        if self.normalized_value is not None:
            object.__setattr__(
                self,
                "normalized_value",
                _observation_scalar(self.normalized_value),
            )
        if self.currency is not None and not isinstance(self.currency, CurrencyCode):
            raise InvalidConnectorObservationError("Observation currency must be a CurrencyCode.")
        if self.unit is not None:
            object.__setattr__(
                self,
                "unit",
                _safe_text(self.unit, field_name="Observation unit", maximum_length=64),
            )
        if self.period is not None and not isinstance(self.period, ObservationPeriod):
            raise InvalidConnectorObservationError(
                "Observation period must be an ObservationPeriod."
            )
        if self.language is not None and not isinstance(self.language, LocaleTag):
            raise InvalidConnectorObservationError("Observation language must be a LocaleTag.")
        if self.locator is not None and not isinstance(self.locator, ArtifactLocator):
            raise InvalidConnectorObservationError(
                "Observation locator must be an ArtifactLocator."
            )
        object.__setattr__(self, "observed_at", _optional_utc(self.observed_at))
        object.__setattr__(self, "published_at", _optional_utc(self.published_at))
        _validate_confidence(self.extraction_confidence)
        _validate_parsing_warnings(self.parsing_warnings)
        object.__setattr__(self, "parsing_warnings", tuple(self.parsing_warnings))


def _observation_scalar(value: object) -> ObservationScalar:
    if isinstance(value, str):
        return _safe_text(value, field_name="Observation string value", maximum_length=4096)
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise InvalidConnectorObservationError("Observation Decimal values must be finite.")
        return value
    if isinstance(value, datetime):
        try:
            return normalize_utc(value)
        except InvalidDateTimeError as error:
            raise InvalidConnectorObservationError(
                "Observation datetime values must include timezone information."
            ) from error
    if isinstance(value, date):
        return value
    raise InvalidConnectorObservationError(
        "Observation values must use the closed scalar vocabulary."
    )


def _optional_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    try:
        return normalize_utc(value)
    except InvalidDateTimeError as error:
        raise InvalidConnectorObservationError(
            "Observation timestamps must include timezone information."
        ) from error


def _validate_confidence(value: Decimal | None) -> None:
    if value is None:
        return
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0 or value > 1:
        raise InvalidConnectorObservationError(
            "Extraction confidence must be a finite Decimal between zero and one."
        )


def _validate_parsing_warnings(values: tuple[ParsingWarning, ...]) -> None:
    if any(not isinstance(value, ParsingWarning) for value in values):
        raise InvalidConnectorObservationError(
            "Parsing warnings must contain only ParsingWarning values."
        )


def _safe_text(value: str, *, field_name: str, maximum_length: int) -> str:
    if not isinstance(value, str):
        raise InvalidConnectorObservationError(f"{field_name} must be text.")
    canonical = value.strip()
    if (
        not canonical
        or len(canonical) > maximum_length
        or any(character in "\r\n\x00" for character in canonical)
    ):
        raise InvalidConnectorObservationError(f"{field_name} has an invalid value.")
    return canonical


__all__ = [
    "ArtifactLocator",
    "CandidateObservation",
    "Observation",
    "ObservationPeriod",
    "ObservationScalar",
    "ObservationTypeCode",
    "ParsingWarning",
]
