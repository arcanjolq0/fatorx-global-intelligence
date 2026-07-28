"""Tests for minimal semantic and policy versions."""

import pytest

from intelligence.connectors.errors import (
    InvalidConnectorIdentifierError,
    InvalidSemanticVersionError,
)
from intelligence.connectors.versions import (
    CONNECTOR_CONTRACT_VERSION,
    SUPPORTED_CONTRACT_MAJORS,
    SemanticVersion,
    SourcePolicyVersion,
)


def test_semantic_version_parse_order_hash_and_compatibility() -> None:
    first = SemanticVersion.parse("1.2.3")
    compatible = SemanticVersion(1, 9, 0)
    later = SemanticVersion(2, 0, 0)

    assert str(first) == "1.2.3"
    assert first < compatible < later
    assert hash(first) == hash(SemanticVersion(1, 2, 3))
    assert first.is_compatible_with(compatible)
    assert not first.is_compatible_with(later)
    assert not first.is_compatible_with("1.2.3")
    assert SemanticVersion(1, 0, 0) == CONNECTOR_CONTRACT_VERSION
    assert frozenset({1}) == SUPPORTED_CONTRACT_MAJORS


@pytest.mark.parametrize(
    "value",
    [
        "",
        "1",
        "1.2",
        "1.2.3.4",
        " 1.2.3",
        "1.2.3 ",
        "+1.2.3",
        "01.2.3",
        "1.-2.3",
        "1.2.x",
        "1.2.3-alpha",
        "1.2.3+build",
    ],
)
def test_semantic_version_parse_rejects_noncanonical_forms(value: str) -> None:
    with pytest.raises(InvalidSemanticVersionError):
        SemanticVersion.parse(value)


@pytest.mark.parametrize("components", [(-1, 0, 0), (1, -1, 0), (1, 0, -1), (True, 0, 0)])
def test_semantic_version_rejects_invalid_components(components: tuple[int, int, int]) -> None:
    with pytest.raises(InvalidSemanticVersionError):
        SemanticVersion(*components)


def test_semantic_version_rejects_non_text_parse_input() -> None:
    with pytest.raises(InvalidSemanticVersionError):
        SemanticVersion.parse(123)  # type: ignore[arg-type]


def test_semantic_version_comparison_with_other_type_is_not_supported() -> None:
    with pytest.raises(TypeError):
        _ = SemanticVersion(1, 0, 0) < "1.0.0"


def test_source_policy_version_is_strong_and_canonical() -> None:
    version = SourcePolicyVersion("policy-2026.07")

    assert str(version) == "policy-2026.07"
    with pytest.raises(InvalidConnectorIdentifierError):
        SourcePolicyVersion("policy version")
