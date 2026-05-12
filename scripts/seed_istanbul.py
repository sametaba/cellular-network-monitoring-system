"""
Seed script: 500K synthetic cellular measurements for Istanbul's central districts.

WHAT IT DOES
------------
Generates and inserts ~500,000 synthetic LTE/NR/WCDMA signal measurements
covering 6 central Istanbul districts (Şişli, Beşiktaş, Beyoğlu, Fatih,
Kadıköy, Üsküdar) for 3 Turkish operators (Turkcell, Vodafone TR, Türk Telekom).
Measurements are spread uniformly across the last 7 days so the pipeline can
aggregate them into many distinct hourly H3 buckets.

HOW TO RUN
----------
From the project root (where .env lives):

    python scripts/seed_istanbul.py

Or inside the Docker container:

    docker-compose exec app python scripts/seed_istanbul.py

PREREQUISITES
-------------
- PostgreSQL running and reachable (DATABASE_URL in .env or environment)
- Alembic migrations applied (tables exist)
- Python environment with project dependencies installed (.venv or Docker)

TIME ESTIMATE
-------------
~2-3 minutes for 500K rows (bulk Core INSERT, 50 batches of 10K).

AFTER RUNNING
-------------
Raw measurements are stored with is_cleaned=False. You MUST trigger the
aggregation pipeline to compute H3 grid scores and populate the heatmap:

    curl -X POST http://localhost:8000/api/v1/pipeline/run \\
         -H "Content-Type: application/json" \\
         -d '{"hours_back": 168}'

Expected pipeline response:
    {"cleaned": ~500000, "rejected": ~0, "cells_upserted": N}
"""

import asyncio
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path when run as a standalone script
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.core.database import AsyncSessionLocal  # noqa: E402
from app.models.raw_measurement import Technology  # noqa: E402
from app.schemas.raw_measurement import RawMeasurementCreate  # noqa: E402
from app.services.ingestion import bulk_insert  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration — adjust here to tune the seeding run
# ---------------------------------------------------------------------------

TOTAL_MEASUREMENTS = 500_000
BATCH_SIZE = 2_000 # asyncpg max 32767 query args; 12 cols × 2000 ≈ 24000 safe
DAYS_BACK = 7  # timestamps spread uniformly over this many days

DISTRICTS: dict[str, tuple[float, float, float, float]] = {
    # name: (min_lat, min_lon, max_lat, max_lon)
    "Şişli":    (41.045, 28.975, 41.075, 29.020),
    "Beşiktaş": (41.035, 29.000, 41.090, 29.045),
    "Beyoğlu":  (41.020, 28.960, 41.045, 29.010),
    "Fatih":    (41.005, 28.930, 41.030, 28.990),
    "Kadıköy":  (40.965, 29.020, 41.000, 29.085),
    "Üsküdar":  (41.015, 29.010, 41.045, 29.060),
}

OPERATORS = ["28601", "28602", "28603"]  # Turkcell, Vodafone TR, Türk Telekom

# Technology distribution: LTE 70%, NR (5G) 25%, WCDMA 5%
_TECH_CHOICES = [Technology.LTE, Technology.NR, Technology.WCDMA]
_TECH_WEIGHTS = [0.70, 0.25, 0.05]

# Signal distribution parameters
_NORMAL_RSRP_MU = -95.0
_NORMAL_RSRP_SIGMA = 6.0
_NORMAL_RSRP_CLIP = (-110.0, -85.0)

_NORMAL_RSRQ_MU = -11.0
_NORMAL_RSRQ_SIGMA = 1.5
_NORMAL_RSRQ_CLIP = (-14.0, -8.0)

_NORMAL_SINR_MU = 15.0
_NORMAL_SINR_SIGMA = 5.0
_NORMAL_SINR_CLIP = (5.0, 25.0)

_WEAK_FRACTION = 0.05  # 5% of rows get weaker signal values


# ---------------------------------------------------------------------------
# Row generation
# ---------------------------------------------------------------------------

_DISTRICT_NAMES = list(DISTRICTS.keys())


