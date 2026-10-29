import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../../App'
import { anonymousSession } from '../../api/fixtures'
import { AuthResult } from './AuthResult'

const id = '12345678-1234-4234-9234-123456789012'
const member = { ...anonymousSession, authenticated: true, user: { id, roles: ['user'], mfa_verified: false, reauth_until: null } }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount(query = '?purpose=login&status=success') {
  return render(<MemoryRouter initialEntries={['/auth/result' + query]}><AuthResult /></MemoryRouter>)
}
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); vi.unstubAllGlobals() })

it.each(['', '?purpose=login&status=success&return_url=https://attacker.invalid', '?purpose=login&purpose=save&status=success', '?purpose=save&status=success&status=failed', '?purpose=admin&status=success', '?purpose=login&status=unknown', '?purpose=login&status=success&code=private-code'])('rejects ambiguous or extra callback query %s without reflecting it', (query) => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  mount(query)
  expect(screen.getByText('돌아온 주소를 확인할 수 없어요')).toBeVisible()
  expect(screen.queryByRole('button', { name: '서버에서 현재 상태 확인' })).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  expect(document.body).not.toHaveTextContent('attacker.invalid')
  expect(document.body).not.toHaveTextContent('private-code')
})


it.each(['cancelled', 'failed', 'expired'])('checks the server automatically after %s without writing consent or saved content', async status => {
  const fetch = vi.fn(async (_request: Request) => json(member)); vi.stubGlobal('fetch', fetch)
  mount(`?purpose=save&status=${status}`)
  expect(await screen.findByRole('heading', { name: '로그인 상태를 확인했어요' })).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
  expect(screen.queryByRole('link', { name: '저장 대기 자료 확인' })).not.toBeInTheDocument()
})
it('success callbacks go straight to my information and still verify the server session', async () => {
  const fetch = vi.fn(async (_request: Request) => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={['/auth/result?purpose=login&status=success']}><App /></MemoryRouter>)
  expect(await screen.findByText('회원 정보를 보려면 로그인해 주세요.')).toBeVisible()
  expect(screen.queryByRole('heading', { name: '로그인 확인' })).not.toBeInTheDocument()
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
})
it('returns a save login to the pending save screen without writing before confirmation', async () => {
  const pending = { save_intent_id: '52345678-1234-4234-9234-123456789012', targets: { profile: true, draft: false }, existing_saved_profile_version: null, expires_at: new Date(Date.now() + 600000).toISOString() }
  const fetch = vi.fn(async (_request: Request) => json({ ...member, pending_save_intent: pending,
    consents: [{ purpose: 'storage', notice_version: 'storage-v1', granted_at: '2026-10-18T00:00:00Z' }] }))
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={['/auth/result?purpose=save&status=success']}><App /></MemoryRouter>)
  expect(await screen.findByRole('button', { name: '이대로 저장하기' })).toBeDisabled()
  expect(screen.getByLabelText('확정한 경험을 저장할게요.')).not.toBeChecked()
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
  expect(screen.queryByRole('heading', { name: '나의 정보' })).not.toBeInTheDocument()
})
it.each(['?purpose=save&purpose=login&status=success', '?purpose=save&status=success&return_url=https://attacker.invalid'])('rejects an ambiguous success callback at the application route: %s', query => {
  const fetch = vi.fn(async (_request: Request) => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={['/auth/result' + query]}><App /></MemoryRouter>)
  expect(screen.getByText('돌아온 주소를 확인할 수 없어요')).toBeVisible()
  // The shared header may check /me, but the invalid callback opens no private screen.
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET' && request.url.endsWith('/me'))).toBe(true)
  expect(document.body).not.toHaveTextContent('attacker.invalid')
})
it('offers the pending save only when the checked server intent has not expired', async () => {
  const pending = { save_intent_id: '52345678-1234-4234-9234-123456789012', targets: { profile: true, draft: false }, existing_saved_profile_version: null, expires_at: new Date(Date.now() + 600000).toISOString() }
  vi.stubGlobal('fetch', vi.fn(async () => json({ ...member, pending_save_intent: pending })))
  const first = mount('?purpose=save&status=success')
  expect(await screen.findByRole('link', { name: '저장 대기 자료 확인' })).toHaveAttribute('href', '/me/save')
  first.unmount()
  vi.unstubAllGlobals()
  vi.stubGlobal('fetch', vi.fn(async () => json({ ...member, pending_save_intent: { ...pending, expires_at: new Date(Date.now() - 60000).toISOString() } })))
  mount('?purpose=save&status=success')
  expect(await screen.findByRole('heading', { name: '로그인 상태를 확인했어요' })).toBeVisible()
  expect(screen.queryByRole('link', { name: '저장 대기 자료 확인' })).not.toBeInTheDocument()
})
it.each([null, new Date(Date.now()-60000).toISOString(), new Date(Date.now()+600000).toISOString()])('reflects only valid server reauthentication %s', async reauth_until => {
  vi.stubGlobal('fetch', vi.fn(async () => json({ ...member, user: { ...member.user, reauth_until } })))
  mount('?purpose=reauth&status=success')
  expect(await screen.findByText(reauth_until && Date.parse(reauth_until)>Date.now() ? /서버에서 유효한 재인증/ : /현재 유효한 재인증/)).toBeVisible()
  expect(screen.queryByRole('button', { name: /탈퇴/ })).not.toBeInTheDocument()
})
it.each([json({ code: 'SERVICE_UNAVAILABLE', message: 'private internal path' },503), json({ ...anonymousSession, authenticated: true })])('does not trust failed or malformed session responses', async response => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response)); mount()
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(document.body).not.toHaveTextContent('private internal path')
  expect(screen.queryByRole('heading', { name: '로그인 상태를 확인했어요' })).not.toBeInTheDocument()
})
it('discards a late response after departure', async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(resolve => { finish=resolve })))
  mount(); await act(async () => {})
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => finish(json(member)))
  expect(screen.queryByRole('heading', { name: '로그인 상태를 확인했어요' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '로그인 상태 다시 확인' })).toBeEnabled()
})
it('clears checked identity when restored from browser cache', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => json(member))); mount()
  await screen.findByRole('heading', { name: '로그인 상태를 확인했어요' })
  act(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })))
  expect(screen.queryByRole('heading', { name: '로그인 상태를 확인했어요' })).not.toBeInTheDocument()
})
