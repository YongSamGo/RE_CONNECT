import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { JourneyConversation } from './JourneyConversation'
import type { ProfileView } from './model'

const id = '12345678-1234-1234-1234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const catalog = { version: 'v1', provinces: [
  { id: 'seoul', name: '서울특별시', districts: [{ id: 'jung', name: '중구' }, { id: 'seongdong', name: '성동구' }] },
  { id: 'gyeonggi', name: '경기도', districts: [{ id: 'seongnam', name: '성남시' }] },
] }
function view(regions: ProfileView['draft']['preferred_regions'] = [], experiences = 1): ProfileView {
  return { revision: 3, confirmed: null, has_unconfirmed_changes: false, evidence: [], missing_for_recommendation: regions.length ? ['activity_types'] : ['preferred_regions', 'activity_types'], draft: {
    schema_version: 1, experiences: Array.from({ length: experiences }, (_, i) => ({ id: `4234567${i}-1234-1234-1234-123456789012`, description: '가상 도서관에서 책을 정리했어요.', duration_note: null, skill_tags: [] })),
    skills: [], preferred_regions: regions, activity_types: [], paid_preference: null,
    available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null,
    certifications: null, completed_courses: null, activity_constraints: null,
  } }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

function mount(profile: ProfileView) {
  const fetch = vi.fn(async (request: Request) => json(request.url.endsWith('/regions') ? catalog : request.url.endsWith('/me') ? {} : profile))
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter><JourneyConversation journeyId={id} /></MemoryRouter>)
  return { user: userEvent.setup(), fetch }
}

it('lets a region answer be picked from the server list instead of relying on speech recognition', async () => {
  const { user, fetch } = mount(view())
  await user.click(screen.getByRole('button', { name: '체험 대화 준비하기' }))
  expect(await screen.findByRole('heading', { name: '지역 목록에서 고르기' })).toBeVisible()
  const district = screen.getByLabelText('시군구')
  await vi.waitFor(() => expect(district).toBeEnabled())
  await user.selectOptions(district, 'seongdong')
  await user.click(screen.getByRole('button', { name: '답변에 넣기' }))
  await user.selectOptions(district, 'jung')
  await user.click(screen.getByRole('button', { name: '답변에 넣기' }))
  await user.click(screen.getByRole('button', { name: '답변에 넣기' }))
  expect(screen.getByLabelText('내 답변')).toHaveValue('서울 성동구, 서울 중구')
  await user.selectOptions(screen.getByLabelText('시도'), 'gyeonggi')
  await user.click(screen.getByRole('button', { name: '답변에 넣기' }))
  expect(screen.getByLabelText('내 답변')).toHaveValue('서울 성동구, 서울 중구, 경기 전체')
  expect(fetch.mock.calls.filter(([request]) => (request as Request).method === 'POST')).toHaveLength(0)
})

it('does not show the picker once preferred regions are known', async () => {
  const { user, fetch } = mount(view([{ province: 'seoul', district: null }]))
  await user.click(screen.getByRole('button', { name: '체험 대화 준비하기' }))
  await screen.findByLabelText('내 답변')
  expect(screen.queryByRole('heading', { name: '지역 목록에서 고르기' })).toBeNull()
  expect(fetch.mock.calls.some(([request]) => (request as Request).url.endsWith('/regions'))).toBe(false)
})
