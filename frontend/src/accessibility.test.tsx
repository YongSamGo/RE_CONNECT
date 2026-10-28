import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import App from './App'
import { anonymousSession } from './api/fixtures'
import { sampleDetail } from './features/public-opportunities/test-fixtures'

beforeEach(() => {
  // axe feature detection asks for a canvas context; jsdom has no renderer.
  // Report the missing capability without stubbing audit results or rules.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function mount(path: string) { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
async function audit() {
  // jsdom cannot calculate rendered contrast/geometry. Inspect the app subtree
  // rather than asserting that jsdom's host document has production HTML attrs.
  const result = await axe.run(document.getElementById('root-test')!, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    rules: { 'color-contrast': { enabled: false } },
  })
  expect(result.passes.length).toBeGreaterThan(0)
  expect(result.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([])
}
function app(path: string) {
  const view = mount(path)
  view.container.id = 'root-test'
  return view
}

it.each(['/', '/consent', '/opportunities', '/opportunities/preview', '/opportunities/preview/preparation', '/me', '/me/saved', '/me/save', '/auth/result?purpose=login&status=success', '/auth/result?purpose=login&status=unknown', '/admin', '/missing', '/journeys/invalid/profile', '/journeys/invalid/save', '/journeys/invalid/opportunities/invalid/preparation'])('%s 화면의 구조·레이블·ARIA를 자동 검사한다', async path => {
  vi.stubGlobal('fetch', vi.fn())
  app(path)
  await screen.findByRole('heading', { level: 1 })
  await audit()
})

it('audits an asynchronous request error while preserving the result focus and retry action', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('test network failure')))
  app('/opportunities')
  await userEvent.click(screen.getByRole('button', { name: '공고 검색하기' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByRole('region', { name: '공고 조회 결과' })).toHaveFocus()
  expect(screen.getByRole('button', { name: '같은 조건으로 다시 조회' })).toBeVisible()
  await audit()
})

it('audits loaded public detail and the expanded report form', async () => {
  const detail = sampleDetail()
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(detail), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  app(`/opportunities/${detail.id}`)
  await userEvent.click(screen.getByRole('button', { name: '공고 정보 불러오기' }))
  expect(await screen.findByRole('heading', { name: detail.title })).toBeVisible()
  await userEvent.click(screen.getByText('공고 정보 오류 알리기'))
  expect(screen.getByRole('combobox', { name: '어떤 정보가 다른가요?' })).toBeVisible()
  await audit()
})

it('audits a confirmed login result with a separate save action', async () => {
  const id = '12345678-1234-4234-9234-123456789012'
  const session = { ...anonymousSession, authenticated: true, user: { id, roles: ['user'], mfa_verified: false, reauth_until: null },
    pending_save_intent: { save_intent_id: id, expires_at: new Date(Date.now() + 600000).toISOString(), targets: { profile: true, draft: true }, existing_saved_profile_version: null } }
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify(session), { status: 200, headers: { 'Content-Type': 'application/json' } })))
  app('/auth/result?purpose=save&status=success')
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByRole('link', { name: '저장 대기 자료 확인' })).toBeVisible()
  await audit()
})

it('audits experience input, empty profile errors and manual writing in one preview lifetime', async () => {
  vi.stubGlobal('fetch', vi.fn())
  app('/consent')
  const user = userEvent.setup()
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: /시작하기/ }))
  await audit()
  await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
  expect(screen.getByRole('button', { name: '활동 조건 고르기' })).toBeDisabled()
  await audit()
  await user.click(screen.getByRole('link', { name: '경험 수정하기' }))
  await user.type(screen.getByRole('textbox'), '가상 경험')
  await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
  await user.click(screen.getByRole('button', { name: '활동 조건 고르기' }))
  expect(screen.getByRole('heading', { level: 1 })).toHaveFocus()
  await audit()
  await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
  expect(screen.getByRole('region', { name: '입력한 항목을 확인해 주세요' })).toHaveFocus()
  await audit()
  await user.click(screen.getByText('다른 화면 살펴보기', { exact: true }))
  await user.click(screen.getByRole('link', { name: '지원 내용 직접 작성해 보기' }))
  fireEvent.change(screen.getByRole('textbox', { name: '자기소개' }), { target: { value: '가상 경험입니다.' } })
  fireEvent.change(screen.getByRole('textbox', { name: '지원동기' }), { target: { value: '가상의 지원 이유입니다.' } })
  await user.click(screen.getByRole('checkbox', { name: '두 항목을 읽고 내 경험과 맞는지 확인했어요.' }))
  await audit()
})
