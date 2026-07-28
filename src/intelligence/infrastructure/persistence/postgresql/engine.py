"""Explicit PostgreSQL engine construction without import-time side effects."""

from collections.abc import Mapping

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from intelligence.infrastructure.persistence.postgresql.configuration import (
    require_database_url,
)


def create_postgresql_engine(environment: Mapping[str, str] | None = None) -> Engine:
    """Create a caller-owned synchronous engine from the required configuration."""

    return create_engine(require_database_url(environment))


__all__ = ["create_postgresql_engine"]
