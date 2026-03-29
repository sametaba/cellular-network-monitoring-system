import type { Feature, FeatureCollection, Polygon } from 'geojson'

export interface HeatmapProperties {
  grid_index: string
  operator_id: string
  quality_score: number | null
  aggregated_rsrp: number | null
  aggregated_rsrq: number | null
  aggregated_sinr: number | null
  sample_count: number | null
  confidence_score: number | null
  time_bucket: string | null
  qoe_index: number | null
  estimated_mos: number | null
  fit_streaming: boolean | null
  fit_volte: boolean | null
}

export type HeatmapFeature = Feature<Polygon, HeatmapProperties>
export type HeatmapCollection = FeatureCollection<Polygon, HeatmapProperties>

export const EMPTY_COLLECTION: HeatmapCollection = {
  type: 'FeatureCollection',
  features: [],
}

export type Resolution = 7 | 8 | 9

export interface FetchHeatmapParams {
  bbox: string
  operatorId: string | null
  resolution: Resolution
}

export interface ScoreInfo {
  label: string
  color: string
  textColor: string
}

export function getScoreInfo(score: number | null): ScoreInfo {
  if (score === null) return { label: 'No Data', color: '#475569', textColor: '#e2e8f0' }
  if (score >= 4.5)   return { label: 'Excellent', color: '#22c55e', textColor: '#052e16' }
  if (score >= 4.0)   return { label: 'Good',      color: '#84cc16', textColor: '#1a2e05' }
  if (score >= 3.0)   return { label: 'Fair',       color: '#eab308', textColor: '#1c1917' }
  if (score >= 2.0)   return { label: 'Poor',       color: '#f97316', textColor: '#1c1917' }
  return                     { label: 'Very Poor',  color: '#ef4444', textColor: '#fff1f2' }
}
