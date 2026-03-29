import { useState, useCallback, useRef, useEffect, useMemo } from 'react'
import maplibregl from 'maplibre-gl'
import Map from '../components/Map'
import FilterBar from '../components/FilterBar'
import Sidebar from '../components/Sidebar'
import Legend from '../components/Legend'
import { fetchHeatmap, EMPTY_COLLECTION } from '../api/heatmap'
import type { HeatmapCollection, HeatmapFeature } from '../types/heatmap'

export default function PublicMap() {
  const [activeOperator, setActiveOperator] = useState<string | null>(null)
  const [allData, setAllData] = useState<HeatmapCollection>(EMPTY_COLLECTION)
  const [selectedCellId, setSelectedCellId] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [, setMapInstance] = useState<maplibregl.Map | null>(null)

  const bboxRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Load data (all operators, always res-9) ──────────────────
  const loadData = useCallback((bbox: string) => {
    if (abortRef.current) abortRef.current.abort()
    abortRef.current = new AbortController()

    setLoading(true)
    fetchHeatmap({ bbox, operatorId: null, resolution: 9 }, abortRef.current.signal)
      .then((data) => {
        setAllData(data)
        setLoading(false)
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          console.error('Heatmap fetch error:', err)
          setLoading(false)
        }
      })
  }, [])

  // ── Bounds change from map ───────────────────────────────────
  const handleBoundsChange = useCallback(
    (bbox: string) => {
      bboxRef.current = bbox
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        loadData(bbox)
      }, 400)
    },
    [loadData],
  )

  // ── Compute per-cell best operator & filtered display data ───
  const { displayData, operatorCounts, totalCells } = useMemo(() => {
    // Group features by grid_index
    const cellMap: Record<string, HeatmapFeature[]> = {}
    for (const f of allData.features) {
      const key = f.properties.grid_index
      if (cellMap[key]) cellMap[key].push(f)
      else cellMap[key] = [f]
    }

    // Count cells where each operator is the "best" (highest RSRP)
    const counts: Record<string, number> = {}
    const bestPerCell: Record<string, HeatmapFeature> = {}

    for (const cellId of Object.keys(cellMap)) {
      const features = cellMap[cellId]
      let best: HeatmapFeature | null = null
      for (const f of features) {
        const rsrp = f.properties.aggregated_rsrp
        if (rsrp == null) continue
        if (!best || rsrp > (best.properties.aggregated_rsrp ?? -Infinity)) {
          best = f
        }
      }
      if (best) {
        bestPerCell[cellId] = best
        const opId = best.properties.operator_id
        counts[opId] = (counts[opId] ?? 0) + 1
      }
    }

    // Build display collection
    let displayFeatures: HeatmapFeature[]
    if (activeOperator === null) {
      // "Tümü": show best operator per cell
      displayFeatures = Object.values(bestPerCell)
    } else {
      // Specific operator: show only that operator's features
      displayFeatures = allData.features.filter(
        (f) => f.properties.operator_id === activeOperator,
      )
    }

    return {
      displayData: {
        type: 'FeatureCollection' as const,
        features: displayFeatures,
      },
      operatorCounts: counts,
      totalCells: Object.keys(bestPerCell).length,
    }
  }, [allData, activeOperator])

  // ── Cell click → find all operators for that cell ────────────
  const selectedFeatures = useMemo(() => {
    if (!selectedCellId) return []
    return allData.features.filter(
      (f) => f.properties.grid_index === selectedCellId,
    )
  }, [allData, selectedCellId])

  const handleCellClick = useCallback(
    (gridIndex: string) => {
      if (!gridIndex) {
        setSelectedCellId(null)
        return
      }
      setSelectedCellId(gridIndex)
    },
    [],
  )

  const handleClose = useCallback(() => {
    setSelectedCellId(null)
  }, [])

  // Re-fetch if needed (e.g. initial load)
  useEffect(() => {
    if (bboxRef.current) loadData(bboxRef.current)
  }, [loadData])

  return (
    <div className="map-page">
      <FilterBar
        activeOperator={activeOperator}
        onOperatorChange={setActiveOperator}
        totalCount={totalCells}
        operatorCounts={operatorCounts}
        loading={loading}
      />

      <div className="map-page-body">
        <main className="map-container">
          <Map
            data={displayData}
            onBoundsChange={handleBoundsChange}
            onCellClick={handleCellClick}
            selectedCellId={selectedCellId}
            onMapReady={setMapInstance}
          />
          <Legend />
        </main>

        <Sidebar
          selectedFeatures={selectedFeatures}
          onClose={handleClose}
        />
      </div>
    </div>
  )
}
