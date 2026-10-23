import { createBrowserRouter } from 'react-router-dom'
import Layout from '../components/Layout'
import CreatePage from '../pages/CreatePage'
import NotFound from '../pages/NotFound'
import ViewPage from '../pages/ViewPage'

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <CreatePage /> },
      { path: '/view/:id', element: <ViewPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])
