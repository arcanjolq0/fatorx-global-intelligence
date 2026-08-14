"""Content limits, runtime validation, and redaction tests."""

from typing import cast

import pytest

from intelligence.connectors.enums import (
    ConnectorErrorCode,
    ConnectorOutcomeStatus,
    ConnectorWarningCode,
)
from intelligence.connectors.execution import ConnectorExecutionControlCode
from intelligence.connectors.identifiers import ConnectorId, SourceId
from intelligence.connectors.observations import CandidateObservation
from intelligence.connectors.outcomes import ConnectorOutcome, Pagination
from tests.connectors.execution.doubles import (
    TEST_CONNECTOR_ID,
    ControlledConnector,
    connector_usage,
    details_request,
    details_success,
    document_success,
    execution_policy,
    failed_outcome,
    operation_runner,
    run_async,
    search_request,
    search_success,
    source_snapshot,
)
from tests.connectors.execution.doubles import (
    test_candidate as make_candidate,
)
from tests.connectors.synthetic_fixtures import synthetic_query

pytestmark = pytest.mark.allow_hosts(["127.0.0.1"])


def test_smaller_descriptor_and_policy_item_limit_truncates_to_partial() -> None:
    connector = ControlledConnector(search_values=(search_success(count=5),))
    policy = execution_policy(max_items=2)

    result = run_async(operation_runner().execute(search_request(connector, policy=policy)))

    assert result.outcome.status is ConnectorOutcomeStatus.PARTIAL
    assert len(result.outcome.items) == 2
    assert result.outcome.pagination is not None
    assert result.outcome.pagination.returned_count == 2
    assert {warning.code for warning in result.outcome.warnings} == {ConnectorWarningCode.TRUNCATED}


def test_has_more_never_fetches_another_page_and_cursor_is_removed() -> None:
    cursor = "cursor-must-never-be-published"
    connector = ControlledConnector(search_values=(search_success(has_more=True, cursor=cursor),))

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.status is ConnectorOutcomeStatus.PARTIAL
    assert connector.operation_calls == 1
    assert result.outcome.pagination is not None
    assert not result.outcome.pagination.has_more
    assert result.outcome.pagination.continuation is None
    assert ConnectorWarningCode.PAGINATION_LIMITED in {
        warning.code for warning in result.outcome.warnings
    }
    assert cursor not in repr(result)
    assert cursor not in repr(result.events)
    assert cursor not in result.digest


def test_artifact_limit_truncates_without_exposing_payload_bytes() -> None:
    base = search_success()
    payloads = document_success(artifact_count=3).items
    with_artifacts = ConnectorOutcome(
        status=ConnectorOutcomeStatus.SUCCEEDED,
        items=base.items,
        artifacts=payloads,
        source_snapshot=base.source_snapshot,
        pagination=base.pagination,
        usage=base.usage,
        response_digest=base.response_digest,
    )
    connector = ControlledConnector(search_values=(with_artifacts,))
    policy = execution_policy(max_artifacts=1)

    result = run_async(operation_runner().execute(search_request(connector, policy=policy)))

    assert result.outcome.status is ConnectorOutcomeStatus.PARTIAL
    assert len(result.outcome.artifacts) == 1
    assert ConnectorWarningCode.TRUNCATED in {warning.code for warning in result.outcome.warnings}
    assert "synthetic document" not in repr(result)
    assert "synthetic document" not in repr(result.events)


def test_wrong_item_type_becomes_invalid_response_without_payload() -> None:
    wrong = details_success(make_candidate())
    connector = ControlledConnector(search_values=(wrong,))

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
    assert result.outcome.items == ()
    assert result.control_code is ConnectorExecutionControlCode.INVALID_CONNECTOR_RESPONSE


def test_wrong_source_and_candidate_connector_become_invalid_response() -> None:
    wrong_source = ControlledConnector(
        search_values=(search_success(source_id=SourceId("source.synthetic.wrong")),)
    )
    candidate = make_candidate(connector_id=ConnectorId("controlled.wrong"))
    candidate_item = CandidateObservation(candidate=candidate)
    wrong_candidate_outcome = ConnectorOutcome(
        status=ConnectorOutcomeStatus.SUCCEEDED,
        items=(candidate_item,),
        artifacts=(),
        source_snapshot=source_snapshot(),
        pagination=Pagination(returned_count=1, has_more=False),
        usage=connector_usage(),
        response_digest="f" * 64,
    )
    wrong_candidate = ControlledConnector(search_values=(wrong_candidate_outcome,))

    results = (
        run_async(operation_runner().execute(search_request(wrong_source))),
        run_async(operation_runner().execute(search_request(wrong_candidate))),
    )

    assert all(result.outcome.error is not None for result in results)
    assert all(
        result.outcome.error is not None
        and result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
        for result in results
    )


