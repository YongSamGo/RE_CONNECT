import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { MemberHome } from './MemberHome'
import { parseSavedProfile } from './saved-profile-model'

const id = '12345678-1234-4234-8234-123456789012'
const member = { ...anonymousSession, authenticated: true, user: { id, roles: ['user'], mfa_verified: false, reauth_until: null } }
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
const profile = { profile_id: id, version: 1, saved_at: '2026-10-28T00:00:00Z', confirmed_at: '2026-10-28T00:00:00Z', content: {
  schema_version: 1, experiences: [{ id, description: '<img src=x onerror=alert(1)> 도서 정리', duration_note: null, skill_tags: ['자료 정리'] }],
  skills: [], preferred_regions: [{ province: 'seoul', district: 'mapo' }], activity_types: ['volunteering'], paid_preference: 'any',
  available_weekdays: [1], hours_per_week: 8, mobility_note: null, residence_region: null, birth_year: null,
  certifications: null, completed_courses: null, activity_constraints: null,
} }
const regions = { version: 'v1', provinces: [{ id: 'seoul', name: '서울', districts: [{ id: 'mapo', name: '마포구' }] }] }
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('shows only validated saved content after rechecking the owner, renders HTML as text, and clears it on departure', async () => {
  const fetch = vi.fn(async (request: Request) => json(request.url.endsWith('/profiles/me') ? { saved: profile } : request.url.endsWith('/regions') ? regions : member))
  vi.stubGlobal('fetch', fetch)
  const { container } = render(<MemoryRouter><MemberHome /></MemoryRouter>)
  expect((await screen.findAllByText(profile.content.experiences[0].description))[0]).toBeVisible()
  expect(screen.getByText('희망 지역')).toBeVisible()
  expect(container.querySelector('img, script')).toBeNull()
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryAllByText(profile.content.experiences[0].description)).toHaveLength(0)
})

it('does not fetch private profiles for an anonymous session', async () => {
  const fetch = vi.fn(async () => json(anonymousSession)); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter><MemberHome /></MemoryRouter>)
  expect(await screen.findByText('회원 정보를 보려면 로그인해 주세요.')).toBeVisible()
  expect(fetch).toHaveBeenCalledTimes(1)
  expect(screen.queryAllByText(profile.content.experiences[0].description)).toHaveLength(0)
})

it('discards the profile if the owner changes during loading', async () => {
  let checks = 0
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    if (request.url.endsWith('/profiles/me')) return json({ saved: profile })
    if (request.url.endsWith('/regions')) return json(regions)
    return json(++checks === 1 ? member : anonymousSession)
  }))
  render(<MemoryRouter><MemberHome /></MemoryRouter>)
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryAllByText(profile.content.experiences[0].description)).toHaveLength(0)
})

it('rejects malformed saved-profile content instead of treating it as display data', () => {
  expect(() => parseSavedProfile({ saved: { ...profile, content: { ...profile.content, hours_per_week: 999 } } })).toThrow()
  expect(() => parseSavedProfile({ saved: { ...profile, profile_id: '../another-user' } })).toThrow()
})

function managedProfile() {
  let saved: typeof profile | null = profile
  let session = { ...member, consents: [
    { purpose: 'storage', notice_version: 'storage-v1', granted_at: '2026-10-18T00:00:00Z' },
    { purpose: 'ai_processing', notice_version: 'ai-v1', granted_at: '2026-10-18T00:00:00Z' },
  ] }
  const fetch = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/profiles/me')) {
      if (request.method === 'DELETE') { saved = null; return new Response(null, { status: 204 }) }
      return json({ saved })
    }
    if (request.url.endsWith('/consents/withdraw')) {
      const { purpose } = await request.json()
      session = { ...session, consents: session.consents.filter(consent => consent.purpose !== purpose) }
      if (purpose === 'storage') saved = null
      return json({ purpose, withdrawn_at: '2026-10-30T00:00:00Z', deleted: {} })
    }
    return json(session)
  })
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><MemberHome /></MemoryRouter>)
  return { fetch, changeOwner: () => { session = { ...session, user: { ...session.user, id: '22345678-1234-4234-8234-123456789012' } } } }
}

it('deletes a saved profile only after confirmation, uses CSRF, and reloads the empty member screen', async () => {
  const { fetch } = managedProfile()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '저장 프로필 삭제' }))
  expect(screen.getByRole('button', { name: '프로필과 연결된 지원서 삭제' })).toBeDisabled()
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
  await user.click(screen.getByLabelText('저장 프로필과 연결된 지원서를 삭제할게요.'))
  await user.click(screen.getByRole('button', { name: '프로필과 연결된 지원서 삭제' }))
  expect(await screen.findByText('아직 정보가 없습니다.')).toBeVisible()
  expect(screen.queryAllByText(profile.content.experiences[0].description)).toHaveLength(0)
  const writes = fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'DELETE')
  expect(writes).toHaveLength(1)
  expect(writes[0].url).toBe('https://reconnect.test/api/v1/profiles/me')
  expect(writes[0].headers.get('X-CSRF-Token')).toBe('token')
  expect(writes[0].body).toBeNull()
  expect(fetch.mock.calls.some(([request]) => request.url.endsWith('/drafts'))).toBe(false)
})

it('clears the previous profile and refuses deletion after the account changes (부적절한 인가, SEC-02)', async () => {
  const { fetch, changeOwner } = managedProfile()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '저장 프로필 삭제' }))
  await user.click(screen.getByLabelText('저장 프로필과 연결된 지원서를 삭제할게요.'))
  changeOwner()
  await user.click(screen.getByRole('button', { name: '프로필과 연결된 지원서 삭제' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryAllByText(profile.content.experiences[0].description)).toHaveLength(0)
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
})

it.each(['storage', 'ai_processing'])('reloads member data after %s withdrawal without deleting the account', async purpose => {
  const { fetch } = managedProfile()
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: '동의 관리' }))
  await user.click(screen.getByLabelText(purpose === 'storage' ? '회원 저장 동의 철회와 자료 삭제를 확인했어요.' : 'AI 처리 동의 철회와 임시 체험 종료를 확인했어요.'))
  await user.click(screen.getByRole('button', { name: purpose === 'storage' ? '회원 저장 동의 철회' : 'AI 처리 동의 철회' }))
  if (purpose === 'storage') expect(await screen.findByText('아직 정보가 없습니다.')).toBeVisible()
  else expect(await screen.findByRole('button', { name: '저장 프로필 삭제' })).toBeVisible()
  // The enclosing screen was refreshed; open the newly loaded consent summary.
  const toggle = await screen.findByRole('button', { name: '동의 관리' })
  if (toggle.getAttribute('aria-expanded') === 'false') await user.click(toggle)
  expect(await screen.findByText(purpose === 'storage' ? '현재 동의: AI 처리' : '현재 동의: 회원 저장')).toBeVisible()
  expect(screen.getByRole('button', { name: '회원 탈퇴' })).toBeVisible()
  const writes = fetch.mock.calls.map(([request]) => request).filter(request => request.method !== 'GET')
  expect(writes).toHaveLength(1)
  expect(writes[0].method).toBe('POST')
  expect(writes[0].headers.get('X-CSRF-Token')).toBe('token')
})
