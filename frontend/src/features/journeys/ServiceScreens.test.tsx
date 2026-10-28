import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../../App'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('offers the main service destinations without creating user data', () => {
  const fetch = vi.fn(async (_request: Request) => new Response(JSON.stringify({ authenticated: false, user: null }), { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const view = render(<MemoryRouter initialEntries={['/guide']}><App /></MemoryRouter>)
  const links = [...view.container.querySelectorAll('.service-guide a')].map(link => link.getAttribute('href'))
  expect(links).toEqual(expect.arrayContaining(['/start', '/conversation', '/recommendations', '/opportunities', '/login', '/me']))
  expect(new Set(links).size).toBe(links.length)
  expect(fetch.mock.calls.every(([request]) => (request as Request).method === 'GET')).toBe(true)
})

it('redirects results without inventing a profile or sending a request', () => {
  const fetch = vi.fn(async (_request: Request) => new Response('{}', { headers: { 'Content-Type': 'application/json' } })); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={['/results']}><App /></MemoryRouter>)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('다시잇다가 추천하는 공고입니다')
  expect(screen.queryByRole('button', { name: '추천 다시 확인하기' })).not.toBeInTheDocument()
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
})

it('keeps the user-specified start screen free of screen-directory or draft controls', () => {
  render(<MemoryRouter initialEntries={['/start']}><App /></MemoryRouter>)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('시작하기 전에 확인해주세요')
  expect(screen.getAllByRole('button', { name: /자세히 보기/ })).toHaveLength(3)
  expect(screen.getByRole('button', { name: '동의하고 대화 시작하기' })).toBeVisible()
  expect(screen.queryByRole('link', { name: '다시잇다 이용 안내' })).not.toBeInTheDocument()
})
