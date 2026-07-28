"""Tests for neutral observations that remain distinct from evidence and claims."""

from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal
from typing import cast

import pytest

from intelligence.connectors.context import LocaleTag
from intelligence.connectors.enums import ArtifactLocatorKind, ParsingWarningCode
from intelligence.connectors.errors import InvalidConnectorObservationError
from intelligence.connectors.identifiers import ArtifactRefId, CandidateRefId, ConnectorId
from intelligence.connectors.observations import (
    ArtifactLocator,
    CandidateObservation,
    Observation,
    ObservationPeriod,
    ObservationScalar,
    ObservationTypeCode,
    ParsingWarning,
)
from intelligence.connectors.queries import CandidateRef, CandidateSnapshot
from intelligence.connectors.versions import SemanticVersion
from intelligence.domain.geography import CountryCode
from intelligence.domain.money import CurrencyCode


def candidate() -> CandidateRef:
    return CandidateRef(
        candidate_ref_id=CandidateRefId.new(),
        connector_id=ConnectorId("registry.alpha"),
        snapshot=CandidateSnapshot("Synthetic candidate"),
        country=CountryCode("BR"),
        display_name="Example Ltda.",
    )


def observation(**overrides: object) -> Observation:
    values: dict[str, object] = {
        "observation_type": ObservationTypeCode("COMPANY.LEGAL_NAME", SemanticVersion(1, 0, 0)),
        "subject_candidate_ref": candidate(),
        "original_value": "Example Ltda.",
        "normalized_value": "example ltda",
        "currency": None,
        "unit": None,
        "period": None,
        "language": LocaleTag("pt-BR"),
        "locator": None,
        "observed_at": datetime(2026, 7, 28, 12, tzinfo=UTC),
        "published_at": None,
        "extraction_confidence": Decimal("0.95"),
        "parsing_warnings": (),
    }
    values.update(overrides)
    return Observation(
        observation_type=cast(ObservationTypeCode, values["observation_type"]),
        subject_candidate_ref=cast(CandidateRef, values["subject_candidate_ref"]),
        original_value=cast(ObservationScalar, values["original_value"]),
        normalized_value=cast(ObservationScalar | None, values["normalized_value"]),
        currency=cast(CurrencyCode | None, values["currency"]),
        unit=cast(str | None, values["unit"]),
        period=cast(ObservationPeriod | None, values["period"]),
        language=cast(LocaleTag | None, values["language"]),
        locator=cast(ArtifactLocator | None, values["locator"]),
        observed_at=cast(datetime | None, values["observed_at"]),
        published_at=cast(datetime | None, values["published_at"]),
        extraction_confidence=cast(Decimal | None, values["extraction_confidence"]),
        parsing_warnings=cast(tuple[ParsingWarning, ...], values["parsing_warnings"]),
    )


@pytest.mark.parametrize(
    "scalar",
    [
        "value",
        42,
        True,
        Decimal("123.45"),
        date(2026, 7, 28),
        datetime(2026, 7, 28, 9, tzinfo=UTC),
        datetime(2026, 7, 28, 6, tzinfo=timezone(-timedelta(hours=3))),
    ],
)
def test_observation_accepts_only_closed_scalar_vocabulary(scalar: ObservationScalar) -> None:
    value = observation(original_value=scalar, normalized_value=None)

    if isinstance(scalar, datetime):
        assert cast(datetime, value.original_value).tzinfo is UTC
    else:
        assert value.original_value == scalar


@pytest.mark.parametrize(
    "scalar",
    [
        1.5,
        {"value": "x"},
        ["x"],
        " ",
        Decimal("NaN"),
        datetime(2026, 7, 28, 9),
    ],
)
def test_observation_rejects_arbitrary_or_invalid_values(scalar: object) -> None:
    with pytest.raises(InvalidConnectorObservationError):
        observation(original_value=scalar)


