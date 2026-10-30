import { Suspense, lazy } from 'react'
import { render, screen } from '@testing-library/react'
import { createMemoryRouter, RouterProvider } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { appRoutes } from './app-routes'

afterEach(() => vi.restoreAllMocks())

it.each(['render', 'lazy'] as const)('uses the production router recovery screen for %s failure without exposing details', async kind => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  function Broken(): never { throw new Error('private-input-and-server-path') }
  const MissingBundle = lazy(() => Promise.reject(new Error('private-chunk-url')))
  const router = createMemoryRouter([{ ...appRoutes[0], element: kind === 'render' ? <Broken /> : <Suspense fallback={<p>불러오는 중</p>}><MissingBundle /></Suspense> }], { initialEntries: ['/admin'] })
  const view = render(<RouterProvider router={router} />)
  expect(await screen.findByRole('heading', { name: '화면을 표시하지 못했습니다' })).toBeVisible()
  expect(screen.getByRole('button', { name: '현재 화면 다시 열기' })).toBeEnabled()
  expect(screen.getByRole('link', { name: '새로 시작하기' })).toHaveAttribute('href', '/')
  expect(screen.getByRole('alert')).toHaveTextContent('서버에서 처리되었을 수')
  expect(document.body).not.toHaveTextContent('private')
  view.unmount()
  router.dispose()
})
