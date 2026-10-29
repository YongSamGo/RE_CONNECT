import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { AccountPage } from './AccountPage'
import { AdminPage } from '../admin/AdminPage'
import { parseSession } from './session'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const member = { ...anonymousSession, authenticated: true, user: { id: '12345678-1234-1234-1234-123456789012', roles: ['user'], mfa_verified: false, reauth_until: null } }
function mount(component: React.ReactNode) { return render(<MemoryRouter>{component}</MemoryRouter>) }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

  it.each([anonymousSession, member])('never requests operator data without operator role', async (session) => {
    const fetch = vi.fn(async () => json(session)); vi.stubGlobal('fetch', fetch)
    mount(<AdminPage />)
    expect(fetch).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '운영자 접근 확인' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('운영자 권한이 필요합니다')
    expect(fetch).toHaveBeenCalledTimes(1)
    expect((fetch.mock.calls[0] as unknown as [Request])[0].url).toBe('https://reconnect.test/api/v1/me')
    expect(screen.queryByRole('button', { name: '공고 목록 조회' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '새 공고 등록' })).not.toBeInTheDocument()
  })
  it('requires server MFA verification and clears OTP before a failed attempt', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...member, user: { ...member.user, roles: ['operator'] } })).mockResolvedValueOnce(json({ code: 'MFA_INVALID', message: 'private otp and path' }, 403))
    vi.stubGlobal('fetch', fetch)
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    mount(<AdminPage />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '운영자 접근 확인' }))
    await user.type(await screen.findByLabelText('인증 앱의 6자리 코드'), '123456')
    await user.click(screen.getByRole('button', { name: '추가 인증 확인' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('인증 코드를 확인해 주세요.')
    expect(screen.queryByLabelText('인증 앱의 6자리 코드')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '공고 목록 조회' })).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('private otp and path')
    const request = fetch.mock.calls[1]![0] as Request
    expect(request.headers.get('X-CSRF-Token')).toBe('token')
    expect(await request.json()).toEqual({ otp: '123456' })
  })
  it('unlocks the workspace only after a validated server role and MFA response', async () => {
    const fetch = vi.fn(async () => json({ ...member, user: { ...member.user, roles: ['operator'], mfa_verified: true } }))
    vi.stubGlobal('fetch', fetch)
    mount(<AdminPage />)
    await userEvent.click(screen.getByRole('button', { name: '운영자 접근 확인' }))
    expect(await screen.findByRole('button', { name: '공고 목록 조회' })).toBeVisible()
    expect(screen.getByRole('heading', { name: '운영 자료 조회' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: '새 공고 등록' }))
    expect(screen.getByRole('heading', { name: '공고 직접 등록하기' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: '작성 화면 닫고 운영 목록으로' }))
    expect(screen.getByRole('heading', { name: '운영 자료 조회' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: '감사 기록 조회' }))
    expect(screen.getByRole('heading', { name: '최소 감사 기록 조회' })).toHaveFocus()
    await userEvent.click(screen.getByRole('button', { name: '운영 목록으로 돌아가기' }))
    expect(screen.getByRole('heading', { name: '운영 자료 조회' })).toHaveFocus()
    expect(fetch).toHaveBeenCalledTimes(1)
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(screen.queryByRole('button', { name: '공고 목록 조회' })).not.toBeInTheDocument()
  })
  it.each([
    { ...member, user: null },
    { ...member, user: { ...member.user, roles: ['superuser'] } },
    { ...member, user: { ...member.user, mfa_verified: 'true' } },
    { ...member, pending_save_intent: { save_intent_id: 'javascript:alert(1)' } },
  ])('rejects malformed identity, permissions and opaque references', (value) => {
    expect(() => parseSession(value)).toThrow('응답을 확인하지 못했습니다.')
  })

it('loads the current account and requires confirmation and live reauthentication before deleting', async () => {
  const fetch = vi.fn(async (_request: Request) => json(member)); vi.stubGlobal('fetch', fetch)
  mount(<AccountPage autoLoad />)
  await userEvent.click(await screen.findByRole('button', { name: '회원 탈퇴' }))
  await userEvent.click(screen.getByLabelText('회원 탈퇴와 저장 자료 삭제를 확인했어요.'))
  expect(screen.getByRole('button', { name: '탈퇴하기' })).toBeDisabled()
  expect(screen.getByRole('link', { name: '카카오에서 다시 인증' })).toHaveAttribute('href', '/api/v1/auth/kakao/start?purpose=reauth')
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
})

it('deletes only after explicit confirmation and verifies the resulting anonymous session', async () => {
  const onLogout = vi.fn()
  const fetch = vi.fn().mockResolvedValueOnce(json({ ...member, user: { ...member.user, reauth_until: new Date(Date.now() + 300000).toISOString() } }))
    .mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(json(anonymousSession))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  mount(<AccountPage autoLoad onLogout={onLogout} />)
  await userEvent.click(await screen.findByRole('button', { name: '회원 탈퇴' }))
  expect(screen.getByRole('button', { name: '탈퇴하기' })).toBeDisabled()
  await userEvent.click(screen.getByLabelText('회원 탈퇴와 저장 자료 삭제를 확인했어요.'))
  await userEvent.click(screen.getByRole('button', { name: '탈퇴하기' }))
  expect(await screen.findByText('회원 탈퇴를 완료했습니다.')).toBeVisible()
  expect(onLogout).toHaveBeenCalledOnce()
  const request = fetch.mock.calls[1]![0] as Request
  expect(request.method).toBe('DELETE'); expect(request.headers.get('X-CSRF-Token')).toBe('token')
  expect(request.body).toBeNull()
})

it('offers login to anonymous users without requesting private profile data', async () => {
  const fetch = vi.fn(async (_request: Request) => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
  mount(<AccountPage autoLoad />)
  expect(await screen.findByRole('link', { name: '로그인하기' })).toHaveAttribute('href', '/login')
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.queryByRole('button', { name: '회원 탈퇴' })).not.toBeInTheDocument()
})
