import { Link } from 'react-router-dom'
import { Activity } from 'lucide-react'

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div>
          <div className="footer__brand-name">
            <Activity size={18} style={{ color: 'var(--accent-light)' }} />
            CellScope
          </div>
          <p className="footer__brand-desc">
            Hücresel ağ kalitesini gerçek zamanlı izleyin, AI destekli tahminlerle kapsama alanını analiz edin.
          </p>
        </div>

        <div>
          <h4 className="footer__col-title">Hızlı Linkler</h4>
          <ul className="footer__links">
            <li><Link to="/" className="footer__link">Anasayfa</Link></li>
            <li><Link to="/map" className="footer__link">Harita</Link></li>
            <li><Link to="/dashboard" className="footer__link">Dashboard</Link></li>
          </ul>
        </div>

        <div>
          <h4 className="footer__col-title">Platform</h4>
          <ul className="footer__links">
            <li><span className="footer__link">API Dokümantasyon</span></li>
            <li><span className="footer__link">Gizlilik Politikası</span></li>
            <li><span className="footer__link">İletişim</span></li>
          </ul>
        </div>
      </div>

      <div className="footer__bottom">
        <span>&copy; {new Date().getFullYear()} CellScope. Tüm hakları saklıdır.</span>
        <span>Istanbul, Türkiye</span>
      </div>
    </footer>
  )
}
