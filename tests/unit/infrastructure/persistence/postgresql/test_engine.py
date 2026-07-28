"""Tests for explicit PostgreSQL engine construction."""

import pytest
from sqlalchemy.engine import Engine

from intelligence.infrastructure.persistence.postgresql.configuration import (
    DatabaseConfigurationError,
)
from intelligence.infrastructure.persistence.postgresql.engine import (
    create_postgresql_engine,
)

DATABASE_URL = "postgresql+psycopg://fatorx:local-only@127.0.0.1:55432/fatorx_test"


def test_engine_factory_requires_explicit_postgresql_configuration() -> None:
    with pytest.raises(DatabaseConfigurationError):
        create_postgresql_engine({})


def test_engine_factory_returns_distinct_caller_owned_engines() -> None:
    first = create_postgresql_engine({"DATABASE_URL": DATABASE_URL})
    second = create_postgresql_engine({"DATABASE_URL": DATABASE_URL})
    try:
        assert isinstance(first, Engine)
        assert isinstance(second, Engine)
        assert first is not second
        assert first.url.drivername == "postgresql+psycopg"
    finally:
        first.dispose()
        second.dispose()
