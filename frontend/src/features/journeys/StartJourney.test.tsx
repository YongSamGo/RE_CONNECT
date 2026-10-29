import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { StartJourney } from './StartJourney'

// jsdom lacks the native dialog methods. These tests cover consent/request flow;
// focus containment and the backdrop are checked in the browser separately.
Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } },
  close: { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open'); this.dispatchEvent(new Event('close')) } },
})

const id = '12345678-1234-4234-9234-123456789012'
const notice = { version: 'fixture-ai', title: '가상 AI 처리 안내', controller: '가상 운영 주체', contact: '시험 문의처',
  aws_region: '시험 리전', body: '가상 시험 안내 본문', retention: '시험 보관', deletion: '시험 삭제' }
const checkbox = '위 안내문을 읽고 AI 처리에 동의합니다.'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const journey = () => ({ journey_id: id, revision: 1, confirmed: null,
  expires_at: new Date(Date.now() + 7200000).toISOString(), idle_expires_at: new Date(Date.now() + 1800000).toISOString() })

function mount(options: { published?: boolean; stale?: boolean; lost?: boolean; deferred?: (request: Request) => Promise<Response> } = {}) {
  let granted = false, created = 0
  const calls: Request[] = []
  const fetch = vi.fn(async (request: Request) => {
    calls.push(request)
    const path = new URL(request.url).pathname
    if (path.endsWith('/me')) return json({ authenticated: false, user: null, pending_save_intent: null,
      consents: granted ? [{ purpose: 'ai_processing', notice_version: notice.version, granted_at: new Date().toISOString() }] : [] })
    if (path.endsWith('/consents/notices')) return json({ ai_processing: options.published === false ? null : notice, storage: null, login_available: false })
    if (path.endsWith('/consents')) {
      if (options.stale) return json({ code: 'CONSENT_REQUIRED', message: 'private notice error' }, 403)
      granted = true
      return json({ purpose: 'ai_processing', notice_version: notice.version, granted_at: new Date().toISOString() }, 201)
    }
    if (path.endsWith('/journeys')) {
      created += 1
      if (options.lost && created === 1) throw new TypeError('private network detail')
      return options.deferred ? options.deferred(request) : json(journey(), 201)
    }
    throw new Error('Unexpected request')
  })
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=initial; Secure; Path=/'
  const onStart = vi.fn()
  render(<MemoryRouter initialEntries={['/start']}><Routes><Route path="/start" element={<StartJourney onStart={onStart} />} />
    <Route path="/journeys/:id/conversation" element={<h1>체험 대화 연결됨</h1>} /></Routes></MemoryRouter>)
  return { calls, fetch, onStart }
}

async function readAndAgree() {
  await userEvent.click(screen.getByRole('button', { name: '시작하기' }))
  await userEvent.click(await screen.findByLabelText(checkbox))
}

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('does not write or offer consent when no AI notice has been published', async () => {
  const { calls } = mount({ published: false })
  await userEvent.click(screen.getByRole('button', { name: '시작하기' }))
  expect(await screen.findByText('AI 처리 안내가 아직 준비되지 않았어요')).toBeVisible()
  expect(screen.queryByLabelText(checkbox)).not.toBeInTheDocument()
  expect(calls.every(request => request.method === 'GET')).toBe(true)
})

it('keeps the specified entry layout and closes the current notice without recording consent', async () => {
  const { calls } = mount()
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('시작하기 전에 확인해주세요')
  expect(screen.getAllByRole('button', { name: /자세히 보기/ })).toHaveLength(3)
  expect(screen.queryByText(/가상 경험|미리보기/)).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '시작하기' }))
  expect(await screen.findByRole('dialog', { name: 'AI 처리 안내와 동의' })).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '닫기' }))
  expect(screen.queryByRole('dialog', { name: 'AI 처리 안내와 동의' })).not.toBeInTheDocument()
  expect(calls.every(request => request.method === 'GET')).toBe(true)
})

