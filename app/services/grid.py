"""
H3 Spatial Indexing Service  (WP3)
------------------------------------
Provides hexagonal grid assignment, adaptive resolution selection, and
geometry conversion utilities built on Uber's H3 library (v4 API).

H3 encodes every point on Earth into a hierarchical hexagonal grid at
resolutions 0–15.  This project uses resolutions 7–9:

  Resolution 7  →  hex edge ≈ 1.2 km  (rural / sparse data)
  Resolution 8  →  hex edge ≈ 461 m   (suburban)
  Resolution 9  →  hex edge ≈ 174 m   (urban / dense data)

All functions in this module are pure (no DB side-effects) so they can be
unit-tested without a database connection.  DB-level helpers (get_or_create_
grid_cell, etc.) live in the aggregation service (Faz 4).
"""

from __future__ import annotations

import h3
from shapely.geometry import Polygon

# ── Adaptive resolution thresholds ───────────────────────────────────────────

RESOLUTION_HIGH: int = 9   # ~174 m hex edge — urban, dense sampling
RESOLUTION_MED: int = 8    # ~461 m hex edge — suburban
RESOLUTION_LOW: int = 7    # ~1.2 km hex edge — rural / sparse

DENSITY_HIGH_THRESHOLD: int = 50  # sample_count > 50 → resolution 9
DENSITY_MED_THRESHOLD: int = 10   # sample_count 10–50 → resolution 8
                                   # sample_count < 10  → resolution 7


# ── Core functions ────────────────────────────────────────────────────────────

def assign_h3_index(lat: float, lon: float, resolution: int = RESOLUTION_HIGH) -> str:
    """
    Return the H3 cell index that contains (lat, lon) at the given resolution.

    Uses the h3 v4 API: h3.latlng_to_cell(lat, lng, res).

    Args:
        lat:        WGS-84 latitude  [-90, 90].
        lon:        WGS-84 longitude [-180, 180].
        resolution: H3 resolution level (0–15); default 9 (~174 m edge).

    Returns:
        H3 index string, e.g. "891f1d48177ffff".

    Raises:
        h3.H3ResolotionError: if resolution is outside [0, 15].
        h3.H3ValueError: if lat/lon are out of range.
    """
    return h3.latlng_to_cell(lat, lon, resolution)


def get_adaptive_resolution(sample_count: int) -> int:
    """
    Select the optimal H3 resolution for a given sample density.

    High density → fine hexagons (more spatial detail, less noise averaging).
    Low density  → coarse hexagons (group sparse samples, reduce empty cells).

    Thresholds:
      sample_count > 50  → resolution 9  (~174 m, urban)
      10 ≤ count ≤ 50    → resolution 8  (~461 m, suburban)
      count < 10         → resolution 7  (~1.2 km, rural)

    Args:
        sample_count: Number of measurements in the area of interest.

    Returns:
        Integer resolution in {7, 8, 9}.
    """
    if sample_count > DENSITY_HIGH_THRESHOLD:
        return RESOLUTION_HIGH
    if sample_count >= DENSITY_MED_THRESHOLD:
        return RESOLUTION_MED
    return RESOLUTION_LOW


def h3_to_geojson_polygon(h3_index: str) -> dict:
    """
    Convert an H3 cell index into a GeoJSON Polygon geometry dict.

    H3 v4 returns boundary vertices as (lat, lon) pairs; GeoJSON requires
    (lon, lat) ordering (i.e. x=longitude, y=latitude).  The ring is closed
    by appending the first vertex at the end.

    Args:
        h3_index: Valid H3 cell index string.

    Returns:
        GeoJSON-compatible geometry dict:
        {
            "type": "Polygon",
            "coordinates": [[[lon0, lat0], [lon1, lat1], ..., [lon0, lat0]]]
        }
    """
    # h3.cell_to_boundary → list of (lat, lon) tuples
    boundary: list[tuple[float, float]] = h3.cell_to_boundary(h3_index)

    # Reorder to (lon, lat) for GeoJSON compliance
    coords = [[lon, lat] for lat, lon in boundary]
    coords.append(coords[0])  # close the linear ring

    return {"type": "Polygon", "coordinates": [coords]}


def h3_to_shapely_polygon(h3_index: str) -> Polygon:
    """
    Return a Shapely Polygon for the given H3 cell.

    Useful for:
      - Spatial operations (area, intersection, contains checks)
      - Feeding into GeoAlchemy2 for PostGIS WKB inserts:
            from geoalchemy2.shape import from_shape
            geom_col = from_shape(h3_to_shapely_polygon(idx), srid=4326)

    Args:
        h3_index: Valid H3 cell index string.

    Returns:
        Shapely Polygon with (lon, lat) coordinate order (EPSG:4326).
    """
    boundary: list[tuple[float, float]] = h3.cell_to_boundary(h3_index)
    # Shapely Polygon: exterior ring as (x=lon, y=lat) pairs
    return Polygon([(lon, lat) for lat, lon in boundary])


def cell_center(h3_index: str) -> tuple[float, float]:
    """
    Return the (lat, lon) geographic centroid of an H3 cell.

    Wraps h3.cell_to_latlng for a consistent, import-free interface.

    Args:
        h3_index: Valid H3 cell index string.

    Returns:
        (latitude, longitude) tuple in WGS-84 degrees.
    """
    lat, lon = h3.cell_to_latlng(h3_index)
    return lat, lon


def batch_assign_h3(
    coords: list[tuple[float, float]],
    resolution: int = RESOLUTION_HIGH,
) -> list[str]:
    """
    Assign H3 indices to a list of (lat, lon) pairs at a fixed resolution.

    Convenience wrapper for bulk operations (e.g. after a CSV upload).

    Args:
        coords:     List of (lat, lon) tuples.
        resolution: H3 resolution for all points; default 9.

    Returns:
        List of H3 index strings, one per input coordinate.
    """
    return [h3.latlng_to_cell(lat, lon, resolution) for lat, lon in coords]
