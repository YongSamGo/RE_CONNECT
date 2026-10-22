import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
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
