import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { PendingSave } from './PendingSave'

const id = '12345678-1234-4234-9234-123456789012'
const owner = '22345678-1234-4234-9234-123456789012'
const documentId = '32345678-1234-4234-9234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const stamp = '2026-10-20T00:00:00Z'
function setup(options: { bundle?: boolean; consent?: boolean; existing?: number | null; loseProfile?: boolean; loseDraft?: boolean; cancelFails?: boolean } = {}) {
  const bundle = options.bundle ?? true
  const intent = { save_intent_id: id, expires_at: new Date(Date.now() + 600000).toISOString(), targets: { profile: true, draft: bundle }, existing_saved_profile_version: options.existing ?? null }
  const me = { authenticated: true, user: { id: owner, roles: ['user'], mfa_verified: false, reauth_until: null }, consents: options.consent === false ? [] : [{ purpose: 'storage', notice_version: 'fixture-storage', granted_at: stamp }], pending_save_intent: intent as typeof intent | null }
  const writes: Request[] = []
  const profileReply = { version: options.existing ? options.existing + 1 : 1, created: true, replaced_version: options.existing ?? null, saved_at: stamp }
  let lostProfile = false, lostDraft = false
  const fetch = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname
    if (request.method === 'GET' && path === '/api/v1/me') return json(me)
    writes.push(request.clone())
    if (request.method === 'DELETE' && path === '/api/v1/auth/save-intents/' + id) {
      if (options.cancelFails) return json({ code: 'SERVICE_UNAVAILABLE', message: 'private cancellation path' }, 503)
      me.pending_save_intent = null; return new Response(null, { status: 204 })
    }
    if (request.method === 'POST' && path === '/api/v1/profiles/me/versions') {
      if (!bundle) me.pending_save_intent = null
      if (options.loseProfile && !lostProfile) { lostProfile = true; throw new Error('private transport detail') }
      return json(profileReply, 201)
    }
    if (request.method === 'POST' && path === '/api/v1/drafts') {
      me.pending_save_intent = null
      if (options.loseDraft && !lostDraft) { lostDraft = true; throw new Error('private transport detail') }
      return json({ document_id: documentId, version: 1, profile_version: profileReply.version, saved_at: stamp }, 201)
    }
    throw new Error('unexpected endpoint')
  })
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><PendingSave /></MemoryRouter>)
  return { me, fetch, writes, profileReply }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
async function load() { await userEvent.click(screen.getByRole('button', { name: '현재 저장 대기 확인' })); await screen.findByRole('heading', { name: /확정 프로필 저장|프로필과 지원서 함께 저장/ }) }
async function checkBundle() { await userEvent.click(screen.getByLabelText('프로필과 지원서 모두 저장 대상임을 확인했어요.')) }

it('requires explicit bundle confirmation and separates profile and draft writes', async () => {
  const { writes } = setup(); await load()
  expect(writes).toHaveLength(0)
  expect(screen.getByRole('button', { name: '확인한 프로필 저장' })).toBeDisabled()
  expect(screen.getByRole('button', { name: /프로필에 연결해 지원서 저장/ })).toBeDisabled()
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  const accessibility = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
  expect(accessibility.violations).toEqual([])
  await checkBundle()
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' }))
  expect(await screen.findByText('프로필 저장을 확인했습니다. 지원서는 아직 저장하지 않았습니다.')).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(await writes[0]!.json()).toEqual({ source: { type: 'save_intent', save_intent_id: id }, base_saved_version: null })
  await userEvent.click(screen.getByRole('button', { name: /프로필에 연결해 지원서 저장/ }))
  expect(await screen.findByText('프로필과 지원서 저장을 모두 완료했습니다.')).toBeVisible()
  expect(await writes[1]!.json()).toEqual({ source: { type: 'save_intent', save_intent_id: id }, document_id: null, base_document_version: null })
  expect(writes[0]!.headers.get('Idempotency-Key')).not.toBe(writes[1]!.headers.get('Idempotency-Key'))
  expect(screen.queryByRole('button', { name: '남은 저장 대기 취소' })).not.toBeInTheDocument()
})

it('requires separate existing-profile replacement confirmation and sends its exact base', async () => {
  const { writes } = setup({ existing: 3 }); await load(); await checkBundle()
  expect(screen.getByRole('button', { name: '확인한 프로필 저장' })).toBeDisabled()
  await userEvent.click(screen.getByLabelText('기존 저장 프로필 기준으로 교체 여부를 확인했어요.'))
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' }))
  await screen.findByText('프로필 저장을 확인했습니다. 지원서는 아직 저장하지 않았습니다.')
  expect((await writes[0]!.json()).base_saved_version).toBe(3)
})

