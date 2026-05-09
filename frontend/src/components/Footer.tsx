import { Link } from 'react-router-dom'

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div>
          <div className="footer__brand-name">
            <img src="/bars-logo.svg" alt="BARS" className="footer__logo-img" />
            BARS
          </div>
          <p className="footer__brand-tagline">See Every Bar</p>
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
        <span>&copy; {new Date().getFullYear()} BARS. All rights reserved.</span>
        <span>Istanbul, Türkiye</span>
      </div>
    </footer>
  )
}
