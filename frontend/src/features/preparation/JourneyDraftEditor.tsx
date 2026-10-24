import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { invalid, isOpportunityId } from '../public-opportunities/catalog'
import { parseProfileView } from '../profile/server-model'
import { parseSession } from '../account/session'
import { OfficialPreparation } from './OfficialPreparation'
import { parsePreparation } from './official'
import { parseJourneyDraft } from './draft-model'
import type { JourneyDraft } from './draft-model'

type Attempt = { key: string; body: components['schemas']['DraftCreate']; owner: string | null }
type Editor = { draft: JourneyDraft; introduction: string; motivation: string; dirty: boolean; reviewed: boolean; replace: boolean }
type Result = { draft: JourneyDraft; message: string }

export function JourneyDraftPreparationRoute() {
  const { journeyId = '', opportunityId = '' } = useParams()
  if (!isOpportunityId(journeyId) || !isOpportunityId(opportunityId)) return <StatusNotice kind="error" title="체험과 공고 주소를 확인해 주세요">프로필의 추천 화면에서 공고를 다시 선택해 주세요.</StatusNotice>
  return <><OfficialPreparation opportunityId={opportunityId} withDraft /><JourneyDraftEditor key={`${journeyId}:${opportunityId}`} journeyId={journeyId} opportunityId={opportunityId} /></>
}

