import { useState, useEffect } from 'react'
import { NavLink, Link } from 'react-router-dom'
import { Activity, Menu, X, ArrowRight } from 'lucide-react'

export default function Navbar() {
  const [scrolled, setScrolled] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 10)
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `navbar__link${isActive ? ' navbar__link--active' : ''}`

  return (
    <nav className={`navbar${scrolled ? ' navbar--scrolled' : ''}`}>
      <Link to="/" className="navbar__logo">
        <Activity size={22} className="navbar__logo-icon" />
        <span className="navbar__logo-text">CellScope</span>
      </Link>

      <div className="navbar__links">
        <NavLink to="/" end className={linkClass}>Anasayfa</NavLink>
        <NavLink to="/map" className={linkClass}>Harita</NavLink>
        <NavLink to="/dashboard" className={linkClass}>Dashboard</NavLink>
      </div>

      <div className="navbar__actions">
        <Link to="/map" className="navbar__cta">
          Haritayı Aç <ArrowRight size={14} />
        </Link>
      </div>

      <button
        className="navbar__hamburger"
        onClick={() => setMobileOpen(!mobileOpen)}
        aria-label="Menüyü aç"
      >
        {mobileOpen ? <X size={22} /> : <Menu size={22} />}
      </button>

      <div className={`navbar__mobile-menu${mobileOpen ? ' navbar__mobile-menu--open' : ''}`}>
        <NavLink to="/" end className={linkClass} onClick={() => setMobileOpen(false)}>Anasayfa</NavLink>
        <NavLink to="/map" className={linkClass} onClick={() => setMobileOpen(false)}>Harita</NavLink>
        <NavLink to="/dashboard" className={linkClass} onClick={() => setMobileOpen(false)}>Dashboard</NavLink>
        <Link to="/map" className="navbar__cta" style={{ marginTop: 8, justifyContent: 'center' }} onClick={() => setMobileOpen(false)}>
          Haritayı Aç <ArrowRight size={14} />
        </Link>
      </div>
    </nav>
  )
}
