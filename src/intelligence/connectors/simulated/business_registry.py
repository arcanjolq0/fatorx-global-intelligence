"""Deterministic synthetic business registry connector with no external I/O."""

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from intelligence.connectors.artifacts import ArtifactPayload, ArtifactReference
from intelligence.connectors.context import ConnectorContext, LocaleTag
from intelligence.connectors.descriptor import ConnectorDescriptor
from intelligence.connectors.enums import (
    ConnectorAccessType,
    ConnectorCapability,
    ConnectorCoverageKind,
    ConnectorErrorCode,
    ConnectorOperation,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
    UsageCostKind,
)
from intelligence.connectors.identifiers import (
    CandidateRefId,
    ConnectorId,
    OriginReferenceId,
    SourceId,
)
from intelligence.connectors.observations import (
    CandidateObservation,
    Observation,
    ObservationTypeCode,
)
from intelligence.connectors.outcomes import (
    ConnectorError,
    ConnectorOutcome,
    ConnectorUsage,
    ConnectorWarning,
    Pagination,
    SourceSnapshot,
)
from intelligence.connectors.queries import (
    BusinessIdentifier,
    BusinessIdentifierType,
    CandidateRef,
    CandidateSnapshot,
    CompanyQuery,
    DomainName,
)
from intelligence.connectors.simulated.scenarios import BusinessRegistryScenario
from intelligence.connectors.versions import CONNECTOR_CONTRACT_VERSION, SemanticVersion
from intelligence.domain.geography import CountryCode
from intelligence.domain.money import CurrencyCode, Money

SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID = ConnectorId("simulated.business_registry")
SIMULATED_BUSINESS_REGISTRY_SOURCE_ID = SourceId("source.synthetic.business_registry")

_SCHEMA_VERSION = SemanticVersion(1, 0, 0)
_FIXED_RETRIEVED_AT = datetime(2026, 7, 29, 12, 0, tzinfo=UTC)
_FIXED_PUBLISHED_AT = datetime(2026, 1, 15, 9, 0, tzinfo=UTC)
_SEARCH_ORIGIN = OriginReferenceId("synthetic-registry-search-v1")
_DETAILS_ORIGIN = OriginReferenceId("synthetic-registry-details-v1")
_SYNTHETIC_COUNTRY = CountryCode("BR")

_DESCRIPTOR = ConnectorDescriptor(
    connector_id=SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    version=SemanticVersion(1, 0, 0),
    contract_version=CONNECTOR_CONTRACT_VERSION,
    source_id=SIMULATED_BUSINESS_REGISTRY_SOURCE_ID,
    coverage_kind=ConnectorCoverageKind.COUNTRY_SET,
    countries=(_SYNTHETIC_COUNTRY,),
    capabilities=(
        ConnectorCapability.COMPANY_IDENTITY,
        ConnectorCapability.COMPANY_REGISTRY,
    ),
    operations=(ConnectorOperation.SEARCH, ConnectorOperation.FETCH_DETAILS),
    access_type=ConnectorAccessType.API,
    supports_test_mode=True,
    max_page_size=2,
)

_IDENTIFIER_TYPE = BusinessIdentifierType("SYNTHETIC_REGISTRY_ID")
_ALPHA_CANDIDATE = CandidateRef(
    candidate_ref_id=CandidateRefId.from_value("10000000-0000-4000-8000-000000000001"),
    connector_id=SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    snapshot=CandidateSnapshot("Synthetic registry test record Alpha"),
    country=_SYNTHETIC_COUNTRY,
    display_name="Synthetic Alpha Registry Test Ltd.",
    primary_identifier=BusinessIdentifier(
        _IDENTIFIER_TYPE,
        original_value="TEST-REG-0001",
        normalized_value="TESTREG0001",
    ),
    domain=DomainName("synthetic-alpha.test"),
)
_BETA_CANDIDATE = CandidateRef(
    candidate_ref_id=CandidateRefId.from_value("10000000-0000-4000-8000-000000000002"),
    connector_id=SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID,
    snapshot=CandidateSnapshot("Synthetic registry test record Beta"),
    country=_SYNTHETIC_COUNTRY,
    display_name="Synthetic Beta Registry Test Ltd.",
    primary_identifier=BusinessIdentifier(
        _IDENTIFIER_TYPE,
        original_value="TEST-REG-0002",
        normalized_value="TESTREG0002",
    ),
    domain=DomainName("synthetic-beta.test"),
)

