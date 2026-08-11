"""Pure F4.3 Company materialization policy and digest tests."""

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any, cast

import pytest

from intelligence.domain.companies import CompanyStatus
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.geography import CountryCode
from intelligence.domain.identifiers import CompanyId, WorkspaceId
from intelligence.domain.investigation_inputs import (
    CorporateDomainInput,
    OriginalAndNormalizedText,
)
from intelligence.entity_resolution.contracts import (
    CandidateIdentitySnapshot,
    SourceRegistrationStatus,
)
from intelligence.entity_resolution.errors import InvalidMatchingPolicyError
from intelligence.entity_resolution.materialization import (
    COMPANY_MATERIALIZATION_V1,
    CompanyMaterializationPolicy,
    company_snapshot_digest,
    materialize_company,
)

NOW = datetime(2026, 8, 1, 15, tzinfo=UTC)


def _text(original: str, normalized: str | None = None) -> OriginalAndNormalizedText:
    return OriginalAndNormalizedText(
        original_value=original,
        normalized_value=normalized or original.casefold(),
    )


def _identity(
    status: SourceRegistrationStatus | None = SourceRegistrationStatus.ACTIVE,
) -> CandidateIdentitySnapshot:
    return CandidateIdentitySnapshot(
        legal_name=_text("Empresa Original S.A.", "empresa original sa"),
        trade_name=_text("Marca Original", "marca original"),
        country_code=CountryCode("BR"),
        incorporated_on=date(2014, 2, 3),
        corporate_domain=CorporateDomainInput(
            original_value="Empresa.Example",
            normalized_value="empresa.example",
        ),
        registry_status=status,
    )


def test_policy_is_canonical_versioned_reconstitutable_and_redacted() -> None:
    serialized = COMPANY_MATERIALIZATION_V1.to_canonical_json()
    restored = CompanyMaterializationPolicy.from_canonical_json(serialized)

    assert restored == COMPANY_MATERIALIZATION_V1
    assert restored.digest == COMPANY_MATERIALIZATION_V1.digest
    assert '"status_mapping":{"ACTIVE":"ACTIVE"' in serialized
    assert restored.to_public_redacted().rule_count == 8
    assert "Empresa" not in repr(restored)


def test_policy_digest_changes_with_version_and_invalid_shapes_fail_closed() -> None:
    changed = replace(COMPANY_MATERIALIZATION_V1, version=2)
    assert changed.digest != COMPANY_MATERIALIZATION_V1.digest

    with pytest.raises(InvalidMatchingPolicyError):
        replace(COMPANY_MATERIALIZATION_V1, version=0)
    with pytest.raises(InvalidMatchingPolicyError):
        replace(COMPANY_MATERIALIZATION_V1, mapping_rules=())
    with pytest.raises(InvalidMatchingPolicyError):
        CompanyMaterializationPolicy.from_canonical_json("{}")


@pytest.mark.parametrize(
    ("source_status", "expected"),
    [
        (SourceRegistrationStatus.ACTIVE, CompanyStatus.ACTIVE),
        (SourceRegistrationStatus.INACTIVE, CompanyStatus.INACTIVE),
        (SourceRegistrationStatus.DISSOLVED, CompanyStatus.UNKNOWN),
        (SourceRegistrationStatus.UNKNOWN, CompanyStatus.UNKNOWN),
        (None, CompanyStatus.UNKNOWN),
    ],
)
def test_materialization_maps_only_allowed_candidate_fields(
    source_status: SourceRegistrationStatus | None,
    expected: CompanyStatus,
) -> None:
    company_id = CompanyId.new()
    workspace_id = WorkspaceId.new()
    identity = _identity(source_status)

    company = materialize_company(
        policy=COMPANY_MATERIALIZATION_V1,
        company_id=company_id,
        workspace_id=workspace_id,
        candidate_identity=identity,
        occurred_at=NOW,
    )

    assert company.id == company_id
    assert company.workspace_id == workspace_id
    assert company.legal_name == "Empresa Original S.A."
    assert company.trade_name == "Marca Original"
    assert company.country_code == CountryCode("BR")
    assert company.incorporated_on == date(2014, 2, 3)
    assert company.official_domain == "empresa.example"
    assert company.status is expected
    assert company.legal_form is None
    assert company.dissolved_on is None
    assert company.created_at == company.updated_at == NOW
    assert identity == _identity(source_status)


