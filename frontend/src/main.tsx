import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import { ErrorBoundary } from './App.tsx'
import { appRoutes } from './app-routes'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary><RouterProvider router={createBrowserRouter(appRoutes)} /></ErrorBoundary>
  </StrictMode>,
)
