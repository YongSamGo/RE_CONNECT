import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { JourneyDraftEditor } from './JourneyDraftEditor'
import { parseJourneyDraft } from './draft-model'

const journeyId = '12345678-1234-1234-1234-123456789012'
const opportunityId = '22345678-1234-1234-1234-123456789012'
const draftId = '32345678-1234-1234-1234-123456789012'
const stamp = '2026-10-18T00:00:00Z'
const reference = { id: opportunityId, version: 1 }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const empty = () => ({ draft_id: draftId, revision: 1, mode: 'manual', profile_version: 1, opportunity: reference, self_introduction: '', motivation: '', approved_at: null as string | null, review_reasons: [], warnings: [] })
function server(options: { loseFirst?: boolean; conflict?: boolean; aiFailure?: boolean; consent?: boolean } = {}) {
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
      if (options.aiFailure && body.mode === 'generate') return json({ error: { code: 'SERVICE_UNAVAILABLE' } }, 503)
      if (options.loseFirst && creations === 1) throw new TypeError('fixture lost response')
      current = { ...empty(), mode: body.mode }; return json(current, 201)
    }
    if (request.method === 'PATCH') {
      if (options.conflict) return json({ error: { code: 'REVISION_CONFLICT' } }, 409)
      const body = await request.clone().json()
      current = { ...current, revision: current.revision + 1, self_introduction: body.self_introduction, motivation: body.motivation, approved_at: null }
    }
    if (path.endsWith('/approve')) current = { ...current, revision: current.revision + 1, approved_at: stamp }
    return json(current)
  })
  vi.stubGlobal('fetch', fetch)
  return fetch
}
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const rendered = render(<MemoryRouter><JourneyDraftEditor journeyId={journeyId} opportunityId={opportunityId} /></MemoryRouter>)
  return { ...rendered, user: userEvent.setup() }
}
const manual = () => screen.getByRole('button', { name: 'AI 없이 빈 초안 직접 작성' })
const approve = () => screen.getByRole('button', { name: '확인한 현재 본문 승인' })
const review = () => screen.getByRole('checkbox', { name: '두 항목을 읽고 확정 경험과 공고에 맞는 내용임을 확인했어요.' })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('requires explicit patch, renewed review and server approval before offering member save', async () => {
  const fetch = server(), { user, container } = mount()
  await user.click(manual())
  await user.type(await screen.findByLabelText('지원 자기소개'), '자료를 정리한 경험')
  await user.type(screen.getByLabelText('지원 동기'), '가상 활동에 참여하고 싶어요')
  await user.click(review()); expect(approve()).toBeDisabled()
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  await screen.findByText('수정 내용을 서버 임시 초안에 반영했습니다. 다시 읽고 승인해 주세요.')
  expect(review()).not.toBeChecked(); expect(approve()).toBeDisabled()
  expect(screen.queryByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).not.toBeInTheDocument()
  await user.click(review()); await user.click(approve())
  expect(await screen.findByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).toHaveAttribute('href', `/journeys/${journeyId}/drafts/${draftId}/save`)
  const patch = fetch.mock.calls.find(([request]) => request.method === 'PATCH')![0]
  expect(await patch.clone().json()).toEqual({ base_revision: 1, self_introduction: '자료를 정리한 경험', motivation: '가상 활동에 참여하고 싶어요' })
  expect((await axe.run(container)).violations).toEqual([])
})

it('reuses the creation key after response loss and changes it only for an explicit new draft', async () => {
  const fetch = server({ loseFirst: true }), { user } = mount()
  await user.click(manual()); await screen.findByText(/AI 실패 시 직접 작성을 선택할 수 있습니다/)
  await user.click(manual()); await screen.findByLabelText('지원 자기소개')
  const posts = () => fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST')
  expect(posts()).toHaveLength(2)
  expect(posts()[0].headers.get('Idempotency-Key')).toBe(posts()[1].headers.get('Idempotency-Key'))
  expect(await posts()[0].clone().json()).toEqual(await posts()[1].clone().json())
  expect(manual()).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: '현재 화면 내용을 새 초안이나 서버 편집본으로 바꾸는 것을 확인했어요.' }))
  await user.click(manual()); await screen.findByText('직접 작성할 임시 초안을 만들었습니다. 아직 승인·회원 저장하지 않았습니다.')
  expect(posts()).toHaveLength(3)
  expect(posts()[2].headers.get('Idempotency-Key')).not.toBe(posts()[1].headers.get('Idempotency-Key'))
})

