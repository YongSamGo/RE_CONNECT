import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { AccountPage } from './AccountPage'
import { SavedMaterials } from './SavedMaterials'
import { AdminPage } from '../admin/AdminPage'
import { parseSession } from './session'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const member = { ...anonymousSession, authenticated: true, user: { id: '12345678-1234-1234-1234-123456789012', roles: ['user'], mfa_verified: false, reauth_until: null } }
function mount(component: React.ReactNode) { return render(<MemoryRouter>{component}</MemoryRouter>) }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

describe('member and operator request boundaries', () => {
  it.each([false, true])('shows the management entry only for a server-confirmed operator: %s', async operator => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ ...member, user: { ...member.user, roles: operator ? ['user', 'operator'] : ['user'] } })))
    mount(<AccountPage />)
    expect(screen.queryByRole('link', { name: '운영자 관리 화면' })).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
    await screen.findByText('회원 세션이 확인되었습니다. 대화는 새로 시작하며 저장하지 않은 입력은 회원 자료에 포함되지 않습니다.')
    if (operator) expect(screen.getByRole('link', { name: '운영자 관리 화면' })).toHaveAttribute('href', '/admin')
    else expect(screen.queryByRole('link', { name: '운영자 관리 화면' })).not.toBeInTheDocument()
  })
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
  it('does not request saved materials for an anonymous session', async () => {
    const fetch = vi.fn(async () => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
    mount(<SavedMaterials />)
    await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('로그인 후 다시 시도해 주세요.')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('moves focus to loaded materials and then to the selected document', async () => {
    const documentId = '32345678-1234-4234-9234-123456789012'
    const opportunityId = '42345678-1234-4234-9234-123456789012'
    const fetch = vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname
      if (path.endsWith('/me') && !path.endsWith('/profiles/me')) return json(member)
      if (path.endsWith('/profiles/me')) return json({ saved: { profile_id: member.user.id, version: 1, content: { experiences: [{ description: '가상 경험' }] } } })
      if (path.endsWith('/drafts')) return json({ items: [{ document_id: documentId, opportunity_title: '가상 공고', version: 1 }], page: 1, total: 1 })
      return json({ document_id: documentId, version: 1, opportunity: { id: opportunityId }, review_reasons: [], self_introduction: '가상 소개', motivation: '가상 지원동기' })
    })
    vi.stubGlobal('fetch', fetch)
    mount(<SavedMaterials />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
    expect(await screen.findByRole('heading', { name: '저장 프로필의 경험' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '내용 보기: 가상 공고' }))
    expect(await screen.findByRole('heading', { name: '가상 공고' })).toHaveFocus()
    expect(fetch).toHaveBeenCalledTimes(5)
  })
  it('does not write consent or submit login based on preview state', async () => {
    const fetch = vi.fn(async () => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
    mount(<AccountPage />)
    await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
    expect(await screen.findByText(/로그인하지 않은 상태입니다/)).toBeVisible()
    expect(screen.queryByRole('link', { name: /카카오/ })).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('keeps account deletion disabled without server reauthentication even after confirmation', async () => {
    const fetch = vi.fn(async () => json(member)); vi.stubGlobal('fetch', fetch)
    mount(<AccountPage />)
    await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
    expect(await screen.findByRole('heading', { level: 2, name: '회원 저장 동의 철회' })).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: 'AI 처리 동의 철회' })).toBeVisible()
    expect(screen.getByRole('heading', { level: 2, name: '회원 탈퇴' })).toBeVisible()
    await userEvent.click(await screen.findByLabelText('회원 탈퇴와 모든 저장 자료 삭제를 확인했어요.'))
    expect(screen.getByRole('button', { name: '재인증한 계정 탈퇴' })).toBeDisabled()
    expect(screen.getByRole('link', { name: '카카오에서 내 계정 재인증' })).toHaveAttribute('href', '/api/v1/auth/kakao/start?purpose=reauth')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('deletes only after confirmation and reauth, and verifies anonymous state before completion', async () => {
    const onLogout = vi.fn()
    const fetch = vi.fn().mockResolvedValueOnce(json({ ...member, user: { ...member.user, reauth_until: new Date(Date.now() + 300000).toISOString() } }))
      .mockResolvedValueOnce(new Response(null, { status: 204 })).mockResolvedValueOnce(json(anonymousSession))
    vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    mount(<AccountPage onLogout={onLogout} />)
    await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
    expect(await screen.findByRole('button', { name: '재인증한 계정 탈퇴' })).toBeDisabled()
    await userEvent.click(screen.getByLabelText('회원 탈퇴와 모든 저장 자료 삭제를 확인했어요.'))
    await userEvent.click(screen.getByRole('button', { name: '재인증한 계정 탈퇴' }))
    expect(await screen.findByText('회원 탈퇴와 저장 자료 삭제를 완료했습니다.')).toBeVisible()
    expect(onLogout).toHaveBeenCalledTimes(1)
    const request = fetch.mock.calls[1]![0] as Request
    expect(request.method).toBe('DELETE')
    expect(request.url).toBe('https://reconnect.test/api/v1/me')
    expect(request.headers.get('X-CSRF-Token')).toBe('token')
    expect(request.body).toBeNull()
  })
  it('withdraws AI purpose explicitly without requesting saved profile deletion', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockResolvedValueOnce(json({ purpose: 'ai_processing' })).mockResolvedValueOnce(json({ ...member, consents: [] }))
    vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    mount(<AccountPage />)
    await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
    await userEvent.click(await screen.findByLabelText('AI 처리 동의를 철회하고 임시 체험을 종료할게요.'))
    await userEvent.click(screen.getByRole('button', { name: 'AI 동의 철회하고 임시 체험 종료' }))
    expect(await screen.findByText('AI 처리 동의를 철회하고 임시 체험을 종료했습니다.')).toBeVisible()
    const request = fetch.mock.calls[1]![0] as Request
    expect(request.url).toBe('https://reconnect.test/api/v1/consents/withdraw')
    expect(await request.json()).toEqual({ purpose: 'ai_processing' })
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it.each([
    { ...member, user: null },
    { ...member, user: { ...member.user, roles: ['superuser'] } },
    { ...member, user: { ...member.user, mfa_verified: 'true' } },
    { ...member, pending_save_intent: { save_intent_id: 'javascript:alert(1)' } },
  ])('rejects malformed identity, permissions and opaque references', (value) => {
    expect(() => parseSession(value)).toThrow('응답을 확인하지 못했습니다.')
  })
})
