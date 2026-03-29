import type { FetchHeatmapParams, HeatmapCollection } from '../types/heatmap'
import { EMPTY_COLLECTION } from '../types/heatmap'

export async function fetchHeatmap(
  params: FetchHeatmapParams,
  signal?: AbortSignal,
): Promise<HeatmapCollection> {
  const url = new URL('/api/v1/heatmap', window.location.origin)
  url.searchParams.set('bbox', params.bbox)
  url.searchParams.set('resolution', String(params.resolution))
  if (params.operatorId) {
    url.searchParams.set('operator_id', params.operatorId)
  }

  const resp = await fetch(url.toString(), { signal })
  if (!resp.ok) {
    throw new Error(`Heatmap fetch failed: ${resp.status}`)
  }
  const data = await resp.json()
  return data as HeatmapCollection
}

export { EMPTY_COLLECTION }
