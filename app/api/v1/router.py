from fastapi import APIRouter

from app.api.v1.endpoints.heatmap import router as heatmap_router
from app.api.v1.endpoints.insights import router as insights_router
from app.api.v1.endpoints.measurements import router as measurements_router
from app.api.v1.endpoints.pipeline import router as pipeline_router

# Central API v1 router.
router = APIRouter(prefix="/api/v1")

# ── Health ────────────────────────────────────────────────────────────────────
@router.get("/health", tags=["health"])
async def health_check() -> dict:
    """Liveness probe — returns 200 when the app is running."""
    return {"status": "ok"}


# ── Domain sub-routers ────────────────────────────────────────────────────────
router.include_router(measurements_router)
router.include_router(heatmap_router,  prefix="/heatmap")
router.include_router(pipeline_router, prefix="/pipeline")
router.include_router(insights_router,  prefix="/insights")
