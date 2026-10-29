import { act, render, screen } from '@testing-library/react'
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

it.each(['SERVICE_UNAVAILABLE', 'REAUTH_REQUIRED'] as const)('does not claim account deletion after %s', async code => {
  const onLogout = vi.fn()
  const fetch = vi.fn().mockResolvedValueOnce(json({ ...member, user: { ...member.user, reauth_until: new Date(Date.now() + 300000).toISOString() } }))
    .mockResolvedValueOnce(json({ code, message: 'private backend detail' }, 503))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><AccountPage autoLoad onLogout={onLogout} /></MemoryRouter>)
  await userEvent.click(await screen.findByRole('button', { name: '회원 탈퇴' }))
  await userEvent.click(screen.getByLabelText('회원 탈퇴와 저장 자료 삭제를 확인했어요.'))
  await userEvent.click(screen.getByRole('button', { name: '탈퇴하기' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(onLogout).not.toHaveBeenCalled(); expect(document.body).not.toHaveTextContent('private backend detail')
})

function importServer(options: { lost?: boolean; changedOwner?: boolean; delayed?: boolean } = {}) {
  let imports = 0, checked = 0
  let finish!: (response: Response) => void
  const consented = { ...member, consents: [{ purpose: 'ai_processing', notice_version: 'ai-v1', granted_at: new Date().toISOString() }] }
  const fetch = vi.fn(async (request: Request): Promise<Response> => {
    if (request.url.endsWith('/profiles/me')) return json({ saved: { profile_id: id, version: 4 } })
    if (request.method === 'POST') {
      imports++
      if (options.lost && imports === 1) throw new TypeError('private failure')
      if (options.delayed) return new Promise(resolve => { finish = resolve })
      return json({ journey_id: id, confirmed: { version: 1 } }, 201)
    }
    checked++
    return json(options.changedOwner && checked >= 3 ? { ...consented, user: { ...consented.user, id: '22345678-1234-4234-9234-123456789012' } } : consented)
  })
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  return { fetch, finish: (response: Response) => finish(response) }
}

it('retries an uncertain saved-profile edit with the same body and key', async () => {
  const { fetch } = importServer({ lost: true })
  await userEvent.click(await screen.findByRole('button', { name: '수정하기' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  await userEvent.click(screen.getByRole('button', { name: '수정하기' }))
  const writes = fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST')
  expect(writes).toHaveLength(2)
  expect(writes[0].headers.get('Idempotency-Key')).toBe(writes[1].headers.get('Idempotency-Key'))
  expect(await writes[0].clone().json()).toEqual(await writes[1].clone().json())
  expect(await writes[0].clone().json()).toEqual({ ai_notice_version: 'ai-v1', saved_profile: { profile_id: id, version: 4 } })
})
it('does not import the previous owner profile after the account changes', async () => {
  const { fetch } = importServer({ changedOwner: true })
  await userEvent.click(await screen.findByRole('button', { name: '수정하기' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(fetch.mock.calls.some(([request]) => request.method === 'POST')).toBe(false)
})
it('discards an import reply after the CSRF session changes', async () => {
  const { finish } = importServer({ delayed: true })
  await userEvent.click(await screen.findByRole('button', { name: '수정하기' }))
  document.cookie = '__Host-rc_csrf=other; Secure; Path=/'
  await act(async () => finish(json({ journey_id: id, confirmed: { version: 1 } }, 201)))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(document.body).not.toHaveTextContent('private failure')
})
it('refuses a new import after an uncertain write and a CSRF change', async () => {
  const { fetch } = importServer({ lost: true })
  await userEvent.click(await screen.findByRole('button', { name: '수정하기' }))
  await screen.findByRole('alert')
  document.cookie = '__Host-rc_csrf=other; Secure; Path=/'
  await userEvent.click(screen.getByRole('button', { name: '수정하기' }))
  expect(fetch.mock.calls.filter(([request]) => request.method === 'POST')).toHaveLength(1)
})
it('never fetches a document library for anonymous users', async () => {
  const fetch = vi.fn(async (_request: Request) => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter><SavedMaterials /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
})
