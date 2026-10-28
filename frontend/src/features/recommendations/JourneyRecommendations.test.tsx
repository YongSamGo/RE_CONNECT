import { act, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { EligibilityCheck, JourneyRecommendations } from './JourneyRecommendations'
import { parseEligibility, parseRecommendations } from './model'
import type { Eligibility, ProfileRef } from './model'

const id = '12345678-1234-1234-1234-123456789012'
const opportunityId = '22345678-1234-1234-1234-123456789012'
const requirementId = '32345678-1234-1234-1234-123456789012'
const experienceId = '42345678-1234-1234-1234-123456789012'
const profile: ProfileRef = { kind: 'journey', id, version: 2 }
const opportunity = { id: opportunityId, version: 3 }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function view(confirmed = true) {
  return { revision: 8, confirmed: confirmed ? { version: 2, confirmed_at: '2026-10-18T00:00:00Z' } : null,
    has_unconfirmed_changes: true, missing_for_recommendation: [], evidence: [], draft: {
      schema_version: 1, experiences: [], skills: [], preferred_regions: [{ province: 'seoul', district: null }], activity_types: ['volunteering'],
      paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null,
      residence_region: null, birth_year: null, certifications: null, completed_courses: null, activity_constraints: null,
    } }
}
function recommendations(empty = false) {
  return { profile, generated_at: '2026-10-18T00:00:00Z', based_on_previous_confirmed: true, items: empty ? [] : [{ rank: 1,
    opportunity: { ...opportunity, title: '가상 자료 정리 봉사', organization_name: '가상 기관', activity_type: 'volunteering', is_public_job: null,
      activity_region: { province: 'seoul', district: null }, remote_allowed: false, paid: false,
      deadline_date: '2026-12-01', deadline_at: null, recruitment_status: 'open', change_pending: false },
    matched: { experience_ids: [experienceId], skill_tags: ['자료 정리'], keywords: ['도서관'], role_ids: ['library_assistant'] },
    eligibility: { overall: 'unknown', no_requirements: false, needs_review_count: 1 },
  }] }
}
function eligibility(result: Eligibility['overall'] = 'unknown', value: Eligibility['conditions'][number]['user_value'] = null): Eligibility {
  return { profile, opportunity, evaluated_at: '2026-10-18T00:00:00Z', overall: result, no_requirements: false, groups: [],
    conditions: [{ requirement_id: requirementId, field: 'certification', result, user_value: value, source_evidence: '가상 자격증 필요',
      review_reason: result === 'unknown' ? 'missing_profile_value' : null }] }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><JourneyRecommendations journeyId={id} /></MemoryRouter>)
  return userEvent.setup()
}

it('uses the latest explicit confirmed reference, displays old-confirmed status and evidence without scores', async () => {
  const fetch = vi.fn(async (req: Request) => json(req.method === 'POST' ? recommendations() : req.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await screen.findByRole('heading', { name: '가상 자료 정리 봉사' })
  expect(screen.getByRole('heading', { name: '이전 확정 프로필 기준' })).toBeVisible()
  expect(screen.getByText('확정 경험 1개와 연결했습니다.')).toBeVisible()
  expect(screen.getByText('연결 역량: 자료 정리')).toBeVisible()
  expect(screen.getByText(/필수조건: 확인 필요/)).toBeVisible()
  expect(screen.getByRole('link', { name: '공고 상세와 공식 원문 보기' })).toHaveAttribute('href', `/opportunities/${opportunityId}`)
  const post = fetch.mock.calls.find(([req]) => req.method === 'POST')![0]
  expect(await post.clone().json()).toEqual({ profile, filters: {} })
  expect(post.headers.get('X-CSRF-Token')).toBe('token')
  expect(screen.queryByText(/\d+%/)).not.toBeInTheDocument()
})

it('does not request recommendations before explicit profile confirmation', async () => {
  const fetch = vi.fn(async (req: Request) => json(req.url.endsWith('/me') ? {} : view(false)))
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await screen.findByRole('heading', { name: '먼저 프로필을 직접 확정해 주세요' })
  expect(fetch.mock.calls.some(([req]) => req.method === 'POST')).toBe(false)
})

it('keeps narrowed filters on empty results and never sends an automatic relaxed request', async () => {
  const fetch = vi.fn(async (req: Request) => json(req.method === 'POST' ? recommendations(true) : req.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount()
  await user.click(screen.getByText('지역과 활동 조건 더 고르기'))
  await user.selectOptions(screen.getByLabelText('활동 지역 추가 제한'), 'gyeonggi')
  await user.selectOptions(screen.getByLabelText('활동 유형 추가 제한'), 'volunteering')
  await user.selectOptions(screen.getByLabelText('보수 추가 제한'), 'false')
  await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await screen.findByRole('heading', { name: '현재 조건에 연결되는 추천이 없습니다' })
  const writes = fetch.mock.calls.filter(([req]) => req.method === 'POST')
  expect(writes).toHaveLength(1)
  expect((await writes[0][0].clone().json()).filters).toEqual({ regions: [{ province: 'gyeonggi', district: null }], activity_types: ['volunteering'], paid: false })
  expect(screen.getByLabelText('활동 지역 추가 제한')).toHaveValue('gyeonggi')
})

it('removes old results when filters change and preserves the selection after a network error', async () => {
  let count = 0
  vi.stubGlobal('fetch', vi.fn(async (req: Request) => {
    if (req.method === 'POST') { if (++count === 2) throw new Error('private'); return json(recommendations()) }
    return json(req.url.endsWith('/me') ? {} : view())
  }))
  const user = mount(); await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await screen.findByRole('heading', { name: '가상 자료 정리 봉사' })
  await user.click(screen.getByText('지역과 활동 조건 더 고르기'))
  await user.selectOptions(screen.getByLabelText('보수 추가 제한'), 'true')
  expect(screen.queryByText('가상 자료 정리 봉사')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('보수 추가 제한')).toHaveValue('true')
  expect(screen.getByRole('region', { name: '추천 조회 결과' })).toHaveFocus()
})

it.each([['unknown', null, '미확인', '확인 필요'], ['not_satisfied', [], '없음으로 확인', '미충족']] as const)('shows %s with the actual compared value and source', async (status, value, label, resultLabel) => {
  const fetch = vi.fn(async (_request: Request) => json(eligibility(status, value === null ? null : [...value])))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><EligibilityCheck profile={profile} opportunity={opportunity} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '이 공고의 필수조건 자세히 대조' }))
  await screen.findByRole('heading', { name: `필수조건 대조: ${resultLabel}` })
  expect(screen.getByText(`대조한 확정 자격증: ${label}`)).toBeVisible()
  expect(screen.getByText('원문 조건: 가상 자격증 필요')).toBeVisible()
  expect(await fetch.mock.calls[0][0].clone().json()).toEqual({ profile, opportunity_version: 3 })
})

it('keeps satisfied OR results distinct from an individual unmet condition', async () => {
  const response = eligibility('not_satisfied', [])
  response.overall = 'satisfied'
  response.groups = [{ group_id: id, operator: 'or', result: 'satisfied' }]
  vi.stubGlobal('fetch', vi.fn(async () => json(response))); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><EligibilityCheck profile={profile} opportunity={opportunity} /></MemoryRouter>)
  await userEvent.setup().click(screen.getByRole('button', { name: '이 공고의 필수조건 자세히 대조' }))
  await screen.findByRole('heading', { name: '필수조건 대조: 조건 충족' })
  expect(screen.getByText('미충족')).toBeVisible()
  expect(screen.getByText(/하나 이상 충족\(OR\): 조건 충족/)).toBeVisible()
})

