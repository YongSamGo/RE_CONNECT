import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App, { ErrorBoundary } from './App'
import { anonymousSession } from './api/fixtures'

beforeEach(() => { vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } }))) })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear() })
function mount(path = '/') { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }

it.each([
  ['/recommendations', '공고 살펴보기 | 다시잇다'],
  ['/preparation/old', '공고 살펴보기 | 다시잇다'],
  ['/opportunities/invalid/extra', '페이지를 찾을 수 없어요 | 다시잇다'],
  ['/me/unknown', '페이지를 찾을 수 없어요 | 다시잇다'],
])('주소 %s에 맞는 제목을 표시한다', (path, title) => { mount(path); expect(document.title).toBe(title) })

it('홈에서 영상과 두 가지 진입 행동을 보여준다', () => {
  mount()
  expect(screen.getByRole('heading', { name: '여러분의 이야기를 들려주세요' })).toBeVisible()
  expect(screen.getByRole('link', { name: '시작하기' })).toHaveAttribute('href', '/start')
  expect(screen.getByRole('link', { name: '모집 공고 살펴보기' })).toHaveAttribute('href', '/opportunities')
  const video = document.querySelector<HTMLVideoElement>('.home-player')!
  expect(video.loop).toBe(true)
  expect(video.controls).toBe(false)
  expect(video.muted).toBe(false)
})

it('첫 진입에서 본문 초점을 강제하지 않고 본문 바로가기를 먼저 제공한다', async () => {
  mount(); expect(screen.getByRole('main')).not.toHaveFocus()
  await userEvent.tab()
  expect(screen.getByRole('link', { name: '본문으로 바로가기' })).toHaveFocus()
})

it('큰 글씨와 선명하게 보기를 독립적으로 바꾸고 설정만 보관한다', async () => {
  mount()
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '큰 글씨 보기' }))
  await user.click(screen.getByRole('button', { name: '선명하게 보기' }))
  expect(screen.getByRole('button', { name: '큰 글씨 보기' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: '선명하게 보기' })).toHaveAttribute('aria-pressed', 'true')
  expect(Object.keys(localStorage).sort()).toEqual(['reconnect-high-contrast', 'reconnect-large-text'])
})

it('공개 조건 선택은 프로필이나 동의 요청 없이 열린다', async () => {
  const fetch = vi.mocked(globalThis.fetch)
  mount('/opportunities'); await act(async () => {})
  expect(screen.getByRole('button', { name: '공고 검색하기' })).toBeVisible()
  expect(fetch.mock.calls.every(([request]) => new URL((request as Request).url).pathname === '/api/v1/me' && (request as Request).method === 'GET')).toBe(true)
})

it.each(['/journeys/invalid/conversation', '/journeys/invalid/profile', '/journeys/invalid/opportunities/invalid/application', '/journeys/invalid/save'])('잘못된 체험 주소 %s에서 공개 공고로 복귀한다', async path => {
  mount(path)
  expect(screen.getByRole('heading', { level: 1, name: /주소를 확인해 주세요/ })).toBeVisible()
  await userEvent.click(screen.getByRole('link', { name: /공고.*살펴보기/ }))
  expect(screen.getByRole('heading', { name: '조건에 맞는 기회 찾아보기' })).toBeVisible()
  expect(vi.mocked(fetch).mock.calls.every(([request]) => (request as Request).method === 'GET')).toBe(true)
})

it('렌더 오류의 내부 경로나 입력을 노출하지 않는다', () => {
  vi.spyOn(console, 'error').mockImplementation(() => {})
  function Broken(): never { throw new Error('private-input-and-server-path') }
  render(<ErrorBoundary><Broken /></ErrorBoundary>)
  expect(screen.getByRole('alert')).toHaveTextContent('새로 시작해 주세요.')
  expect(document.body).not.toHaveTextContent('private-input-and-server-path')
})
