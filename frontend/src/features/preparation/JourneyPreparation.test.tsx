import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { JourneyPreparation, JourneyPreparationRoute } from './JourneyPreparation'
import { parseDraft, parseExistingDraft } from './drafts'
import type { JourneyDraft } from './drafts'
import { sampleDetail, sourceUrl } from '../public-opportunities/test-fixtures'

const id = '12345678-1234-1234-1234-123456789012'
const opportunityId = sampleDetail().id
const draftId = '22345678-1234-1234-1234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function profile(confirmed = true) {
  return { revision: 3, confirmed: confirmed ? { version: 1, confirmed_at: '2026-10-18T00:00:00Z' } : null, has_unconfirmed_changes: false,
    missing_for_recommendation: [], evidence: [], draft: { schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [],
      paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null,
      birth_year: null, certifications: null, completed_courses: null, activity_constraints: null } }
}
function preparation() { return { opportunity: { id: opportunityId, version: 1 }, application_method: 'online', application_instructions: '가상 공식 안내',
  application_url: sourceUrl, source_url: sourceUrl, required_documents: ['공식 시험 서류'], deadline_date: '2099-10-31', deadline_at: null, recruitment_status: 'open', change_pending: false } }
function draft(mode: 'manual' | 'generate' = 'manual'): JourneyDraft {
  return { draft_id: draftId, revision: 1, mode, profile_version: 1, opportunity: { id: opportunityId, version: 1 },
    self_introduction: mode === 'generate' ? '경험: 확인된 가상 경험' : '', motivation: '', approved_at: null, review_reasons: [], warnings: [] }
}
function server(override?: (request: Request) => Promise<Response | undefined>) {
  const state = { draft: draft(), profile: profile(), detail: sampleDetail({ source_checked_at: new Date(Date.now() - 1000).toISOString() }) }
  const fetch = vi.fn(async (request: Request): Promise<Response> => {
    const custom = await override?.(request)
    if (custom) return custom
    const path = new URL(request.url).pathname
    if (request.method === 'DELETE') return new Response(null, { status: 204 })
    if (path.endsWith('/me')) return json({})
    if (path.endsWith('/profile')) return json(state.profile)
    if (path.endsWith('/preparation')) return json(preparation())
    if (path.endsWith('/drafts')) { state.draft = draft((await request.clone().json()).mode); return json(state.draft, 201) }
    if (path.endsWith('/approve')) { state.draft = { ...state.draft, revision: state.draft.revision + 1, approved_at: new Date().toISOString() }; return json(state.draft) }
    if (request.method === 'PATCH') { const body = await request.clone().json(); state.draft = { ...state.draft, self_introduction: body.self_introduction, motivation: body.motivation, revision: state.draft.revision + 1, approved_at: null }; return json(state.draft) }
    if (path.includes('/drafts/')) return json(state.draft)
    return json(state.detail)
  })
  vi.stubGlobal('fetch', fetch)
  return { state, fetch }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><JourneyPreparation journeyId={id} opportunityId={opportunityId} /></MemoryRouter>)
  return userEvent.setup()
}
async function prepare(user: ReturnType<typeof userEvent.setup>, mode: 'manual' | 'generate' = 'manual') {
  await user.click(screen.getByRole('button', { name: '최신 준비 안내와 확정 프로필 확인' }))
  await user.click(await screen.findByRole('button', { name: mode === 'manual' ? '새 빈 초안으로 직접 작성' : '확정 경험으로 새 초안 생성' }))
  await screen.findByRole('heading', { name: '지원서 내용을 확인해 주세요' })
}
async function editApprove(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('자기소개'), '직접 쓴 경험')
  await user.type(screen.getByLabelText('지원동기'), '직접 쓴 동기')
  await user.click(screen.getByRole('button', { name: '현재 편집을 초안에 반영' }))
  await user.click(screen.getByRole('checkbox', { name: '두 항목을 읽고 내 경험과 뜻에 맞는지 확인했어요.' }))
  await user.click(screen.getByRole('button', { name: '확인한 이 리비전 승인' }))
  await screen.findByText(/서버에서 이 리비전의 사용자 승인을 확인했습니다/)
}