it('shows a short retention summary and offers further details without recording consent', async () => {
  const { calls } = mount()
  await userEvent.click(screen.getByRole('button', { name: '보관 및 삭제 자세히 보기' }))
  expect(screen.getByText(/시작 후 최대 2시간 보관합니다/)).toHaveTextContent('30분 동안 활동이 없으면 더 일찍 만료됩니다')
  expect(screen.getByText(/저장 대기 자료는 최대 10분 보관합니다/)).toBeVisible()
  expect(calls).toHaveLength(0)
})

it('requires explicit consent and starts the existing server conversation with CSRF protection', async () => {
  const { calls, onStart } = mount()
  await userEvent.click(screen.getByRole('button', { name: '시작하기' }))
  expect(await screen.findByRole('checkbox', { name: checkbox })).not.toBeChecked()
  expect(calls.every(request => request.method === 'GET')).toBe(true)
  await userEvent.click(screen.getByLabelText(checkbox))
  expect(await screen.findByRole('heading', { name: '체험 대화 연결됨' })).toBeVisible()
  expect(onStart).toHaveBeenCalledOnce()
  const writes = calls.filter(request => request.method === 'POST')
  expect(writes.map(request => new URL(request.url).pathname)).toEqual(['/api/v1/consents', '/api/v1/journeys'])
  expect(await writes[0]!.json()).toEqual({ purpose: 'ai_processing', notice_version: notice.version })
  expect(await writes[1]!.json()).toEqual({ ai_notice_version: notice.version, saved_profile: null })
  expect(writes[1]!.headers.get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/)
  expect(writes.every(request => request.headers.get('X-CSRF-Token') === 'initial')).toBe(true)
})

it('requires reading again after a rejected notice and never starts a journey', async () => {
  const { calls } = mount({ stale: true })
  await readAndAgree()
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByLabelText(checkbox)).not.toBeInTheDocument()
  expect(calls.some(request => new URL(request.url).pathname.endsWith('/journeys'))).toBe(false)
  expect(document.body).not.toHaveTextContent('private notice error')
})

it('reuses the creation key and body when a creation response is lost', async () => {
  const { calls } = mount({ lost: true })
  await readAndAgree()
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button', { name: '같은 요청으로 다시 확인하기' }))
  await screen.findByRole('heading', { name: '체험 대화 연결됨' })
  const attempts = calls.filter(request => new URL(request.url).pathname.endsWith('/journeys'))
  expect(attempts).toHaveLength(2)
  expect(attempts[0]!.headers.get('Idempotency-Key')).toBe(attempts[1]!.headers.get('Idempotency-Key'))
  expect(await attempts[0]!.json()).toEqual(await attempts[1]!.json())
  expect(document.body).not.toHaveTextContent('private network detail')
})

it('rejects a changed session before submitting consent', async () => {
  const { calls } = mount()
  await userEvent.click(screen.getByRole('button', { name: '시작하기' }))
  await screen.findByLabelText(checkbox)
  document.cookie = '__Host-rc_csrf=rotated; Secure; Path=/'
  await userEvent.click(screen.getByLabelText(checkbox))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(calls.every(request => request.method === 'GET')).toBe(true)
})

it('discards a late creation result after leaving the page', async () => {
  let finish!: (response: Response) => void
  const { onStart, calls } = mount({ deferred: () => new Promise(resolve => { finish = resolve }) })
  await readAndAgree()
  await waitFor(() => expect(finish).toBeTypeOf('function'))
  await act(async () => { window.dispatchEvent(new Event('pagehide')); finish(json(journey(), 201)) })
  expect(calls.at(-1)!.signal.aborted).toBe(true)
  expect(onStart).not.toHaveBeenCalled()
  expect(screen.queryByRole('heading', { name: '체험 대화 연결됨' })).not.toBeInTheDocument()
})