it.each(['VERSION_CONFLICT', 'SESSION_EXPIRED'])('removes all previous personal results when eligibility detects %s', async code => {
  vi.stubGlobal('fetch', vi.fn(async (req: Request) => req.url.endsWith('/eligibility') ? json({ code }, code === 'SESSION_EXPIRED' ? 401 : 409)
    : json(req.method === 'POST' ? recommendations() : req.url.endsWith('/me') ? {} : view())))
  const user = mount(); await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await user.click(await screen.findByText('필수조건 자세히 확인하기'))
  await user.click(await screen.findByRole('button', { name: '이 공고의 필수조건 자세히 대조' }))
  await screen.findByText(/기존 결과를 지웠습니다/)
  expect(screen.queryByText('가상 자료 정리 봉사')).not.toBeInTheDocument()
})

it('blocks duplicate submits, aborts on cancel, and ignores late results after pagehide', async () => {
  let finish!: (value: Response) => void
  const fetch = vi.fn(async (req: Request) => req.method === 'POST' ? new Promise<Response>(resolve => { finish = resolve }) : json(req.url.endsWith('/me') ? {} : view()))
  vi.stubGlobal('fetch', fetch)
  const user = mount(); await user.dblClick(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  expect(fetch.mock.calls.filter(([req]) => req.method === 'POST')).toHaveLength(1)
  const post = fetch.mock.calls.find(([req]) => req.method === 'POST')![0]
  await user.click(screen.getByRole('button', { name: '조회 취소하기' }))
  expect(post.signal.aborted).toBe(true)
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => finish(json(recommendations())))
  expect(screen.queryByText('가상 자료 정리 봉사')).not.toBeInTheDocument()
})

it('passes structural accessibility for loaded recommendations and eligibility', async () => {
  vi.stubGlobal('fetch', vi.fn(async (req: Request) => json(req.url.endsWith('/eligibility') ? eligibility() : req.method === 'POST' ? recommendations() : req.url.endsWith('/me') ? {} : view())))
  const user = mount(); await user.click(screen.getByRole('button', { name: '추천 다시 확인하기' }))
  await user.click(await screen.findByText('필수조건 자세히 확인하기'))
  await user.click(await screen.findByRole('button', { name: '이 공고의 필수조건 자세히 대조' }))
  await screen.findByRole('heading', { name: '필수조건 대조: 확인 필요' })
  expect(within(screen.getByRole('region', { name: '추천 조회 결과' })).getByText('확인 필요', { selector: 'strong' })).toBeVisible()
  const report = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
  expect(report.violations).toEqual([])
})

it('rejects incorrect references, scores, duplicate ranks, closed or pending opportunities, and malformed comparisons', () => {
  const good = recommendations()
  expect(parseRecommendations(good, profile).items).toHaveLength(1)
  for (const bad of [{ ...good, profile: { ...profile, version: 99 } }, { ...good, items: [{ ...good.items[0], score: 0.9 }] },
    { ...good, items: [good.items[0], good.items[0]] }, { ...good, items: [{ ...good.items[0], opportunity: { ...good.items[0].opportunity, change_pending: true } }] },
    { ...good, items: [{ ...good.items[0], eligibility: { ...good.items[0].eligibility, overall: 'not_satisfied' } }] }]) {
    expect(() => parseRecommendations(bad, profile)).toThrow()
  }
  expect(parseEligibility(eligibility(), profile, opportunity).conditions[0].user_value).toBeNull()
  for (const bad of [{ ...eligibility(), opportunity: { ...opportunity, version: 4 } }, { ...eligibility(), no_requirements: true },
    { ...eligibility(), conditions: [{ ...eligibility().conditions[0], user_value: { owner_id: 'forged' } }] }]) {
    expect(() => parseEligibility(bad, profile, opportunity)).toThrow()
  }
})
