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
function server(options: { loseFirst?: boolean; conflict?: boolean; aiFailure?: boolean; consent?: boolean; loseApproval?: boolean; changedApproval?: boolean; reviewReasons?: string[]; invalid?: boolean } = {}) {
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
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const rendered = render(<MemoryRouter><JourneyDraftEditor journeyId={journeyId} opportunityId={opportunityId} /></MemoryRouter>)
  return { ...rendered, user: userEvent.setup() }
}
const manual = () => screen.getByRole('button', { name: 'AI 없이 빈 초안 직접 작성' })
const approve = () => screen.getByRole('button', { name: '확인한 현재 본문 승인' })
const review = () => screen.getByRole('checkbox', { name: '두 항목을 읽고 확정 경험과 공고에 맞는 내용임을 확인했어요.' })
async function writeAndUpdate(user: ReturnType<typeof userEvent.setup>) {
  await user.click(manual())
  await user.type(await screen.findByLabelText('지원 자기소개'), '가상 경험')
  await user.type(screen.getByLabelText('지원 동기'), '가상 지원동기')
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  await screen.findByText('수정 내용을 서버 임시 초안에 반영했습니다. 다시 읽고 승인해 주세요.')
}
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
  await user.click(manual()); await screen.findByText(/생성 요청의 응답을 받지 못했다면/)
  await user.click(manual()); await screen.findByLabelText('지원 자기소개')
  const posts = () => fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST')
  expect(posts()).toHaveLength(2)
  expect(posts()[0].headers.get('Idempotency-Key')).toBe(posts()[1].headers.get('Idempotency-Key'))
  expect(await posts()[0].clone().json()).toEqual(await posts()[1].clone().json())
  expect(manual()).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: '현재 화면 내용을 새 초안이나 서버 편집본으로 바꾸는 것을 확인했어요.' }))
  await user.click(manual()); await screen.findByText('직접 작성할 임시 초안을 만들었어요. 아직 내용을 승인하거나 회원 자료로 저장하지 않았어요.')
  expect(posts()).toHaveLength(3)
  expect(posts()[2].headers.get('Idempotency-Key')).not.toBe(posts()[1].headers.get('Idempotency-Key'))
})

it('preserves local text on revision conflict and requires explicit replacement before reload', async () => {
  const fetch = server({ conflict: true }), { user } = mount()
  await user.click(manual()); await user.type(await screen.findByLabelText('지원 자기소개'), '사라지면 안 되는 임시 입력')
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  await screen.findByText(/생성 요청의 응답을 받지 못했다면/)
  expect(screen.getByLabelText('지원 자기소개')).toHaveValue('사라지면 안 되는 임시 입력')
  expect(screen.getByRole('button', { name: '서버의 현재 편집본 확인' })).toBeDisabled()
  expect(fetch.mock.calls.some(([request]) => request.url.endsWith('/approve'))).toBe(false)
})

it('offers manual entry after AI failure without automatically sending another creation', async () => {
  const fetch = server({ aiFailure: true }), { user } = mount()
  await user.click(screen.getByRole('button', { name: 'AI 초안 만들기' }))
  await screen.findByText(/생성 요청의 응답을 받지 못했다면/)
  expect(fetch.mock.calls.filter(([request]) => request.method === 'POST')).toHaveLength(1)
  await user.click(manual()); expect(await screen.findByLabelText('지원 자기소개')).toHaveValue('')
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByLabelText('지원 자기소개')).not.toBeInTheDocument()
})

it('explains a generation refused for lack of usable facts without offering a pointless retry', async () => {
  const fetch = server({ invalid: true }), { user } = mount()
  const generations = () => fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST' && request.url.endsWith('/drafts'))
  await user.click(manual()); await screen.findByLabelText('지원 자기소개')
  await user.click(screen.getByRole('checkbox', { name: '현재 화면 내용을 새 초안이나 서버 편집본으로 바꾸는 것을 확인했어요.' }))
  const generate = () => screen.getByRole('button', { name: 'AI 초안 생성 · 같은 요청 재확인' })
  await user.click(generate())
  expect(await screen.findByText('AI 초안을 만들지 못했어요')).toBeInTheDocument()
  // 안내는 하나만 보인다. 같은 요청을 다시 보내라는 일반 오류 문단은 숨긴다.
  expect(screen.queryByText(/AI 실패 시 직접 작성을 선택할 수 있습니다/)).not.toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'AI 실패 후 새 요청으로 다시 생성' })).not.toBeInTheDocument()
  // 확정된 422 뒤에 다시 누르면 옛 키를 재전송하지 않고 새 키로 보낸다.
  await user.click(generate())
  await vi.waitFor(() => expect(generations()).toHaveLength(3))
  const [, first, second] = generations()
  expect(second.headers.get('Idempotency-Key')).not.toBe(first.headers.get('Idempotency-Key'))
  expect(await screen.findByText('AI 초안을 만들지 못했어요')).toBeInTheDocument()
  expect(screen.queryByRole('button', { name: 'AI 실패 후 새 요청으로 다시 생성' })).not.toBeInTheDocument()
  // 기존 편집기는 남고, 편집 저장의 422는 생성 실패 안내로 보이지 않는다.
  await user.type(screen.getByLabelText('지원 자기소개'), '사라지면 안 되는 입력')
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  await screen.findByText(/AI 실패 시 직접 작성을 선택할 수 있습니다/)
  expect(screen.getByLabelText('지원 자기소개')).toHaveValue('사라지면 안 되는 입력')
  expect(screen.queryByText('AI 초안을 만들지 못했어요')).not.toBeInTheDocument()
})

