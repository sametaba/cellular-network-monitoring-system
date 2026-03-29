import { RefreshCw, Radio, Wifi } from 'lucide-react'

const OPERATORS = [
  { id: '28601', label: 'Turkcell' },
  { id: '28602', label: 'Vodafone TR' },
  { id: '28603', label: 'Türk Telekom' },
]

interface FilterPanelProps {
  operatorId: string
  featureCount: number
  loading: boolean
  onOperatorChange: (id: string) => void
  onRefresh: () => void
}

export default function FilterPanel({
  operatorId,
  featureCount,
  loading,
  onOperatorChange,
  onRefresh,
}: FilterPanelProps) {
  return (
    <aside className="filter-panel">
      {/* Header */}
      <div className="panel-header">
        <Wifi size={18} className="accent-icon" />
        <span className="panel-title">Network Monitor</span>
      </div>

      {/* Operator */}
      <section className="filter-section">
        <label className="filter-label">
          <Radio size={14} />
          <span>Operatör</span>
        </label>
        <select
          className="filter-select"
          value={operatorId}
          onChange={(e) => onOperatorChange(e.target.value)}
        >
          {OPERATORS.map((op) => (
            <option key={op.id} value={op.id}>
              {op.label} ({op.id})
            </option>
          ))}
        </select>
      </section>

      {/* Status + Refresh */}
      <section className="filter-section filter-section--bottom">
        <div className="status-chip">
          {loading ? (
            <RefreshCw size={13} className="spin" />
          ) : (
            <span className="status-dot status-dot--ok" />
          )}
          <span>
            {loading
              ? 'Yükleniyor…'
              : featureCount > 0
              ? `${featureCount} hücre görüntüleniyor`
              : 'Veri bulunamadı'}
          </span>
        </div>
        <button className="refresh-btn" onClick={onRefresh} disabled={loading}>
          <RefreshCw size={14} className={loading ? 'spin' : ''} />
          <span>Yenile</span>
        </button>
      </section>
    </aside>
  )
}
