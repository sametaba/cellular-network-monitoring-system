"""
Background Scheduler  (APScheduler 3.x)
-----------------------------------------
Runs the aggregation job every 15 minutes so grid_scores stays up to date
without requiring manual pipeline triggers.

Lifecycle:
  start_scheduler(session_factory) — call on FastAPI startup
  stop_scheduler()                 — call on FastAPI shutdown

The scheduler is module-level so it can be stopped from any import context.
"""

from __future__ import annotations

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Module-level scheduler instance (singleton per process)
_scheduler: AsyncIOScheduler = AsyncIOScheduler(timezone="UTC")

# How many hours of data the scheduled job re-aggregates each run.
# 1 hour covers data written since the last 15-minute tick with headroom.
_JOB_HOURS_BACK: int = 1


def start_scheduler(session_factory) -> None:
    """
    Register and start the aggregation background job.

    Args:
        session_factory: The async session factory (e.g. AsyncSessionLocal)
                         from app.core.database.  Passed in to avoid a
                         circular import between core modules.
    """
    from app.services.aggregation import run_aggregation  # deferred import

    async def _aggregation_job() -> None:
        """Scheduled task: aggregate the last hour of cleaned measurements."""
        async with session_factory() as session:
            async with session.begin():
                n = await run_aggregation(session, hours_back=_JOB_HOURS_BACK)
        logger.info("Scheduled aggregation complete: %d grid_scores upserted", n)

    _scheduler.add_job(
        _aggregation_job,
        trigger="interval",
        minutes=15,
        id="aggregation_job",
        replace_existing=True,
        misfire_grace_time=60,  # allow up to 60s late start before skipping
    )
    _scheduler.start()
    logger.info("APScheduler started — aggregation job every 15 minutes")


def stop_scheduler() -> None:
    """Gracefully shut down the scheduler on application exit."""
    if _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler stopped")
