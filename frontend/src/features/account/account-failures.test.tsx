import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { AccountPage } from './AccountPage'
import { SavedMaterials } from './SavedMaterials'

const id = '12345678-1234-4234-9234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const member = { ...anonymousSession, authenticated: true, user: { id, roles: ['user'], mfa_verified: false, reauth_until: new Date(Date.now() + 300000).toISOString() } }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it.each(['SERVICE_UNAVAILABLE', 'REAUTH_REQUIRED'] as const)('does not show account deletion completion after %s', async (code) => {
  const onLogout = vi.fn()
  const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockResolvedValueOnce(json({ code, message: 'private backend detail' }, code === 'REAUTH_REQUIRED' ? 403 : 503))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><AccountPage onLogout={onLogout} /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
  await userEvent.click(await screen.findByLabelText('회원 탈퇴와 모든 저장 자료 삭제를 확인했어요.'))
  await userEvent.click(screen.getByRole('button', { name: '재인증한 계정 탈퇴' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText('회원 탈퇴와 저장 자료 삭제를 완료했습니다.')).not.toBeInTheDocument()
  expect(onLogout).not.toHaveBeenCalled()
  expect(fetch).toHaveBeenCalledTimes(2)
  expect(document.body).not.toHaveTextContent('private backend detail')
})

