"""Tests for the dependency-free repository secret scanner."""

from pathlib import Path

from scripts.check_secrets import scan_repository


def test_scanner_detects_an_assigned_secret_without_echoing_it(tmp_path: Path) -> None:
    """A credential-like assignment is reported by location and pattern only."""

    secret_file = tmp_path / "unsafe.env"
    secret_file.write_text('api_key = "' + ("x" * 24) + '"\n', encoding="utf-8")

    findings = scan_repository(tmp_path)

    assert len(findings) == 1
    assert findings[0].path == secret_file
    assert findings[0].pattern_name == "assigned-secret"


def test_scanner_allows_empty_environment_placeholders(tmp_path: Path) -> None:
    """An empty example variable is documentation, not a credential."""

    (tmp_path / ".env").write_text("FUTURE_CREDENTIAL=\n", encoding="utf-8")

    assert scan_repository(tmp_path) == []


def test_repository_contains_no_obvious_secret_values() -> None:
    """The current repository passes its own basic scanner."""

    repository_root = Path(__file__).parents[2]

    assert scan_repository(repository_root) == []