def test_observation_preserves_typed_metadata_without_creating_claim() -> None:
    locator = ArtifactLocator(
        ArtifactRefId.new(),
        ArtifactLocatorKind.JSON_POINTER,
        "/company/legalName",
    )
    warning = ParsingWarning(ParsingWarningCode.NORMALIZATION_LOSS, "Diacritics preserved")
    value = observation(
        original_value=Decimal("10.50"),
        normalized_value=Decimal("10.50"),
        currency=CurrencyCode("BRL"),
        unit="thousand",
        period=ObservationPeriod(start=date(2025, 1, 1), end=date(2025, 12, 31)),
        locator=locator,
        parsing_warnings=(warning,),
    )

    assert value.currency == CurrencyCode("BRL")
    assert value.period == ObservationPeriod(start=date(2025, 1, 1), end=date(2025, 12, 31))
    assert value.parsing_warnings == (warning,)
    assert "/company/legalName" not in repr(locator)


def test_observation_type_code_is_versioned_and_validated() -> None:
    value = ObservationTypeCode("COMPANY.REGISTRY_STATUS", SemanticVersion(1, 1, 0))

    assert value.schema_version == SemanticVersion(1, 1, 0)
    with pytest.raises(InvalidConnectorObservationError):
        ObservationTypeCode("company status", SemanticVersion(1, 0, 0))
    with pytest.raises(InvalidConnectorObservationError):
        ObservationTypeCode("COMPANY.STATUS", cast(SemanticVersion, "1.0.0"))


@pytest.mark.parametrize(
    ("start", "end"),
    [
        (None, None),
        (date(2026, 2, 1), date(2026, 1, 1)),
        (cast(date, datetime(2026, 1, 1, tzinfo=UTC)), None),
    ],
)
def test_observation_period_rejects_invalid_boundaries(
    start: date | None,
    end: date | None,
) -> None:
    with pytest.raises(InvalidConnectorObservationError):
        ObservationPeriod(start=start, end=end)


@pytest.mark.parametrize("confidence", [Decimal("-0.01"), Decimal("1.01"), Decimal("NaN")])
def test_observation_rejects_invalid_decimal_confidence(confidence: Decimal) -> None:
    with pytest.raises(InvalidConnectorObservationError):
        observation(extraction_confidence=confidence)


def test_observation_rejects_untyped_optional_metadata() -> None:
    with pytest.raises(InvalidConnectorObservationError):
        observation(currency="BRL")
    with pytest.raises(InvalidConnectorObservationError):
        observation(language="pt-BR")
    with pytest.raises(InvalidConnectorObservationError):
        observation(period="2026")
    with pytest.raises(InvalidConnectorObservationError):
        observation(locator="/value")
    with pytest.raises(InvalidConnectorObservationError):
        observation(parsing_warnings=("warning",))


def test_candidate_observation_normalizes_time_and_rejects_wrong_candidate() -> None:
    value = CandidateObservation(
        candidate=candidate(),
        observed_at=datetime(2026, 7, 28, 9, tzinfo=timezone(-timedelta(hours=3))),
        extraction_confidence=Decimal("0.80"),
        parsing_warnings=(
            ParsingWarning(ParsingWarningCode.MISSING_CONTEXT, "Address unavailable"),
        ),
    )

    assert value.observed_at == datetime(2026, 7, 28, 12, tzinfo=UTC)
    with pytest.raises(InvalidConnectorObservationError):
        CandidateObservation(candidate=cast(CandidateRef, "candidate"))
    with pytest.raises(InvalidConnectorObservationError):
        CandidateObservation(candidate=candidate(), observed_at=datetime(2026, 7, 28, 12))


def test_locator_and_warning_validate_closed_safe_shapes() -> None:
    with pytest.raises(InvalidConnectorObservationError):
        ArtifactLocator(
            cast(ArtifactRefId, CandidateRefId.new()),
            ArtifactLocatorKind.PAGE,
            "page-1",
        )
    with pytest.raises(InvalidConnectorObservationError):
        ArtifactLocator(ArtifactRefId.new(), ArtifactLocatorKind.PAGE, " ")
    with pytest.raises(InvalidConnectorObservationError):
        ParsingWarning(cast(ParsingWarningCode, "TRUNCATED"), "Message")
    with pytest.raises(InvalidConnectorObservationError):
        ParsingWarning(ParsingWarningCode.TRUNCATED, "line 1\nline 2")
