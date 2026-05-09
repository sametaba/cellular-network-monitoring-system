import { useEffect, useRef, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { HeatmapCollection, HeatmapFeature } from '../types/heatmap'
import {
  BASEMAP,
  ISTANBUL,
  INITIAL_ZOOM,
  ZOOM_HEX_VISIBLE,
  SOURCE_POLYGON,
  LAYER_FILL,
  LAYER_OUTLINE,
  LAYER_OUTLINE_AI,
  LAYER_SELECTED_GLOW,
  LAYER_SELECTED,
  SOURCE_PARENT_HEX,
  LAYER_PARENT_BORDER,
} from '../constants/map'

interface MapProps {
  data: HeatmapCollection
  onBoundsChange: (bbox: string) => void
  onFeatureSelect: (feature: HeatmapFeature | null) => void
  selectedFeatureId: string | null
  neighborIndices: string[]
  onMapReady?: (map: maplibregl.Map) => void
  parentHexGeojson?: HeatmapCollection | null
}

export default function Map({
  data,
  onBoundsChange,
  onFeatureSelect,
  selectedFeatureId,
  neighborIndices,
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

      // ── Layer 1: Hex fill (quality-colored) ──────────────────
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
            ['==', ['get', 'is_ai_predicted'], true], 0.35,
            ['boolean', ['feature-state', 'hovered'], false], 0.75,
            0.6,
          ],
          'fill-opacity-transition': { duration: 250, delay: 0 },
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

      // ── Layer 4a: Selected hex glow (wide blur) ───────────────
      map.addLayer({
        id: LAYER_SELECTED_GLOW,
        type: 'line',
        source: SOURCE_POLYGON,
        minzoom: ZOOM_HEX_VISIBLE,
        paint: {
          'line-color': '#F2EAD3',
          'line-width': 8,
          'line-blur': 4,
          'line-opacity': 0.6,
        },
        filter: ['==', ['get', 'grid_index'], ''],
      })

      // ── Layer 4b: Selected hex sharp border ───────────────────
      map.addLayer({
        id: LAYER_SELECTED,
        type: 'line',
        source: SOURCE_POLYGON,
        minzoom: ZOOM_HEX_VISIBLE,
        paint: {
          'line-color': '#F2EAD3',
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

    // ── Click: hex selection ─────────────────────────────────
    map.on('click', LAYER_FILL, (e) => {
      if (!e.features?.length) return
      const feature = e.features[0] as unknown as HeatmapFeature
      onFeatureSelect(feature)
    })

    // ── Click: empty area deselects ──────────────────────────
    map.on('click', (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: [LAYER_FILL] })
      if (hits.length === 0) {
        onFeatureSelect(null)
      }
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

  // ── 3-tier opacity based on selection + neighbors ──────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer(LAYER_FILL)) return

    if (!selectedFeatureId) {
      map.setPaintProperty(LAYER_FILL, 'fill-opacity', [
        'case',
        ['==', ['get', 'is_ai_predicted'], true], 0.35,
        ['boolean', ['feature-state', 'hovered'], false], 0.75,
        0.6,
      ])
      return
    }

    map.setPaintProperty(LAYER_FILL, 'fill-opacity', [
      'case',
      // Tier 1: selected hex — full opacity
      ['==', ['get', 'grid_index'], selectedFeatureId], 0.9,
      // Tier 2: neighbors within ring 3 — medium opacity
      ['in', ['get', 'grid_index'], ['literal', neighborIndices]], 0.6,
      // Tier 3: everything else — very dim
      0.2,
    ])
  }, [selectedFeatureId, neighborIndices])

  // ── Update selected hex highlight (glow + border) ──────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer(LAYER_SELECTED)) return

    const filter: maplibregl.FilterSpecification = [
      '==',
      ['get', 'grid_index'],
      selectedFeatureId ?? '',
    ]
    map.setFilter(LAYER_SELECTED, filter)
    if (map.getLayer(LAYER_SELECTED_GLOW)) {
      map.setFilter(LAYER_SELECTED_GLOW, filter)
    }
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
