import { createBrowserRouter, RouterProvider, Outlet } from 'react-router-dom'
import Navbar from './components/Navbar'
import Footer from './components/Footer'
import LandingPage from './pages/LandingPage'
import PublicMap from './pages/PublicMap'
import Dashboard from './pages/Dashboard'

/** Pages with Navbar + Footer */
function RootLayout() {
  return (
    <div className="root-layout">
      <Navbar />
      <div className="root-layout__content">
        <Outlet />
      </div>
      <Footer />
    </div>
  )
}

/** Full-screen map — no navbar/footer */
function MapLayout() {
  return <Outlet />
}

const router = createBrowserRouter([
  {
    element: <RootLayout />,
    children: [
      { index: true, element: <LandingPage /> },
      { path: 'dashboard', element: <Dashboard /> },
    ],
  },
  {
    path: 'map',
    element: <MapLayout />,
    children: [
      { index: true, element: <PublicMap /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
