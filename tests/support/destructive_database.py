"""Safety gate for integration tests that intentionally downgrade a database."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Final

from sqlalchemy.engine import make_url

from intelligence.infrastructure.persistence.postgresql.configuration import (
    DatabaseConfigurationError,
    require_database_url,
)

DESTRUCTIVE_DATABASE_TESTS_VARIABLE: Final = "FATORX_ALLOW_DESTRUCTIVE_DATABASE_TESTS"
_ALLOWED_HOSTS: Final = frozenset({"localhost", "127.0.0.1", "::1"})
_TARGET_ALTERING_LIBPQ_VARIABLES: Final = frozenset(
    {
        "PGDATABASE",
        "PGHOST",
        "PGHOSTADDR",
        "PGPORT",
        "PGSERVICE",
        "PGSERVICEFILE",
        "PGOPTIONS",
    }
)
_DATABASE_NAME_PATTERN: Final = re.compile(
    r"fatorx_test(?:_[a-z0-9]+)*",
    flags=re.ASCII,
)
_SAFETY_ERROR: Final = (
    "Destructive database tests require explicit consent and a dedicated local "
    "fatorx_test database."
)


class DestructiveDatabaseTestSafetyError(RuntimeError):
    """The destructive-test target did not satisfy every required guard."""


def require_safe_destructive_database_url(
    environment: Mapping[str, str] | None = None,
) -> str:
    """Validate consent and a dedicated local target without opening a connection."""

    source = os.environ if environment is None else environment
    if source.get(DESTRUCTIVE_DATABASE_TESTS_VARIABLE) != "1":
        raise DestructiveDatabaseTestSafetyError(_SAFETY_ERROR)

    try:
        database_url = require_database_url(source)
        parsed_url = make_url(database_url)
    except DatabaseConfigurationError:
        raise DestructiveDatabaseTestSafetyError(_SAFETY_ERROR) from None

    database_name = parsed_url.database or ""
    if (
        parsed_url.host not in _ALLOWED_HOSTS
        or _DATABASE_NAME_PATTERN.fullmatch(database_name) is None
        or bool(parsed_url.query)
        or any(source.get(name) for name in _TARGET_ALTERING_LIBPQ_VARIABLES)
    ):
        raise DestructiveDatabaseTestSafetyError(_SAFETY_ERROR)

    return database_url


__all__ = [
    "DESTRUCTIVE_DATABASE_TESTS_VARIABLE",
    "DestructiveDatabaseTestSafetyError",
    "require_safe_destructive_database_url",
]