_SEARCH_DIGESTS = (
    (
        BusinessRegistryScenario.SUCCESS,
        "0000000000000000000000000000000000000000000000000000000000000001",
    ),
    (
        BusinessRegistryScenario.NO_RESULTS,
        "0000000000000000000000000000000000000000000000000000000000000002",
    ),
    (
        BusinessRegistryScenario.MULTIPLE_CANDIDATES,
        "0000000000000000000000000000000000000000000000000000000000000003",
    ),
    (
        BusinessRegistryScenario.PARTIAL,
        "0000000000000000000000000000000000000000000000000000000000000004",
    ),
    (
        BusinessRegistryScenario.RATE_LIMITED,
        "0000000000000000000000000000000000000000000000000000000000000005",
    ),
    (
        BusinessRegistryScenario.TIMEOUT,
        "0000000000000000000000000000000000000000000000000000000000000006",
    ),
    (
        BusinessRegistryScenario.UNAVAILABLE,
        "0000000000000000000000000000000000000000000000000000000000000007",
    ),
    (
        BusinessRegistryScenario.INVALID_RESPONSE,
        "0000000000000000000000000000000000000000000000000000000000000008",
    ),
    (
        BusinessRegistryScenario.CANCELLED,
        "0000000000000000000000000000000000000000000000000000000000000009",
    ),
    (
        BusinessRegistryScenario.POLICY_BLOCKED,
        "000000000000000000000000000000000000000000000000000000000000000a",
    ),
    (
        BusinessRegistryScenario.BUDGET_EXCEEDED,
        "000000000000000000000000000000000000000000000000000000000000000b",
    ),
)
_DETAILS_DIGESTS = (
    (
        BusinessRegistryScenario.SUCCESS,
        "1000000000000000000000000000000000000000000000000000000000000001",
    ),
    (
        BusinessRegistryScenario.NO_RESULTS,
        "1000000000000000000000000000000000000000000000000000000000000002",
    ),
    (
        BusinessRegistryScenario.MULTIPLE_CANDIDATES,
        "1000000000000000000000000000000000000000000000000000000000000003",
    ),
    (
        BusinessRegistryScenario.PARTIAL,
        "1000000000000000000000000000000000000000000000000000000000000004",
    ),
    (
        BusinessRegistryScenario.RATE_LIMITED,
        "1000000000000000000000000000000000000000000000000000000000000005",
    ),
    (
        BusinessRegistryScenario.TIMEOUT,
        "1000000000000000000000000000000000000000000000000000000000000006",
    ),
    (
        BusinessRegistryScenario.UNAVAILABLE,
        "1000000000000000000000000000000000000000000000000000000000000007",
    ),
    (
        BusinessRegistryScenario.INVALID_RESPONSE,
        "1000000000000000000000000000000000000000000000000000000000000008",
    ),
    (
        BusinessRegistryScenario.CANCELLED,
        "1000000000000000000000000000000000000000000000000000000000000009",
    ),
    (
        BusinessRegistryScenario.POLICY_BLOCKED,
        "100000000000000000000000000000000000000000000000000000000000000a",
    ),
    (
        BusinessRegistryScenario.BUDGET_EXCEEDED,
        "100000000000000000000000000000000000000000000000000000000000000b",
    ),
)


