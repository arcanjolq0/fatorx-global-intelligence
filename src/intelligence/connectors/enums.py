"""Closed connector vocabulary that carries no provider-specific semantics."""

from enum import StrEnum


class ConnectorCapability(StrEnum):
    COMPANY_IDENTITY = "COMPANY_IDENTITY"
    COMPANY_REGISTRY = "COMPANY_REGISTRY"
    OWNERSHIP = "OWNERSHIP"
    CONTACTS = "CONTACTS"
    FINANCIALS = "FINANCIALS"
    INSOLVENCY = "INSOLVENCY"
    LEGAL_CASES = "LEGAL_CASES"
    SANCTIONS = "SANCTIONS"
    ADVERSE_MEDIA = "ADVERSE_MEDIA"
    DOCUMENTS = "DOCUMENTS"


class ConnectorOperation(StrEnum):
    SEARCH = "SEARCH"
    FETCH_DETAILS = "FETCH_DETAILS"
    FETCH_DOCUMENT = "FETCH_DOCUMENT"


class ConnectorAccessType(StrEnum):
    API = "API"
    FILE = "FILE"
    WEB_PUBLIC = "WEB_PUBLIC"
    USER_UPLOAD = "USER_UPLOAD"


class ConnectorMode(StrEnum):
    TEST = "TEST"
    PRODUCTION = "PRODUCTION"


class ConnectorOutcomeStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    NO_RESULTS = "NO_RESULTS"
    PARTIAL = "PARTIAL"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ConnectorErrorCode(StrEnum):
    INVALID_REQUEST = "INVALID_REQUEST"
    UNSUPPORTED_COUNTRY = "UNSUPPORTED_COUNTRY"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    POLICY_BLOCKED = "POLICY_BLOCKED"
    RATE_LIMITED = "RATE_LIMITED"
    TIMEOUT = "TIMEOUT"
    UNAVAILABLE = "UNAVAILABLE"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    CANCELLED = "CANCELLED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ArtifactRetentionMode(StrEnum):
    STORE_ORIGINAL = "STORE_ORIGINAL"
    STORE_EXCERPT_ONLY = "STORE_EXCERPT_ONLY"
    REFERENCE_ONLY = "REFERENCE_ONLY"
    EPHEMERAL_PROCESSING = "EPHEMERAL_PROCESSING"


class ConnectorCoverageKind(StrEnum):
    GLOBAL = "GLOBAL"
    COUNTRY_SET = "COUNTRY_SET"


class ConnectorWarningCode(StrEnum):
    TRUNCATED = "TRUNCATED"
    PARTIAL_DATA = "PARTIAL_DATA"
    STALE_DATA = "STALE_DATA"
    PAGINATION_LIMITED = "PAGINATION_LIMITED"
    POLICY_REDACTED = "POLICY_REDACTED"
    PARSING_WARNING = "PARSING_WARNING"


class ParsingWarningCode(StrEnum):
    UNPARSED_VALUE = "UNPARSED_VALUE"
    NORMALIZATION_LOSS = "NORMALIZATION_LOSS"
    MISSING_CONTEXT = "MISSING_CONTEXT"
    TRUNCATED = "TRUNCATED"


class ArtifactLocatorKind(StrEnum):
    INLINE_OFFSET = "INLINE_OFFSET"
    JSON_POINTER = "JSON_POINTER"
    PAGE = "PAGE"
    EXTERNAL_REFERENCE = "EXTERNAL_REFERENCE"


class UsageCostKind(StrEnum):
    KNOWN = "KNOWN"
    ESTIMATED = "ESTIMATED"


__all__ = [
    "ArtifactLocatorKind",
    "ArtifactRetentionMode",
    "ConnectorAccessType",
    "ConnectorCapability",
    "ConnectorCoverageKind",
    "ConnectorErrorCode",
    "ConnectorMode",
    "ConnectorOperation",
    "ConnectorOutcomeStatus",
    "ConnectorWarningCode",
    "ParsingWarningCode",
    "UsageCostKind",
]
