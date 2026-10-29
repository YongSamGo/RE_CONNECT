import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { sourceUrl } from '../public-opportunities/test-fixtures'
import { JourneyDraftEditor } from './JourneyDraftEditor'
import { parseJourneyDraft } from './draft-model'

const journeyId = '12345678-1234-1234-1234-123456789012'
const opportunityId = '22345678-1234-1234-1234-123456789012'
const draftId = '32345678-1234-1234-1234-123456789012'
const stamp = '2026-10-18T00:00:00Z'
const reference = { id: opportunityId, version: 1 }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const empty = () => ({ draft_id: draftId, revision: 1, mode: 'manual', profile_version: 1, opportunity: reference, self_introduction: '', motivation: '', approved_at: null as string | null, review_reasons: [], warnings: [] })
function server(options: { loseFirst?: boolean; conflict?: boolean; aiFailure?: boolean; consent?: boolean; loseApproval?: boolean; reviewReasons?: string[]; changedApproval?: boolean; invalid?: boolean } = {}) {
  let current = empty(), creations = 0
  const fetch = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname
    if (path === '/api/v1/me') return json({ authenticated: false, user: null, consents: options.consent === false ? [] : [{ purpose: 'ai_processing', notice_version: 'fixture-ai', granted_at: stamp }], pending_save_intent: null })
    if (path.endsWith('/profile')) return json({ revision: 3, confirmed: { version: 1, confirmed_at: stamp }, has_unconfirmed_changes: false, missing_for_recommendation: [], evidence: [], draft: {
      schema_version: 1, experiences: [{ id: draftId, description: '가상 도서관 경험', duration_note: null, skill_tags: ['자료 정리'] }], skills: [], preferred_regions: [{ province: 'seoul', district: null }], activity_types: ['volunteering'], paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: [], activity_constraints: null,
    } })
    if (path.endsWith('/preparation')) return json({ opportunity: reference, application_method: 'online', application_instructions: '가상 안내', application_url: 'https://example.org/apply', source_url: 'https://example.org/source', required_documents: [], deadline_date: null, deadline_at: null, recruitment_status: 'open', change_pending: false })
    if (path.endsWith('/drafts') && request.method === 'POST') {
      creations++
      const body = await request.clone().json()
      if (options.aiFailure && body.mode === 'generate' && creations === 1) return json({ code: 'MODEL_UNAVAILABLE' }, 503)
      if (options.invalid && body.mode === 'generate') return json({ code: 'VALIDATION_FAILED' }, 422)
      if (options.loseFirst && creations === 1) throw new TypeError('fixture lost response')
      current = { ...empty(), mode: body.mode }; return json(current, 201)
    }
    if (request.method === 'PATCH') {
      if (options.conflict) return json({ code: 'VERSION_CONFLICT' }, 409)
      if (options.invalid) return json({ code: 'VALIDATION_FAILED' }, 422)
      const body = await request.clone().json()
      current = { ...current, revision: current.revision + 1, self_introduction: body.self_introduction, motivation: body.motivation, approved_at: null }
    }
    if (path.endsWith('/approve')) {
      current = { ...current, revision: current.revision + 1, approved_at: stamp, self_introduction: options.changedApproval ? '확인하지 않은 본문' : current.self_introduction }
      if (options.loseApproval) throw new TypeError('fixture lost approval response')
    }
    if (request.method === 'GET' && path.endsWith(draftId)) return json({ ...current, review_reasons: options.reviewReasons ?? [] })
    return json(current)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}