@dataclass(frozen=True, slots=True)
class SimulatedBusinessRegistryConnector:
    """Synthetic test connector selected entirely by an explicit immutable scenario."""

    scenario: BusinessRegistryScenario

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, BusinessRegistryScenario):
            raise TypeError("scenario must be a BusinessRegistryScenario")

    def describe(self) -> ConnectorDescriptor:
        """Return the stable descriptor without reading external state."""

        return _DESCRIPTOR

    async def search(
        self,
        query: CompanyQuery,
        context: ConnectorContext,
    ) -> ConnectorOutcome[CandidateObservation]:
        """Return the configured synthetic search outcome without inspecting magic inputs."""

        del query, context
        if self.scenario is BusinessRegistryScenario.SUCCESS:
            return _candidate_outcome(self.scenario, (_ALPHA_CANDIDATE,))
        if self.scenario is BusinessRegistryScenario.MULTIPLE_CANDIDATES:
            return _candidate_outcome(
                self.scenario,
                (_ALPHA_CANDIDATE, _BETA_CANDIDATE),
            )
        if self.scenario is BusinessRegistryScenario.PARTIAL:
            return _candidate_outcome(
                self.scenario,
                (_ALPHA_CANDIDATE,),
                partial=True,
            )
        if self.scenario is BusinessRegistryScenario.NO_RESULTS:
            return _no_results(
                item_type=CandidateObservation,
                search=True,
                scenario=self.scenario,
            )
        return _search_failure(self.scenario)

    async def fetch_details(
        self,
        candidate_ref: CandidateRef,
        context: ConnectorContext,
    ) -> ConnectorOutcome[Observation]:
        """Return fixed neutral observations for the supplied connector-scoped candidate."""

        del context
        if candidate_ref.connector_id != _DESCRIPTOR.connector_id:
            return _failed_outcome(
                code=ConnectorErrorCode.INVALID_REQUEST,
                message="Candidate belongs to a different connector",
                usage=_details_usage(),
                response_digest=_digest(self.scenario, search=False),
            )
        if self.scenario in {
            BusinessRegistryScenario.SUCCESS,
            BusinessRegistryScenario.MULTIPLE_CANDIDATES,
        }:
            observations = _observations(candidate_ref)
            return ConnectorOutcome(
                status=ConnectorOutcomeStatus.SUCCEEDED,
                items=observations,
                artifacts=(),
                source_snapshot=_source_snapshot(search=False),
                pagination=Pagination(returned_count=len(observations), has_more=False),
                usage=_details_usage(),
                response_digest=_digest(self.scenario, search=False),
            )
        if self.scenario is BusinessRegistryScenario.PARTIAL:
            observations = _observations(candidate_ref)[:3]
            return ConnectorOutcome(
                status=ConnectorOutcomeStatus.PARTIAL,
                items=observations,
                artifacts=(),
                source_snapshot=_source_snapshot(search=False),
                pagination=Pagination(returned_count=len(observations), has_more=False),
                usage=_details_usage(),
                warnings=(_partial_warning(),),
                response_digest=_digest(self.scenario, search=False),
            )
        if self.scenario is BusinessRegistryScenario.NO_RESULTS:
            return _no_results(
                item_type=Observation,
                search=False,
                scenario=self.scenario,
            )
        return _details_failure(self.scenario)

    async def fetch_document(
        self,
        document_ref: ArtifactReference,
        context: ConnectorContext,
    ) -> ConnectorOutcome[ArtifactPayload]:
        """Reject the uniform but undeclared document operation without performing I/O."""

        del document_ref, context
        return _failed_outcome(
            code=ConnectorErrorCode.UNSUPPORTED_OPERATION,
            message="Synthetic registry does not provide documents",
            usage=_document_usage(),
            response_digest="2000000000000000000000000000000000000000000000000000000000000001",
        )


def _candidate_outcome(
    scenario: BusinessRegistryScenario,
    candidates: tuple[CandidateRef, ...],
    *,
    partial: bool = False,
) -> ConnectorOutcome[CandidateObservation]:
    items = tuple(
        CandidateObservation(
            candidate=candidate,
            observed_at=_FIXED_RETRIEVED_AT,
            extraction_confidence=Decimal("0.99"),
        )
        for candidate in candidates
    )
    return ConnectorOutcome(
        status=(ConnectorOutcomeStatus.PARTIAL if partial else ConnectorOutcomeStatus.SUCCEEDED),
        items=items,
        artifacts=(),
        source_snapshot=_source_snapshot(search=True),
        pagination=Pagination(returned_count=len(items), has_more=False),
        usage=_search_usage(),
        warnings=(_partial_warning(),) if partial else (),
        response_digest=_digest(scenario, search=True),
    )


