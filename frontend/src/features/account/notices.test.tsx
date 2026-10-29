import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { LoginEntry, StorageConsent } from './notices'
import { parseNotices } from './notices-model'

const owner = '22345678-1234-4234-9234-123456789012'
const stamp = '2026-10-20T00:00:00Z'
const notice = { version: 'fixture-storage', title: '가상 회원 저장 안내', controller: '가상 시험 주체', contact: '시험 문의처', aws_region: '시험 리전', body: '<img src=x onerror=alert(1)>\n가상 자료로만 시험', retention: '시험 보관', deletion: '시험 삭제' }
const catalog = { ai_processing: null, storage: notice, login_available: true }
const member = { authenticated: true, user: { id: owner, roles: ['user'], mfa_verified: false, reauth_until: null }, consents: [], pending_save_intent: null }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('keeps login unavailable when no notice has been published even after reading', async () => {
  const fetch = vi.fn().mockResolvedValue(json({ ai_processing: null, storage: null, login_available: false })); vi.stubGlobal('fetch', fetch)
  render(<LoginEntry />)
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '현재 로그인 안내 확인' }))
  expect(await screen.findByText('새 로그인 준비 중이에요')).toBeVisible()
  expect(screen.queryByRole('link', { name: '카카오에서 로그인' })).not.toBeInTheDocument()
})

it('renders published data as text and enables only the fixed login URL after explicit confirmation', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(catalog)))
  render(<LoginEntry />); await userEvent.click(screen.getByRole('button', { name: '현재 로그인 안내 확인' }))
  expect(await screen.findByText('가상 시험 주체')).toBeVisible()
  expect(document.querySelector('img')).toBeNull()
  expect(screen.queryByRole('link', { name: '카카오에서 로그인' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByLabelText('안내를 읽고 카카오 로그인을 진행할게요.'))
  expect(screen.getByRole('link', { name: '카카오에서 로그인' })).toHaveAttribute('href', '/api/v1/auth/kakao/start?purpose=login')
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByRole('link', { name: '카카오에서 로그인' })).not.toBeInTheDocument()
})

it('requires the published notice and explicit confirmation from the compact login screen', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(json(catalog)))
  render(<LoginEntry compact />)
  await userEvent.click(screen.getByRole('button', { name: '카카오로 로그인' }))
  expect(await screen.findByText('가상 시험 주체')).toBeVisible()
  expect(screen.queryByRole('link', { name: '카카오에서 로그인' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByLabelText('안내를 읽고 카카오 로그인을 진행할게요.'))
  expect(screen.getByRole('link', { name: '카카오에서 로그인' })).toHaveAttribute('href', '/api/v1/auth/kakao/start?purpose=login')
})

it.each([{ ...catalog, storage: null }, { ...catalog, login_available: 'yes' }, { ...catalog, storage: { ...notice, contact: '' } }, { ...catalog, storage: { ...notice, version: 'invalid version' } }])('rejects inconsistent or incomplete notice data', value => {
  expect(() => parseNotices(value)).toThrow()
})

it('submits only the read notice version after an explicit consent choice and verifies it in me', async () => {
  const accepted = vi.fn(), calls: Request[] = []
  let granted = false
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    calls.push(request.clone())
    if (new URL(request.url).pathname === '/api/v1/consents/notices') return json(catalog)
    if (request.method === 'POST') { granted = true; return json({ purpose: 'storage', notice_version: notice.version, granted_at: stamp }, 201) }
    return json({ ...member, consents: granted ? [{ purpose: 'storage', notice_version: notice.version, granted_at: stamp }] : [] })
  }))
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<StorageConsent owner={owner} onGranted={accepted} />)
  await userEvent.click(screen.getByRole('button', { name: '현재 회원 저장 안내 확인' }))
  const submit = await screen.findByRole('button', { name: '읽은 안내문으로 회원 저장 동의' })
  expect(submit).toBeDisabled(); expect(accepted).not.toHaveBeenCalled()
  await userEvent.click(screen.getByLabelText('위 안내문을 읽고 회원 저장에 동의합니다.'))
  await userEvent.click(submit)
  expect(accepted).toHaveBeenCalledExactlyOnceWith('fixture-storage')
  const post = calls.find(request => request.method === 'POST')!
  expect(await post.json()).toEqual({ purpose: 'storage', notice_version: 'fixture-storage' })
  expect(post.headers.get('X-CSRF-Token')).toBe('token')
  expect(calls.filter(request => request.method === 'POST')).toHaveLength(1)
})

it.each(['stale', 'wrong-member', 'unconfirmed'])('does not apply a consent result after %s', async problem => {
  const accepted = vi.fn()
  const fetch = vi.fn().mockResolvedValueOnce(json(catalog))
    .mockResolvedValueOnce(json(problem === 'wrong-member' ? { ...member, user: { ...member.user, id: '32345678-1234-4234-9234-123456789012' } } : member))
  if (problem === 'stale') fetch.mockResolvedValueOnce(json({ code: 'VALIDATION_FAILED', message: 'private raw notice' }, 422))
  if (problem === 'unconfirmed') fetch.mockResolvedValueOnce(json({ purpose: 'storage', notice_version: notice.version, granted_at: stamp }, 201)).mockResolvedValueOnce(json(member))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<StorageConsent owner={owner} onGranted={accepted} />)
  await userEvent.click(screen.getByRole('button', { name: '현재 회원 저장 안내 확인' }))
  await userEvent.click(await screen.findByLabelText('위 안내문을 읽고 회원 저장에 동의합니다.'))
  await userEvent.click(screen.getByRole('button', { name: '읽은 안내문으로 회원 저장 동의' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(accepted).not.toHaveBeenCalled()
  expect(document.body).not.toHaveTextContent('private raw notice')
})
