import { NavLink } from 'react-router-dom'
import { Download } from 'lucide-react'

export default function Header() {
  return (
    <header className="header">
      {/* Logo */}
      <NavLink to="/" className="header-logo">
        <span className="logo-dots">
          <span className="dot dot--yellow" />
          <span className="dot dot--red" />
          <span className="dot dot--blue" />
        </span>
        <span className="logo-text">çekiyoo</span>
      </NavLink>

      {/* Nav */}
      <nav className="header-nav">
        <NavLink
          to="/"
          end
          className={({ isActive }) =>
            `header-nav-link ${isActive ? 'header-nav-link--active' : ''}`
          }
        >
          Harita
        </NavLink>
        <NavLink
          to="/hakkimizda"
          className={({ isActive }) =>
            `header-nav-link ${isActive ? 'header-nav-link--active' : ''}`
          }
        >
          Hakkımızda
        </NavLink>
      </nav>

      {/* CTA */}
      <a
        href="https://apps.apple.com"
        target="_blank"
        rel="noopener noreferrer"
        className="header-cta"
      >
        <Download size={16} />
        <span>Uygulamayı İndir</span>
      </a>
    </header>
  )
}
