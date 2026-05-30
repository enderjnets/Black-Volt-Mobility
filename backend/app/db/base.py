"""Async SQLAlchemy 2.x setup — engine, session, FastAPI dep, declarative Base.

Multi-tenant ready: every domain model carries a `tenant_id`. For the MVP there
is a single tenant (Black Volt) but all queries scope by tenant so activating
other drivers (SaaS) never requires a rewrite.
"""
from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import Enum as SqlEnum
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models. Alembic autogenerate scans Base.metadata."""

    pass


def pg_enum(enum_cls: type, *, name: str) -> SqlEnum:
    """SQLAlchemy Enum column keyed on the members' lowercase `.value`, not the
    UPPERCASE Python name. Always wrap str-enums with this helper so the values
    match the Postgres enum declared in the migration."""
    return SqlEnum(enum_cls, name=name, values_callable=lambda x: [e.value for e in x])


_engine: AsyncEngine | None = None
_SessionLocal: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.DEBUG and settings.APP_ENV == "development",
            future=True,
            # NullPool: a fresh asyncpg connection per checkout, closed with the
            # session. Avoids reusing a pooled connection across event loops
            # (the source of "Event loop is closed" under TestClient) and is fine
            # for the MVP's traffic. Revisit pooling when scaling.
            poolclass=NullPool,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = async_sessionmaker(
            get_engine(),
            expire_on_commit=False,
            autoflush=False,
            class_=AsyncSession,
        )
    return _SessionLocal


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency. Yields a session, rolls back on exception, always closes."""
    session = get_session_factory()()
    try:
        yield session
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def dispose_engine() -> None:
    global _engine, _SessionLocal
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _SessionLocal = None


__all__: list[str] = [
    "Base",
    "get_engine",
    "get_session_factory",
    "get_db",
    "dispose_engine",
    "pg_enum",
]
