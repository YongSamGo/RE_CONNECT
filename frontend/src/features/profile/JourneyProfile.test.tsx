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

function server(options: { confirmed?: boolean; conflict?: boolean; delayed?: boolean; empty?: boolean } = {}) {
  let current=view(options.confirmed), finish!: (response:Response)=>void
  if(options.empty) current={...current,draft:{...current.draft,experiences:[],preferred_regions:[],activity_types:[]}}
  const fetch=vi.fn(async (request:Request):Promise<Response>=>{
    if(request.url.endsWith('/me')) return json({})
    if(request.url.endsWith('/roles')) return json(roles(current.revision,current.confirmed?.version??1))
    if(request.url.endsWith('/role-exclusions')) return json({revision:current.revision,role_ids:[]})
    if(request.url.endsWith('/confirm')) { current={...current,revision:current.revision+1,confirmed:{version:1,confirmed_at:'2026-10-18T00:00:00Z'}};return json({}) }
    if(request.method==='PATCH') {
      if(options.delayed) return new Promise(resolve=>{finish=resolve})
      if(options.conflict) return json({code:'VERSION_CONFLICT'},409)
      const body=await request.clone().json();current={...current,revision:current.revision+1,draft:body.draft}
    }
    return json(current)
  })
  vi.stubGlobal('fetch',fetch)
  return {fetch,finish:(response:Response)=>finish(response)}
}
async function loaded(user:ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('button',{name:'정리한 경험 불러오기'}))
  await screen.findByRole('button',{name:'내가 해온 일 수정하기'})
}
async function editExperience(user:ReturnType<typeof userEvent.setup>) {
  await loaded(user);await user.click(screen.getByRole('button',{name:'내가 해온 일 수정하기'}))
}
it('shows concise summaries and opens only the selected field for editing',async()=>{
  server();const user=mount();await loaded(user)
  expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'희망 지역 수정하기'}))
  expect(screen.getByRole('button',{name:'시군구 목록 불러오기'})).toBeVisible()
  expect(screen.queryByLabelText('경험 1 내용')).not.toBeInTheDocument()
})
it('keeps unsaved experience text when cancelling discard and reloads only after confirmation',async()=>{
  const {fetch}=server();const user=mount();await editExperience(user)
  await user.type(screen.getByLabelText('경험 1 내용'),' 수정')
  await user.click(screen.getByRole('button',{name:'수정 취소'}))
  expect(screen.getByRole('heading',{name:'수정을 취소할까요?'})).toHaveFocus()
  await user.click(screen.getByRole('button',{name:'계속 수정하기'}))
  expect(screen.getByLabelText('경험 1 내용')).toHaveValue('가상 도서관 경험 수정')
  await user.click(screen.getByRole('button',{name:'수정 취소'}))
  await user.click(screen.getByRole('button',{name:'수정 내용 버리기'}))
  expect(await screen.findByText('가상 도서관 경험')).toBeVisible()
  expect(fetch.mock.calls.some(([req])=>req.method==='PATCH')).toBe(false)
})
it('separates editing from confirmation and preserves unknown and empty optional values',async()=>{
  const {fetch}=server();const user=mount();await editExperience(user)
  await user.type(screen.getByLabelText('경험 1 내용'),' 수정')
  await user.click(screen.getByRole('button',{name:'변경 내용 반영하기'}))
  await screen.findByText('수정한 내용을 확인해 주세요.')
  const patch=fetch.mock.calls.find(([req])=>req.method==='PATCH')![0]
  const body=await patch.clone().json()
  expect(body.base_revision).toBe(1);expect(body.draft.certifications).toBeNull()
  expect(body.draft.completed_courses).toEqual([]);expect(body.draft.experiences[0].id).toBe(experienceId)
  expect(fetch.mock.calls.some(([req])=>req.url.endsWith('/confirm'))).toBe(false)
  await user.click(screen.getByRole('button',{name:'이 내용으로 확정'}))
  expect(await screen.findByRole('link',{name:'추천 공고 확인하기'})).toHaveAttribute('href',`/journeys/${id}/recommendations`)
  expect(screen.getByRole('button',{name:'이대로 저장하기'})).toBeVisible()
})
it('rejects an empty added experience before sending a patch and focuses its error',async()=>{
  const {fetch}=server();const user=mount();await editExperience(user)
  await user.click(screen.getByRole('button',{name:'경험 추가'}))
  await user.click(screen.getByRole('button',{name:'변경 내용 반영하기'}))
  await user.click(screen.getByRole('link',{name:/경험 2의 내용을 적거나/}))
  expect(screen.getByLabelText('경험 2 내용')).toHaveFocus()
  expect(fetch.mock.calls.some(([req])=>req.method==='PATCH')).toBe(false)
})
it('preserves edits on conflict and rejects duplicate writes and late pagehide replies',async()=>{
  const {fetch,finish}=server({delayed:true});const user=mount();await editExperience(user)
  await user.type(screen.getByLabelText('경험 1 내용'),' 수정')
  await user.dblClick(screen.getByRole('button',{name:'변경 내용 반영하기'}))
  expect(fetch.mock.calls.filter(([req])=>req.method==='PATCH')).toHaveLength(1)
  await act(async()=>finish(json({code:'VERSION_CONFLICT'},409)))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByLabelText('경험 1 내용')).toHaveValue('가상 도서관 경험 수정')
  await user.click(screen.getByRole('button',{name:'변경 내용 반영하기'}))
  act(()=>window.dispatchEvent(new Event('pagehide')))
  await act(async()=>finish(json(view())))
  expect(screen.queryByLabelText('경험 1 내용')).not.toBeInTheDocument()
})
it('keeps summary and individual editing controls accessible',async()=>{
  vi.spyOn(HTMLCanvasElement.prototype,'getContext').mockReturnValue(null)
  server({confirmed:true});const user=mount();await editExperience(user)
  const result=await axe.run(document.body,{runOnly:{type:'tag',values:['wcag2a','wcag2aa','wcag21a','wcag21aa']},rules:{'color-contrast':{enabled:false}}})
  expect(result.violations.map(v=>v.id)).toEqual([])
},20000)
it('validates evidence/version boundaries and does not render malformed role candidates', () => {
  expect(() => parseRoles({ ...roles(), profile_version: 999 }, view(true))).toThrow()
  expect(() => parseProfileView({ ...view(), draft: { ...view().draft, experiences: [{ ...view().draft.experiences[0], id: 'forged' }] } })).toThrow()
})
