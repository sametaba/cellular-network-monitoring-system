import { useState } from 'react'
import { X, MapPin, ChevronDown, ChevronUp, Trophy } from 'lucide-react'
import type { HeatmapFeature } from '../types/heatmap'
import { getOperator, OPERATORS } from '../constants/operators'
import StarRating from './StarRating'

interface SidebarProps {
  /** All features for the selected cell (one per operator) */
  selectedFeatures: HeatmapFeature[]
  onClose: () => void
}

function fmt(val: number | null | undefined, unit: string, decimals = 1): string {
  if (val == null) return '—'
  return `${val.toFixed(decimals)} ${unit}`
}

/** Find the best operator (highest quality_score) */
function getBestOperatorId(features: HeatmapFeature[]): string | null {
  let best: HeatmapFeature | null = null
  for (const f of features) {
    if (f.properties.quality_score == null) continue
    if (!best || (f.properties.quality_score > (best.properties.quality_score ?? 0))) {
      best = f
    }
  }
  return best?.properties.operator_id ?? null
}

function OperatorCard({ feature, isBest }: { feature: HeatmapFeature; isBest: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const p = feature.properties
  const op = getOperator(p.operator_id)

  return (
    <div
      className="op-card"
      style={{ borderLeftColor: op.color }}
    >
      <div className="op-card-header">
        <div className="op-card-name-row">
          <span
            className="op-card-dot"
            style={{ background: op.color }}
          />
          <span className="op-card-name">{op.label}</span>
          {isBest && (
            <span className="op-card-best">
              <Trophy size={12} /> En İyi
            </span>
          )}
        </div>
        <StarRating score={p.quality_score} />
      </div>

      {/* Quick metrics */}
      <div className="op-card-metrics">
        <div className="op-metric">
          <span className="op-metric-label">RSRP</span>
          <span className="op-metric-value">{fmt(p.aggregated_rsrp, 'dBm')}</span>
        </div>
        <div className="op-metric">
          <span className="op-metric-label">RSRQ</span>
          <span className="op-metric-value">{fmt(p.aggregated_rsrq, 'dB')}</span>
        </div>
        <div className="op-metric">
          <span className="op-metric-label">SINR</span>
          <span className="op-metric-value">{fmt(p.aggregated_sinr, 'dB')}</span>
        </div>
      </div>

      {/* Expand toggle */}
      <button
        className="op-card-toggle"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
        <span>{expanded ? 'Gizle' : 'Tüm Hücre Verilerini Görüntüle'}</span>
      </button>

      {/* Expanded details */}
      {expanded && (
        <div className="op-card-details">
          <table className="op-detail-table">
            <tbody>
              <tr>
                <td>QoE İndeksi</td>
                <td>{p.qoe_index != null ? `${p.qoe_index.toFixed(0)}/100` : '—'}</td>
              </tr>
              <tr>
                <td>MOS</td>
                <td>{p.estimated_mos != null ? `${p.estimated_mos.toFixed(2)}/5` : '—'}</td>
              </tr>
              <tr>
                <td>Güvenilirlik</td>
                <td>{p.confidence_score != null ? `${(p.confidence_score * 100).toFixed(0)}%` : '—'}</td>
              </tr>
              <tr>
                <td>Ölçüm Sayısı</td>
                <td>{p.sample_count ?? '—'}</td>
              </tr>
              <tr>
                <td>Video Streaming</td>
                <td className={p.fit_streaming ? 'fit-ok' : 'fit-fail'}>
                  {p.fit_streaming ? '\u2713 Uygun' : '\u2717 Yetersiz'}
                </td>
              </tr>
              <tr>
                <td>VoLTE</td>
                <td className={p.fit_volte ? 'fit-ok' : 'fit-fail'}>
                  {p.fit_volte ? '\u2713 Uygun' : '\u2717 Yetersiz'}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function Sidebar({ selectedFeatures, onClose }: SidebarProps) {
  if (selectedFeatures.length === 0) {
    return (
      <aside className="sidebar sidebar--empty">
        <div className="sidebar-placeholder">
          <MapPin size={40} className="placeholder-icon" />
          <h3 className="placeholder-title">Sinyal Analizi</h3>
          <p className="placeholder-text">
            Haritadaki renkli hexagonlara tıklayarak detaylı verileri görüntüleyin
          </p>
        </div>
      </aside>
    )
  }

  const bestOpId = getBestOperatorId(selectedFeatures)

  // Sort: show operators in standard order (Turkcell, Vodafone, Türk Telekom)
  const sorted = [...selectedFeatures].sort((a, b) => {
    const ai = OPERATORS.findIndex((op) => op.id === a.properties.operator_id)
    const bi = OPERATORS.findIndex((op) => op.id === b.properties.operator_id)
    return ai - bi
  })

  return (
    <aside className="sidebar">
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <MapPin size={16} className="sidebar-header-icon" />
          <span className="sidebar-title">Hücre Sinyal Analizi</span>
        </div>
        <button className="sidebar-close" onClick={onClose} aria-label="Kapat">
          <X size={16} />
        </button>
      </div>

      <div className="sidebar-body">
        {/* Best operator summary */}
        {bestOpId && (
          <div className="best-operator-banner">
            <Trophy size={16} className="best-op-icon" />
            <span>
              En İyi Operatör:{' '}
              <strong style={{ color: getOperator(bestOpId).color }}>
                {getOperator(bestOpId).label}
              </strong>
            </span>
          </div>
        )}

        {/* Operator cards */}
        {sorted.map((feature) => (
          <OperatorCard
            key={feature.properties.operator_id}
            feature={feature}
            isBest={feature.properties.operator_id === bestOpId}
          />
        ))}
      </div>
    </aside>
  )
}
