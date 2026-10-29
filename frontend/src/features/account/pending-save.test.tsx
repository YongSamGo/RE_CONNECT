import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { PendingSave } from './PendingSave'

const id = '12345678-1234-4234-9234-123456789012'
const owner = '22345678-1234-4234-9234-123456789012'
const documentId = '32345678-1234-4234-9234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const stamp = '2026-10-20T00:00:00Z'
function setup(options: { bundle?: boolean; consent?: boolean; existing?: number | null; loseProfile?: boolean; loseDraft?: boolean; cancelFails?: boolean } = {}) {
  const bundle = options.bundle ?? false
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
async function load() { await userEvent.click(screen.getByRole('button',{name:'저장 자료 확인'})); await screen.findByRole('heading',{name:'확정한 경험 저장'}) }
async function save() { await userEvent.click(screen.getByLabelText('확정한 경험을 저장할게요.')); await userEvent.click(screen.getByRole('button',{name:'이대로 저장하기'})) }
it('requires explicit selection and saves only the confirmed profile', async () => {
  const { writes }=setup(); await load()
  expect(screen.getByRole('button',{name:'이대로 저장하기'})).toBeDisabled()
  await save(); expect(await screen.findByText('경험을 저장했습니다.')).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(await writes[0].clone().json()).toEqual({source:{type:'save_intent',save_intent_id:id},base_saved_version:null})
})
it('requires a separate acknowledgement before replacing an existing profile', async () => {
  const { writes }=setup({existing:3}); await load()
  await userEvent.click(screen.getByLabelText('확정한 경험을 저장할게요.'))
  expect(screen.getByRole('button',{name:'이대로 저장하기'})).toBeDisabled()
  await userEvent.click(screen.getByLabelText('기존 프로필을 새 내용으로 바꾸는 것을 확인했어요.'))
  await userEvent.click(screen.getByRole('button',{name:'이대로 저장하기'}))
  await screen.findByText('경험을 저장했습니다.')
  expect((await writes[0].clone().json()).base_saved_version).toBe(3)
})
it('reuses the exact profile write after losing its reply', async () => {
  const { writes }=setup({loseProfile:true}); await load(); await save()
  await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button',{name:'저장 결과 다시 확인'}))
  await screen.findByText('경험을 저장했습니다.')
  expect(writes).toHaveLength(2)
  expect(writes[0].headers.get('Idempotency-Key')).toBe(writes[1].headers.get('Idempotency-Key'))
  expect(await writes[0].clone().json()).toEqual(await writes[1].clone().json())
})
it('cancels legacy application save intents without saving either target', async () => {
  const { writes }=setup({bundle:true})
  await userEvent.click(screen.getByRole('button',{name:'저장 자료 확인'}))
  expect(await screen.findByText(/지원서 보관 기능은 제공하지 않습니다/)).toBeVisible()
  expect(writes).toHaveLength(1); expect(writes[0].method).toBe('DELETE')
  expect(screen.queryByRole('button',{name:'이대로 저장하기'})).not.toBeInTheDocument()
})
it('does not claim cancellation after a server failure', async () => {
  setup({cancelFails:true}); await load()
  await userEvent.click(screen.getByRole('button',{name:'취소'}))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText('저장을 취소했습니다.')).not.toBeInTheDocument()
  expect(document.body).not.toHaveTextContent('private cancellation path')
})
it('clears a profile selection on page departure and ignores late responses', async () => {
  setup(); await load(); act(()=>window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByRole('button',{name:'이대로 저장하기'})).not.toBeInTheDocument()
})
