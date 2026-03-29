import { OPERATORS } from '../constants/operators'

export default function Legend() {
  return (
    <div className="map-legend">
      <h4 className="legend-title">EN İYİ OPERATÖR</h4>
      {OPERATORS.map((op) => (
        <div key={op.id} className="legend-item">
          <span className="legend-swatch" style={{ background: op.color }} />
          <span className="legend-label">{op.label}</span>
        </div>
      ))}
      <p className="legend-hint">
        Rank = o bölgedeki en yüksek RSRP değerine sahip operatör
      </p>
    </div>
  )
}