function mount(autoGenerate = false) {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const rendered = render(<MemoryRouter><JourneyDraftEditor journeyId={journeyId} opportunityId={opportunityId} applicationUrl={sourceUrl} autoGenerate={autoGenerate} /></MemoryRouter>)
  return { ...rendered, user: userEvent.setup() }
}
const manual = () => screen.getByRole('button', { name: 'AI 없이 빈 초안 직접 작성' })
const approve = () => screen.getByRole('button', { name: '확인한 현재 본문 승인' })
const review = () => screen.getByRole('checkbox', { name: '두 항목을 읽고 확정 경험과 공고에 맞는 내용임을 확인했어요.' })
async function writeAndUpdate(user:ReturnType<typeof userEvent.setup>) {
  await user.click(manual());await user.type(await screen.findByLabelText('지원 자기소개'),'가상 경험')
  await user.type(screen.getByLabelText('지원 동기'),'가상 지원동기')
  await user.click(screen.getByRole('button',{name:'수정하고 검토하기'}))
  await screen.findByRole('dialog',{name:'지원 내용을 확인해 주세요'})
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('patches changes before showing the review dialog and approves only the exact confirmed text',async()=>{
  const fetch=server(),{user}=mount();await writeAndUpdate(user)
  expect(review()).not.toBeChecked();expect(approve()).toBeDisabled()
  await user.click(review());await user.click(approve())
  expect(await screen.findByText('확인한 내용을 승인했어요. 공식 신청처로 이동해 제출해 주세요.')).toBeVisible()
  const patch=fetch.mock.calls.find(([request])=>request.method==='PATCH')![0]
  expect(await patch.clone().json()).toEqual({base_revision:1,self_introduction:'가상 경험',motivation:'가상 지원동기'})
  expect(screen.queryByRole('link',{name:/회원 저장/})).not.toBeInTheDocument()
  expect(screen.getByRole('link',{name:/공식 신청처로 이동/})).toHaveAttribute('href',sourceUrl)
})
it('reuses a creation key after losing its reply without automatically generating again',async()=>{
  const fetch=server({loseFirst:true}),{user}=mount();await user.click(manual());await screen.findByRole('alert')
  expect(fetch.mock.calls.filter(([req])=>req.method==='POST')).toHaveLength(1)
  await user.click(manual());await screen.findByLabelText('지원 자기소개')
  const posts=fetch.mock.calls.map(([req])=>req).filter(req=>req.method==='POST')
  expect(posts[0].headers.get('Idempotency-Key')).toBe(posts[1].headers.get('Idempotency-Key'))
  expect(await posts[0].clone().json()).toEqual(await posts[1].clone().json())
})
it('preserves conflicting edits and asks before replacing them with the current server content',async()=>{
  server({conflict:true});const {user}=mount()
  await user.click(manual());await user.type(await screen.findByLabelText('지원 자기소개'),'유지할 내용');await user.type(screen.getByLabelText('지원 동기'),'유지할 이유')
  await user.click(screen.getByRole('button',{name:'수정하고 검토하기'}));await screen.findByRole('alert')
  await user.click(screen.getByRole('button',{name:'현재 내용 다시 확인'}))
  await user.click(screen.getByRole('button',{name:'작성한 내용 유지'}))
  expect(screen.getByLabelText('지원 자기소개')).toHaveValue('유지할 내용')
  await user.click(screen.getByRole('button',{name:'현재 내용 다시 확인'}));await user.click(screen.getByRole('button',{name:'현재 내용으로 바꾸기'}))
  expect(await screen.findByLabelText('지원 자기소개')).toHaveValue('')
})
it('offers a fresh AI request only after a confirmed model failure',async()=>{
  const fetch=server({aiFailure:true}),{user}=mount();await user.click(screen.getByRole('button',{name:'AI 초안 만들기'}))
  await user.click(await screen.findByRole('button',{name:'AI 실패 후 새 요청으로 다시 생성'}));await screen.findByLabelText('지원 자기소개')
  const posts=fetch.mock.calls.map(([req])=>req).filter(req=>req.method==='POST')
  expect(posts).toHaveLength(2);expect(posts[0].headers.get('Idempotency-Key')).not.toBe(posts[1].headers.get('Idempotency-Key'))
})
it('does not offer a fresh AI key while the original request result is uncertain',async()=>{
  const fetch=server({loseFirst:true}),{user}=mount();await user.click(screen.getByRole('button',{name:'AI 초안 만들기'}));await screen.findByRole('alert')
  expect(screen.queryByRole('button',{name:'AI 실패 후 새 요청으로 다시 생성'})).not.toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'AI 초안 만들기'}));await screen.findByLabelText('지원 자기소개')
  const posts=fetch.mock.calls.map(([req])=>req).filter(req=>req.method==='POST');expect(posts[0].headers.get('Idempotency-Key')).toBe(posts[1].headers.get('Idempotency-Key'))
})
it('guides unusable AI facts to manual input without a pointless inference retry',async()=>{
  const fetch=server({invalid:true}),{user}=mount();await user.click(screen.getByRole('button',{name:'AI 초안 만들기'}))
  expect(await screen.findByText('AI 초안을 만들지 못했어요')).toBeVisible()
  expect(screen.queryByRole('button',{name:'AI 실패 후 새 요청으로 다시 생성'})).not.toBeInTheDocument()
  await user.click(manual());expect(await screen.findByLabelText('지원 자기소개')).toHaveValue('')
  expect(fetch.mock.calls.filter(([req])=>req.method==='POST')).toHaveLength(2)
})
it('blocks AI without current consent but still allows explicit manual writing',async()=>{
  const fetch=server({consent:false}),{user}=mount();await user.click(screen.getByRole('button',{name:'AI 초안 만들기'}));await screen.findByRole('alert')
  expect(fetch.mock.calls.some(([req])=>req.method==='POST')).toBe(false)
  await user.click(manual());await screen.findByLabelText('지원 자기소개')
  expect((await fetch.mock.calls.find(([req])=>req.method==='POST')![0].clone().json()).mode).toBe('manual')
})
it('discards a parsed creation response after pagehide',async()=>{
  server();let release!:()=>void,arrived!:()=>void
  const waiting=new Promise<void>(resolve=>{release=resolve}),parsing=new Promise<void>(resolve=>{arrived=resolve})
  const original=Response.prototype.text
  vi.spyOn(Response.prototype,'text').mockImplementation(async function(this:Response){const body=await original.call(this);if(body.includes('"draft_id"')){arrived();await waiting}return body})
  const {user}=mount();await user.click(manual());await parsing
  act(()=>window.dispatchEvent(new Event('pagehide')));await act(async()=>release())
  expect(screen.queryByLabelText('지원 자기소개')).not.toBeInTheDocument()
})
it('recovers a lost approval by reading current state without repeating approval',async()=>{
  const fetch=server({loseApproval:true}),{user}=mount();await writeAndUpdate(user);await user.click(review());await user.click(approve());await screen.findByRole('alert')
  await user.click(screen.getByRole('button',{name:'현재 내용 다시 확인'}))
  expect(await screen.findByText('확인한 내용을 승인했어요. 공식 신청처로 이동해 제출해 주세요.')).toBeVisible()
  expect(fetch.mock.calls.filter(([req])=>req.url.endsWith('/approve'))).toHaveLength(1)
})
it('rejects an approval reply with substituted text without overwriting the reviewed input',async()=>{
  server({changedApproval:true});const {user}=mount();await writeAndUpdate(user);await user.click(review());await user.click(approve())
  await screen.findByRole('alert');expect(screen.getByLabelText('지원 자기소개')).toHaveValue('가상 경험')
  expect(screen.queryByText('확인한 내용을 승인했어요. 공식 신청처로 이동해 제출해 주세요.')).not.toBeInTheDocument()
})
it.each(['profile_changed','opportunity_changed','opportunity_closed'])('blocks approval on recovered %s',async reason=>{
  server({loseApproval:true,reviewReasons:[reason]});const {user}=mount();await writeAndUpdate(user);await user.click(review());await user.click(approve());await screen.findByRole('alert')
  await user.click(screen.getByRole('button',{name:'현재 내용 다시 확인'}))
  expect(await screen.findByText('지원 내용을 다시 확인해 주세요')).toBeVisible()
  expect(screen.getByRole('button',{name:'지원 내용 검토하기'})).toBeDisabled()
})
it('rejects substituted references, unsafe revisions and unrecognized review flags', () => {
  expect(parseJourneyDraft(empty(), reference, 1).revision).toBe(1)
  for (const changed of [{ opportunity: { ...reference, version: 2 } }, { profile_version: 2 }, { revision: 0 }, { review_reasons: ['approve_now'] }, { self_introduction: '가'.repeat(2001) }]) {
    expect(() => parseJourneyDraft({ ...empty(), ...changed }, reference, 1)).toThrow()
  }
})