export function JourneyDraftEditor({ journeyId, opportunityId }: { journeyId: string; opportunityId: string }) {
  const scope = useMemoryScope<Editor | null>(() => null)
  const attempt = useMemoryScope<Attempt | null>(() => null)
  const request = useRequest<Result>()
  const copy = useRequest<string>()
  const fallback = useRef<HTMLDivElement>(null)
  const editor = scope.value, busy = request.state.status === 'pending'
  const clear = scope.clear, clearAttempt = attempt.clear
  useEffect(() => {
    if (request.state.status === 'error' && ['SESSION_EXPIRED', 'UNAUTHENTICATED', 'NOT_FOUND', 'CONSENT_REQUIRED'].includes(request.state.error.code)) { clear(); clearAttempt() }
  }, [request.state, clear, clearAttempt])
  const accept = ({ draft }: Result) => {
    scope.setValue({ draft, introduction: draft.self_introduction, motivation: draft.motivation, dirty: false, reviewed: false, replace: false })
    clearAttempt()
  }
  const apply = (draft: JourneyDraft, message: string): Result => ({ draft, message })
  const create = (mode: 'manual' | 'generate', restart = false) => {
    if (busy || (editor && !editor.replace)) return
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
      return apply(draft, mode === 'manual' ? '직접 작성할 임시 초안을 만들었습니다. 아직 승인·회원 저장하지 않았습니다.' : '확정 사실에 근거한 미승인 초안입니다. 내용을 직접 확인하고 지원동기를 작성해 주세요.')
    }, accept)
  }
  const edit = (field: 'introduction' | 'motivation', value: string) => {
    if (!editor || busy) return
    request.clear(); copy.clear()
    scope.setValue({ ...editor, [field]: value, dirty: true, reviewed: false, replace: false })
  }
  const update = () => {
    if (!editor || busy || !editor.dirty) return
    void request.run(async (api, signal) => {
      const draft = parseJourneyDraft(required((await api.PATCH('/journeys/{journey_id}/drafts/{draft_id}', { signal,
        params: { path: { journey_id: journeyId, draft_id: editor.draft.draft_id } }, body: {
          base_revision: editor.draft.revision, self_introduction: editor.introduction, motivation: editor.motivation,
        },
      })).data), editor.draft.opportunity, editor.draft.profile_version)
      if (draft.draft_id !== editor.draft.draft_id || draft.revision !== editor.draft.revision + 1 || draft.approved_at !== null) return invalid()
      return apply(draft, '수정 내용을 서버 임시 초안에 반영했습니다. 다시 읽고 승인해 주세요.')
    }, accept)
  }
  const reload = () => {
    if (!editor || busy || (editor.dirty && !editor.replace)) return
    void request.run(async (api, signal) => {
      const draft = parseJourneyDraft(required((await api.GET('/journeys/{journey_id}/drafts/{draft_id}', { signal, params: { path: { journey_id: journeyId, draft_id: editor.draft.draft_id } } })).data), editor.draft.opportunity, editor.draft.profile_version)
      if (draft.draft_id !== editor.draft.draft_id) return invalid()
      return apply(draft, '현재 서버 편집본을 확인했습니다. 근거와 승인 상태를 확인해 주세요.')
    }, accept)
  }
  const approve = () => {
    if (!editor || busy || editor.dirty || !editor.reviewed || !editor.introduction.trim() || !editor.motivation.trim() || editor.draft.review_reasons.length) return
    void request.run(async (api, signal) => {
      const draft = parseJourneyDraft(required((await api.POST('/journeys/{journey_id}/drafts/{draft_id}/approve', { signal, params: { path: { journey_id: journeyId, draft_id: editor.draft.draft_id } }, body: { base_revision: editor.draft.revision } })).data), editor.draft.opportunity, editor.draft.profile_version)
      if (draft.draft_id !== editor.draft.draft_id || draft.revision !== editor.draft.revision + 1 || !draft.approved_at || draft.review_reasons.length) return invalid()
      return apply(draft, '서버에서 현재 본문의 승인을 확인했습니다. 회원 저장과 실제 신청은 별도입니다.')
    }, accept)
  }
  const approved = !!editor && !editor.dirty && !!editor.draft.approved_at && !editor.draft.review_reasons.length
  const canRestartAI = attempt.value?.body.mode === 'generate' && request.state.status === 'error'
    && ['MODEL_UNAVAILABLE', 'AI_TIMEOUT', 'REQUEST_ALREADY_COMPLETED'].includes(request.state.error.code)
  const body = editor ? `자기소개\n${editor.introduction}\n\n지원동기\n${editor.motivation}` : ''
  return <section className="reading-width" aria-label="확정 경험으로 신청 준비"><h2>내 경험으로 지원 내용을 준비해요</h2>
    <p>AI 초안은 확정한 사실만 사용합니다. 지원동기는 직접 작성하고, 수정·승인·회원 저장을 따로 선택합니다.</p>
    {editor && <CheckboxField label="현재 화면 내용을 새 초안이나 서버 편집본으로 바꾸는 것을 확인했어요." checked={editor.replace} disabled={busy} onChange={event => scope.setValue({ ...editor, replace: event.target.checked })} />}
    <div className="actions"><Button pending={busy} disabled={!!editor && !editor.replace} onClick={() => create('generate')}>AI 초안 생성 · 같은 요청 재확인</Button><Button pending={busy} disabled={!!editor && !editor.replace} onClick={() => create('manual')}>AI 없이 빈 초안 직접 작성</Button>
      {canRestartAI && <Button disabled={!!editor && !editor.replace} onClick={() => create('generate', true)}>AI 실패 후 새 요청으로 다시 생성</Button>}
      {busy && <Button variant="secondary" onClick={request.clear}>기다리기 중지</Button>}</div>
    {editor && <section className="panel"><h3>프로필 {editor.draft.profile_version}번 · 공고 {editor.draft.opportunity.version}번 기준</h3>
      {editor.draft.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
      {!!editor.draft.review_reasons.length && <StatusNotice title="근거를 다시 확인해 주세요">프로필이나 공고가 바뀌었습니다. 본문은 자동으로 바꾸지 않습니다. 현재 내용을 복사한 뒤 새 근거로 초안을 만들고 승인해 주세요.</StatusNotice>}
      <fieldset disabled={busy}><TextAreaField label="지원 자기소개" value={editor.introduction} maxLength={2000} rows={6} onChange={event => edit('introduction', event.target.value)} />
        <TextAreaField label="지원 동기" value={editor.motivation} maxLength={2000} rows={6} onChange={event => edit('motivation', event.target.value)} />
        <CheckboxField label="두 항목을 읽고 확정 경험과 공고에 맞는 내용임을 확인했어요." checked={editor.reviewed} onChange={event => scope.setValue({ ...editor, reviewed: event.target.checked })} /></fieldset>
      <div className="actions"><Button pending={busy} disabled={!editor.dirty} onClick={update}>수정 내용을 임시 초안에 반영</Button>
        <Button pending={busy} disabled={editor.dirty || !editor.reviewed || !editor.introduction.trim() || !editor.motivation.trim() || approved || !!editor.draft.review_reasons.length} onClick={approve}>확인한 현재 본문 승인</Button>
        <Button variant="secondary" disabled={busy || (editor.dirty && !editor.replace)} onClick={reload}>서버의 현재 편집본 확인</Button></div>
      <p role="status">{approved ? '서버 승인 상태입니다. 회원 저장은 아직 별도입니다.' : '화면 내용을 수정했거나 아직 현재 본문을 승인하지 않았습니다.'}</p>
      {approved && <Link className="button primary" to={`/journeys/${journeyId}/drafts/${editor.draft.draft_id}/save`}>프로필과 지원서 회원 저장 선택</Link>}
      <div ref={fallback}><TextAreaField label="복사할 현재 작성 내용" value={body} readOnly rows={6} /></div>
      <Button variant="secondary" pending={copy.state.status === 'pending'} onClick={() => void copy.run(async () => {
        if (!navigator.clipboard?.writeText) throw new ApiError('INVALID_TARGET')
        await navigator.clipboard.writeText(body); return '현재 작성 내용을 복사했습니다. 회원 저장이나 신청 완료를 뜻하지 않습니다.'
      })}>현재 작성 내용 복사</Button>
      {copy.state.status === 'error' && <StatusNotice kind="error" title="자동 복사를 완료하지 못했어요" actions={<Button variant="secondary" onClick={() => { const field = fallback.current?.querySelector('textarea'); field?.focus(); field?.select() }}>복사 내용 전체 선택</Button>}>내용을 직접 선택해 기기의 복사 기능을 사용해 주세요.</StatusNotice>}
      {copy.state.status === 'success' && <p role="status">{copy.state.data}</p>}
      <p>미승인 본문과 준비 체크는 회원 저장하지 않습니다. 화면을 나가면 화면 입력은 지워지며, 서버 임시 초안은 체험 수명을 따릅니다. 이미 복사한 내용은 클립보드에 남을 수 있습니다.</p>
    </section>}
    {request.state.status === 'error' && <><RequestError error={request.state.error} /><p>AI 실패 시 직접 작성을 선택할 수 있습니다. 응답 유실은 같은 생성 요청으로 재확인하고, 수정·승인 결과는 서버 편집본에서 확인해 주세요. 충돌 시 입력을 자동으로 덮어쓰지 않습니다.</p></>}
    {request.state.status === 'success' && <p role="status">{request.state.data.message}</p>}
  </section>
}