it('keeps actual creation, edit, explicit approval and checked copy separate with exact bodies and revisions', async () => {
  const { fetch } = server(); const user = mount(); const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  await prepare(user)
  expect(screen.getByRole('heading', { name: '지원서 내용을 확인해 주세요' })).toHaveFocus()
  expect(screen.getByRole('button', { name: '승인본 최신 상태 확인하고 복사' })).toBeDisabled()
  await editApprove(user)
  const create = fetch.mock.calls.find(([req]) => req.method === 'POST' && req.url.endsWith('/drafts'))![0]
  expect(await create.clone().json()).toEqual({ mode: 'manual', profile_version: 1, opportunity: { id: opportunityId, version: 1 }, saved_document: null })
  const patch = fetch.mock.calls.find(([req]) => req.method === 'PATCH')![0]
  expect(await patch.clone().json()).toEqual({ self_introduction: '직접 쓴 경험', motivation: '직접 쓴 동기', base_revision: 1 })
  const approval = fetch.mock.calls.find(([req]) => req.url.endsWith('/approve'))![0]
  expect(await approval.clone().json()).toEqual({ base_revision: 2 })
  await user.click(screen.getByRole('button', { name: '승인본 최신 상태 확인하고 복사' }))
  await screen.findByText('내용을 복사했습니다. 저장·신청 완료는 아닙니다.')
  expect(clipboard).toHaveBeenCalledExactlyOnceWith('자기소개\n직접 쓴 경험\n\n지원동기\n직접 쓴 동기')
  expect(screen.getByLabelText('최신 상태를 확인한 복사 내용')).toHaveValue('자기소개\n직접 쓴 경험\n\n지원동기\n직접 쓴 동기')
  expect(fetch.mock.calls.some(([req]) => req.url.includes('/save'))).toBe(false)
  await user.type(screen.getByLabelText('자기소개'), ' 수정')
  expect(screen.getByRole('button', { name: '승인본 최신 상태 확인하고 복사' })).toBeDisabled()
  expect(screen.queryByLabelText('최신 상태를 확인한 복사 내용')).not.toBeInTheDocument()
})

