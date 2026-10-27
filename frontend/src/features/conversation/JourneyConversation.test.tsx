import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { JourneyConversation, JourneyConversationRoute } from './JourneyConversation'
import { firstQuestion, parseMessageResult } from './model'
import type { ProfileView } from './model'

const id = '12345678-1234-1234-1234-123456789012'
const userId = '22345678-1234-1234-1234-123456789012'
const assistantId = '32345678-1234-1234-1234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function view(revision = 1): ProfileView {
  return { revision, confirmed: null, has_unconfirmed_changes: false, evidence: [], missing_for_recommendation: ['experiences', 'preferred_regions', 'activity_types'], draft: {
    schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [], paid_preference: null,
    available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null,
    certifications: null, completed_courses: null, activity_constraints: null,
  } }
}
function result(revision = 2, review = false) {
  return { revision, user_message_id: userId, profile: { ...view(revision), missing_for_recommendation: review ? [] : ['preferred_regions'] },
    assistant_message: review ? null : { message_id: assistantId, text: '어느 지역에서 활동하고 싶으세요?', created_at: '2026-10-18T00:00:00Z' }, notices: [], next_step: review ? 'review_profile' : 'continue' }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><Routes><Route path="/" element={<JourneyConversation journeyId={id} />} /><Route path={`/journeys/${id}/profile`} element={<p>서버 프로필 화면</p>} /></Routes></MemoryRouter>)
  return userEvent.setup()
}
async function prepare(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button', { name: '체험 대화 준비하기' }))
  await screen.findByRole('heading', { name: firstQuestion })
  await user.type(screen.getByLabelText('내가 해온 일'), '가상 도서관에서 책을 정리했어요.')
}

it('sends confirmed text with revision, CSRF and a server-independent request key, then shows exactly one next question', async () => {
  const fetch = vi.fn(async (request: Request) => json(request.method === 'POST' ? result() : request.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  const question = await screen.findByRole('heading', { name: '어느 지역에서 활동하고 싶으세요?' })
  expect(question).toHaveFocus()
  expect(screen.queryByText(firstQuestion)).not.toBeInTheDocument()
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('')
  const writes = fetch.mock.calls.filter(([request]) => request.method === 'POST')
  expect(writes).toHaveLength(1)
  expect(await writes[0][0].clone().json()).toEqual({ text: '가상 도서관에서 책을 정리했어요.', transcription_id: null, base_revision: 1 })
  expect(writes[0][0].headers.get('X-CSRF-Token')).toBe('token')
  expect(writes[0][0].headers.get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/)
  expect(fetch.mock.calls.some(([req]) => req.url.endsWith('/confirm'))).toBe(false)
})

it('preserves input and the exact request after a lost response and an in-progress result, without duplicate submission', async () => {
  let count = 0
  let finish!: (value: Response) => void
  const fetch = vi.fn(async (request: Request) => {
    if (request.method !== 'POST') return json(request.url.endsWith('/me') ? {} : view())
    count++
    if (count === 1) throw new Error('private transport detail')
    if (count === 2) return json({ code: 'REQUEST_IN_PROGRESS' }, 409)
    return new Promise<Response>(resolve => { finish = resolve })
  })
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByText(/연결하지 못했습니다/)
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('가상 도서관에서 책을 정리했어요.')
  expect(screen.getByLabelText('내가 해온 일')).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '같은 요청의 처리 결과 다시 확인' }))
  await screen.findByText(/이 요청을 처리하고 있습니다/)
  const form = screen.getByLabelText('내가 해온 일').closest('form')!
  act(() => { fireEvent.submit(form); fireEvent.submit(form) })
  expect(count).toBe(3)
  const writes = fetch.mock.calls.filter(([req]) => req.method === 'POST').map(([req]) => req)
  expect(new Set(writes.map(req => req.headers.get('Idempotency-Key'))).size).toBe(1)
  expect(await writes[0].clone().json()).toEqual(await writes[2].clone().json())
  await act(async () => finish(json(result())))
  await screen.findByRole('heading', { name: '어느 지역에서 활동하고 싶으세요?' })
})