def _no_results[T](
    *,
    item_type: type[T],
    search: bool,
    scenario: BusinessRegistryScenario,
) -> ConnectorOutcome[T]:
    del item_type
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.NO_RESULTS,
        items=(),
        artifacts=(),
        source_snapshot=_source_snapshot(search=search),
        pagination=Pagination(returned_count=0, has_more=False),
        usage=_search_usage() if search else _details_usage(),
        response_digest=_digest(scenario, search=search),
    )


def _search_failure(
    scenario: BusinessRegistryScenario,
) -> ConnectorOutcome[CandidateObservation]:
    return _scenario_failure(scenario, search=True)


def _details_failure(
    scenario: BusinessRegistryScenario,
) -> ConnectorOutcome[Observation]:
    return _scenario_failure(scenario, search=False)


def _scenario_failure[T](
    scenario: BusinessRegistryScenario,
    *,
    search: bool,
) -> ConnectorOutcome[T]:
    if scenario is BusinessRegistryScenario.CANCELLED:
        return ConnectorOutcome(
            status=ConnectorOutcomeStatus.CANCELLED,
            items=(),
            artifacts=(),
            source_snapshot=None,
            pagination=None,
            usage=_search_usage() if search else _details_usage(),
            error=ConnectorError(
                code=ConnectorErrorCode.CANCELLED,
                message="Synthetic operation was cancelled",
            ),
            response_digest=_digest(scenario, search=search),
        )
    error_code, message = _scenario_error(scenario)
    retry_after = (
        timedelta(seconds=30) if scenario is BusinessRegistryScenario.RATE_LIMITED else None
    )
    return _failed_outcome(
        code=error_code,
        message=message,
        usage=_search_usage() if search else _details_usage(),
        retry_after=retry_after,
        response_digest=_digest(scenario, search=search),
        include_snapshot=scenario is BusinessRegistryScenario.INVALID_RESPONSE,
        search=search,
    )


def _failed_outcome[T](
    *,
    code: ConnectorErrorCode,
    message: str,
    usage: ConnectorUsage,
    response_digest: str,
    retry_after: timedelta | None = None,
    include_snapshot: bool = False,
    search: bool = True,
) -> ConnectorOutcome[T]:
    return ConnectorOutcome(
        status=ConnectorOutcomeStatus.FAILED,
        items=(),
        artifacts=(),
        source_snapshot=_source_snapshot(search=search) if include_snapshot else None,
        pagination=None,
        usage=usage,
        error=ConnectorError(code=code, message=message, retry_after=retry_after),
        response_digest=response_digest,
    )


def _scenario_error(
    scenario: BusinessRegistryScenario,
) -> tuple[ConnectorErrorCode, str]:
    if scenario is BusinessRegistryScenario.RATE_LIMITED:
        return ConnectorErrorCode.RATE_LIMITED, "Synthetic source is temporarily limited"
    if scenario is BusinessRegistryScenario.TIMEOUT:
        return ConnectorErrorCode.TIMEOUT, "Synthetic source reported a timeout"
    if scenario is BusinessRegistryScenario.UNAVAILABLE:
        return ConnectorErrorCode.UNAVAILABLE, "Synthetic source is unavailable"
    if scenario is BusinessRegistryScenario.INVALID_RESPONSE:
        return (
            ConnectorErrorCode.INVALID_RESPONSE,
            "Synthetic source response could not be translated",
        )
    if scenario is BusinessRegistryScenario.POLICY_BLOCKED:
        return ConnectorErrorCode.POLICY_BLOCKED, "Synthetic source policy blocked the operation"
    if scenario is BusinessRegistryScenario.BUDGET_EXCEEDED:
        return ConnectorErrorCode.BUDGET_EXCEEDED, "Synthetic operation budget was exceeded"
    raise AssertionError("Scenario does not represent a failed connector outcome")