it('preserves the previous editor when another generation fails and permits direct manual editing', async () => {
  let creates = 0
  server(async req => req.method === 'POST' && req.url.endsWith('/drafts') && ++creates === 2 ? json({ code: 'MODEL_UNAVAILABLE' }, 503) : undefined)
  const user = mount(); await prepare(user, 'generate')
  await user.click(screen.getByRole('button', { name: '확정 경험으로 새 초안 생성' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('자기소개')).toHaveValue('경험: 확인된 가상 경험')
  await user.type(screen.getByLabelText('지원동기'), 'AI 없이 직접 작성')
  expect(screen.getByLabelText('지원동기')).toHaveValue('AI 없이 직접 작성')
  expect(screen.getByRole('button', { name: '확인한 이 리비전 승인' })).toBeDisabled()
})

it('keeps the exact creation key on an ambiguous failure and blocks duplicate clicks', async () => {
  let creates = 0, finish!: (response: Response) => void
  const { fetch } = server(async req => {
    if (req.method === 'POST' && req.url.endsWith('/drafts')) {
      if (++creates === 1) throw new Error('private network detail')
      return new Promise<Response>(resolve => { finish = resolve })
    }
  })
  const user = mount()
  await user.click(screen.getByRole('button', { name: '최신 준비 안내와 확정 프로필 확인' }))
  await user.click(await screen.findByRole('button', { name: '확정 경험으로 새 초안 생성' }))
  await screen.findByRole('alert')
  await user.dblClick(screen.getByRole('button', { name: '같은 생성 요청 결과 확인' }))
  expect(creates).toBe(2)
  const posts = fetch.mock.calls.filter(([req]) => req.method === 'POST')
  expect(posts[0][0].headers.get('Idempotency-Key')).toBe(posts[1][0].headers.get('Idempotency-Key'))
  expect(await posts[0][0].clone().json()).toEqual(await posts[1][0].clone().json())
  await act(async () => finish(json(draft('generate'), 201)))
  await screen.findByLabelText('자기소개')
})

it('keeps edited input on a revision conflict and discards it only on the explicit reload action', async () => {
  server(async req => req.method === 'PATCH' ? json({ code: 'VERSION_CONFLICT' }, 409) : undefined)
  const user = mount(); await prepare(user)
  await user.type(screen.getByLabelText('자기소개'), '반영 전 편집')
  await user.click(screen.getByRole('button', { name: '현재 편집을 초안에 반영' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('자기소개')).toHaveValue('반영 전 편집')
  await user.click(screen.getByRole('button', { name: '화면 편집 버리고 서버 본문 불러오기' }))
  expect(screen.getByLabelText('자기소개')).toHaveValue('')
})

it('does not request creation for an unconfirmed profile and keeps document checks temporary', async () => {
  const { state, fetch } = server(); state.profile = profile(false)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '최신 준비 안내와 확정 프로필 확인' }))
  await screen.findByRole('heading', { name: '프로필을 먼저 확정해 주세요' })
  await user.click(screen.getByRole('checkbox', { name: '공식 시험 서류' }))
  expect(screen.getByRole('checkbox', { name: '공식 시험 서류' })).toBeChecked()
  await user.click(screen.getByRole('button', { name: '최신 준비 안내와 확정 프로필 확인' }))
  expect(await screen.findByRole('checkbox', { name: '공식 시험 서류' })).not.toBeChecked()
  expect(fetch.mock.calls.some(([req]) => req.method === 'POST')).toBe(false)
})

it.each(['revision', 'profile', 'closed', 'stale', 'review'])('never writes to the clipboard when current evidence changed: %s', async change => {
  const { state } = server(); const user = mount(); const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  await prepare(user); await editApprove(user)
  if (change === 'revision') state.draft = { ...state.draft, revision: 9, self_introduction: '다른 편집' }
  if (change === 'profile') state.profile.confirmed!.version = 2
  if (change === 'closed') state.detail.recruitment_status = 'closed'
  if (change === 'stale') state.detail.source_checked_at = '2000-01-01T00:00:00Z'
  if (change === 'review') state.draft.review_reasons = ['opportunity_changed']
  await user.click(screen.getByRole('button', { name: '승인본 최신 상태 확인하고 복사' }))
  await screen.findByRole('alert')
  expect(clipboard).not.toHaveBeenCalled()
  expect(screen.getByLabelText('자기소개')).toHaveValue('직접 쓴 경험')
  expect(screen.queryByLabelText('최신 상태를 확인한 복사 내용')).not.toBeInTheDocument()
})

it('offers selection of only the freshly verified exact text when the clipboard rejects', async () => {
  server(); const user = mount(); vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('denied'))
  await prepare(user); await editApprove(user)
  await user.click(screen.getByRole('button', { name: '승인본 최신 상태 확인하고 복사' }))
  await user.click(await screen.findByRole('button', { name: '복사할 내용 전체 선택' }))
  const field = screen.getByLabelText('최신 상태를 확인한 복사 내용') as HTMLTextAreaElement
  expect(field).toHaveFocus()
  expect(field.selectionStart).toBe(0); expect(field.selectionEnd).toBe(field.value.length)
  expect(screen.queryByText('내용을 복사했습니다. 저장·신청 완료는 아닙니다.')).not.toBeInTheDocument()
})

it('does not lose manual input when a public opportunity becomes unavailable', async () => {
  let missing = false
  server(async req => missing && req.url.endsWith('/preparation') ? json({ code: 'NOT_FOUND' }, 404) : undefined)
  const user = mount(); await prepare(user)
  await user.type(screen.getByLabelText('자기소개'), '보존할 편집')
  missing = true
  await user.click(screen.getByRole('button', { name: '최신 준비 안내와 확정 프로필 확인' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('자기소개')).toHaveValue('보존할 편집')
})

it('discards late generation and all private text on pagehide', async () => {
  let finish!: (response: Response) => void
  server(async req => req.method === 'POST' ? new Promise<Response>(resolve => { finish = resolve }) : undefined)
  const user = mount()
  await user.click(screen.getByRole('button', { name: '최신 준비 안내와 확정 프로필 확인' }))
  await user.click(await screen.findByRole('button', { name: '확정 경험으로 새 초안 생성' }))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => finish(json(draft('generate'), 201)))
  expect(screen.queryByLabelText('자기소개')).not.toBeInTheDocument()
  expect(screen.queryByText('같은 요청의 처리 결과를 다시 확인할 수 있어요.')).not.toBeInTheDocument()
})

it('keeps body on delete failure and clears it only after a real 204', async () => {
  let deletes = 0
  server(async req => req.method === 'DELETE' && ++deletes === 1 ? json({ code: 'SERVICE_UNAVAILABLE' }, 503) : undefined)
  const user = mount(); await prepare(user)
  await user.type(screen.getByLabelText('자기소개'), '삭제 전 편집')
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  expect(deletes).toBe(0)
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('자기소개')).toHaveValue('삭제 전 편집')
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  expect(screen.queryByLabelText('자기소개')).not.toBeInTheDocument()
})

