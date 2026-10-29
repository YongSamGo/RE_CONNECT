import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../../App'
import { anonymousSession } from '../../api/fixtures'
afterEach(() => vi.unstubAllGlobals())
function mount(path: string) {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } })))
  return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
}
it('이용 안내에는 이용자용 약관 블록만 제공한다', async () => {
  mount('/guide'); await act(async () => {})
  expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
  expect(screen.queryByText('개발용 흐름 확인')).not.toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /자세히 보기/ }).length).toBeGreaterThanOrEqual(3)
})
it('추천 자료가 없으면 경험 이야기와 전체 공고로 이어진다', async () => {
  mount('/results'); await act(async () => {})
  expect(screen.getByRole('link', { name: '경험 이야기하기' })).toHaveAttribute('href', '/start')
  expect(screen.getByRole('link', { name: '전체 공고 둘러보기' })).toHaveAttribute('href', '/opportunities?browse=all')
})
it('시작 안내는 세 가지 상세 블록과 시작 행동을 제공한다', () => {
  mount('/start')
  expect(screen.getAllByRole('button', { name: /자세히 보기/ })).toHaveLength(3)
  expect(screen.getByRole('button', { name: '시작하기' })).toBeEnabled()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})
