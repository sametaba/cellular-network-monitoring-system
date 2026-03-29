from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import router as api_v1_router
from app.core.config import settings
from app.core.database import AsyncSessionLocal, engine
from app.core.scheduler import start_scheduler, stop_scheduler
from app.models.base import Base


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application startup / shutdown lifecycle.

    On startup : creates all tables that don't exist yet (development
                 convenience).  In production, run Alembic migrations instead.
                 Starts the APScheduler background aggregation job.
    On shutdown: stops the scheduler, then disposes the connection pool.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    start_scheduler(AsyncSessionLocal)
    yield
    stop_scheduler()
    await engine.dispose()


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    debug=settings.APP_DEBUG,
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# Allows the React dev server (localhost:5173) and the production frontend to
# call the API.  The CORS_ORIGINS setting controls allowed origins.
_origins = (
    ["*"]
    if settings.CORS_ORIGINS == "*"
    else [o.strip() for o in settings.CORS_ORIGINS.split(",")]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(api_v1_router)

# ── Static frontend — served at /map/ ─────────────────────────────────────────
# html=True → GET /map/ automatically serves static/index.html
app.mount("/map", StaticFiles(directory="static", html=True), name="static")
