"""
Integration tests for GET /api/v1/heatmap

Flow:
  1. Seed data for TEST_OPERATOR_ID
  2. Run pipeline to produce grid_scores
  3. Query heatmap endpoint and validate GeoJSON response
"""

import pytest
from httpx import AsyncClient

from tests.integration.conftest import TEST_OPERATOR_ID

_BBOX_STR = "28.9,41.0,29.1,41.1"
_BBOX_SIM = [41.0, 28.9, 41.1, 29.1]


async def _seed_and_run(client: AsyncClient, count: int = 50):
    """Helper: simulate data (query params) and run pipeline for the test operator."""
    # simulate uses query params, not request body
    sim = await client.post(
        "/api/v1/measurements/simulate",
        params={
            "count": count,
            "min_lat": 41.0,
            "min_lon": 28.9,
            "max_lat": 41.1,
            "max_lon": 29.1,
            "operator_id": TEST_OPERATOR_ID,
        },
    )
    assert sim.status_code == 201, sim.text
    pipe = await client.post(
        "/api/v1/pipeline/run",
        json={"operator_id": TEST_OPERATOR_ID, "hours_back": 24},
    )
    assert pipe.status_code == 200, pipe.text


# ── GeoJSON format validation ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heatmap_returns_feature_collection(client: AsyncClient):
    await _seed_and_run(client)
    resp = await client.get(
        "/api/v1/heatmap",
        params={"bbox": _BBOX_STR, "operator_id": TEST_OPERATOR_ID},
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["type"] == "FeatureCollection"
    assert "features" in data
    assert isinstance(data["features"], list)


@pytest.mark.asyncio
async def test_heatmap_features_have_correct_structure(client: AsyncClient):
    await _seed_and_run(client)
    resp = await client.get(
        "/api/v1/heatmap",
        params={"bbox": _BBOX_STR, "operator_id": TEST_OPERATOR_ID},
    )
    data = resp.json()

    assert len(data["features"]) > 0, "Should have at least one feature after pipeline"

    for feature in data["features"]:
        assert feature["type"] == "Feature"
        assert "geometry" in feature
        assert "properties" in feature

        geo = feature["geometry"]
        assert geo["type"] == "Polygon"
        assert "coordinates" in geo
        coords = geo["coordinates"][0]
        # Ring must be closed (first == last)
        assert coords[0] == coords[-1], "Polygon ring must be closed"
        # Each coordinate is [lon, lat]
        for lon, lat in coords:
            assert -180 <= lon <= 180
            assert -90  <= lat <= 90


@pytest.mark.asyncio
async def test_heatmap_properties_in_valid_range(client: AsyncClient):
    await _seed_and_run(client)
    resp = await client.get(
        "/api/v1/heatmap",
        params={"bbox": _BBOX_STR, "operator_id": TEST_OPERATOR_ID},
    )
    data = resp.json()

    for feature in data["features"]:
        props = feature["properties"]

        # Required fields present
        assert "quality_score" in props
        assert "confidence_score" in props
        assert "sample_count" in props
        assert "operator_id" in props
        assert "time_bucket" in props

        # quality_score in [1, 5] when present
        if props["quality_score"] is not None:
            assert 1.0 <= props["quality_score"] <= 5.0, (
                f"quality_score out of range: {props['quality_score']}"
            )

        # confidence_score in [0, 1] when present
        if props["confidence_score"] is not None:
            assert 0.0 <= props["confidence_score"] <= 1.0, (
                f"confidence_score out of range: {props['confidence_score']}"
            )

        # sample_count positive
        if props["sample_count"] is not None:
            assert props["sample_count"] > 0


# ── Bbox and query parameter validation ──────────────────────────────────────

@pytest.mark.asyncio
async def test_heatmap_missing_bbox_returns_422(client: AsyncClient):
    resp = await client.get("/api/v1/heatmap")
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_invalid_bbox_format_returns_422(client: AsyncClient):
    resp = await client.get("/api/v1/heatmap", params={"bbox": "notabbox"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_invalid_bbox_values_returns_422(client: AsyncClient):
    # longitude out of [-180, 180]
    resp = await client.get("/api/v1/heatmap", params={"bbox": "200,41,201,42"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_heatmap_empty_bbox_returns_empty_features(client: AsyncClient):
    # A bbox in the middle of the ocean — no data there
    resp = await client.get(
        "/api/v1/heatmap",
        params={"bbox": "-10.0,0.0,-9.0,1.0", "operator_id": TEST_OPERATOR_ID},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


@pytest.mark.asyncio
async def test_heatmap_operator_filter_isolates_data(client: AsyncClient):
    """Data seeded for TEST_OPERATOR_ID should not appear under a different operator."""
    await _seed_and_run(client)

    # Query with a different operator that has no data
    resp = await client.get(
        "/api/v1/heatmap",
        params={"bbox": _BBOX_STR, "operator_id": "11111"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # Should have no features for this unrelated operator
    test_op_features = [
        f for f in data["features"]
        if f["properties"]["operator_id"] == TEST_OPERATOR_ID
    ]
    assert test_op_features == []
