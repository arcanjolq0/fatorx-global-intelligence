"""Explicit and redacted PostgreSQL configuration loading."""

import os
from collections.abc import Mapping
from typing import Final

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

DATABASE_URL_VARIABLE: Final = "DATABASE_URL"
EXPECTED_DRIVER: Final = "postgresql+psycopg"
_CONFIGURATION_ERROR = (
    "DATABASE_URL must be set to a valid postgresql+psycopg URL with a database name."
)


class DatabaseConfigurationError(RuntimeError):
    """Database configuration is missing or incompatible with the selected stack."""


def require_database_url(environment: Mapping[str, str] | None = None) -> str:
    """Return an explicit PostgreSQL URL without ever logging its contents."""

    source = os.environ if environment is None else environment
    raw_url = source.get(DATABASE_URL_VARIABLE, "").strip()
    if not raw_url:
        raise DatabaseConfigurationError(_CONFIGURATION_ERROR)

    try:
        parsed_url = make_url(raw_url)
    except ArgumentError as error:
        raise DatabaseConfigurationError(_CONFIGURATION_ERROR) from error

    if parsed_url.drivername != EXPECTED_DRIVER or not parsed_url.database:
        raise DatabaseConfigurationError(_CONFIGURATION_ERROR)
    return raw_url


def alembic_database_url(environment: Mapping[str, str] | None = None) -> str:
    """Escape interpolation markers before assigning the URL to Alembic Config."""

    return require_database_url(environment).replace("%", "%%")


__all__ = [
    "DATABASE_URL_VARIABLE",
    "DatabaseConfigurationError",
    "alembic_database_url",
    "require_database_url",
]
