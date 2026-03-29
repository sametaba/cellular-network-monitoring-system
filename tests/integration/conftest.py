"""
Integration test fixtures — DB isolation using a reserved operator_id.

All integration tests use operator_id="99999" which is never used in
production data.  An autouse fixture deletes all rows with this operator_id
before and after each test so tests are independent and leave no garbage.

Uses a NullPool engine to avoid event-loop mismatch issues with asyncpg.
"""

import pytest
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.grid_score import GridScore
from app.models.raw_measurement import RawMeasurement

TEST_OPERATOR_ID = "99999"

_cleanup_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool)
_CleanupSession = async_sessionmaker(
    _cleanup_engine, class_=AsyncSession, expire_on_commit=False
)


async def _delete_test_data():
    async with _CleanupSession() as session:
        async with session.begin():
            await session.execute(
                delete(GridScore).where(GridScore.operator_id == TEST_OPERATOR_ID)
            )
            await session.execute(
                delete(RawMeasurement).where(
                    RawMeasurement.operator_id == TEST_OPERATOR_ID
                )
            )


@pytest.fixture(autouse=True)
async def clean_test_data():
    """Delete all rows tagged with the test operator_id before and after each test."""
    await _delete_test_data()
    yield
    await _delete_test_data()
