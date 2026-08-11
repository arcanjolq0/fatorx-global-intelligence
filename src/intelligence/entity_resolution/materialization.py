"""Pure, versioned materialization of one selected candidate into a Company."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import cast

from intelligence.domain.companies import Company, CompanyStatus
from intelligence.domain.errors import InvariantViolationError
from intelligence.domain.identifiers import CompanyId, WorkspaceId
from intelligence.domain.time import normalize_utc
from intelligence.entity_resolution.contracts import (
    CANDIDATE_IDENTITY_SCHEMA_VERSION,
    CandidateIdentitySnapshot,
    SourceRegistrationStatus,
)
from intelligence.entity_resolution.errors import InvalidMatchingPolicyError

COMPANY_MATERIALIZATION_POLICY_SCHEMA_VERSION = 1
COMPANY_MATERIALIZATION_POLICY_ID = "COMPANY_MATERIALIZATION_V1"
_CODE_PATTERN = re.compile(r"[A-Z][A-Z0-9_.:-]{0,63}", flags=re.ASCII)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}", flags=re.ASCII)


class CompanyMaterializationRule(StrEnum):
    """Closed mapping rules whose semantics are fixed by policy schema 1."""

    LEGAL_NAME_ORIGINAL = "LEGAL_NAME_ORIGINAL"
    TRADE_NAME_ORIGINAL = "TRADE_NAME_ORIGINAL"
    COUNTRY_CODE = "COUNTRY_CODE"
    INCORPORATED_ON = "INCORPORATED_ON"
    CORPORATE_DOMAIN_NORMALIZED = "CORPORATE_DOMAIN_NORMALIZED"
    LEGAL_FORM_ABSENT = "LEGAL_FORM_ABSENT"
    DISSOLVED_ON_ABSENT = "DISSOLVED_ON_ABSENT"
    CONSERVATIVE_REGISTRATION_STATUS = "CONSERVATIVE_REGISTRATION_STATUS"


@dataclass(frozen=True, slots=True, kw_only=True)
class RedactedCompanyMaterializationPolicy:
    """Public policy metadata without candidate or Company values."""

    policy_id: str
    version: int
    schema_version: int
    candidate_identity_schema_version: int
    rule_count: int
    digest: str


@dataclass(frozen=True, slots=True, kw_only=True, repr=False)
class CompanyMaterializationPolicy:
    """Canonical policy snapshot used to materialize a Company deterministically."""

    policy_id: str
    version: int
    candidate_identity_schema_version: int
    mapping_rules: tuple[CompanyMaterializationRule, ...]
    schema_version: int = COMPANY_MATERIALIZATION_POLICY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.schema_version, bool)
            or self.schema_version != COMPANY_MATERIALIZATION_POLICY_SCHEMA_VERSION
        ):
            raise InvalidMatchingPolicyError(
                "Company materialization policy schema version is unsupported."
            )
        if not isinstance(self.policy_id, str) or _CODE_PATTERN.fullmatch(self.policy_id) is None:
            raise InvalidMatchingPolicyError("Company materialization policy ID is invalid.")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise InvalidMatchingPolicyError("Company materialization policy version is invalid.")
        if (
            isinstance(self.candidate_identity_schema_version, bool)
            or self.candidate_identity_schema_version != CANDIDATE_IDENTITY_SCHEMA_VERSION
        ):
            raise InvalidMatchingPolicyError(
                "Company materialization candidate identity schema is unsupported."
            )
        if not isinstance(self.mapping_rules, tuple) or any(
            not isinstance(rule, CompanyMaterializationRule) for rule in self.mapping_rules
        ):
            raise InvalidMatchingPolicyError(
                "Company materialization rules must use the closed immutable vocabulary."
            )
        if len(self.mapping_rules) != len(CompanyMaterializationRule) or set(
            self.mapping_rules
        ) != set(CompanyMaterializationRule):
            raise InvalidMatchingPolicyError(
                "Company materialization policy must contain every mapping rule once."
            )
        object.__setattr__(
            self,
            "mapping_rules",
            tuple(sorted(self.mapping_rules, key=lambda rule: rule.value)),
        )

    def to_canonical_json(self) -> str:
        return _canonical_json(self._canonical_object())

    @classmethod
    def from_canonical_json(cls, serialized: str) -> CompanyMaterializationPolicy:
        if not isinstance(serialized, str):
            raise InvalidMatchingPolicyError(
                "Persisted company materialization policy must be JSON text."
            )
        try:
            raw = cast(object, json.loads(serialized))
        except (json.JSONDecodeError, TypeError) as error:
            raise InvalidMatchingPolicyError(
                "Persisted company materialization policy is invalid."
            ) from error
        if not isinstance(raw, dict) or set(raw) != _POLICY_KEYS:
            raise InvalidMatchingPolicyError(
                "Persisted company materialization policy has unsupported fields."
            )
        typed = cast(dict[str, object], raw)
        status_mapping = typed["status_mapping"]
        if status_mapping != _STATUS_MAPPING_OBJECT:
            raise InvalidMatchingPolicyError(
                "Persisted company materialization status mapping is invalid."
            )
        rules = typed["mapping_rules"]
        if not isinstance(rules, list) or any(not isinstance(rule, str) for rule in rules):
            raise InvalidMatchingPolicyError("Persisted company materialization rules are invalid.")
        try:
            result = cls(
                policy_id=_required_string(typed, "policy_id"),
                version=_required_integer(typed, "version"),
                candidate_identity_schema_version=_required_integer(
                    typed, "candidate_identity_schema_version"
                ),
                mapping_rules=tuple(CompanyMaterializationRule(rule) for rule in rules),
                schema_version=_required_integer(typed, "schema_version"),
            )
        except ValueError as error:
            raise InvalidMatchingPolicyError(
                "Persisted company materialization vocabulary is invalid."
            ) from error
        if result.to_canonical_json() != serialized:
            raise InvalidMatchingPolicyError(
                "Persisted company materialization policy is not canonical."
            )
        return result

    @property
    def digest(self) -> str:
        return sha256(self.to_canonical_json().encode("utf-8")).hexdigest()

    def to_public_redacted(self) -> RedactedCompanyMaterializationPolicy:
        return RedactedCompanyMaterializationPolicy(
            policy_id=self.policy_id,
            version=self.version,
            schema_version=self.schema_version,
            candidate_identity_schema_version=self.candidate_identity_schema_version,
            rule_count=len(self.mapping_rules),
            digest=self.digest,
        )

    def __repr__(self) -> str:
        public = self.to_public_redacted()
        return (
            "CompanyMaterializationPolicy("
            f"policy_id={public.policy_id!r}, version={public.version}, "
            f"schema_version={public.schema_version}, digest={public.digest!r})"
        )

    def _canonical_object(self) -> dict[str, object]:
        return {
            "candidate_identity_schema_version": self.candidate_identity_schema_version,
            "mapping_rules": [rule.value for rule in self.mapping_rules],
            "policy_id": self.policy_id,
            "schema_version": self.schema_version,
            "status_mapping": _STATUS_MAPPING_OBJECT,
            "version": self.version,
        }


_STATUS_MAPPING_OBJECT: dict[str, str] = {
    "ACTIVE": "ACTIVE",
    "DISSOLVED": "UNKNOWN",
    "INACTIVE": "INACTIVE",
    "MISSING": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
}
_POLICY_KEYS = {
    "candidate_identity_schema_version",
    "mapping_rules",
    "policy_id",
    "schema_version",
    "status_mapping",
    "version",
}


COMPANY_MATERIALIZATION_V1 = CompanyMaterializationPolicy(
    policy_id=COMPANY_MATERIALIZATION_POLICY_ID,
    version=1,
    candidate_identity_schema_version=CANDIDATE_IDENTITY_SCHEMA_VERSION,
    mapping_rules=tuple(CompanyMaterializationRule),
)


def materialize_company(
    *,
    policy: CompanyMaterializationPolicy,
    company_id: CompanyId,
    workspace_id: WorkspaceId,
    candidate_identity: CandidateIdentitySnapshot,
    occurred_at: datetime,
) -> Company:
    """Apply the supported policy without selecting a candidate or performing I/O."""

    if not isinstance(policy, CompanyMaterializationPolicy) or policy != (
        COMPANY_MATERIALIZATION_V1
    ):
        raise InvalidMatchingPolicyError("Company materialization policy is unsupported.")
    if not isinstance(company_id, CompanyId) or not isinstance(workspace_id, WorkspaceId):
        raise InvariantViolationError("Company materialization identifiers must be typed.")
    if not isinstance(candidate_identity, CandidateIdentitySnapshot):
        raise InvariantViolationError("Company materialization candidate identity must be typed.")
    timestamp = normalize_utc(occurred_at)
    return Company(
        id=company_id,
        workspace_id=workspace_id,
        legal_name=candidate_identity.legal_name.original_value,
        trade_name=(
            candidate_identity.trade_name.original_value
            if candidate_identity.trade_name is not None
            else None
        ),
        country_code=candidate_identity.country_code,
        status=_company_status(candidate_identity.registry_status),
        incorporated_on=candidate_identity.incorporated_on,
        official_domain=(
            candidate_identity.corporate_domain.normalized_value
            if candidate_identity.corporate_domain is not None
            else None
        ),
        legal_form=None,
        dissolved_on=None,
        created_at=timestamp,
        updated_at=timestamp,
    )


def company_snapshot_digest(
    *,
    company: Company,
    policy_digest: str,
    candidate_identity_digest: str,
) -> str:
    """Hash the closed materialized identity representation used by a decision."""

    if not isinstance(company, Company):
        raise InvariantViolationError("Company snapshot requires a typed Company.")
    _digest(policy_digest, "materialization policy digest")
    _digest(candidate_identity_digest, "candidate identity digest")
    canonical = _canonical_json(
        {
            "candidate_identity_digest": candidate_identity_digest,
            "company_id": str(company.id),
            "country_code": company.country_code.value,
            "created_at": _datetime_text(company.created_at),
            "incorporated_on": (
                company.incorporated_on.isoformat() if company.incorporated_on is not None else None
            ),
            "legal_name": company.legal_name,
            "materialization_policy_digest": policy_digest,
            "official_domain": company.official_domain,
            "status": company.status.value,
            "trade_name": company.trade_name,
            "workspace_id": str(company.workspace_id),
        }
    )
    return sha256(canonical.encode("utf-8")).hexdigest()


def _company_status(value: SourceRegistrationStatus | None) -> CompanyStatus:
    if value is SourceRegistrationStatus.ACTIVE:
        return CompanyStatus.ACTIVE
    if value is SourceRegistrationStatus.INACTIVE:
        return CompanyStatus.INACTIVE
    return CompanyStatus.UNKNOWN


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _datetime_text(value: datetime) -> str:
    return normalize_utc(value).isoformat().replace("+00:00", "Z")


def _required_string(values: dict[str, object], field_name: str) -> str:
    value = values[field_name]
    if not isinstance(value, str):
        raise InvalidMatchingPolicyError(
            "Persisted company materialization policy field type is invalid."
        )
    return value


def _required_integer(values: dict[str, object], field_name: str) -> int:
    value = values[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidMatchingPolicyError(
            "Persisted company materialization policy field type is invalid."
        )
    return value


def _digest(value: str, field_name: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise InvariantViolationError(f"{field_name} must be a lowercase SHA-256 digest.")


__all__ = [
    "COMPANY_MATERIALIZATION_POLICY_ID",
    "COMPANY_MATERIALIZATION_POLICY_SCHEMA_VERSION",
    "COMPANY_MATERIALIZATION_V1",
    "CompanyMaterializationPolicy",
    "CompanyMaterializationRule",
    "RedactedCompanyMaterializationPolicy",
    "company_snapshot_digest",
    "materialize_company",
]
