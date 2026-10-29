import { act, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
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
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })

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
