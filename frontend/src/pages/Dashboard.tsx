import { Lock, ArrowLeft, BrainCircuit } from 'lucide-react'
import { Link } from 'react-router-dom'

export default function Dashboard() {
  return (
    <div className="dashboard-page">
      <div className="dashboard-card">
        <div className="dashboard-icon-row">
          <BrainCircuit size={48} className="accent-icon" />
        </div>
        <h1 className="dashboard-title">AI Insights</h1>
        <p className="dashboard-subtitle">
          Makine öğrenimi destekli ağ analizi — yakında
        </p>

        <div className="dashboard-features">
          {[
            'Anomali tespiti (anormal RSRP düşüşleri)',
            'Kapsama tahmin haritası',
            'Zaman serisi trend analizi',
            'Operatör karşılaştırma raporu',
          ].map((f) => (
            <div key={f} className="dashboard-feature-item">
              <Lock size={14} className="feature-lock" />
              <span>{f}</span>
            </div>
          ))}
        </div>

        <Link to="/" className="back-link">
          <ArrowLeft size={14} />
          <span>Ana Haritaya Dön</span>
        </Link>
      </div>
    </div>
  )
}
