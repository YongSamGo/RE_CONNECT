import { useEffect } from 'react'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { invalid, isOpportunityId, record, text } from '../public-opportunities/catalog'
import { parseSession } from './session'

const integer = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value < 2 ** 31 ? value : invalid()
const uuid = (value: unknown) => typeof value === 'string' && isOpportunityId(value) ? value : invalid()
function parseDraft(value: unknown) {
  const item = record(value)
  if (item.mode !== 'from_saved' || !Array.isArray(item.warnings) || !Array.isArray(item.review_reasons)
    || typeof item.self_introduction !== 'string' || [...item.self_introduction].length > 2000
    || typeof item.motivation !== 'string' || [...item.motivation].length > 2000
    || (item.approved_at !== null && (typeof item.approved_at !== 'string' || !Number.isFinite(Date.parse(item.approved_at))))) return invalid()
  return { id: uuid(item.draft_id), revision: integer(item.revision), introduction: item.self_introduction,
    motivation: item.motivation, approved: item.approved_at !== null, review: item.review_reasons.length > 0,
    warnings: item.warnings.map(value => text(value, 300)) }
}
type Draft = ReturnType<typeof parseDraft>
type Editor = { journey: string; draft: Draft; introduction: string; motivation: string; dirty: boolean; base: number; saveKey: string; saved: boolean }

