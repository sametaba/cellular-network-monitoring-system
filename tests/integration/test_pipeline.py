"""
Integration tests for POST /api/v1/pipeline/run

Flow tested:
  1. POST /api/v1/measurements/batch  — seed raw (is_cleaned=False) data
  2. POST /api/v1/pipeline/run        — clean + score + aggregate
  3. Assert response fields are sensible (cleaned > 0, cells_upserted > 0)
"""

from datetime import datetime, timezone

import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_OPERATOR_ID

_TS = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()

# Minimal valid measurements (Istanbul area, valid signal ranges)
def _make_batch(n: int = 20) -> list[dict]:
    return [
        {
            "device_timestamp": _TS,
            "lat": 41.0 + i * 0.001,
            "lon": 29.0 + i * 0.001,
            "precision": 15.0,
            "speed": 0.5,
            "operator_id": TEST_OPERATOR_ID,
            "technology": "LTE",
            "rsrp": -90.0,
            "rsrq": -10.0,
            "sinr": 5.0,
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_pipeline_run_basic(client: AsyncClient):
    """Batch-insert raw measurements → run pipeline → cleaned and cells_upserted positive."""
    # Step 1: seed raw uncleaned measurements via batch endpoint
    batch_resp = await client.post(
        "/api/v1/measurements/batch",
        json=_make_batch(20),
    )
    assert batch_resp.status_code == 202, batch_resp.text
    batch_data = batch_resp.json()
    assert batch_data["accepted"] > 0

    # Step 2: run pipeline
    pipe_resp = await client.post(
        "/api/v1/pipeline/run",
        json={"operator_id": TEST_OPERATOR_ID, "hours_back": 24},
    )
    assert pipe_resp.status_code == 200, pipe_resp.text

    result = pipe_resp.json()
    assert "cleaned" in result
    assert "rejected" in result
    assert "cells_upserted" in result

    # Step 3: verify
    assert result["cleaned"] > 0, f"Expected cleaned > 0, got {result}"
    assert result["cells_upserted"] > 0, f"Expected cells_upserted > 0, got {result}"
    assert result["cleaned"] + result["rejected"] == batch_data["accepted"]


@pytest.mark.asyncio
async def test_pipeline_run_twice_is_idempotent(client: AsyncClient):
    """Running the pipeline twice should not clean rows a second time."""
    # Seed raw uncleaned rows
    batch_resp = await client.post(
        "/api/v1/measurements/batch",
        json=_make_batch(10),
    )
    assert batch_resp.status_code == 202

    # First run — should clean the inserted rows
    r1 = await client.post(
        "/api/v1/pipeline/run",
        json={"operator_id": TEST_OPERATOR_ID, "hours_back": 24},
    )
    assert r1.status_code == 200
    first = r1.json()
    assert first["cleaned"] > 0, "First pipeline run should clean the inserted rows"

    # Second run — no new uncleaned rows → cleaned must be 0
    r2 = await client.post(
        "/api/v1/pipeline/run",
        json={"operator_id": TEST_OPERATOR_ID, "hours_back": 24},
    )
    assert r2.status_code == 200
    second = r2.json()
    assert second["cleaned"] == 0, "No new rows to clean on second run"


@pytest.mark.asyncio
async def test_pipeline_run_hours_back_validation(client: AsyncClient):
    """hours_back outside [1, 168] should return 422."""
    resp = await client.post(
        "/api/v1/pipeline/run",
        json={"hours_back": 0},
    )
    assert resp.status_code == 422

    resp2 = await client.post(
        "/api/v1/pipeline/run",
        json={"hours_back": 169},
    )
    assert resp2.status_code == 422