def _observations(candidate: CandidateRef) -> tuple[Observation, ...]:
    identifier = candidate.primary_identifier
    identifier_value = identifier.original_value if identifier is not None else "TEST-REG-UNKNOWN"
    return (
        _observation(
            candidate,
            code="COMPANY.REGISTERED_NAME",
            original=candidate.display_name,
            normalized=candidate.display_name.casefold(),
        ),
        _observation(
            candidate,
            code="COMPANY.BUSINESS_IDENTIFIER",
            original=identifier_value,
            normalized=identifier_value.replace("-", ""),
        ),
        _observation(
            candidate,
            code="COMPANY.REGISTRY_STATUS",
            original="SYNTHETIC ACTIVE TEST RECORD",
            normalized="synthetic_active_test_record",
        ),
        _observation(
            candidate,
            code="COMPANY.INCORPORATION_DATE",
            original=date(2020, 1, 15),
        ),
        _observation(
            candidate,
            code="COMPANY.LOCALITY",
            original="Synthetic Test City",
            normalized="synthetic test city",
        ),
        _observation(
            candidate,
            code="COMPANY.ECONOMIC_ACTIVITY",
            original="Synthetic registry contract testing",
            normalized="synthetic_registry_contract_testing",
        ),
    )


def _observation(
    candidate: CandidateRef,
    *,
    code: str,
    original: str | date,
    normalized: str | None = None,
) -> Observation:
    return Observation(
        observation_type=ObservationTypeCode(code, _SCHEMA_VERSION),
        subject_candidate_ref=candidate,
        original_value=original,
        normalized_value=normalized,
        language=LocaleTag("en"),
        observed_at=_FIXED_RETRIEVED_AT,
        published_at=_FIXED_PUBLISHED_AT,
        extraction_confidence=Decimal("0.99"),
    )


def _source_snapshot(*, search: bool) -> SourceSnapshot:
    return SourceSnapshot(
        source_id=SIMULATED_BUSINESS_REGISTRY_SOURCE_ID,
        origin_reference=_SEARCH_ORIGIN if search else _DETAILS_ORIGIN,
        retrieved_at=_FIXED_RETRIEVED_AT,
        published_at=_FIXED_PUBLISHED_AT,
    )


def _search_usage() -> ConnectorUsage:
    return ConnectorUsage(
        calls=1,
        bytes_received=512,
        duration=timedelta(milliseconds=12),
        cost=Money(Decimal("0.01"), CurrencyCode("USD")),
        cost_kind=UsageCostKind.ESTIMATED,
    )


def _details_usage() -> ConnectorUsage:
    return ConnectorUsage(
        calls=1,
        bytes_received=768,
        duration=timedelta(milliseconds=18),
        cost=Money(Decimal("0.02"), CurrencyCode("USD")),
        cost_kind=UsageCostKind.ESTIMATED,
    )


def _document_usage() -> ConnectorUsage:
    return ConnectorUsage(calls=0, bytes_received=0, duration=timedelta(0))


def _partial_warning() -> ConnectorWarning:
    return ConnectorWarning(
        ConnectorWarningCode.PARTIAL_DATA,
        "Synthetic registry omitted optional test fields",
    )


def _digest(scenario: BusinessRegistryScenario, *, search: bool) -> str:
    values = _SEARCH_DIGESTS if search else _DETAILS_DIGESTS
    for known_scenario, digest in values:
        if scenario is known_scenario:
            return digest
    raise AssertionError("Scenario digest is not defined")


__all__ = [
    "SIMULATED_BUSINESS_REGISTRY_CONNECTOR_ID",
    "SIMULATED_BUSINESS_REGISTRY_SOURCE_ID",
    "SimulatedBusinessRegistryConnector",
]
