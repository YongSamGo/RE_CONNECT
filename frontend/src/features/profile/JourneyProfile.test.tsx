import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { JourneyProfile } from './JourneyProfile'
import { parseProfileView, parseRoles } from './server-model'
import type { ProfileView } from './server-model'

const id = '12345678-1234-1234-1234-123456789012'
const experienceId = '22345678-1234-1234-1234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function view(confirmed = false): ProfileView {
  return { revision: confirmed ? 3 : 1, confirmed: confirmed ? { version: 1, confirmed_at: '2026-10-18T00:00:00Z' } : null,
    has_unconfirmed_changes: false, missing_for_recommendation: [], evidence: [], draft: {
      schema_version: 1, experiences: [{ id: experienceId, description: '가상 도서관 경험', duration_note: null, skill_tags: ['자료 정리'] }],
      skills: [], preferred_regions: [{ province: 'seoul', district: null }], activity_types: ['volunteering'],
      paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null,
      residence_region: null, birth_year: null, certifications: null, completed_courses: [], activity_constraints: null,
    } }
}
const roles = (revision = 3, version = 1, excluded = false) => ({ revision, profile_version: version, items: [{ role_id: 'library_assistant', name: '자료 정리 도우미', description: '가상 역할 설명', excluded,
  evidence: [{ experience_id: experienceId, skill_tags: ['자료 정리'] }] }] })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><JourneyProfile journeyId={id} /></MemoryRouter>)
  return userEvent.setup()
}

it('keeps draft edits separate from explicit confirmation, preserves null and empty facts, then shows real roles', async () => {
  let current = view()
  const fetch = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname
    if (path.endsWith('/me')) return json({})
    if (path.endsWith('/profile/confirm')) { current = { ...current, revision: 3, confirmed: { version: 1, confirmed_at: '2026-10-18T00:00:00Z' } }; return json({}) }
    if (path.endsWith('/roles')) return json(roles())
    if (path.endsWith('/role-exclusions')) return json({ role_ids: [], revision: current.revision })
    if (request.method === 'PATCH') { const body = await request.clone().json(); current = { ...current, revision: 2, draft: body.draft }; return json(current) }
    return json(current)
  })
  vi.stubGlobal('fetch', fetch)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '체험 프로필 불러오기' }))
  expect(await screen.findByLabelText('경험 1 내용')).toHaveValue('가상 도서관 경험')
  expect(screen.queryByRole('heading', { name: '확정 경험에서 찾은 역할' })).not.toBeInTheDocument()
  await user.type(screen.getByLabelText('경험 1 내용'), ' 수정')
  expect(screen.getByRole('button', { name: '이 프로필 확정' })).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '변경 내용을 초안에 반영' }))
  expect(await screen.findByText(/초안에 변경 내용을 반영했습니다/)).toBeVisible()
  const patch = fetch.mock.calls.find(([req]) => req.method === 'PATCH')![0]
  const body = await patch.clone().json()
  expect(body.base_revision).toBe(1)
  expect(body.draft.certifications).toBeNull()
  expect(body.draft.completed_courses).toEqual([])
  expect(body.draft.experiences[0].id).toBe(experienceId)
  expect(fetch.mock.calls.some(([req]) => req.url.endsWith('/confirm'))).toBe(false)
  await user.click(screen.getByRole('button', { name: '이 프로필 확정' }))
  expect(await screen.findByRole('heading', { name: '확정 경험에서 찾은 역할' })).toBeVisible()
  expect(screen.getByText('확정 경험 근거: 자료 정리')).toBeVisible()
  expect(screen.queryByRole('button', { name: /회원 저장/ })).not.toBeInTheDocument()
})

