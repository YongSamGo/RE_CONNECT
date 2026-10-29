import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../../App'
import { anonymousSession } from '../../api/fixtures'
afterEach(() => vi.unstubAllGlobals())
it.each(['/preparation', '/application'])('이전 미리보기 %s는 현재 화면으로 연결하고 예시 입력을 만들지 않는다', async path => {
  const fetch = vi.fn(async (_request: Request) => new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
  await act(async () => {})
  expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  expect(fetch.mock.calls.every(([request]) => (request as Request).method === 'GET')).toBe(true)
})
