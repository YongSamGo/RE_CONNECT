import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'
import { anonymousSession } from './api/fixtures'
afterEach(() => vi.unstubAllGlobals())
it.each([
  ['/my', '나의 정보'], ['/transcript', '경험을 들려주세요'],
  ['/preparation/example-library', '조건에 맞는 기회 찾아보기'], ['/recommendations', '나에게 맞는 공고 찾기'],
  ['/me/saved', '나의 정보'], ['/me/settings', '나의 정보'],
])('이전 주소 %s를 현재 이용 흐름으로 연결한다', async (path, title) => {
  const fetch = vi.fn(async (_request: Request) => new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
  expect(await screen.findByRole('heading', { level: 1, name: title })).toBeVisible()
  await act(async () => {})
  expect(fetch.mock.calls.every(([request]) => (request as Request).method === 'GET')).toBe(true)
  expect(screen.queryByText('작은 도서관 이용 안내')).not.toBeInTheDocument()
})
