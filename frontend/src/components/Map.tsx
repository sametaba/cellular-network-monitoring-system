import { useEffect, useRef, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { HeatmapCollection, HeatmapFeature } from '../types/heatmap'
import { polygonCentroid } from '../utils/geo'
import {
  BASEMAP,
  ISTANBUL,
  INITIAL_ZOOM,
  ZOOM_HEX_VISIBLE,
  ZOOM_FLY_TO,
  FLY_TO_DURATION,
  SOURCE_POLYGON,
  LAYER_FILL,
  LAYER_OUTLINE,
  LAYER_OUTLINE_AI,
  LAYER_SELECTED,
  SOURCE_PARENT_HEX,
  LAYER_PARENT_BORDER,
} from '../constants/map'

interface MapProps {
  data: HeatmapCollection
  onBoundsChange: (bbox: string) => void
  onFeatureSelect: (feature: HeatmapFeature | null) => void
  selectedFeatureId: string | null
  onMapReady?: (map: maplibregl.Map) => void
  parentHexGeojson?: HeatmapCollection | null
}

export default function Map({
  data,
  onBoundsChange,
  onFeatureSelect,
  selectedFeatureId,
  onMapReady,
  parentHexGeojson,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const hoveredIdRef = useRef<string | number | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const getBbox = useCallback((map: maplibregl.Map): string => {
    const b = map.getBounds()
    return `${b.getWest()},${b.getSouth()},${b.getEast()},${b.getNorth()}`
  }, [])

  // ── Initialise map once ────────────────────────────────────────
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const map = new maplibregl.Map({
      container: containerRef.current,
      style: BASEMAP,
      center: ISTANBUL,
      zoom: INITIAL_ZOOM,
      attributionControl: false,
    })

    map.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right')
    map.addControl(new maplibregl.NavigationControl(), 'bottom-right')

    map.on('load', () => {
      // ── Sources ──────────────────────────────────────────────
      map.addSource(SOURCE_POLYGON, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        generateId: true,
      })

      // ── Layer 1: Hex fill (quality-colored, static opacity) ──
      map.addLayer({
        id: LAYER_FILL,
        type: 'fill',
        source: SOURCE_POLYGON,
        minzoom: ZOOM_HEX_VISIBLE,
        paint: {
          'fill-color': [
            'step',
            ['coalesce', ['get', 'quality_score'], 0],
            '#ef4444',
            2, '#f97316',
            3, '#eab308',
            4, '#84cc16',
            4.5, '#22c55e',
          ],
          'fill-opacity': [
            'case',
            // AI-predicted cells: semi-transparent
            ['==', ['get', 'is_ai_predicted'], true],
            0.35,
            // Hovered real cells: bright
            ['boolean', ['feature-state', 'hovered'], false],
            0.75,
            // Default real cells: clear and readable
            0.6,
          ],
        },
      })

      // ── Layer 2: Hex outline — real cells ────────────────────
      map.addLayer({
        id: LAYER_OUTLINE,
        type: 'line',
        source: SOURCE_POLYGON,
        minzoom: ZOOM_HEX_VISIBLE,
        filter: ['any',
          ['!', ['has', 'is_ai_predicted']],
          ['!=', ['get', 'is_ai_predicted'], true],
        ],
        paint: {
          'line-color': 'rgba(99,102,241,0.65)',
          'line-width': 1.0,
          'line-opacity': 1,
        },
      })

      // ── Layer 3: Hex outline — AI cells (dashed, purple) ─────
      map.addLayer({
        id: LAYER_OUTLINE_AI,
        type: 'line',
        source: SOURCE_POLYGON,
        minzoom: ZOOM_HEX_VISIBLE,
        filter: ['==', ['get', 'is_ai_predicted'], true],
        paint: {
          'line-color': 'rgba(168,85,247,0.7)',
          'line-width': 1.2,
          'line-dasharray': [4, 3],
          'line-opacity': 1,
        },
      })

      // ── Layer 4: Selected hex highlight ──────────────────────
      map.addLayer({
        id: LAYER_SELECTED,
        type: 'line',
        source: SOURCE_POLYGON,
        minzoom: ZOOM_HEX_VISIBLE,
        paint: {
          'line-color': '#818cf8',
          'line-width': 3,
          'line-opacity': 1,
        },
        filter: ['==', ['get', 'grid_index'], ''],
      })

      // ── Layer 5: Parent hex border (neon yellow dashed) ───────
      map.addSource(SOURCE_PARENT_HEX, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
      })

      map.addLayer({
        id: LAYER_PARENT_BORDER,
        type: 'line',
        source: SOURCE_PARENT_HEX,
        paint: {
          'line-color': '#facc15',
          'line-width': 4,
          'line-dasharray': [3, 2],
          'line-opacity': 0.9,
        },
      })

      // Emit initial bbox
      onBoundsChange(getBbox(map))

      // Notify parent that map is ready
      onMapReady?.(map)
    })

    // ── Hover: feature-state ─────────────────────────────────
    map.on('mousemove', LAYER_FILL, (e) => {
      map.getCanvas().style.cursor = 'pointer'
      if (!e.features?.length) return
      const fid = e.features[0].id

      if (hoveredIdRef.current !== null && hoveredIdRef.current !== fid) {
        map.setFeatureState({ source: SOURCE_POLYGON, id: hoveredIdRef.current }, { hovered: false })
      }
      hoveredIdRef.current = fid ?? null
      if (fid !== undefined) {
        map.setFeatureState({ source: SOURCE_POLYGON, id: fid }, { hovered: true })
      }
    })

    map.on('mouseleave', LAYER_FILL, () => {
      map.getCanvas().style.cursor = ''
      if (hoveredIdRef.current !== null) {
        map.setFeatureState({ source: SOURCE_POLYGON, id: hoveredIdRef.current }, { hovered: false })
        hoveredIdRef.current = null
      }
    })

    // ── Click handling ───────────────────────────────────────
    // Boolean flag: layer-specific handler fires BEFORE the general handler
    // in the same synchronous tick, so this is race-condition free.
    let clickHandled = false

    // Click: hex selection
    map.on('click', LAYER_FILL, (e) => {
      if (!e.features?.length) return
      clickHandled = true
      const feature = e.features[0] as unknown as HeatmapFeature
      onFeatureSelect(feature)

      // Only fly if user is zoomed far out; avoid animation interference on re-clicks
      if (map.getZoom() < 13) {
        const center = polygonCentroid(feature.geometry.coordinates[0])
        map.flyTo({ center, zoom: ZOOM_FLY_TO, duration: FLY_TO_DURATION })
      }
    })

    // Click: empty area deselects (only when no hex was hit)
    map.on('click', () => {
      if (clickHandled) {
        clickHandled = false
        return
      }
      onFeatureSelect(null)
    })

    // ── Debounced moveend → update bbox ──────────────────────
    map.on('moveend', () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        onBoundsChange(getBbox(map))
      }, 400)
    })

    mapRef.current = map

    return () => {
      map.remove()
      mapRef.current = null
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Update polygon source when data changes ────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return

    const polySrc = map.getSource(SOURCE_POLYGON) as maplibregl.GeoJSONSource | undefined
    polySrc?.setData(data)
  }, [data])

  // ── Update selected feature highlight ──────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer(LAYER_SELECTED)) return

    map.setFilter(LAYER_SELECTED, [
      '==',
      ['get', 'grid_index'],
      selectedFeatureId ?? '',
    ])
  }, [selectedFeatureId])

  // ── Update parent hex border source ──────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const src = map.getSource(SOURCE_PARENT_HEX) as maplibregl.GeoJSONSource | undefined
    if (!src) return
    src.setData(parentHexGeojson ?? { type: 'FeatureCollection', features: [] })
  }, [parentHexGeojson])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
