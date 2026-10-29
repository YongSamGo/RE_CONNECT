import { UnsavedChangesGuard } from '../../ui/UnsavedChangesGuard'
import { useEntryAction } from '../../state/useEntryAction'
import { useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { UnavailablePage } from '../../ui/UnavailablePage'
import { invalid, isOpportunityId } from '../public-opportunities/catalog'
import { officialLink } from '../public-opportunities/detail'
import { parseProfileView } from '../profile/server-model'
import { parseSession } from '../account/session'
import { OfficialPreparation } from './OfficialPreparation'
import { parsePreparation } from './official'
import { parseJourneyDraft } from './draft-model'
import type { JourneyDraft } from './draft-model'

type Attempt = { key: string; body: components['schemas']['DraftCreate']; owner: string | null }
type Editor = { draft: JourneyDraft; introduction: string; motivation: string; dirty: boolean; reviewed: boolean }
type Result = { draft: JourneyDraft; message: string }

export function JourneyDraftApplicationRoute() {
  const { journeyId = '', opportunityId = '' } = useParams()
  const location = useLocation()
  const navigate = useNavigate()
  const autoGenerate = location.state?.generateDraft === true
  if (!isOpportunityId(journeyId) || !isOpportunityId(opportunityId)) return <UnavailablePage title="체험과 공고 주소를 확인해 주세요">프로필의 추천 화면에서 공고를 다시 선택해 주세요.</UnavailablePage>
  return <OfficialPreparation opportunityId={opportunityId} withDraft>{applicationUrl => <JourneyDraftEditor key={`${journeyId}:${opportunityId}`} journeyId={journeyId} opportunityId={opportunityId} applicationUrl={applicationUrl} autoGenerate={autoGenerate} onAutoStart={() => navigate(location.pathname, { replace: true, state: null })} />}</OfficialPreparation>
}

export const JourneyDraftPreparationRoute = JourneyDraftApplicationRoute

export function JourneyDraftEditor({ journeyId, opportunityId, applicationUrl = '', autoGenerate = false, onAutoStart }: { journeyId: string; opportunityId: string; applicationUrl?: string; autoGenerate?: boolean; onAutoStart?: () => void }) {
  const scope = useMemoryScope<Editor | null>(() => null)
  const attempt = useMemoryScope<Attempt | null>(() => null)
  const request = useRequest<Result>()
  const reviewDialog = useRef<HTMLDialogElement>(null)
  const reviewTrigger = useRef<HTMLButtonElement>(null)
  // 마지막 요청이 AI 생성이었는지. 편집, 승인의 422와 구분해 생성 실패 안내만 보인다.
  const [generating, setGenerating] = useState(false)
  const editor = scope.value, busy = request.state.status === 'pending'
  const officialApplication = officialLink(applicationUrl)
  const clear = scope.clear, clearAttempt = attempt.clear
  useEffect(() => {
    if (request.state.status === 'error' && ['SESSION_EXPIRED', 'UNAUTHENTICATED', 'NOT_FOUND', 'CONSENT_REQUIRED'].includes(request.state.error.code)) { clear(); clearAttempt() }
    // 생성 요청의 422는 확정된 실패다. 같은 키 재전송(409)으로 이어지지 않게 키를 버린다. 다음 생성은 최신 프로필로 새 키를 만든다.
    else if (generating && request.state.status === 'error' && request.state.error.code === 'VALIDATION_FAILED') clearAttempt()
  }, [request.state, generating, clear, clearAttempt])
  const accept = ({ draft }: Result) => {
    scope.setValue({ draft, introduction: draft.self_introduction, motivation: draft.motivation, dirty: false, reviewed: false })
    clearAttempt()
  }
  const apply = (draft: JourneyDraft, message: string): Result => ({ draft, message })
  const create = (mode: 'manual' | 'generate', restart = false) => {
    if (busy) return
    setGenerating(mode === 'generate')
    void request.run(async (api, signal) => {
      const me = parseSession(required((await api.GET('/me', { signal })).data))
      if (mode === 'generate' && !me.consents.some(value => value.purpose === 'ai_processing')) throw new ApiError('CONSENT_REQUIRED', 403)
      let pending = restart ? null : attempt.value
      if (!pending || pending.body.mode !== mode) {
        const view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { signal, params: { path: { journey_id: journeyId } } })).data))
        if (!view.confirmed || view.has_unconfirmed_changes) throw new ApiError('PROFILE_NOT_CONFIRMED', 409)
        const preparation = parsePreparation(required((await api.GET('/opportunities/{opportunity_id}/preparation', { signal, params: { path: { opportunity_id: opportunityId } } })).data), opportunityId)
        if (preparation.recruitment_status !== 'open' || preparation.change_pending) throw new ApiError('OPPORTUNITY_NOT_AVAILABLE', 409)
        pending = { key: crypto.randomUUID(), owner: me.user?.id ?? null, body: { profile_version: view.confirmed.version, opportunity: preparation.opportunity, mode, saved_document: null } }
        if (signal.aborted) throw new ApiError('CANCELLED')
        attempt.setValue(pending)
      }
      if ((me.user?.id ?? null) !== pending.owner) throw new ApiError('SESSION_EXPIRED', 401)
      const draft = parseJourneyDraft(required((await api.POST('/journeys/{journey_id}/drafts', { signal,
        params: { path: { journey_id: journeyId }, header: { 'Idempotency-Key': pending.key } }, body: pending.body,
      })).data), pending.body.opportunity, pending.body.profile_version)
      if (draft.mode !== mode || draft.approved_at !== null || draft.review_reasons.length) return invalid()
      return apply(draft, mode === 'manual' ? '직접 작성할 수 있어요.' : 'AI가 만든 초안을 읽고 내 경험과 지원 의사에 맞게 고쳐 주세요.')
    }, accept)
  }
  useEntryAction(() => { create('generate'); onAutoStart?.() }, autoGenerate, opportunityId)
  const edit = (field: 'introduction' | 'motivation', value: string) => {
    if (!editor || busy) return
    request.clear()
    scope.setValue({ ...editor, [field]: value, dirty: true, reviewed: false })
  }
  const update = (review = false) => {
    if (!editor || busy || !editor.dirty) return
    setGenerating(false)
    void request.run(async (api, signal) => {
      const draft = parseJourneyDraft(required((await api.PATCH('/journeys/{journey_id}/drafts/{draft_id}', { signal,
        params: { path: { journey_id: journeyId, draft_id: editor.draft.draft_id } }, body: {
          base_revision: editor.draft.revision, self_introduction: editor.introduction, motivation: editor.motivation,
        },
      })).data), editor.draft.opportunity, editor.draft.profile_version)
      if (draft.draft_id !== editor.draft.draft_id || draft.revision !== editor.draft.revision + 1 || draft.approved_at !== null) return invalid()
      return apply(draft, '수정 내용을 서버 임시 초안에 반영했습니다. 다시 읽고 승인해 주세요.')
    }, result => { accept(result); if (review) reviewDialog.current?.showModal() })
  }
  const approve = () => {
    if (!editor || busy || editor.dirty || !editor.reviewed || !editor.introduction.trim() || !editor.motivation.trim() || editor.draft.review_reasons.length) return
    setGenerating(false)
    void request.run(async (api, signal) => {
      const draft = parseJourneyDraft(required((await api.POST('/journeys/{journey_id}/drafts/{draft_id}/approve', { signal, params: { path: { journey_id: journeyId, draft_id: editor.draft.draft_id } }, body: { base_revision: editor.draft.revision } })).data), editor.draft.opportunity, editor.draft.profile_version)
      if (draft.draft_id !== editor.draft.draft_id || draft.revision !== editor.draft.revision + 1 || !draft.approved_at || draft.review_reasons.length || draft.self_introduction !== editor.introduction || draft.motivation !== editor.motivation) return invalid()
      return apply(draft, '서버에서 현재 지원서 본문의 승인을 확인했습니다. 아래 공식 신청 안내를 따라 제출해 주세요.')
    }, result => { accept(result); reviewDialog.current?.close() })
  }
  const approved = !!editor && !editor.dirty && !!editor.draft.approved_at && !editor.draft.review_reasons.length
  const canRestartAI = attempt.value?.body.mode === 'generate' && request.state.status === 'error'
    && ['MODEL_UNAVAILABLE', 'AI_TIMEOUT', 'REQUEST_ALREADY_COMPLETED'].includes(request.state.error.code)
  // 서버는 AI에 보낼 수 있는 확정 사실이 없으면 모델을 부르지 않고 422로 거절한다. 다시 생성해도 같으므로 직접 작성을 안내한다.
  const noUsableFacts = generating && request.state.status === 'error' && request.state.error.code === 'VALIDATION_FAILED'
  const generationControls = <>
    <div className="actions"><Button pending={busy} onClick={() => create('generate')}>AI 초안 만들기</Button><Button pending={busy} onClick={() => create('manual')}>AI 없이 빈 초안 직접 작성</Button>
      {canRestartAI && <Button onClick={() => create('generate', true)}>AI 실패 후 새 요청으로 다시 생성</Button>}
      {busy && <Button variant="secondary" onClick={request.clear}>기다리기 중지</Button>}</div>
  </>
  return <section className="journey-draft-editor preparation-writing" aria-label="지원서 작성"><UnsavedChangesGuard dirty={!!editor?.dirty} />
    {!editor && generationControls}
    {editor && <section className="draft-workspace">
      {!!editor.draft.review_reasons.length && <StatusNotice title="지원 내용을 다시 확인해 주세요">프로필이나 공고가 변경되어 기존 내용을 승인할 수 없습니다. 공고 상세에서 지원서를 다시 열어 주세요.</StatusNotice>}
      <fieldset className="draft-fields" disabled={busy}><TextAreaField label="지원 자기소개" value={editor.introduction} maxLength={2000} rows={5} onChange={event => edit('introduction', event.target.value)} />
        <TextAreaField label="지원 동기" value={editor.motivation} maxLength={2000} rows={5} onChange={event => edit('motivation', event.target.value)} /></fieldset>
      <div className="actions"><Button ref={reviewTrigger} pending={busy} disabled={approved || !editor.introduction.trim() || !editor.motivation.trim() || !!editor.draft.review_reasons.length} onClick={() => { if (editor.dirty) update(true); else reviewDialog.current?.showModal() }}>{editor.dirty ? '수정하고 검토하기' : '지원 내용 검토하기'}</Button>
        {officialApplication ? <a className="button secondary" href={officialApplication.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" aria-label="공식 신청처로 이동, 새 창에서 열림">공식 신청처로 이동</a> : <Button variant="secondary" disabled>공식 신청처로 이동</Button>}
      </div>
      <dialog ref={reviewDialog} className="draft-review-dialog" aria-labelledby="draft-review-title" onClose={() => reviewTrigger.current?.focus()}>
        <h2 id="draft-review-title">지원 내용을 확인해 주세요</h2>
        <h3>자기소개</h3><p className="user-text">{editor.introduction}</p><h3>지원 동기</h3><p className="user-text">{editor.motivation}</p>
        <CheckboxField label="두 항목을 읽고 확정 경험과 공고에 맞는 내용임을 확인했어요." checked={editor.reviewed} onChange={event => scope.setValue({ ...editor, reviewed: event.target.checked })} />
        <div className="actions"><Button pending={busy} disabled={editor.dirty || !editor.reviewed || approved || !!editor.draft.review_reasons.length} onClick={approve}>확인한 현재 본문 승인</Button><Button variant="secondary" disabled={busy} onClick={() => reviewDialog.current?.close()}>계속 수정하기</Button></div>
      </dialog>
      {approved && <p role="status">확인한 내용을 승인했어요. 공식 신청처로 이동해 제출해 주세요.</p>}
    </section>}
    {noUsableFacts && <StatusNotice title="AI 초안을 만들지 못했어요">확정 프로필에 AI에 보낼 수 있는 경험, 역량이 없을 수 있어요. 연락처, 건강, 가족 사정이 담긴 문장은 AI에 보내지 않습니다. 직접 작성하거나 프로필을 확인해 주세요.</StatusNotice>}
    {request.state.status === 'error' && !noUsableFacts && <><RequestError error={request.state.error} /><p>생성 요청의 응답을 받지 못했다면 같은 요청으로 다시 확인해 주세요. 수정과 승인 결과는 서버 편집본에서 확인해 주세요. 충돌이 생겨도 입력을 자동으로 덮어쓰지 않아요.</p></>}
    {request.state.status === 'success' && !editor && <p role="status">{request.state.data.message}</p>}
  </section>
}
