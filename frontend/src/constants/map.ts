/** Default flyTo zoom when clicking a feature */
export const ZOOM_FLY_TO = 14

/** flyTo animation duration in milliseconds */
export const FLY_TO_DURATION = 1500

/** Map center: Istanbul */
export const ISTANBUL: [number, number] = [29.01, 41.015]

/** Initial zoom level */
export const INITIAL_ZOOM = 11

/** Basemap style URL (light / positron) */
export const BASEMAP = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json'

// ── Source IDs ──────────────────────────────────────────────────
export const SOURCE_POLYGON = 'heatmap'

// ── Layer IDs (bottom → top render order) ───────────────────────
export const LAYER_FILL = 'heatmap-fill'
export const LAYER_OUTLINE = 'heatmap-outline'
export const LAYER_SELECTED = 'heatmap-selected'