def _generate_batch(batch_index: int, size: int, now: datetime) -> list[RawMeasurementCreate]:
    """Generate `size` synthetic RawMeasurementCreate objects for one batch."""
    rows: list[RawMeasurementCreate] = []
    global_row_offset = batch_index * size

    for i in range(size):
        # --- Location ---
        district = _DISTRICT_NAMES[random.randrange(len(_DISTRICT_NAMES))]
        min_lat, min_lon, max_lat, max_lon = DISTRICTS[district]
        lat = round(random.uniform(min_lat, max_lat), 7)
        lon = round(random.uniform(min_lon, max_lon), 7)

        # --- Operator (round-robin for equal distribution) ---
        operator_id = OPERATORS[(global_row_offset + i) % len(OPERATORS)]

        # --- Technology (weighted random) ---
        technology = random.choices(_TECH_CHOICES, weights=_TECH_WEIGHTS, k=1)[0]

        # --- Timestamp (uniform over last DAYS_BACK days) ---
        seconds_back = random.uniform(0, DAYS_BACK * 86400)
        device_ts = now - timedelta(seconds=seconds_back)

        # --- Signal values ---
        is_weak = random.random() < _WEAK_FRACTION

        if is_weak:
            rsrp = round(random.uniform(-120.0, -110.0), 1)
            rsrq = round(random.uniform(-18.0, -14.0), 1)
            sinr = round(random.uniform(0.0, 5.0), 1)
        else:
            rsrp = round(
                max(_NORMAL_RSRP_CLIP[0], min(_NORMAL_RSRP_CLIP[1],
                    random.gauss(_NORMAL_RSRP_MU, _NORMAL_RSRP_SIGMA))),
                1,
            )
            rsrq = round(
                max(_NORMAL_RSRQ_CLIP[0], min(_NORMAL_RSRQ_CLIP[1],
                    random.gauss(_NORMAL_RSRQ_MU, _NORMAL_RSRQ_SIGMA))),
                1,
            )
            sinr = round(
                max(_NORMAL_SINR_CLIP[0], min(_NORMAL_SINR_CLIP[1],
                    random.gauss(_NORMAL_SINR_MU, _NORMAL_SINR_SIGMA))),
                1,
            )

        rows.append(
            RawMeasurementCreate(
                device_timestamp=device_ts,
                lat=lat,
                lon=lon,
                precision=round(random.uniform(5.0, 50.0), 1),
                speed=None,
                bearing=None,
                operator_id=operator_id,
                technology=technology,
                cell_id=None,
                rsrp=rsrp,
                rsrq=rsrq,
                sinr=sinr,
            )
        )

    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    n_batches = TOTAL_MEASUREMENTS // BATCH_SIZE
    now = datetime.now(tz=timezone.utc)

    print("=" * 60)
    print("Istanbul Measurement Seeder")
    print("=" * 60)
    print(f"  Total rows   : {TOTAL_MEASUREMENTS:,}")
    print(f"  Batch size   : {BATCH_SIZE:,}  ({n_batches} batches)")
    print(f"  Districts    : {', '.join(_DISTRICT_NAMES)}")
    print(f"  Operators    : {', '.join(OPERATORS)}")
    print(f"  Time window  : last {DAYS_BACK} days")
    print("=" * 60)

    start = time.perf_counter()
    total_inserted = 0

    for batch_num in range(n_batches):
        rows = _generate_batch(batch_num, BATCH_SIZE, now)

        async with AsyncSessionLocal() as session:
            try:
                inserted = await bulk_insert(session, rows)
                await session.commit()
                total_inserted += inserted
                elapsed = time.perf_counter() - start
                rate = total_inserted / elapsed if elapsed > 0 else 0
                print(
                    f"  Batch {batch_num + 1:>3}/{n_batches}"
                    f"  ({total_inserted:>7,}/{TOTAL_MEASUREMENTS:,} rows)"
                    f"  {rate:,.0f} rows/s"
                )
            except Exception as exc:
                await session.rollback()
                print(f"  ERROR batch {batch_num + 1}: {exc} — skipping batch")

    elapsed = time.perf_counter() - start
    print()
    print("=" * 60)
    print(f"Done: {total_inserted:,} rows inserted in {elapsed:.1f}s")
    print("=" * 60)
    print()
    print("Next step — trigger the aggregation pipeline:")
    print()
    print(
        "  curl -X POST http://localhost:8000/api/v1/pipeline/run \\\n"
        "       -H 'Content-Type: application/json' \\\n"
        "       -d '{\"hours_back\": 168}'"
    )
    print()
    print("Expected response: {\"cleaned\": ~500000, \"rejected\": ~0, \"cells_upserted\": N}")


if __name__ == "__main__":
    asyncio.run(main())