it('never fabricates or automatically grants missing storage consent', async () => {
  const { writes } = setup({ consent: false }); await load(); await checkBundle()
  expect(screen.getByText('저장 동의가 필요해요')).toBeVisible()
  expect(screen.getByRole('button', { name: '확인한 프로필 저장' })).toBeDisabled()
  expect(writes).toHaveLength(0)
  await userEvent.click(screen.getByRole('button', { name: '남은 저장 대기 취소' }))
  expect(await screen.findByText(/남아 있는 저장 대기를 취소했습니다/)).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(writes[0]!.method).toBe('DELETE')
})

it('replays exactly the same profile request after a lost successful response even when pending was consumed', async () => {
  const { writes } = setup({ bundle: false, loseProfile: true }); await load()
  await userEvent.click(screen.getByLabelText('확정 프로필 저장을 확인했어요.'))
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText('프로필 저장을 완료했습니다.')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '같은 요청으로 프로필 저장 재확인' }))
  expect(await screen.findByText('프로필 저장을 완료했습니다.')).toBeVisible()
  expect(writes).toHaveLength(2)
  expect(writes[0]!.headers.get('Idempotency-Key')).toBe(writes[1]!.headers.get('Idempotency-Key'))
  expect(await writes[0]!.json()).toEqual(await writes[1]!.json())
  expect(document.body).not.toHaveTextContent('private transport detail')
})

it('retains the successful profile and replays only the draft after a lost draft response', async () => {
  const { writes } = setup({ loseDraft: true }); await load(); await checkBundle()
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' })); await screen.findByText('프로필 저장을 확인했습니다. 지원서는 아직 저장하지 않았습니다.')
  await userEvent.click(screen.getByRole('button', { name: /프로필에 연결해 지원서 저장/ }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByText(/지원서는 아직 저장 완료로 확인되지 않았습니다/)).toBeVisible()
  expect(screen.queryByText('프로필과 지원서 저장을 모두 완료했습니다.')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: /프로필에 연결해 지원서 저장/ }))
  expect(await screen.findByText('프로필과 지원서 저장을 모두 완료했습니다.')).toBeVisible()
  expect(writes).toHaveLength(3)
  expect(writes[1]!.headers.get('Idempotency-Key')).toBe(writes[2]!.headers.get('Idempotency-Key'))
  expect(await writes[1]!.json()).toEqual(await writes[2]!.json())
})

it('does not report cancellation completion or forget pending state after a failed cancellation', async () => {
  setup({ cancelFails: true }); await load()
  await userEvent.click(screen.getByRole('button', { name: '남은 저장 대기 취소' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText(/남아 있는 저장 대기를 취소했습니다/)).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '남은 저장 대기 취소' })).toBeEnabled()
  expect(document.body).not.toHaveTextContent('private cancellation path')
})

it('rejects a different current member before applying an earlier save choice', async () => {
  const { me, writes } = setup(); await load(); await checkBundle()
  me.user.id = documentId
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(writes).toHaveLength(0)
  expect(screen.queryByLabelText('프로필과 지원서 모두 저장 대상임을 확인했어요.')).not.toBeInTheDocument()
})

it('checks current consent again before sending a previously confirmed operation', async () => {
  const { me, writes } = setup(); await load(); await checkBundle()
  me.consents = []
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(writes).toHaveLength(0)
})

it('drops the loaded pending choice on pagehide and never stores it in browser persistence', async () => {
  const { writes } = setup(); await load(); await checkBundle()
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByLabelText('프로필과 지원서 모두 저장 대상임을 확인했어요.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '현재 저장 대기 확인' })).toBeEnabled()
  expect(writes).toHaveLength(0)
})

it('discards a body parser that finishes after pagehide even after transport validation has finished', async () => {
  const { me } = setup()
  const original = Response.prototype.text
  let reads = 0, finish!: (value: string) => void
  vi.spyOn(Response.prototype, 'text').mockImplementation(function (this: Response) {
    reads += 1
    if (reads === 1) return new Promise(resolve => { finish = resolve })
    return original.call(this)
  })
  await userEvent.click(screen.getByRole('button', { name: '현재 저장 대기 확인' }))
  await waitFor(() => expect(reads).toBe(1))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => { finish(JSON.stringify(me)) })
  expect(screen.queryByLabelText('프로필과 지원서 모두 저장 대상임을 확인했어요.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '현재 저장 대기 확인' })).toBeEnabled()
})
