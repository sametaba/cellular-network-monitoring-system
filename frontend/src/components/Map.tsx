import { useEffect, useRef, useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import type { HeatmapCollection } from '../types/heatmap'
import {
  BASEMAP,
  ISTANBUL,
  INITIAL_ZOOM,
  ZOOM_FLY_TO,
  FLY_TO_DURATION,
  SOURCE_POLYGON,
  LAYER_FILL,
  LAYER_OUTLINE,
  LAYER_SELECTED,
} from '../constants/map'
import { OPERATORS } from '../constants/operators'
import { polygonCentroid } from '../utils/geo'

interface MapProps {
  data: HeatmapCollection
  onBoundsChange: (bbox: string) => void
  /** Reports the grid_index of clicked hex */
  onCellClick: (gridIndex: string, lng: number, lat: number) => void
  selectedCellId: string | null
  onMapReady?: (map: maplibregl.Map) => void
}

export default function Map({
  data,
  onBoundsChange,
  onCellClick,
  selectedCellId,
  onMapReady,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const hoveredIdRef = useRef<string | number | null>(null)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const dataRef = useRef<HeatmapCollection>(data)

  useEffect(() => {
    dataRef.current = data
  }, [data])

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
    map.addControl(new maplibregl.NavigationControl(), 'top-left')

    map.on('load', () => {
      // ── Source ──────────────────────────────────────────────
      map.addSource(SOURCE_POLYGON, {
        type: 'geojson',
        data: { type: 'FeatureCollection', features: [] },
        generateId: true,
      })

      // ── Build color expression: match operator_id → brand color ──
      const colorExpr = [
        'match',
        ['get', 'operator_id'],
        ...OPERATORS.flatMap((op) => [op.id, op.color]),
        '#94A3B8', // fallback grey
      ] as unknown as maplibregl.ExpressionSpecification

      // ── Layer 1: Hex fill (operator-colored) ──────────────
      map.addLayer({
        id: LAYER_FILL,
        type: 'fill',
        source: SOURCE_POLYGON,
        paint: {
          'fill-color': colorExpr,
          'fill-opacity': [
            'case',
            ['boolean', ['feature-state', 'hovered'], false],
            0.65,
            0.35,
          ],
        },
      })

      // ── Layer 2: Hex outline ─────────────────────────────
      map.addLayer({
        id: LAYER_OUTLINE,
        type: 'line',
        source: SOURCE_POLYGON,
        paint: {
          'line-color': colorExpr,
          'line-width': 1,
          'line-opacity': 0.5,
        },
      })

      // ── Layer 3: Selected hex highlight ──────────────────
      map.addLayer({
        id: LAYER_SELECTED,
        type: 'line',
        source: SOURCE_POLYGON,
        paint: {
          'line-color': '#1e293b',
          'line-width': 3,
          'line-opacity': 1,
        },
        filter: ['==', ['get', 'grid_index'], ''],
      })

      // Emit initial bbox
      onBoundsChange(getBbox(map))
      onMapReady?.(map)
    })

    // ── Hover ───────────────────────────────────────────────
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

    // ── Click: hex cell ────────────────────────────────────
    map.on('click', LAYER_FILL, (e) => {
      if (!e.features?.length) return
      const gridIndex = e.features[0].properties?.grid_index as string
      const center = polygonCentroid(
        (e.features[0].geometry as GeoJSON.Polygon).coordinates[0],
      )
      onCellClick(gridIndex, center[0], center[1])
      map.flyTo({ center, zoom: Math.max(map.getZoom(), ZOOM_FLY_TO), duration: FLY_TO_DURATION })
    })

    // ── Click: empty area deselects ────────────────────────
    map.on('click', (e) => {
      const hits = map.queryRenderedFeatures(e.point, { layers: [LAYER_FILL] })
      if (!hits.length) {
        onCellClick('', 0, 0) // empty = deselect
      }
    })

    // ── Debounced moveend → update bbox ────────────────────
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

  // ── Update source when data changes ──────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.isStyleLoaded()) return

    const src = map.getSource(SOURCE_POLYGON) as maplibregl.GeoJSONSource | undefined
    src?.setData(data)
  }, [data])

  // ── Update selected highlight ────────────────────────────────
  useEffect(() => {
    const map = mapRef.current
    if (!map || !map.getLayer(LAYER_SELECTED)) return

    map.setFilter(LAYER_SELECTED, [
      '==',
      ['get', 'grid_index'],
      selectedCellId ?? '',
    ])
  }, [selectedCellId])

  return (
    <div
      ref={containerRef}
      style={{ width: '100%', height: '100%' }}
    />
  )
}
