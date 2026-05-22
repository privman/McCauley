"""Shared pytest fixtures.

The integration tests spin up an ephemeral pgvector Postgres in Docker via
testcontainers, run Alembic against it, and yield a session factory.

Skipped automatically if Docker isn't available (so unit tests still run
in environments without Docker).
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

try:
    from testcontainers.postgres import PostgresContainer  # type: ignore[import-not-found]

    _HAS_TESTCONTAINERS = True
except ImportError:
    _HAS_TESTCONTAINERS = False


@pytest_asyncio.fixture(scope="session")
async def postgres_url() -> AsyncIterator[str]:
    if not _HAS_TESTCONTAINERS:
        pytest.skip("testcontainers not installed")
    container = PostgresContainer("pgvector/pgvector:pg16", username="t", password="t", dbname="t")
    container.start()
    try:
        # testcontainers gives us psycopg2-style URL; we need asyncpg.
        sync_url = container.get_connection_url()
        async_url = sync_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace(
            "postgresql://", "postgresql+asyncpg://"
        )
        os.environ["POSTGRES_URL"] = async_url
        # Run migrations.
        from alembic import command
        from alembic.config import Config

        cfg = Config("alembic.ini")
        cfg.set_main_option("sqlalchemy.url", async_url)
        command.upgrade(cfg, "head")
        yield async_url
    finally:
        container.stop()


@pytest_asyncio.fixture
async def session_factory(postgres_url: str) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(postgres_url, pool_pre_ping=True)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