it('keeps editable input on definitive AI failure and uses a fresh key on retry', async () => {
  let count = 0
  const fetch = vi.fn(async (request: Request) => request.method === 'POST'
    ? ++count === 1 ? json({ code: 'MODEL_UNAVAILABLE' }, 503) : json(result()) : json(request.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByText(/AI를 준비하고 있습니다/)
  expect(screen.getByLabelText('내가 해온 일')).toBeEnabled()
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByRole('heading', { name: '어느 지역에서 활동하고 싶으세요?' })
  const writes = fetch.mock.calls.filter(([req]) => req.method === 'POST')
  expect(writes[0][0].headers.get('Idempotency-Key')).not.toBe(writes[1][0].headers.get('Idempotency-Key'))
})

it('requires a revision refresh after conflict, retains input, and never applies an old replay as a new revision', async () => {
  let count = 0, revision = 1
  const fetch = vi.fn(async (request: Request) => {
    if (request.method === 'POST') {
      if (++count === 1) { revision = 4; return json({ code: 'VERSION_CONFLICT' }, 409) }
      return json(result(2))
    }
    return json(request.url.endsWith('/me') ? {} : view(revision))
  })
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByRole('heading', { name: '최신 프로필을 확인해 주세요' })
  expect(screen.getByRole('button', { name: '확인한 내용 보내기' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '최신 프로필 상태 확인' }))
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('가상 도서관에서 책을 정리했어요.')
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByText(/응답을 확인하지 못했습니다/)
  expect(screen.queryByRole('heading', { name: '어느 지역에서 활동하고 싶으세요?' })).not.toBeInTheDocument()
  const writes = fetch.mock.calls.filter(([req]) => req.method === 'POST')
  expect((await writes[1][0].clone().json()).base_revision).toBe(4)
})

it('allows profile navigation while pending and discards the late response on unmount', async () => {
  let finish!: (value: Response) => void
  const fetch = vi.fn(async (request: Request) => request.method === 'POST' ? new Promise<Response>(resolve => { finish = resolve }) : json(request.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  const write = fetch.mock.calls.find(([req]) => req.method === 'POST')![0]
  await user.click(screen.getByRole('link', { name: '언제든 프로필 확인하기' }))
  expect(await screen.findByText('서버 프로필 화면')).toBeVisible()
  expect(write.signal.aborted).toBe(true)
  await act(async () => finish(json(result())))
  expect(screen.queryByText('어느 지역에서 활동하고 싶으세요?')).not.toBeInTheDocument()
})

it('clears all sensitive screen state on pagehide and ignores the late response', async () => {
  let finish!: (value: Response) => void
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'POST' ? new Promise<Response>(resolve => { finish = resolve }) : json(request.url.endsWith('/me') ? {} : view())))
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => finish(json(result())))
  expect(screen.queryByLabelText('내가 해온 일')).not.toBeInTheDocument()
  expect(screen.queryByText(/같은 내용과 요청 번호/)).not.toBeInTheDocument()
})

it('stops waiting without claiming server cancellation and rechecks the same request', async () => {
  let finish!: (value: Response) => void, count = 0
  const fetch = vi.fn(async (request: Request) => request.method === 'POST' ? ++count === 1 ? new Promise<Response>(resolve => { finish = resolve }) : json(result()) : json(request.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await user.click(screen.getByRole('button', { name: '응답 기다리기 중지' }))
  await user.click(screen.getByRole('button', { name: '같은 요청의 처리 결과 다시 확인' }))
  await screen.findByRole('heading', { name: '어느 지역에서 활동하고 싶으세요?' })
  await act(async () => finish(json(result())))
  const writes = fetch.mock.calls.filter(([req]) => req.method === 'POST')
  expect(writes[0][0].headers.get('Idempotency-Key')).toBe(writes[1][0].headers.get('Idempotency-Key'))
})

it('shows the review action without auto-confirming and passes the structural accessibility check', async () => {
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => json(request.method === 'POST' ? result(2, true) : request.url.endsWith('/me') ? {} : view())))
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByRole('heading', { name: '프로필 내용을 확인해 주세요' })
  expect(screen.queryByLabelText('내가 해온 일')).not.toBeInTheDocument()
  const report = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
  expect(report.violations).toEqual([])
  expect(report.passes.length).toBeGreaterThan(0)
})

it.each(['NOT_FOUND', 'SESSION_EXPIRED', 'CONSENT_REQUIRED'])('discards input when access is lost: %s', async code => {
  const status = code === 'NOT_FOUND' ? 404 : code === 'SESSION_EXPIRED' ? 401 : 403
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'POST' ? json({ code }, status) : json(request.url.endsWith('/me') ? {} : view())))
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByRole('alert')
  expect(screen.queryByLabelText('내가 해온 일')).not.toBeInTheDocument()
})

it('only clears input after actual deletion succeeds, preserving it on failure', async () => {
  let deletes = 0
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'DELETE'
    ? ++deletes === 1 ? json({ code: 'SERVICE_UNAVAILABLE' }, 503) : new Response(null, { status: 204 })
    : json(request.url.endsWith('/me') ? {} : view())))
  const user = mount(); await prepare(user)
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  expect(deletes).toBe(0)
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('가상 도서관에서 책을 정리했어요.')
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  await screen.findByRole('button', { name: '체험 대화 준비하기' })
  expect(screen.queryByLabelText('내가 해온 일')).not.toBeInTheDocument()
})

it('rejects this conversation URL on reload before sending an API request', () => {
  vi.spyOn(performance, 'getEntriesByType').mockReturnValue([{ type: 'reload', name: `https://app.test/journeys/${id}/conversation` }] as unknown as PerformanceEntryList)
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={[`/journeys/${id}/conversation`]}><Routes><Route path="/" element={<p>시작 화면</p>} /><Route path="/journeys/:journeyId/conversation" element={<JourneyConversationRoute />} /></Routes></MemoryRouter>)
  expect(screen.getByText('시작 화면')).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
})

it('validates revisions, ids, question/next-step, notices and profile before displaying a message', () => {
  expect(parseMessageResult(result(), 1).revision).toBe(2)
  for (const bad of [result(1), { ...result(), user_message_id: 'forged' }, { ...result(), profile: view(99) },
    { ...result(), next_step: 'review_profile' }, { ...result(), assistant_message: null }, { ...result(), notices: ['x'.repeat(301)] },
    { ...result(), assistant_message: { ...result().assistant_message, created_at: 'not-a-date' } }]) {
    expect(() => parseMessageResult(bad, 1)).toThrow()
  }
})