it('rejects reload of the actual nested journey route before requesting private data', () => {
  const path = `/journeys/${id}/opportunities/${opportunityId}/preparation`
  vi.spyOn(performance, 'getEntriesByType').mockReturnValue([{ type: 'reload', name: `https://app.test${path}` }] as unknown as PerformanceEntryList)
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={[path]}><Routes><Route path="/" element={<p>시작 화면</p>} /><Route path="/journeys/:journeyId/opportunities/:opportunityId/preparation" element={<JourneyPreparationRoute />} /></Routes></MemoryRouter>)
  expect(screen.getByText('시작 화면')).toBeVisible(); expect(fetch).not.toHaveBeenCalled()
})

it('validates draft references and preserves original dependency metadata during editor reads', () => {
  expect(parseDraft(draft(), opportunityId).revision).toBe(1)
  for (const bad of [{ ...draft(), revision: true }, { ...draft(), draft_id: 'forged' }, { ...draft(), approved_at: 'yesterday' },
    { ...draft(), self_introduction: '가'.repeat(2001) }, { ...draft(), review_reasons: ['invented'] }]) expect(() => parseDraft(bad, opportunityId)).toThrow()
  expect(() => parseExistingDraft({ ...draft(), profile_version: 2 }, draft())).toThrow()
})

it('passes structural accessibility for preparation, editing and explicit approval', async () => {
  server(); const user = mount(); await prepare(user); await editApprove(user)
  const report = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
  expect(report.violations).toEqual([])
})

it('lets the user abandon an uncertain new generation while keeping the existing editable body', async () => {
  let posts = 0, finish!: (response: Response) => void
  server(async req => req.method === 'POST' && req.url.endsWith('/drafts') && ++posts === 2 ? new Promise<Response>(resolve => { finish = resolve }) : undefined)
  const user = mount(); await prepare(user, 'generate')
  await user.click(screen.getByRole('button', { name: '확정 경험으로 새 초안 생성' }))
  await user.click(screen.getByRole('button', { name: '대기 결과를 버리고 기존 본문 계속 편집' }))
  await user.type(screen.getByLabelText('지원동기'), '이전 본문에 직접 작성')
  await act(async () => finish(json(draft('generate'), 201)))
  expect(screen.getByLabelText('자기소개')).toHaveValue('경험: 확인된 가상 경험')
  expect(screen.getByLabelText('지원동기')).toHaveValue('이전 본문에 직접 작성')
})

it('does not write a clipboard body after leaving during the server freshness check', async () => {
  let pause = false, finish!: (response: Response) => void
  const { state } = server(async req => pause && req.method === 'GET' && req.url.includes('/drafts/') ? new Promise<Response>(resolve => { finish = resolve }) : undefined)
  const user = mount(); const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  await prepare(user); await editApprove(user)
  pause = true
  await user.click(screen.getByRole('button', { name: '승인본 최신 상태 확인하고 복사' }))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => finish(json(state.draft)))
  expect(clipboard).not.toHaveBeenCalled()
  expect(screen.queryByLabelText('자기소개')).not.toBeInTheDocument()
})

it('erases editor and cached private results when the session expires', async () => {
  let expired = false
  server(async req => expired && req.url.includes('/drafts/') ? json({ code: 'SESSION_EXPIRED' }, 401) : undefined)
  const user = mount(); await prepare(user); await editApprove(user)
  expired = true
  await user.click(screen.getByRole('button', { name: '서버 본문과 재검토 사유 다시 확인' }))
  await screen.findByRole('alert')
  expect(screen.queryByLabelText('자기소개')).not.toBeInTheDocument()
  expect(screen.queryByLabelText('최신 상태를 확인한 복사 내용')).not.toBeInTheDocument()
})
