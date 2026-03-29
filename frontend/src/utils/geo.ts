import type { FeatureCollection, Point } from 'geojson'
import type { HeatmapCollection } from '../types/heatmap'

interface PointProperties {
  quality_score: number | null
  sample_count: number | null
  grid_index: string
}

/**
 * Derive a Point FeatureCollection from polygon features.
 * Centroid = arithmetic mean of the exterior ring vertices
 * (excluding the closing duplicate vertex).
 *
 * H3 hexagons have exactly 6 vertices → O(n) with minimal overhead.
 */
export function polygonsToPoints(
  polygons: HeatmapCollection,
): FeatureCollection<Point, PointProperties> {
  const features = polygons.features.map((f) => {
    const ring = f.geometry.coordinates[0]
    const verts = ring.slice(0, -1) // exclude closing vertex
    const lon = verts.reduce((s, v) => s + v[0], 0) / verts.length
    const lat = verts.reduce((s, v) => s + v[1], 0) / verts.length

    return {
      type: 'Feature' as const,
      geometry: { type: 'Point' as const, coordinates: [lon, lat] },
      properties: {
        quality_score: f.properties.quality_score,
        sample_count: f.properties.sample_count,
        grid_index: f.properties.grid_index,
      },
    }
  })

  return { type: 'FeatureCollection', features }
}

/**
 * Compute the centroid [lon, lat] of a GeoJSON Polygon.
 */
export function polygonCentroid(coords: number[][]): [number, number] {
  const verts = coords.slice(0, -1)
  const lon = verts.reduce((s, v) => s + v[0], 0) / verts.length
  const lat = verts.reduce((s, v) => s + v[1], 0) / verts.length
  return [lon, lat]
}
