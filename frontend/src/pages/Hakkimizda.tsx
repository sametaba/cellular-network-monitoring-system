import { Users, Target } from 'lucide-react'

const FOUNDERS = [
  { name: 'Kurucu 1', role: 'Co-Founder & CEO' },
  { name: 'Kurucu 2', role: 'Co-Founder & CTO' },
  { name: 'Kurucu 3', role: 'Co-Founder & COO' },
]

export default function Hakkimizda() {
  return (
    <div className="about-page">
      <div className="about-container">
        {/* Mission */}
        <section className="about-section">
          <div className="about-section-icon">
            <Target size={28} />
          </div>
          <h2 className="about-section-title">Amacımız</h2>
          <p className="about-text">
            Çekiyo, Türkiye&apos;deki mobil ağ kalitesini şeffaf ve erişilebilir kılmayı
            hedefler. Kullanıcılarımızın katkılarıyla toplanan gerçek sinyal verilerini
            analiz ederek, herkesin bulunduğu bölgedeki operatör performansını
            karşılaştırmasını sağlıyoruz.
          </p>
          <p className="about-text">
            3GPP ve ITU-T standartlarına dayanan skorlama algoritmamız; RSRP, RSRQ ve
            SINR metriklerini birleştirerek objektif bir kalite puanı üretir. Amacımız,
            kullanıcıların bilinçli operatör tercihleri yapabilmesi ve operatörlerin
            ağ yatırımlarını doğru bölgelere yönlendirmesidir.
          </p>
        </section>

        {/* Founders */}
        <section className="about-section">
          <div className="about-section-icon">
            <Users size={28} />
          </div>
          <h2 className="about-section-title">Kurucularımız</h2>
          <div className="founders-grid">
            {FOUNDERS.map((f) => (
              <div key={f.name} className="founder-card">
                <div className="founder-avatar">
                  {f.name.charAt(0)}
                </div>
                <h3 className="founder-name">{f.name}</h3>
                <p className="founder-role">{f.role}</p>
              </div>
            ))}
          </div>
        </section>
      </div>
    </div>
  )
}
