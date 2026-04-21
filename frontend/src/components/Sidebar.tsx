import { X, Signal, TowerControl, ArrowUp } from 'lucide-react'
import { getResolution, cellToParent } from 'h3-js'
import type { HeatmapFeature } from '../types/heatmap'
import { getScoreInfo } from '../types/heatmap'

const RES_LABELS: Record<number, string> = {
  7: '~1.2km bölge',
  8: '~460m semt',
  9: '~175m sokak',
}

interface SidebarProps {
  feature: HeatmapFeature | null
  onClose: () => void
  onNavigateParent: (parentGridIndex: string, resolution: number) => void
  parentLoading?: boolean
}

function fmt(val: number | null | undefined, unit: string, decimals = 1): string {
  if (val == null) return '—'
  return `${val.toFixed(decimals)} ${unit}`
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '—'
  return `${(val * 100).toFixed(0)}%`
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('tr-TR', {
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function Sidebar({ feature, onClose, onNavigateParent, parentLoading }: SidebarProps) {
  if (!feature) {
    return (
      <aside className="sidebar sidebar--empty">
        <div className="sidebar-placeholder">
          <TowerControl size={40} className="placeholder-icon" />
          <p className="placeholder-text">Detayları görmek için haritada bir hücreye tıklayın</p>
        </div>
      </aside>
    )
  }

  const p = feature.properties
  const isAI = p.is_ai_predicted === true
  const score = getScoreInfo(p.quality_score)
  const confidence = p.confidence_score ?? 0
  const currentRes = getResolution(p.grid_index)

  return (
    <aside className="sidebar">
      {/* Header */}
      <div className="sidebar-header">
        <div className="sidebar-title-row">
          <Signal size={16} className="accent-icon" />
          <span className="sidebar-title">Hücre Detayı</span>
        </div>
        <button className="sidebar-close" onClick={onClose} aria-label="Kapat">
          <X size={16} />
        </button>
      </div>

      {/* AI prediction badge */}
      {isAI && (
        <div className="ai-badge">
          <span className="ai-badge-icon">🤖</span>
          <div className="ai-badge-text">
            <span className="ai-badge-label">AI Tahmini</span>
            <span className="ai-badge-sub">Yapay Zeka ile tahmin edildi</span>
          </div>
        </div>
      )}

      {/* Quality badge */}
      <div
        className="score-badge"
        style={{ background: score.color, color: score.textColor }}
      >
        <span className="score-value">
          {p.quality_score != null ? p.quality_score.toFixed(2) : '—'} / 5
        </span>
        <span className="score-label">{score.label}</span>
      </div>

      {/* Signal metrics */}
      <section className="sidebar-section">
        <h3 className="section-title">{isAI ? 'Tahmini Sinyal Metrikleri' : 'Sinyal Metrikleri'}</h3>
        <table className="metrics-table">
          <tbody>
            <tr>
              <td className="metric-key">{isAI ? 'Tahmini RSRP' : 'RSRP'}</td>
              <td className="metric-val">{fmt(p.aggregated_rsrp, 'dBm')}</td>
            </tr>
            <tr>
              <td className="metric-key">{isAI ? 'Tahmini RSRQ' : 'RSRQ'}</td>
              <td className="metric-val">{fmt(p.aggregated_rsrq, 'dB')}</td>
            </tr>
            <tr>
              <td className="metric-key">{isAI ? 'Tahmini SINR' : 'SINR'}</td>
              <td className="metric-val">{fmt(p.aggregated_sinr, 'dB')}</td>
            </tr>
          </tbody>
        </table>
      </section>

      {/* Quality Assessment */}
      <section className="sidebar-section">
        <h3 className="section-title">{isAI ? 'Tahmini Kalite Değerlendirmesi' : 'Kalite Değerlendirmesi'}</h3>

        <div className="qoe-row">
          <span className="qoe-label">{isAI ? 'Tahmini QoE' : 'QoE İndeksi'}</span>
          <div className="qoe-bar-track">
            <div className="qoe-bar-fill" style={{ width: `${p.qoe_index ?? 0}%` }} />
          </div>
          <span className="qoe-value">{p.qoe_index != null ? p.qoe_index.toFixed(0) : '—'}/100</span>
        </div>

        <div className="mos-row">
          <span className="mos-label">{isAI ? 'Tahmini MOS' : 'MOS'}</span>
          <span className="mos-value">{p.estimated_mos != null ? p.estimated_mos.toFixed(2) : '—'}/5</span>
        </div>
      </section>

      {/* Network Fitness (hidden for AI predictions — no fitness data available) */}
      {!isAI && (
        <section className="sidebar-section">
          <h3 className="section-title">Ağ Uygunluğu</h3>
          <div className="fitness-badges">
            <span className={`fitness-badge ${p.fit_streaming ? 'fitness-badge--ok' : 'fitness-badge--fail'}`}>
              {p.fit_streaming ? '\u2713' : '\u2717'} Video Streaming
            </span>
            <span className={`fitness-badge ${p.fit_volte ? 'fitness-badge--ok' : 'fitness-badge--fail'}`}>
              {p.fit_volte ? '\u2713' : '\u2717'} VoLTE
            </span>
            <span className="fitness-badge fitness-badge--ok">
              {'\u2713'} IoT
            </span>
          </div>
        </section>
      )}

      {/* Confidence */}
      <section className="sidebar-section">
        <h3 className="section-title">Güvenilirlik</h3>
        <div className="confidence-row">
          <div className="confidence-bar-track">
            <div
              className="confidence-bar-fill"
              style={{ width: `${confidence * 100}%` }}
            />
          </div>
          <span className="confidence-pct">{fmtPct(p.confidence_score)}</span>
        </div>
        <p className="confidence-hint">
          {isAI
            ? 'Tahmin güvenilirliği · Komşu hücre verilerine dayalı'
            : `${p.sample_count ?? 0} ölçüm · Res ${currentRes}${currentRes < 9 ? ' · Geniş alan ortalaması' : ''}`
          }
        </p>
      </section>

      {/* Meta */}
      <section className="sidebar-section">
        <h3 className="section-title">Bilgi</h3>
        <table className="metrics-table">
          <tbody>
            <tr>
              <td className="metric-key">Operatör</td>
              <td className="metric-val">{p.operator_id}</td>
            </tr>
            <tr>
              <td className="metric-key">H3 Çözünürlük</td>
              <td className="metric-val">Res {currentRes} ({RES_LABELS[currentRes] ?? ''})</td>
            </tr>
            <tr>
              <td className="metric-key">H3 İndeks</td>
              <td className="metric-val metric-val--mono">{p.grid_index}</td>
            </tr>
            <tr>
              <td className="metric-key">{isAI ? 'Kaynak' : 'Güncelleme'}</td>
              <td className="metric-val">{isAI ? 'XGBoost tahmin modeli' : fmtTime(p.time_bucket)}</td>
            </tr>
          </tbody>
        </table>
      </section>

      {/* Parent hex navigation */}
      {currentRes > 7 && (
        <section className="sidebar-section sidebar-section--action">
          <button
            className="parent-hex-btn"
            onClick={() => {
              const parentRes = currentRes - 1
              const parentIndex = cellToParent(p.grid_index, parentRes)
              onNavigateParent(parentIndex, parentRes)
            }}
            disabled={parentLoading}
          >
            {parentLoading ? (
              <ArrowUp size={14} className="spin" />
            ) : (
              <ArrowUp size={14} />
            )}
            <div className="parent-hex-btn-text">
              <span className="parent-hex-btn-label">
                Üst Hücre (Res {currentRes - 1})
              </span>
              <span className="parent-hex-btn-sub">
                {RES_LABELS[currentRes - 1]} · Aggrege veri
              </span>
            </div>
          </button>
        </section>
      )}
    </aside>
  )
}
