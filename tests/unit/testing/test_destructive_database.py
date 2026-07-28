"""Unit tests for the destructive PostgreSQL test safety gate."""

from __future__ import annotations

import pytest

from tests.support.destructive_database import (
    DESTRUCTIVE_DATABASE_TESTS_VARIABLE,
    DestructiveDatabaseTestSafetyError,
    require_safe_destructive_database_url,
)

VALID_DATABASE_URL = "postgresql+psycopg://fatorx:local-only@127.0.0.1:55432/fatorx_test"


def _environment(
    *,
    database_url: str = VALID_DATABASE_URL,
    consent: str | None = "1",
) -> dict[str, str]:
    environment = {"DATABASE_URL": database_url}
    if consent is not None:
        environment[DESTRUCTIVE_DATABASE_TESTS_VARIABLE] = consent
    return environment


def test_destructive_database_requires_explicit_consent() -> None:
    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(_environment(consent=None))


@pytest.mark.parametrize("consent", ["", "0", "true", "yes", " 1 "])
def test_destructive_database_rejects_incorrect_consent(consent: str) -> None:
    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(_environment(consent=consent))


@pytest.mark.parametrize(
    "database_name",
    [
        "contest",
        "production_test_backup",
        "customer_testing",
        "fatorx-test",
        "fatorx_test_",
        "FATORX_TEST",
    ],
)
def test_destructive_database_rejects_non_dedicated_names(database_name: str) -> None:
    database_url = f"postgresql+psycopg://fatorx:local-only@127.0.0.1/{database_name}"

    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(_environment(database_url=database_url))


@pytest.mark.parametrize("host", ["database", "192.168.1.20", "example.test"])
def test_destructive_database_rejects_non_local_hosts(host: str) -> None:
    database_url = f"postgresql+psycopg://fatorx:local-only@{host}/fatorx_test"

    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(_environment(database_url=database_url))


@pytest.mark.parametrize(
    "query",
    [
        "host=database.example",
        "hostaddr=192.0.2.1",
        "dbname=production",
        "service=production",
        "servicefile=production.conf",
    ],
)
def test_destructive_database_rejects_connection_query_parameters(query: str) -> None:
    database_url = f"{VALID_DATABASE_URL}?{query}"

    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(_environment(database_url=database_url))


@pytest.mark.parametrize(
    "variable_name",
    ["PGDATABASE", "PGHOST", "PGHOSTADDR", "PGPORT", "PGSERVICE", "PGSERVICEFILE"],
)
def test_destructive_database_rejects_target_altering_libpq_environment(
    variable_name: str,
) -> None:
    environment = _environment()
    environment[variable_name] = "unsafe-override"

    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(environment)


@pytest.mark.parametrize(
    "database_url",
    [
        "not-a-database-url",
        "sqlite:///fatorx_test",
        "postgresql+psycopg://fatorx:local-only@127.0.0.1",
    ],
)
def test_destructive_database_rejects_invalid_or_incompatible_urls(
    database_url: str,
) -> None:
    with pytest.raises(DestructiveDatabaseTestSafetyError):
        require_safe_destructive_database_url(_environment(database_url=database_url))


def test_destructive_database_error_does_not_reveal_credentials() -> None:
    credential_marker = "credential-must-not-appear"
    database_url = f"postgresql+psycopg://fatorx:{credential_marker}@database.example/fatorx_test"

    with pytest.raises(DestructiveDatabaseTestSafetyError) as captured:
        require_safe_destructive_database_url(_environment(database_url=database_url))

    assert credential_marker not in str(captured.value)
    assert captured.value.__cause__ is None


@pytest.mark.parametrize(
    "database_name",
    ["fatorx_test", "fatorx_test_worker_01"],
)
def test_destructive_database_accepts_strict_dedicated_names(database_name: str) -> None:
    database_url = f"postgresql+psycopg://fatorx:local-only@localhost/{database_name}"

    assert (
        require_safe_destructive_database_url(_environment(database_url=database_url))
        == database_url
    )


@pytest.mark.parametrize("url_host", ["localhost", "127.0.0.1", "[::1]"])
def test_destructive_database_accepts_only_supported_loopback_hosts(url_host: str) -> None:
    database_url = f"postgresql+psycopg://fatorx:local-only@{url_host}/fatorx_test"

    assert (
        require_safe_destructive_database_url(_environment(database_url=database_url))
        == database_url
    )


def test_consent_is_checked_before_database_url_parsing() -> None:
    with pytest.raises(DestructiveDatabaseTestSafetyError) as captured:
        require_safe_destructive_database_url(
            _environment(database_url="invalid-with-sensitive-marker", consent=None)
        )

    assert "sensitive-marker" not in str(captured.value)
