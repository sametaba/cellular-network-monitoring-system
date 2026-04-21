import { useState, useCallback, useRef, useEffect } from 'react'
import { Link } from 'react-router-dom'
import maplibregl from 'maplibre-gl'
import { cellToBoundary } from 'h3-js'
import { ArrowLeft } from 'lucide-react'
import Map from '../components/Map'
import FilterPanel from '../components/FilterPanel'
import Sidebar from '../components/Sidebar'
import { fetchHeatmap, fetchPredictions, EMPTY_COLLECTION } from '../api/heatmap'
import { FLY_TO_DURATION } from '../constants/map'
import { polygonCentroid } from '../utils/geo'
import type { HeatmapCollection, HeatmapFeature, Resolution } from '../types/heatmap'

function mergeWithPredictions(
  real: HeatmapCollection,
  predictions: HeatmapCollection,
): HeatmapCollection {
  const realIndices = new Set(real.features.map((f) => f.properties.grid_index))
  const newPredictions = predictions.features.filter(
    (f) => !realIndices.has(f.properties.grid_index),
  )
  return {
    type: 'FeatureCollection',
    features: [...real.features, ...newPredictions],
  }
}

// Zoom level appropriate for each parent resolution
const PARENT_ZOOM_MAP: Record<number, number> = {
  8: 12.5,
  7: 11,
}

export default function PublicMap() {
  const [operatorId, setOperatorId] = useState('28601')
  const [geoData, setGeoData] = useState<HeatmapCollection>(EMPTY_COLLECTION)
  const [selectedFeature, setSelectedFeature] = useState<HeatmapFeature | null>(null)
  const [loading, setLoading] = useState(false)
  const [parentLoading, setParentLoading] = useState(false)
  const [mapInstance, setMapInstance] = useState<maplibregl.Map | null>(null)
  const [parentHexGeo, setParentHexGeo] = useState<HeatmapCollection | null>(null)

  const bboxRef = useRef<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const predictAbortRef = useRef<AbortController | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // ── Load data (always res-9) + AI predictions ─────────────
  const loadData = useCallback(
    (bbox: string, op: string) => {
      if (abortRef.current) abortRef.current.abort()
      if (predictAbortRef.current) predictAbortRef.current.abort()
      abortRef.current = new AbortController()

      setLoading(true)
      fetchHeatmap({ bbox, operatorId: op, resolution: 9 }, abortRef.current.signal)
        .then((realData) => {
          setGeoData(realData)
          setLoading(false)

          // Fire AI predictions fetch in background (non-blocking)
          predictAbortRef.current = new AbortController()
          fetchPredictions(
            { bbox, operatorId: op },
            predictAbortRef.current.signal,
          )
            .then((predData) => {
              if (predData.features.length > 0) {
                setGeoData((prev) => mergeWithPredictions(prev, predData))
              }
            })
            .catch((err) => {
              if (err.name !== 'AbortError') {
                console.warn('Predictions fetch error (non-critical):', err)
              }
            })
        })
        .catch((err) => {
          if (err.name !== 'AbortError') {
            console.error('Heatmap fetch error:', err)
            setLoading(false)
          }
        })
    },
    [],
  )

  // ── Bounds change from map ─────────────────────────────────
  const handleBoundsChange = useCallback(
    (bbox: string) => {
      bboxRef.current = bbox
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        loadData(bbox, operatorId)
      }, 400)
    },
    [operatorId, loadData],
  )

  // Re-fetch when operator changes
  useEffect(() => {
    if (bboxRef.current) {
      loadData(bboxRef.current, operatorId)
    }
  }, [operatorId]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleRefresh = useCallback(() => {
    if (bboxRef.current) loadData(bboxRef.current, operatorId)
  }, [operatorId, loadData])

  // ── Navigate to parent hex ─────────────────────────────────
  const handleNavigateParent = useCallback(
    async (parentGridIndex: string, resolution: number) => {
      if (!mapInstance) return
      setParentLoading(true)

      try {
        // Compute parent hex boundary via h3-js
        const boundary = cellToBoundary(parentGridIndex) // [[lat,lon], ...]
        const lats = boundary.map((v) => v[0])
        const lons = boundary.map((v) => v[1])
        const pad = 0.005

        const parentBbox = `${Math.min(...lons) - pad},${Math.min(...lats) - pad},${Math.max(...lons) + pad},${Math.max(...lats) + pad}`

        const data = await fetchHeatmap({
          bbox: parentBbox,
          operatorId,
          resolution: resolution as Resolution,
        })

        // Find the specific parent feature
        const parentFeature = data.features.find(
          (f) => f.properties.grid_index === parentGridIndex,
        )

        if (parentFeature) {
          setSelectedFeature(parentFeature)
        }

        // Build parent hex polygon GeoJSON for border highlight
        const coords = boundary.map((v) => [v[1], v[0]] as [number, number])
        coords.push(coords[0]) // close the ring
        setParentHexGeo({
          type: 'FeatureCollection',
          features: [{
            type: 'Feature',
            geometry: { type: 'Polygon', coordinates: [coords] },
            properties: parentFeature?.properties ?? {} as any,
          }],
        })

        // Fly to the CURRENT child hex centroid, zoom out to parent level.
        // This keeps the user's focus point centered while zooming out.
        const targetZoom = PARENT_ZOOM_MAP[resolution] ?? 11.5

        let flyCenter: [number, number]
        if (selectedFeature) {
          // Stay centered on where the user was looking
          flyCenter = polygonCentroid(selectedFeature.geometry.coordinates[0])
        } else {
          // Fallback: parent hex centroid
          flyCenter = [
            coords.reduce((s, c) => s + c[0], 0) / coords.length,
            coords.reduce((s, c) => s + c[1], 0) / coords.length,
          ]
        }

        mapInstance.flyTo({
          center: flyCenter,
          zoom: targetZoom,
          duration: FLY_TO_DURATION,
        })
      } catch (err) {
        console.error('Parent hex fetch error:', err)
      } finally {
        setParentLoading(false)
      }
    },
    [mapInstance, operatorId, selectedFeature],
  )

  return (
    <div className="map-layout">
      <FilterPanel
        operatorId={operatorId}
        featureCount={geoData.features.length}
        loading={loading}
        onOperatorChange={setOperatorId}
        onRefresh={handleRefresh}
      />

      <main className="map-container">
        <Link to="/" className="map-back-btn">
          <ArrowLeft size={14} /> Anasayfa
        </Link>
        <Map
          data={geoData}
          onBoundsChange={handleBoundsChange}
          onFeatureSelect={setSelectedFeature}
          selectedFeatureId={selectedFeature?.properties.grid_index ?? null}
          onMapReady={setMapInstance}
          parentHexGeojson={parentHexGeo}
        />
      </main>

      <Sidebar
        feature={selectedFeature}
        onClose={() => { setSelectedFeature(null); setParentHexGeo(null) }}
        onNavigateParent={handleNavigateParent}
        parentLoading={parentLoading}
      />
    </div>
  )
}
