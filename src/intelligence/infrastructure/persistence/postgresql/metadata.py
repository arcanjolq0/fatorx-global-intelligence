"""Shared SQLAlchemy metadata for PostgreSQL tables."""

from sqlalchemy import MetaData

from intelligence.infrastructure.persistence.postgresql.naming import NAMING_CONVENTION

metadata = MetaData(naming_convention=NAMING_CONVENTION)

__all__ = ["metadata"]
