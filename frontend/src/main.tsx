import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { createBrowserRouter, RouterProvider } from 'react-router-dom'
import './index.css'
import App, { ErrorBoundary } from './App.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ErrorBoundary><RouterProvider router={createBrowserRouter([{ path: '*', element: <App /> }])} /></ErrorBoundary>
  </StrictMode>,
)
