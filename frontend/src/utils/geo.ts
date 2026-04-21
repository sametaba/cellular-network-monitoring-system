/**
 * Compute the centroid [lon, lat] of a GeoJSON Polygon exterior ring.
 */
export function polygonCentroid(coords: number[][]): [number, number] {
  const verts = coords.slice(0, -1) // exclude closing vertex
  const lon = verts.reduce((s, v) => s + v[0], 0) / verts.length
  const lat = verts.reduce((s, v) => s + v[1], 0) / verts.length
  return [lon, lat]
}
