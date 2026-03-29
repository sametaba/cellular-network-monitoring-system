import { Filter } from 'lucide-react'
import { OPERATORS } from '../constants/operators'

interface FilterBarProps {
  /** null = show all ("Tümü") */
  activeOperator: string | null
  onOperatorChange: (id: string | null) => void
  /** total hex count across all operators */
  totalCount: number
  /** count per operator id */
  operatorCounts: Record<string, number>
  loading: boolean
}

export default function FilterBar({
  activeOperator,
  onOperatorChange,
  totalCount,
  operatorCounts,
  loading,
}: FilterBarProps) {
  const pct = (count: number) =>
    totalCount > 0 ? `${Math.round((count / totalCount) * 100)}%` : '0%'

  return (
    <div className="filter-bar">
      <div className="filter-bar-left">
        <Filter size={14} className="filter-bar-icon" />
        <span className="filter-bar-label">Filtrele:</span>

        {/* "All" capsule */}
        <button
          className={`filter-capsule ${activeOperator === null ? 'filter-capsule--active' : ''}`}
          onClick={() => onOperatorChange(null)}
        >
          Tümü <span className="capsule-pct">100%</span>
        </button>

        {/* Per-operator capsules */}
        {OPERATORS.map((op) => {
          const count = operatorCounts[op.id] ?? 0
          return (
            <button
              key={op.id}
              className={`filter-capsule ${activeOperator === op.id ? 'filter-capsule--active' : ''}`}
              onClick={() => onOperatorChange(op.id)}
              style={
                activeOperator === op.id
                  ? { background: op.colorLight, borderColor: op.colorBorder, color: op.color }
                  : undefined
              }
            >
              <span
                className="capsule-dot"
                style={{ background: op.color }}
              />
              {op.label}{' '}
              <span className="capsule-pct">{pct(count)}</span>
            </button>
          )
        })}
      </div>

      <div className="filter-bar-right">
        {loading && <span className="filter-bar-loading">Yükleniyor…</span>}
        <span className="filter-bar-count">
          {totalCount} hücre
        </span>
      </div>
    </div>
  )
}
