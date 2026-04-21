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

export interface FetchPredictionsParams {
  bbox: string
  operatorId: string | null
}

export async function fetchPredictions(
  params: FetchPredictionsParams,
  signal?: AbortSignal,
): Promise<HeatmapCollection> {
  const url = new URL('/api/v1/insights/predict-coverage', window.location.origin)
  url.searchParams.set('bbox', params.bbox)
  if (params.operatorId) {
    url.searchParams.set('operator_id', params.operatorId)
  }

  try {
    const resp = await fetch(url.toString(), { signal })
    if (!resp.ok) {
      console.warn(`Predictions fetch failed: ${resp.status}`)
      return EMPTY_COLLECTION
    }
    return (await resp.json()) as HeatmapCollection
  } catch (err: unknown) {
    if (err instanceof Error && err.name === 'AbortError') throw err
    console.warn('Predictions fetch error:', err)
    return EMPTY_COLLECTION
  }
}

export { EMPTY_COLLECTION }