it('does not report storage withdrawal success or reset memory when the server fails', async () => {
  const reset = vi.fn()
  const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockResolvedValueOnce(json({ code: 'SERVICE_UNAVAILABLE' }, 503))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><AccountPage onSessionReset={reset} /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '내 로그인 상태 확인' }))
  await userEvent.click(await screen.findByLabelText('저장 동의를 철회하고 저장 자료를 삭제할게요.'))
  await userEvent.click(screen.getByRole('button', { name: '동의 철회하고 저장 자료 삭제' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText('회원 저장 동의를 철회했습니다. 저장 프로필과 지원서 삭제를 완료했습니다.')).not.toBeInTheDocument()
  expect(reset).not.toHaveBeenCalled()
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('does not show saved profile deletion as complete after a failed response', async () => {
  const reset = vi.fn()
  const fetch = vi.fn().mockResolvedValueOnce(json(member))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 1, content: { experiences: [{ description: '가상 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(member))
    .mockResolvedValueOnce(json({ code: 'SERVICE_UNAVAILABLE', message: 'private data path' }, 503))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials onSessionReset={reset} /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await userEvent.click(await screen.findByLabelText('저장 프로필과 연결된 지원서를 모두 삭제할게요.'))
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필과 지원서 삭제' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText('저장 프로필과 연결된 지원서를 삭제했습니다.')).not.toBeInTheDocument()
  expect(reset).not.toHaveBeenCalled()
  expect(document.body).not.toHaveTextContent('private data path')
})

it('retries an ambiguous saved-profile import with the identical idempotency key and request body', async () => {
  const consented = { ...member, consents: [{ purpose: 'ai_processing', granted_at: new Date().toISOString(), notice_version: 'ai-v1' }] }
  const fetch = vi.fn()
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 4, content: { experiences: [{ description: '가상 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json(consented))
    .mockRejectedValueOnce(new TypeError('connection lost after request'))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ journey_id: '22345678-1234-4234-9234-123456789012', confirmed: { version: 1 } }))
    .mockResolvedValueOnce(json(consented))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('가상 저장 경험')
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(9))
  const first = fetch.mock.calls[5]![0] as Request
  const retry = fetch.mock.calls[7]![0] as Request
  expect(first.headers.get('Idempotency-Key')).toBe(retry.headers.get('Idempotency-Key'))
  expect(await first.clone().json()).toEqual(await retry.clone().json())
  expect(await retry.json()).toEqual({ ai_notice_version: 'ai-v1', saved_profile: { profile_id: id, version: 4 } })
})

it('clears saved profile data and refuses import when the confirmed owner changes', async () => {
  const consented = { ...member, consents: [{ purpose: 'ai_processing', granted_at: new Date().toISOString(), notice_version: 'ai-v1' }] }
  const other = { ...consented, user: { ...consented.user!, id: '92345678-1234-4234-9234-123456789012' } }
  const fetch = vi.fn()
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 4, content: { experiences: [{ description: '가상 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json(other))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('가상 저장 경험')
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(await screen.findByRole('button', { name: '저장 자료 불러오기' })).toBeVisible()
  expect(screen.queryByText('가상 저장 경험')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(5)
  expect(fetch.mock.calls.some(([request]) => (request as Request).method === 'POST')).toBe(false)
})

it.each(['profile', 'draft'] as const)('refuses %s deletion and clears account A data after switching to account B', async (target) => {
  const other = { ...member, user: { ...member.user!, id: '92345678-1234-4234-9234-123456789012' } }
  const fetch = vi.fn()
    .mockResolvedValueOnce(json(member))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 4, content: { experiences: [{ description: '계정 A의 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [{ document_id: '22345678-1234-4234-9234-123456789012', opportunity_title: '계정 A 공고', version: 1 }], page: 1, total: 1 }))
    .mockResolvedValueOnce(json(member))
  if (target === 'draft') fetch.mockResolvedValueOnce(json({
    document_id: '22345678-1234-4234-9234-123456789012', version: 1, review_reasons: [],
    self_introduction: '계정 A의 지원서', motivation: '가상 동기',
    opportunity: { id: '32345678-1234-4234-9234-123456789012' },
  }))
  fetch.mockResolvedValueOnce(json(other))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('계정 A의 경험')
  if (target === 'profile') {
    await userEvent.click(await screen.findByLabelText('저장 프로필과 연결된 지원서를 모두 삭제할게요.'))
    await userEvent.click(screen.getByRole('button', { name: '저장 프로필과 지원서 삭제' }))
  } else {
    await userEvent.click(screen.getByRole('button', { name: '내용 보기 · 계정 A 공고' }))
    await screen.findByText('계정 A의 지원서')
    await userEvent.click(screen.getByLabelText('이 지원서의 모든 저장 버전을 삭제할게요.'))
    await userEvent.click(screen.getByRole('button', { name: '선택한 지원서 삭제' }))
  }
  await screen.findByRole('button', { name: '저장 자료 불러오기' })
  expect(screen.queryByText('계정 A의 경험')).not.toBeInTheDocument()
  expect(screen.queryByText('계정 A의 지원서')).not.toBeInTheDocument()
  expect(fetch.mock.calls.some(([request]) => (request as Request).method === 'DELETE')).toBe(false)
})

it('does not navigate to an imported journey if its response arrives after the CSRF session changed', async () => {
  const consented = { ...member, consents: [{ purpose: 'ai_processing', granted_at: new Date().toISOString(), notice_version: 'ai-v1' }] }
  const fetch = vi.fn()
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 4, content: { experiences: [{ description: '가상 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json(consented))
    .mockImplementationOnce(async (request: Request) => {
      if (request.method === 'POST') document.cookie = '__Host-rc_csrf=rotated; Secure; Path=/'
      return json({ journey_id: '22345678-1234-4234-9234-123456789012', confirmed: { version: 1 } })
    })
    .mockResolvedValueOnce(json(consented))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  function Location() { return <output>{useLocation().pathname}</output> }
  render(<MemoryRouter initialEntries={['/me/saved']}><SavedMaterials /><Location /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('가상 저장 경험')
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByText(/이전 요청이 이미 처리됐을 수 있습니다/)).toBeVisible()
  expect(screen.getByText('/me/saved')).toBeVisible()
  expect(screen.queryByText('가상 저장 경험')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(7)
})

it('blocks a new import key after an ambiguous attempt and a CSRF change', async () => {
  const consented = { ...member, consents: [{ purpose: 'ai_processing', granted_at: new Date().toISOString(), notice_version: 'ai-v1' }] }
  const fetch = vi.fn()
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 4, content: { experiences: [{ description: '가상 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json(consented))
    .mockRejectedValueOnce(new TypeError('connection lost after request'))
    .mockResolvedValueOnce(json(consented))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('가상 저장 경험')
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  document.cookie = '__Host-rc_csrf=reauthenticated; Secure; Path=/'
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByText(/이전 요청이 이미 처리됐을 수 있습니다/)).toBeVisible()
  expect(screen.queryByText('가상 저장 경험')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(7)
  expect(fetch.mock.calls.filter(([request]) => (request as Request).method === 'POST')).toHaveLength(1)
})

it('requires reloading changed saved-profile context before starting a new import', async () => {
  const consented = { ...member, consents: [{ purpose: 'ai_processing', granted_at: new Date().toISOString(), notice_version: 'ai-v1' }] }
  const fetch = vi.fn()
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 4, content: { experiences: [{ description: '가상 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json(consented))
    .mockRejectedValueOnce(new TypeError('connection lost after request'))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json({ saved: { profile_id: id, version: 5, content: { experiences: [{ description: '새 저장 경험' }] } } }))
    .mockResolvedValueOnce(json({ items: [], page: 1, total: 0 }))
    .mockResolvedValueOnce(json(consented))
    .mockResolvedValueOnce(json(consented))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('가상 저장 경험')
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '저장 자료 불러오기' }))
  await screen.findByText('새 저장 경험')
  await userEvent.click(screen.getByRole('button', { name: '저장 프로필로 새 체험·편집 시작' }))
  expect(await screen.findByText(/이전 요청이 이미 처리됐을 수 있습니다/)).toBeVisible()
  expect(screen.queryByText('새 저장 경험')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(11)
  expect(fetch.mock.calls.filter(([request]) => (request as Request).method === 'POST')).toHaveLength(1)
})
