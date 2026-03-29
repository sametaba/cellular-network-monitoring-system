import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import Layout from './components/Layout'
import PublicMap from './pages/PublicMap'
import Hakkimizda from './pages/Hakkimizda'

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <PublicMap /> },
      { path: '/hakkimizda', element: <Hakkimizda /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