def test_company_snapshot_digest_is_stable_and_bound_to_company_policy_and_candidate() -> None:
    identity = _identity()
    company = materialize_company(
        policy=COMPANY_MATERIALIZATION_V1,
        company_id=CompanyId.new(),
        workspace_id=WorkspaceId.new(),
        candidate_identity=identity,
        occurred_at=NOW,
    )

    first = company_snapshot_digest(
        company=company,
        policy_digest=COMPANY_MATERIALIZATION_V1.digest,
        candidate_identity_digest=identity.digest,
    )
    second = company_snapshot_digest(
        company=company,
        policy_digest=COMPANY_MATERIALIZATION_V1.digest,
        candidate_identity_digest=identity.digest,
    )

    assert first == second
    assert len(first) == 64
    assert first != company_snapshot_digest(
        company=replace(company, legal_name="Changed"),
        policy_digest=COMPANY_MATERIALIZATION_V1.digest,
        candidate_identity_digest=identity.digest,
    )


def test_materialization_rejects_structurally_valid_but_unsupported_policy() -> None:
    with pytest.raises(InvalidMatchingPolicyError, match="unsupported"):
        materialize_company(
            policy=replace(COMPANY_MATERIALIZATION_V1, version=2),
            company_id=CompanyId.new(),
            workspace_id=WorkspaceId.new(),
            candidate_identity=_identity(),
            occurred_at=NOW,
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"schema_version": 2},
        {"policy_id": "invalid"},
        {"version": True},
        {"candidate_identity_schema_version": 2},
        {"mapping_rules": cast(Any, [])},
    ],
)
def test_policy_constructor_rejects_invalid_closed_fields(changes: dict[str, object]) -> None:
    with pytest.raises(InvalidMatchingPolicyError):
        replace(COMPANY_MATERIALIZATION_V1, **cast(Any, changes))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: cast(Any, None),
        lambda value: "{",
        lambda value: json.dumps({**value, "extra": 1}),
        lambda value: json.dumps({**value, "status_mapping": {}}),
        lambda value: json.dumps({**value, "mapping_rules": "invalid"}),
        lambda value: json.dumps({**value, "mapping_rules": ["INVALID"]}),
        lambda value: json.dumps({**value, "policy_id": 1}),
        lambda value: json.dumps({**value, "version": True}),
        lambda value: json.dumps(value, indent=2),
    ],
)
def test_policy_reconstitution_rejects_invalid_or_noncanonical_json(
    mutate: Callable[[dict[str, object]], object],
) -> None:
    raw = json.loads(COMPANY_MATERIALIZATION_V1.to_canonical_json())
    with pytest.raises(InvalidMatchingPolicyError):
        CompanyMaterializationPolicy.from_canonical_json(cast(Any, mutate(raw)))


def test_materialization_and_company_digest_require_typed_valid_inputs() -> None:
    identity = _identity()
    with pytest.raises(InvariantViolationError):
        materialize_company(
            policy=COMPANY_MATERIALIZATION_V1,
            company_id=cast(Any, "company"),
            workspace_id=WorkspaceId.new(),
            candidate_identity=identity,
            occurred_at=NOW,
        )
    with pytest.raises(InvariantViolationError):
        materialize_company(
            policy=COMPANY_MATERIALIZATION_V1,
            company_id=CompanyId.new(),
            workspace_id=WorkspaceId.new(),
            candidate_identity=cast(Any, "candidate"),
            occurred_at=NOW,
        )
    with pytest.raises(InvariantViolationError):
        company_snapshot_digest(
            company=cast(Any, "company"),
            policy_digest="0" * 64,
            candidate_identity_digest="1" * 64,
        )
    company = materialize_company(
        policy=COMPANY_MATERIALIZATION_V1,
        company_id=CompanyId.new(),
        workspace_id=WorkspaceId.new(),
        candidate_identity=identity,
        occurred_at=NOW,
    )
    with pytest.raises(InvariantViolationError):
        company_snapshot_digest(
            company=company,
            policy_digest="invalid",
            candidate_identity_digest=identity.digest,
        )


def test_materialization_preserves_absent_optional_fields() -> None:
    identity = CandidateIdentitySnapshot(
        legal_name=_text("Empresa Sem Opcionais"),
        country_code=CountryCode("BR"),
    )
    company = materialize_company(
        policy=COMPANY_MATERIALIZATION_V1,
        company_id=CompanyId.new(),
        workspace_id=WorkspaceId.new(),
        candidate_identity=identity,
        occurred_at=NOW,
    )
    assert company.trade_name is None
    assert company.official_domain is None


def test_materialization_preserves_original_name_whitespace_exactly() -> None:
    identity = CandidateIdentitySnapshot(
        legal_name=_text("  Empresa Original  ", "empresa original"),
        trade_name=_text("  Marca Original  ", "marca original"),
        country_code=CountryCode("BR"),
    )
    company = materialize_company(
        policy=COMPANY_MATERIALIZATION_V1,
        company_id=CompanyId.new(),
        workspace_id=WorkspaceId.new(),
        candidate_identity=identity,
        occurred_at=NOW,
    )
    assert company.legal_name == identity.legal_name.original_value
    assert identity.trade_name is not None
    assert company.trade_name == identity.trade_name.original_value
