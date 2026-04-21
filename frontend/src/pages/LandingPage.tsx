import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { MapPin, Brain, BarChart3, ArrowRight, Zap } from 'lucide-react'

function AnimatedNumber({ value, suffix = '' }: { value: number; suffix?: string }) {
  const ref = useRef<HTMLSpanElement>(null)
  const animated = useRef(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting && !animated.current) {
          animated.current = true
          let start = 0
          const duration = 1200
          const startTime = performance.now()

          const tick = (now: number) => {
            const progress = Math.min((now - startTime) / duration, 1)
            const eased = 1 - Math.pow(1 - progress, 3)
            start = Math.floor(eased * value)
            el.textContent = start.toLocaleString('tr-TR') + suffix
            if (progress < 1) requestAnimationFrame(tick)
          }
          requestAnimationFrame(tick)
        }
      },
      { threshold: 0.3 },
    )

    observer.observe(el)
    return () => observer.disconnect()
  }, [value, suffix])

  return <span ref={ref}>0{suffix}</span>
}

const features = [
  {
    icon: MapPin,
    iconClass: 'feature-card__icon--indigo',
    title: 'Canlı Harita',
    desc: 'H3 hücresel grid üzerinde gerçek zamanlı ağ kalitesi görselleştirme. Zoom seviyesine göre dinamik veri yükleme.',
  },
  {
    icon: Brain,
    iconClass: 'feature-card__icon--purple',
    title: 'AI Tahminleri',
    desc: 'XGBoost makine öğrenimi modeli ile ölçüm yapılmamış bölgelerin kapsama kalitesini tahmin edin.',
  },
  {
    icon: BarChart3,
    iconClass: 'feature-card__icon--emerald',
    title: 'Detaylı Analiz',
    desc: 'RSRP, RSRQ, SINR metrikleri, QoE indeksi ve MOS skoru ile sinyal performansını derinlemesine inceleyin.',
  },
]

const stats = [
  { value: 10000, suffix: '+', label: 'Ölçüm Noktası', colorClass: 'stat__number--accent' },
  { value: 3, suffix: '', label: 'Operatör', colorClass: '' },
  { value: 99, suffix: '%', label: 'Uptime', colorClass: 'stat__number--emerald' },
  { value: 9, suffix: '', label: 'H3 Çözünürlük', colorClass: '' },
]

export default function LandingPage() {
  return (
    <div className="landing">
      {/* Hero */}
      <section className="hero">
        <div className="hero__glow" />

        <div className="hero__badge">
          <span className="hero__badge-dot" />
          Gerçek zamanlı ağ izleme
        </div>

        <h1 className="hero__title">
          Ağ Kalitesini{' '}
          <span className="hero__title-gradient">Görselleştirin</span>
        </h1>

        <p className="hero__subtitle">
          Hücresel ağ performansını harita üzerinde analiz edin. AI destekli
          kapsama tahminleri ile bilinmeyen bölgeleri keşfedin.
        </p>

        <div className="hero__buttons">
          <Link to="/map" className="btn-primary">
            Haritayı Keşfet <ArrowRight size={16} />
          </Link>
          <Link to="/dashboard" className="btn-secondary">
            <Zap size={16} /> Dashboard
          </Link>
        </div>
      </section>

      {/* Features */}
      <section className="features">
        <div className="features__header">
          <p className="features__label">Özellikler</p>
          <h2 className="features__title">Güçlü Araçlar, Sade Arayüz</h2>
          <p className="features__subtitle">
            Karmaşık ağ verilerini anlamlı görselleştirmelere dönüştürün. Her
            seviye kullanıcı için tasarlandı.
          </p>
        </div>

        <div className="features__grid">
          {features.map((f) => (
            <div key={f.title} className="feature-card">
              <div className={`feature-card__icon ${f.iconClass}`}>
                <f.icon size={24} />
              </div>
              <h3 className="feature-card__title">{f.title}</h3>
              <p className="feature-card__desc">{f.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Stats */}
      <section className="stats">
        <div className="stats__grid">
          {stats.map((s) => (
            <div key={s.label}>
              <div className={`stat__number ${s.colorClass}`}>
                <AnimatedNumber value={s.value} suffix={s.suffix} />
              </div>
              <p className="stat__label">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* CTA */}
      <section className="cta-section">
        <h2 className="cta-section__title">Hemen Başlayın</h2>
        <p className="cta-section__subtitle">
          Ağ kalitesi haritasını keşfedin, operatör performansını
          karşılaştırın ve AI tahminlerini inceleyin.
        </p>
        <Link to="/map" className="btn-primary">
          Haritaya Git <ArrowRight size={16} />
        </Link>
      </section>
    </div>
  )
}