it('preserves local text on revision conflict and requires explicit replacement before reload', async () => {
  const fetch = server({ conflict: true }), { user } = mount()
  await user.click(manual()); await user.type(await screen.findByLabelText('지원 자기소개'), '사라지면 안 되는 임시 입력')
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  await screen.findByText(/AI 실패 시 직접 작성을 선택할 수 있습니다/)
  expect(screen.getByLabelText('지원 자기소개')).toHaveValue('사라지면 안 되는 임시 입력')
  expect(screen.getByRole('button', { name: '서버의 현재 편집본 확인' })).toBeDisabled()
  expect(fetch.mock.calls.some(([request]) => request.url.endsWith('/approve'))).toBe(false)
})

it('offers manual entry after AI failure without automatically sending another creation', async () => {
  const fetch = server({ aiFailure: true }), { user } = mount()
  await user.click(screen.getByRole('button', { name: 'AI 초안 생성 · 같은 요청 재확인' }))
  await screen.findByText(/AI 실패 시 직접 작성을 선택할 수 있습니다/)
  expect(fetch.mock.calls.filter(([request]) => request.method === 'POST')).toHaveLength(1)
  await user.click(manual()); expect(await screen.findByLabelText('지원 자기소개')).toHaveValue('')
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByLabelText('지원 자기소개')).not.toBeInTheDocument()
})

it('blocks AI generation without processing consent while allowing explicit manual entry', async () => {
  const fetch = server({ consent: false }), { user } = mount()
  await user.click(screen.getByRole('button', { name: 'AI 초안 생성 · 같은 요청 재확인' })); await screen.findByText(/AI 실패 시 직접 작성을 선택할 수 있습니다/)
  expect(fetch.mock.calls.filter(([request]) => request.method !== 'GET')).toHaveLength(0)
  await user.click(manual()); expect(await screen.findByLabelText('지원 자기소개')).toHaveValue('')
  const post = fetch.mock.calls.find(([request]) => request.method === 'POST')![0]
  expect((await post.clone().json()).mode).toBe('manual')
})

it('discards a parsed creation response after pagehide instead of restoring private text', async () => {
  server()
  const original = Response.prototype.text
  let release: (() => void) | undefined
  const waiting = new Promise<void>(resolve => { release = resolve })
  let arrived: (() => void) | undefined
  const parsing = new Promise<void>(resolve => { arrived = resolve })
  vi.spyOn(Response.prototype, 'text').mockImplementation(async function (this: Response) {
    const body = await original.call(this)
    if (body.includes('"draft_id"')) { arrived?.(); await waiting }
    return body
  })
  const { user } = mount()
  await user.click(manual()); await parsing
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => { release?.(); await waiting })
  expect(screen.queryByLabelText('지원 자기소개')).not.toBeInTheDocument()
  expect(screen.queryByText('직접 작성할 임시 초안을 만들었습니다. 아직 승인·회원 저장하지 않았습니다.')).not.toBeInTheDocument()
})

it('keeps a selectable copy fallback when clipboard permission fails', async () => {
  server(); const { user } = mount()
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new DOMException('fixture denial', 'NotAllowedError'))
  await user.click(manual()); await user.type(await screen.findByLabelText('지원 자기소개'), '가상 복사 내용')
  await user.click(screen.getByRole('button', { name: '현재 작성 내용 복사' }))
  await user.click(await screen.findByRole('button', { name: '복사 내용 전체 선택' }))
  const field = screen.getByLabelText('복사할 현재 작성 내용') as HTMLTextAreaElement
  expect(field).toHaveFocus(); expect(field.selectionStart).toBe(0); expect(field.selectionEnd).toBe(field.value.length)
  expect(screen.queryByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).not.toBeInTheDocument()
})

it('rejects substituted references, unsafe revisions and unrecognized review flags', () => {
  expect(parseJourneyDraft(empty(), reference, 1).revision).toBe(1)
  for (const changed of [{ opportunity: { ...reference, version: 2 } }, { profile_version: 2 }, { revision: 0 }, { review_reasons: ['approve_now'] }, { self_introduction: '가'.repeat(2001) }]) {
    expect(() => parseJourneyDraft({ ...empty(), ...changed }, reference, 1)).toThrow()
  }
})