it('starts a new AI key only after an explicit retry of a confirmed model failure', async () => {
  const fetch = server({ aiFailure: true }), { user } = mount()
  await user.click(screen.getByRole('button', { name: 'AI 초안 만들기' }))
  const retry = await screen.findByRole('button', { name: 'AI 실패 후 새 요청으로 다시 생성' })
  const posts = () => fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST')
  expect(posts()).toHaveLength(1)
  await user.click(retry); await screen.findByLabelText('지원 자기소개')
  expect(posts()).toHaveLength(2)
  expect(posts()[1].headers.get('Idempotency-Key')).not.toBe(posts()[0].headers.get('Idempotency-Key'))
  expect((await posts()[1].clone().json()).mode).toBe('generate')
})

it('keeps the original AI key on network uncertainty and does not offer a fresh inference request', async () => {
  const fetch = server({ loseFirst: true }), { user } = mount()
  const generate = () => screen.getByRole('button', { name: 'AI 초안 만들기' })
  await user.click(generate()); await screen.findByText(/생성 요청의 응답을 받지 못했다면/)
  expect(screen.queryByRole('button', { name: 'AI 실패 후 새 요청으로 다시 생성' })).not.toBeInTheDocument()
  await user.click(generate()); await screen.findByLabelText('지원 자기소개')
  const posts = fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST')
  expect(posts).toHaveLength(2)
  expect(posts[1].headers.get('Idempotency-Key')).toBe(posts[0].headers.get('Idempotency-Key'))
  expect(await posts[1].clone().json()).toEqual(await posts[0].clone().json())
})

it('blocks AI generation without processing consent while allowing explicit manual entry', async () => {
  const fetch = server({ consent: false }), { user } = mount()
  await user.click(screen.getByRole('button', { name: 'AI 초안 만들기' })); await screen.findByText(/생성 요청의 응답을 받지 못했다면/)
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
  expect(screen.queryByText('직접 작성할 임시 초안을 만들었어요. 아직 내용을 승인하거나 회원 자료로 저장하지 않았어요.')).not.toBeInTheDocument()
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

it('recovers a lost approval reply by reading current state without submitting approval again', async () => {
  const fetch = server({ loseApproval: true }), { user } = mount()
  await writeAndUpdate(user); await user.click(review()); await user.click(approve())
  await screen.findByText(/생성 요청의 응답을 받지 못했다면/)
  expect(screen.queryByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '서버의 현재 편집본 확인' }))
  expect(await screen.findByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).toBeVisible()
  expect(fetch.mock.calls.filter(([request]) => request.url.endsWith('/approve'))).toHaveLength(1)
  expect(screen.getByLabelText('지원 동기')).toHaveValue('가상 지원동기')
})

it('does not present changed approval content as the confirmed draft', async () => {
  server({ changedApproval: true })
  const { user } = mount()
  await writeAndUpdate(user); await user.click(review()); await user.click(approve())
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByText(/AI로 만들지 못하면/)).not.toBeInTheDocument()
  expect(screen.getByLabelText('지원 자기소개')).toHaveValue('가상 경험')
  expect(screen.queryByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).not.toBeInTheDocument()
})

it.each(['profile_changed', 'opportunity_changed', 'opportunity_closed'])('blocks approval and member-save on reloaded %s without rewriting the old text', async reason => {
  const fetch = server({ reviewReasons: [reason] }), { user } = mount()
  await writeAndUpdate(user); await user.click(review()); await user.click(approve())
  await screen.findByRole('link', { name: '프로필과 지원서 회원 저장 선택' })
  await user.click(screen.getByRole('button', { name: '서버의 현재 편집본 확인' }))
  expect(await screen.findByRole('heading', { name: '근거를 다시 확인해 주세요' })).toBeVisible()
  expect(screen.getByLabelText('지원 자기소개')).toHaveValue('가상 경험')
  expect(screen.getByLabelText('지원 동기')).toHaveValue('가상 지원동기')
  expect(screen.queryByRole('link', { name: '프로필과 지원서 회원 저장 선택' })).not.toBeInTheDocument()
  await user.click(review()); expect(approve()).toBeDisabled()
  expect(manual()).toBeDisabled()
  expect(fetch.mock.calls.filter(([request]) => request.url.endsWith('/approve'))).toHaveLength(1)
})

it('rejects substituted references, unsafe revisions and unrecognized review flags', () => {
  expect(parseJourneyDraft(empty(), reference, 1).revision).toBe(1)
  for (const changed of [{ opportunity: { ...reference, version: 2 } }, { profile_version: 2 }, { revision: 0 }, { review_reasons: ['approve_now'] }, { self_introduction: '가'.repeat(2001) }]) {
    expect(() => parseJourneyDraft({ ...empty(), ...changed }, reference, 1)).toThrow()
  }
})
