import { Activity, Wifi, Brain, Hexagon, BarChart3, Lock } from 'lucide-react'

const statCards = [
  {
    icon: Activity,
    iconBg: 'var(--accent-glow)',
    iconColor: 'var(--accent-light)',
    value: '10,247',
    label: 'Toplam Ölçüm',
  },
  {
    icon: Wifi,
    iconBg: 'var(--emerald-glow)',
    iconColor: 'var(--emerald)',
    value: '72.4',
    label: 'Ort. Kalite Skoru',
  },
  {
    icon: Brain,
    iconBg: 'rgba(168, 85, 247, 0.15)',
    iconColor: '#a855f7',
    value: '1,832',
    label: 'AI Tahmin',
  },
  {
    icon: Hexagon,
    iconBg: 'rgba(234, 179, 8, 0.15)',
    iconColor: '#eab308',
    value: '4,519',
    label: 'Aktif Hücre',
  },
]

const upcomingFeatures = [
  'Anomali tespiti (anormal RSRP düşüşleri)',
  'Zaman serisi trend analizi',
  'Operatör karşılaştırma raporu',
  'Bölgesel kapsama raporları',
]

export default function Dashboard() {
  return (
    <div className="dashboard">
      <div className="dashboard__header">
        <h1 className="dashboard__title">Dashboard</h1>
        <p className="dashboard__subtitle">Ağ performans metrikleri ve AI analiz özeti</p>
      </div>

      <div className="dashboard__stats-grid">
        {statCards.map((card) => (
          <div key={card.label} className="dash-stat-card">
            <div
              className="dash-stat-card__icon"
              style={{ background: card.iconBg, color: card.iconColor }}
            >
              <card.icon size={20} />
            </div>
            <div className="dash-stat-card__value">{card.value}</div>
            <div className="dash-stat-card__label">{card.label}</div>
          </div>
        ))}
      </div>

      <div className="dashboard__section">
        <h2 className="dashboard__section-title">
          <BarChart3 size={18} style={{ color: 'var(--accent-light)' }} />
          Detaylı Analiz
        </h2>
        <div className="dashboard__placeholder">
          <Lock size={32} style={{ opacity: 0.4 }} />
          <p>Gelişmiş analiz araçları yakında aktif olacak</p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%', maxWidth: 360 }}>
            {upcomingFeatures.map((f) => (
              <div key={f} className="dashboard-feature-item">
                <Lock size={14} className="feature-lock" />
                <span>{f}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