export function SavedDraftEditor({ documentId, version, opportunityId, onUnavailable }: { documentId: string; version: number; opportunityId: string; onUnavailable?: () => void }) {
  const scope = useMemoryScope<Editor | null>(() => null)
  const request = useRequest<Editor | string>()
  const clearEditor = scope.clear
  const editor = scope.value, pending = request.state.status === 'pending'
  useEffect(() => {
    if (request.state.status === 'error' && ['UNAUTHENTICATED', 'SESSION_EXPIRED', 'NOT_FOUND'].includes(request.state.error.code)) {
      clearEditor(); onUnavailable?.()
    }
  }, [request.state, clearEditor, onUnavailable])
  const start = () => request.run(async (api, signal) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated) throw new ApiError('UNAUTHENTICATED', 401)
    const notice = me.consents.find(item => item.purpose === 'ai_processing')?.notice_version
    if (!notice) throw new ApiError('CONSENT_REQUIRED', 403)
    const saved = record(record(required((await api.GET('/profiles/me', { signal })).data)).saved)
    const opportunity = record(required((await api.GET('/opportunities/{opportunity_id}', { signal, params: { path: { opportunity_id: opportunityId } } })).data))
    if (uuid(opportunity.id) !== opportunityId) return invalid()
    const journey = record(required((await api.POST('/journeys', { signal, params: { header: { 'Idempotency-Key': crypto.randomUUID() } }, body: {
      ai_notice_version: notice, saved_profile: { profile_id: uuid(saved.profile_id), version: integer(saved.version) },
    } })).data))
    const journeyId = uuid(journey.journey_id)
    if (integer(record(journey.confirmed).version) !== 1) return invalid()
    const draft = parseDraft(required((await api.POST('/journeys/{journey_id}/drafts', { signal,
      params: { path: { journey_id: journeyId }, header: { 'Idempotency-Key': crypto.randomUUID() } }, body: {
        profile_version: 1, opportunity: { id: opportunityId, version: integer(opportunity.version) }, mode: 'from_saved',
        saved_document: { document_id: documentId, version },
      } })).data))
    if (draft.approved || draft.revision !== 1) return invalid()
    return { journey: journeyId, draft, introduction: draft.introduction, motivation: draft.motivation,
      dirty: false, base: version, saveKey: crypto.randomUUID(), saved: false } satisfies Editor
  }, value => { if (typeof value !== 'string') scope.setValue(value) })
  function edit(field: 'introduction' | 'motivation', value: string) {
    if (!editor || pending) return
    request.clear()
    scope.setValue({ ...editor, [field]: value, dirty: true, saved: false, saveKey: crypto.randomUUID() })
  }
  const update = () => {
    if (!editor || pending || !editor.dirty) return
    void request.run(async (api, signal) => {
      const draft = parseDraft(required((await api.PATCH('/journeys/{journey_id}/drafts/{draft_id}', {
        signal, params: { path: { journey_id: editor.journey, draft_id: editor.draft.id } }, body: {
          base_revision: editor.draft.revision, self_introduction: editor.introduction, motivation: editor.motivation,
        },
      })).data))
      if (draft.id !== editor.draft.id || draft.approved) return invalid()
      return { ...editor, draft, dirty: false, saved: false, saveKey: crypto.randomUUID() }
    }, value => { if (typeof value !== 'string') scope.setValue(value) })
  }
  const approve = () => {
    if (!editor || pending || editor.dirty) return
    void request.run(async (api, signal) => {
      const path = { journey_id: editor.journey, draft_id: editor.draft.id }
      const draft = parseDraft(required((await api.POST('/journeys/{journey_id}/drafts/{draft_id}/approve', {
        signal, params: { path }, body: { base_revision: editor.draft.revision },
      })).data))
      if (draft.id !== editor.draft.id || !draft.approved || draft.review) return invalid()
      return { ...editor, draft, dirty: false, saveKey: crypto.randomUUID(), saved: false } satisfies Editor
    }, value => { if (typeof value !== 'string') scope.setValue(value) })
  }
  const save = () => {
    if (!editor || editor.dirty || !editor.draft.approved || editor.saved || pending) return
    void request.run(async (api, signal) => {
      const result = record(required((await api.POST('/drafts', { signal, params: { header: { 'Idempotency-Key': editor.saveKey } }, body: {
        source: { type: 'journey', journey_id: editor.journey, draft_id: editor.draft.id, revision: editor.draft.revision },
        document_id: documentId, base_document_version: editor.base,
      } })).data))
      if (uuid(result.document_id) !== documentId) return invalid()
      return { ...editor, base: integer(result.version), saved: true }
    }, value => { if (typeof value !== 'string') scope.setValue(value) })
  }
  return <section className="panel"><h3>새 내용으로 편집</h3>
    <p><a href={`/opportunities/${opportunityId}`} target="_blank" rel="noopener noreferrer">현재 공고 조건을 새 창에서 확인</a></p>
    {!editor ? <><p>현재 저장 프로필과 공개 공고를 확인해 새 임시 편집본을 만듭니다.</p><Button pending={pending} onClick={() => void start()}>저장본으로 새 임시 편집 시작</Button></> : <>
      <p>수정 중 자동 저장하지 않습니다. 다시 승인하고 저장하기 전에는 기존 저장본을 유지합니다.</p>
      {editor.draft.warnings.map((warning, index) => <p key={index}>{warning}</p>)}
      <fieldset disabled={pending}><TextAreaField label="재편집 자기소개" value={editor.introduction} maxLength={2000} rows={6} onChange={event => edit('introduction', event.target.value)} />
        <TextAreaField label="재편집 지원동기" value={editor.motivation} maxLength={2000} rows={6} onChange={event => edit('motivation', event.target.value)} /></fieldset>
      <Button pending={pending} disabled={!editor.dirty} onClick={update}>수정 내용을 임시 초안에 반영</Button>
      <Button pending={pending} disabled={editor.dirty || !editor.introduction.trim() || !editor.motivation.trim() || editor.draft.approved} onClick={approve}>내용을 읽고 현재 근거에 맞게 재승인</Button>
      <Button pending={pending} disabled={editor.dirty || !editor.draft.approved || editor.saved} onClick={save}>재승인한 지원서 저장 · 실패 시 재시도</Button>
      <Button variant="secondary" disabled={pending} onClick={() => void request.run(async () => {
        if (!navigator.clipboard?.writeText) throw new ApiError('INVALID_TARGET')
        await navigator.clipboard.writeText(`자기소개\n${editor.introduction}\n\n지원동기\n${editor.motivation}`)
        return '편집 내용을 복사했습니다.'
      })}>편집 내용 복사</Button>
      <p role="status">{editor.saved ? `지원서 ${editor.base}번을 저장했습니다.` : editor.dirty || !editor.draft.approved ? '재승인 전입니다.' : '재승인했습니다. 회원 저장은 별도 버튼으로 진행해 주세요.'}</p>
    </>}
    {request.state.status === 'error' && <><RequestError error={request.state.error} /><p>실패하면 저장 여부를 확인하고 다시 시도해 주세요. 남아 있는 편집 내용은 복사할 수 있습니다. 버전 충돌이면 저장 자료를 다시 불러오세요.</p></>}
    {request.state.status === 'success' && request.state.data === '편집 내용을 복사했습니다.' && <p role="status">{request.state.data}</p>}
  </section>
}
