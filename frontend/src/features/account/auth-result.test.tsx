import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
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

it('routes the server return address and never trusts success without checking the current session', async () => {
  const fetch = vi.fn().mockResolvedValue(json(anonymousSession))
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={['/auth/result?purpose=login&status=success']}><App /></MemoryRouter>)
  expect(screen.getByRole('heading', { name: '현재 로그인 상태를 확인해요' })).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText('현재 로그인하지 않은 상태입니다. 로그인이나 저장 완료를 확인할 수 없습니다.')).toBeVisible()
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
  const request = fetch.mock.calls[0]![0] as Request
  expect(new URL(request.url).pathname).toBe('/api/v1/me')
  expect(request.method).toBe('GET')
  expect(fetch).toHaveBeenCalledTimes(1)
})

it.each(['', '?purpose=login&status=success&return_url=https://attacker.invalid', '?purpose=login&purpose=save&status=success', '?purpose=save&status=success&status=failed', '?purpose=admin&status=success', '?purpose=login&status=unknown', '?purpose=login&status=success&code=private-code'])('rejects ambiguous or extra callback query %s without reflecting it', (query) => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  mount(query)
  expect(screen.getByText('돌아온 주소를 확인할 수 없어요')).toBeVisible()
  expect(screen.queryByRole('button', { name: '서버에서 현재 상태 확인' })).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
  expect(document.body).not.toHaveTextContent('attacker.invalid')
  expect(document.body).not.toHaveTextContent('private-code')
})

it.each(['cancelled', 'failed', 'expired'])('allows a server state check after %s without claiming request completion', async status => {
  const fetch = vi.fn().mockResolvedValue(json(member)); vi.stubGlobal('fetch', fetch)
  mount(`?purpose=save&status=${status}`)
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText('로그인 상태를 확인했어요')).toBeVisible()
  expect(screen.getByText('계속할 수 있는 저장 대기 요청이 없습니다. 저장된 자료는 내 정보에서 따로 조회해 주세요.')).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('makes a live profile and draft bundle explicit and never writes consent or saves on return', async () => {
  const fetch = vi.fn().mockResolvedValue(json({ ...member, pending_save_intent: { save_intent_id: id, expires_at: new Date(Date.now() + 600000).toISOString(), targets: { profile: true, draft: true }, existing_saved_profile_version: 2 } }))
  vi.stubGlobal('fetch', fetch); mount('?purpose=save&status=success')
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText('프로필과 지원서를 함께 저장하는 요청입니다. 프로필도 저장 대상에 포함됩니다.')).toBeVisible()
  expect(screen.getByText('기존 저장 프로필이 있습니다. 교체 여부를 직접 확인해야 합니다.')).toBeVisible()
  expect(screen.getByText(/로그인만으로 자료를 저장하지는 않았어요/)).toBeVisible()
  expect(screen.getByRole('status')).toHaveTextContent('로그인 상태를 확인했어요.')
  expect(screen.getByRole('link', { name: '저장 대기 자료 확인' }).closest('[role="status"]')).toBeNull()
  expect(document.body).not.toHaveTextContent(id)
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('does not offer a stale server pending intent as an active request', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ...member, pending_save_intent: { save_intent_id: id, expires_at: new Date(Date.now() - 1000).toISOString(), targets: { profile: true, draft: false }, existing_saved_profile_version: null } })))
  mount('?purpose=save&status=success')
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText(/계속할 수 있는 저장 대기 요청이 없습니다/)).toBeVisible()
  expect(screen.queryByText('저장 대기 자료가 있어요')).not.toBeInTheDocument()
})

it.each([null, new Date(Date.now() - 60000).toISOString(), new Date(Date.now() + 600000).toISOString()])('checks reauthentication against server time-bound state %s', async reauth_until => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ...member, user: { ...member.user, reauth_until } })))
  mount('?purpose=reauth&status=success')
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText(reauth_until && Date.parse(reauth_until) > Date.now() ? /서버에서 유효한 재인증을 확인했습니다/ : /현재 유효한 재인증이 확인되지 않았습니다/)).toBeVisible()
  expect(screen.queryByRole('button', { name: /탈퇴/ })).not.toBeInTheDocument()
})

it('hides backend failure details and never reports a member after a failed check', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ code: 'SERVICE_UNAVAILABLE', message: 'private internal path' }, 503)))
  mount(); await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(document.body).not.toHaveTextContent('private internal path')
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
})

it('rejects a successful HTTP response whose authenticated flag disagrees with its user', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json({ ...anonymousSession, authenticated: true })))
  mount(); await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
})

it('discards a late member response after the page has been hidden', async () => {
  let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn().mockImplementation(() => new Promise<Response>(resolve => { finish = resolve })))
  mount(); await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => { finish(json(member)) })
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '서버에서 현재 상태 확인' })).toBeEnabled()
})

it('clears a previously checked member when restoring a cached page', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(member)))
  mount(); await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText('로그인 상태를 확인했어요')).toBeVisible()
  act(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })))
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '서버에서 현재 상태 확인' })).toBeEnabled()
})

it('clears verified session display when navigating to a different callback URL', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(member)))
  render(<MemoryRouter initialEntries={['/auth/result?purpose=login&status=success']}><Routes><Route path="/auth/result" element={<><AuthResult /><Link to="/auth/result?purpose=reauth&status=expired">다른 요청</Link></>} /></Routes></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText('로그인 상태를 확인했어요')).toBeVisible()
  await userEvent.click(screen.getByRole('link', { name: '다른 요청' }))
  expect(screen.getByText('요청 시간이 지났어요')).toBeVisible()
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
})

it('clears a verified result when its pending request expires and requires a fresh server check', async () => {
  const timer = vi.spyOn(window, 'setTimeout')
  const fetch = vi.fn().mockResolvedValue(json({ ...member, pending_save_intent: { save_intent_id: id, expires_at: new Date(Date.now() + 30000).toISOString(), targets: { profile: true, draft: true }, existing_saved_profile_version: null } }))
  vi.stubGlobal('fetch', fetch); mount('?purpose=save&status=success')
  await userEvent.click(screen.getByRole('button', { name: '서버에서 현재 상태 확인' }))
  expect(await screen.findByText('저장 대기 자료가 있어요')).toBeVisible()
  const expiry = timer.mock.calls.find(([, delay]) => typeof delay === 'number' && delay > 20000 && delay <= 30000)
  expect(expiry).toBeDefined()
  act(() => { if (typeof expiry?.[0] === 'function') expiry[0]() })
  expect(screen.queryByText('저장 대기 자료가 있어요')).not.toBeInTheDocument()
  expect(screen.queryByText('로그인 상태를 확인했어요')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '서버에서 현재 상태 확인' })).toBeEnabled()
  expect(fetch).toHaveBeenCalledTimes(1)
})