def test_detail_observation_for_another_candidate_is_rejected() -> None:
    supplied = make_candidate()
    other = make_candidate(index=2)
    connector = ControlledConnector(details_values=(details_success(other),))

    result = run_async(operation_runner().execute(details_request(connector, candidate=supplied)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
    assert result.outcome.items == ()


def test_raw_object_and_mutating_descriptor_are_rejected_without_retry() -> None:
    raw = ControlledConnector(search_values=(cast(object, "raw provider payload"),))
    stable_descriptor = raw.descriptor
    mutating = ControlledConnector(
        descriptor=stable_descriptor,
        descriptor_after_operation=type(stable_descriptor)(
            connector_id=stable_descriptor.connector_id,
            version=type(stable_descriptor.version)(1, 2, 4),
            contract_version=stable_descriptor.contract_version,
            source_id=stable_descriptor.source_id,
            coverage_kind=stable_descriptor.coverage_kind,
            countries=stable_descriptor.countries,
            capabilities=stable_descriptor.capabilities,
            operations=stable_descriptor.operations,
            access_type=stable_descriptor.access_type,
            supports_test_mode=stable_descriptor.supports_test_mode,
            max_page_size=stable_descriptor.max_page_size,
        ),
    )

    raw_result = run_async(operation_runner().execute(search_request(raw)))
    retry_invalid_response = execution_policy(
        retriable_codes=(ConnectorErrorCode.INVALID_RESPONSE,)
    )
    mutating_result = run_async(
        operation_runner().execute(search_request(mutating, policy=retry_invalid_response))
    )

    for result in (raw_result, mutating_result):
        assert result.outcome.error is not None
        assert result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
        assert result.attempts_started == 1
    assert raw.operation_calls == mutating.operation_calls == 1


def test_raw_exception_is_redacted_and_never_leaks_external_text() -> None:
    external_text = "token at https://provider.invalid private payload"
    connector = ControlledConnector(search_values=(RuntimeError(external_text),))

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.INTERNAL_ERROR
    assert external_text not in result.outcome.error.message
    assert external_text not in repr(result)
    assert external_text not in repr(result.events)


def test_message_containing_query_content_is_replaced_by_invalid_response() -> None:
    query = synthetic_query()
    unsafe = failed_outcome(ConnectorErrorCode.UNAVAILABLE)
    unsafe = ConnectorOutcome(
        status=unsafe.status,
        items=unsafe.items,
        artifacts=unsafe.artifacts,
        source_snapshot=unsafe.source_snapshot,
        pagination=unsafe.pagination,
        usage=unsafe.usage,
        error=type(unsafe.error)(
            code=ConnectorErrorCode.UNAVAILABLE,
            message=query.original_name,
        )
        if unsafe.error is not None
        else None,
        response_digest=unsafe.response_digest,
    )
    connector = ControlledConnector(search_values=(unsafe,))

    result = run_async(operation_runner().execute(search_request(connector, query=query)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
    assert query.original_name not in result.outcome.error.message
    assert query.original_name not in repr(result.events)


def test_failed_outcome_with_artifact_is_not_publishable_in_f33() -> None:
    payload = document_success().items[0]
    invalid = ConnectorOutcome[CandidateObservation](
        status=ConnectorOutcomeStatus.FAILED,
        items=(),
        artifacts=(payload,),
        source_snapshot=None,
        pagination=None,
        usage=connector_usage(),
        error=failed_outcome(ConnectorErrorCode.UNAVAILABLE).error,
    )
    connector = ControlledConnector(search_values=(invalid,))

    result = run_async(operation_runner().execute(search_request(connector)))

    assert result.outcome.error is not None
    assert result.outcome.error.code is ConnectorErrorCode.INVALID_RESPONSE
    assert result.outcome.artifacts == ()


def test_valid_candidate_ids_still_match_expected_connector() -> None:
    result = run_async(operation_runner().execute(search_request(ControlledConnector())))

    assert result.outcome.items[0].candidate.connector_id == TEST_CONNECTOR_ID