it('preserves excluded roles outside the visible candidates when replacing the selection', async () => {
  let revision = 3, excluded = false
  let allIds = ['hidden_role']
  const fetch = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/me')) return json({})
    if (request.url.endsWith('/roles')) return json(roles(revision, 1, excluded))
    if (request.url.endsWith('/role-exclusions')) {
      if (request.method === 'PUT') { allIds = (await request.clone().json()).role_ids; excluded = allIds.includes('library_assistant'); revision += 1 }
      return json({ revision, role_ids: allIds })
    }
    return json({ ...view(true), revision })
  })
  vi.stubGlobal('fetch', fetch)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '체험 프로필 불러오기' }))
  await user.click(await screen.findByRole('checkbox', { name: '자료 정리 도우미 추천에서 제외' }))
  expect(await screen.findByText(/역할 제외 선택을 반영했습니다/)).toBeVisible()
  const put = fetch.mock.calls.find(([req]) => req.method === 'PUT')![0]
  expect(await put.clone().json()).toEqual({ base_revision: 3, role_ids: ['hidden_role', 'library_assistant'] })
  expect(screen.getByRole('checkbox', { name: '자료 정리 도우미 추천에서 제외' })).toBeChecked()
  await user.click(screen.getByRole('button', { name: '역할 제외 모두 복원' }))
  expect(await screen.findByText('현재 제외한 역할: 0개. 표시된 후보에 없는 역할도 포함합니다.')).toBeVisible()
  const puts = fetch.mock.calls.filter(([req]) => req.method === 'PUT')
  expect(await puts[1][0].clone().json()).toEqual({ base_revision: 4, role_ids: [] })
})

it('focuses minimum errors before confirmation and makes no confirm request', async () => {
  const current = view(); current.draft.experiences = []; current.draft.preferred_regions = []; current.draft.activity_types = []
  const fetch = vi.fn(async (request: Request) => json(request.url.endsWith('/me') ? {} : current))
  vi.stubGlobal('fetch', fetch)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '체험 프로필 불러오기' }))
  await user.click(await screen.findByRole('button', { name: '이 프로필 확정' }))
  expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
  await user.click(screen.getByRole('link', { name: '희망 활동 지역을 한 곳 이상 골라 주세요.' }))
  expect(document.getElementById('server-regions')).toHaveFocus()
  expect(fetch.mock.calls.some(([req]) => req.method === 'POST')).toBe(false)
})

it('keeps input on conflict, blocks duplicate save, and does not apply a late result after pagehide', async () => {
  let finish!: (value: Response) => void
  const fetch = vi.fn(async (request: Request) => request.method === 'PATCH' ? new Promise<Response>(resolve => { finish = resolve }) : json(request.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '체험 프로필 불러오기' }))
  await user.type(await screen.findByLabelText('경험 1 내용'), ' 수정')
  await user.dblClick(screen.getByRole('button', { name: '변경 내용을 초안에 반영' }))
  expect(fetch.mock.calls.filter(([req]) => req.method === 'PATCH')).toHaveLength(1)
  await act(async () => finish(json({ code: 'VERSION_CONFLICT', request_id: 'req_test' }, 409)))
  expect(await screen.findByText(/정보가 변경되었습니다/)).toBeVisible()
  expect(screen.getByLabelText('경험 1 내용')).toHaveValue('가상 도서관 경험 수정')
  await user.click(screen.getByRole('button', { name: '변경 내용을 초안에 반영' }))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => finish(json(view())))
  expect(screen.queryByLabelText('경험 1 내용')).not.toBeInTheDocument()
})

it('validates evidence/version boundaries and does not render malformed role candidates', () => {
  expect(() => parseRoles({ ...roles(), profile_version: 999 }, view(true))).toThrow()
  expect(() => parseProfileView({ ...view(), draft: { ...view().draft, experiences: [{ ...view().draft.experiences[0], id: 'forged' }] } })).toThrow()
})

it('keeps the loaded editor and role controls labelled for keyboard and assistive technology', async () => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.url.endsWith('/me') ? json({})
    : request.url.endsWith('/roles') ? json(roles()) : request.url.endsWith('/role-exclusions') ? json({ revision: 3, role_ids: [] }) : json(view(true))))
  const user = mount()
  await user.click(screen.getByRole('button', { name: '체험 프로필 불러오기' }))
  await screen.findByRole('heading', { name: '확정 경험에서 찾은 역할' })
  const result = await axe.run(document.body, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] }, rules: { 'color-contrast': { enabled: false } } })
  expect(result.violations.map(v => ({ id: v.id, targets: v.nodes.map(n => n.target) }))).toEqual([])
})
