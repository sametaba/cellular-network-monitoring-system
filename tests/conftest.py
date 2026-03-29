"""
Top-level test fixtures shared by unit and integration tests.

Uses a NullPool engine so each request gets a fresh asyncpg connection,
which avoids event-loop mismatch errors when pytest-asyncio creates a new
loop per session.
"""

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.core.database import get_db
from app.main import app

# ── Test DB engine (NullPool — no connection caching) ─────────────────────────
_test_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
_TestSession = async_sessionmaker(
    _test_engine, class_=AsyncSession, expire_on_commit=False
)


async def _override_get_db():
    """Replacement for get_db that uses the NullPool test engine."""
    async with _TestSession() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@pytest.fixture(scope="session")
async def client() -> AsyncClient:
    """
    Session-scoped async HTTP client wired directly to the FastAPI app.

    The get_db dependency is overridden to use the NullPool test engine so
    that each request obtains a fresh connection (no pool reuse across
    event-loop boundaries).
    """
    app.dependency_overrides[get_db] = _override_get_db
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
    app.dependency_overrides.clear()
