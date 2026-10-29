import { useEntryAction } from '../../state/useEntryAction'
import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { createApiClient, csrfToken } from '../../api/client'
import { useMemoryScope } from '../../state/useMemoryScope'
import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { invalid, isOpportunityId, record, text } from '../public-opportunities/catalog'
import { parseSession } from './session'
import { SavedDraftEditor } from './SavedDraftEditor'
import { ServicePage } from '../../ui/ServicePage'

type Material = { id: string; title: string; version: number }
type ImportAttempt = { owner: string; profileId: string; profileVersion: number; notice: string; csrf: string; key: string; body: { ai_notice_version: string; saved_profile: { profile_id: string; version: number } } }
type Saved = { owner: string; experiences: string[] | null; profile?: { id: string; version: number }; documents: Material[]; page: number; total: number; message?: string; selected?: { id: string; version: number; opportunityId: string; title: string; introduction: string; motivation: string; review: boolean } }
type Api = ReturnType<typeof createApiClient>
function version(value: unknown): number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 ? value : invalid() }
function parseList(value: unknown): Pick<Saved, 'documents' | 'page' | 'total'> {
  const data = record(value)
  if (!Array.isArray(data.items) || typeof data.total !== 'number' || !Number.isSafeInteger(data.total) || data.total < 0) return invalid()
  return { page: version(data.page), total: data.total, documents: data.items.map((item) => {
    const document = record(item)
    const id = text(document.document_id, 36)
    if (!isOpportunityId(id)) return invalid()
    return { id, title: text(document.opportunity_title, 200), version: version(document.version) }
  }) }
}

export function SavedMaterials({ onSessionReset, view = 'all', embedded = false, showEmptyAction = true, actionOnly = false, resumeLabel = '이 경험으로 다시 시작' }: { onSessionReset?: () => void; view?: 'all' | 'profile' | 'drafts'; embedded?: boolean; showEmptyAction?: boolean; actionOnly?: boolean; resumeLabel?: string } = {}) {
  const navigate = useNavigate()
  const request = useRequest<Saved>()
  const importRequest = useRequest<string>()
  const importScope = useMemoryScope<ImportAttempt | null>(() => null)
  const importOutcomeUnknown = useMemoryScope(() => false)
  const [confirmed, setConfirmed] = useState(false)
  const [documentConfirmed, setDocumentConfirmed] = useState(false)
  const state = request.state
  const pending = state.status === 'pending' || importRequest.state.status === 'pending'
  const saved = state.status === 'success' ? state.data : null
  const markImportOutcomeUnknown = () => {
    importOutcomeUnknown.setValue(true)
    clearLoadedData()
  }
  const clearLoadedData = () => {
    importScope.clear()
    setConfirmed(false)
    setDocumentConfirmed(false)
    request.clear()
  }
  const assertOwner = async (api: Api, signal: AbortSignal, owner: string, expectedCsrf?: string) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || !me.user || me.user.id !== owner) {
      if (importScope.value) markImportOutcomeUnknown()
      else clearLoadedData()
      throw new ApiError(me.authenticated ? 'SESSION_EXPIRED' : 'UNAUTHENTICATED', 401)
    }
    if (expectedCsrf !== undefined && csrfToken(document.cookie, window.location.href) !== expectedCsrf) {
      markImportOutcomeUnknown()
      throw new ApiError('SESSION_EXPIRED', 401)
    }
    return me
  }
  const profileHeading = useRef<HTMLHeadingElement>(null)
  const documentHeading = useRef<HTMLHeadingElement>(null)
  const selectedId = saved?.selected?.id
  useEffect(() => {
    if (selectedId) documentHeading.current?.focus({ preventScroll: true })
  }, [selectedId])
  const load = (page = 1) => request.run(async (api, signal) => {
    const session = parseSession(required((await api.GET('/me', { signal })).data))
    if (!session.authenticated || !session.user) throw new ApiError('UNAUTHENTICATED', 401)
    const owner = session.user.id
    const profile = record(required((await api.GET('/profiles/me', { signal })).data))
    let experiences: string[] | null = null
    let reference: Saved['profile']
    if (profile.saved !== null) {
      const stored = record(profile.saved), content = record(stored.content)
      const id = text(stored.profile_id, 36)
      if (!isOpportunityId(id)) return invalid()
      reference = { id, version: version(stored.version) }
      if (!Array.isArray(content.experiences)) return invalid()
      experiences = content.experiences.map((experience) => text(record(experience).description, 2000))
    }
    const documents = view === 'profile'
      ? { documents: [], page: 1, total: 0 }
      : parseList(required((await api.GET('/drafts', { signal, params: { query: { page, page_size: 10 } } })).data))
    const confirmed = parseSession(required((await api.GET('/me', { signal })).data))
    if (!confirmed.authenticated || confirmed.user?.id !== owner) throw new ApiError('SESSION_EXPIRED', 401)
    return { owner, experiences, profile: reference, ...documents }
  })
  useEntryAction(() => load(), view !== 'all', view)
  const startEdit = () => {
    if (!saved?.profile) return
    const profile = saved.profile
    void importRequest.run(async (api, signal) => {
      const previous = importScope.value
      const me = await assertOwner(api, signal, saved.owner, previous?.csrf)
      const notice = me.consents.find(item => item.purpose === 'ai_processing')?.notice_version
      if (!notice) {
        if (previous) markImportOutcomeUnknown()
        throw new ApiError('CONSENT_REQUIRED', 403)
      }
      const csrf = csrfToken(document.cookie, window.location.href)
      if (!csrf) throw new ApiError('CSRF_MISSING')
      if (previous && (previous.owner !== saved.owner || previous.profileId !== profile.id
        || previous.profileVersion !== profile.version || previous.notice !== notice || previous.csrf !== csrf)) {
        markImportOutcomeUnknown()
        throw new ApiError('VERSION_CONFLICT', 409)
      }
      const attempt = previous && previous.owner === saved.owner && previous.profileId === profile.id
        && previous.profileVersion === profile.version && previous.notice === notice && previous.csrf === csrf
        ? previous
        : {
          owner: saved.owner,
          profileId: profile.id,
          profileVersion: profile.version,
          notice,
          csrf,
          key: crypto.randomUUID(),
          body: Object.freeze({
            ai_notice_version: notice,
            saved_profile: Object.freeze({ profile_id: profile.id, version: profile.version }),
          }),
        }
      importScope.setValue(attempt)
      let response
      try {
        response = await api.POST('/journeys', { signal,
          params: { header: { 'Idempotency-Key': attempt.key } }, body: attempt.body })
      } catch (error) {
        const ambiguous = error instanceof ApiError && [
          'NETWORK_ERROR', 'TIMEOUT', 'HTTP_ERROR', 'INVALID_RESPONSE', 'INTERNAL_ERROR',
          'SERVICE_UNAVAILABLE', 'AI_TIMEOUT', 'REQUEST_IN_PROGRESS',
        ].includes(error.code)
        if (!ambiguous) importScope.clear()
        throw error
      }
      const result = record(required(response.data))
      const id = text(result.journey_id, 36)
      if (!isOpportunityId(id) || record(result.confirmed).version !== 1) return invalid()
      await assertOwner(api, signal, saved.owner, attempt.csrf)
      return id
    }, id => { importScope.clear(); importOutcomeUnknown.clear(); navigate(`/journeys/${id}/profile`, { state: { savedProfileBaseVersion: profile.version } }) })
  }
  const content = <>
    {!saved && !actionOnly && <Button pending={pending} onClick={() => { setDocumentConfirmed(false); setConfirmed(false); void load() }}>저장 자료 불러오기</Button>}
    {state.status === 'error' && <RequestError error={state.error} />}
    {importRequest.state.status === 'error' && <RequestError error={importRequest.state.error} />}
    {importOutcomeUnknown.value && <StatusNotice kind="error" title="새 체험 생성 결과를 확인하지 못했어요">이전 요청이 이미 처리됐을 수 있습니다. 저장 자료를 다시 불러와 확인한 뒤 새 체험을 시작하면 별도의 체험이 추가될 수 있어요.</StatusNotice>}
    {pending && <p role="status">{actionOnly ? '프로필을 불러오고 있어요.' : '저장 자료를 확인하고 있어요.'}</p>}
    {saved && actionOnly && view === 'profile' && saved.profile && saved.experiences !== null && <Button variant="secondary" pending={pending} onClick={startEdit}>{resumeLabel}</Button>}
    {saved && <>{view !== 'drafts' && !actionOnly && <section className="panel"><h2 className="result-heading" ref={profileHeading} tabIndex={-1}>저장한 경험</h2>{saved.experiences === null ? <div className="service-entry"><p>아직 저장한 경험이 없어요.</p><Link className="button primary" to="/start">경험 이야기하기</Link></div> : <>
      <ul>{saved.experiences.map((experience, index) => <li className="user-text" key={index}>{experience}</li>)}</ul>
      <Button pending={pending} onClick={startEdit}>이 경험으로 다시 시작</Button>
      <p>수정한 내용은 다시 저장하기 전까지 기존 저장본에 반영되지 않아요.</p>
      <details><summary>저장한 경험 삭제</summary><p>경험의 모든 버전과 연결된 지원서를 삭제합니다. 기존 체험과 다른 기기의 로그인 세션도 종료합니다.</p><CheckboxField label="저장 프로필과 연결된 지원서를 모두 삭제할게요." checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
      <Button variant="secondary" disabled={!confirmed} onClick={() => { setConfirmed(false); void request.run(async (api, signal) => { await assertOwner(api, signal, saved.owner); await api.DELETE('/profiles/me', { signal }); return { owner: saved.owner, experiences: null, documents: [], page: 1, total: 0, message: '저장 프로필과 연결된 지원서를 삭제했습니다.' } }, onSessionReset) }}>저장 프로필과 지원서 삭제</Button>
      </details>
    </>}</section>}
    {view !== 'profile' && (view === 'drafts' && saved.documents.length === 0
      ? <div className="service-entry"><p>아직 정보가 없습니다.</p>{showEmptyAction && <Link className="button primary" to="/start">나의 경험 이야기하기</Link>}</div>
      : <section className="panel"><h2 ref={view === 'drafts' ? profileHeading : undefined} tabIndex={-1}>저장한 지원서</h2>{saved.documents.length === 0 ? <div className="service-entry"><p>아직 정보가 없습니다.</p><Link className="button primary" to="/opportunities?browse=all">공고 둘러보기</Link></div> : <ul className="saved-document-list">{saved.documents.map((document) => <li key={document.id}><p>{document.title}</p><div className="actions">
      <Button variant="secondary" onClick={() => { setConfirmed(false); setDocumentConfirmed(false); void request.run(async (api, signal) => {
        const result = record(required((await api.GET('/drafts/{document_id}', { signal, params: { path: { document_id: document.id } } })).data))
        if (result.document_id !== document.id || result.version !== document.version || !Array.isArray(result.review_reasons)) return invalid()
        if (typeof result.self_introduction !== 'string' || result.self_introduction.length > 2000 || typeof result.motivation !== 'string' || result.motivation.length > 2000) return invalid()
        const opportunityId = text(record(result.opportunity).id, 36)
        if (!isOpportunityId(opportunityId)) return invalid()
        return { ...saved, message: undefined, selected: { id: document.id, version: document.version, opportunityId, title: document.title, introduction: result.self_introduction, motivation: result.motivation, review: result.review_reasons.length > 0 } }
      }) }}>내용 보기: {document.title}</Button>
    </div></li>)}</ul>}
    {(saved.page > 1 || saved.total > 10) && <div className="actions"><Button variant="secondary" disabled={saved.page <= 1} onClick={() => void load(saved.page - 1)}>이전 페이지</Button><p>{saved.page}페이지 / 전체 {saved.total}건</p><Button variant="secondary" disabled={saved.page * 10 >= saved.total} onClick={() => void load(saved.page + 1)}>다음 페이지</Button></div>}</section>)}
    {saved.selected && <section className="panel"><h2 className="result-heading" ref={documentHeading} tabIndex={-1}>{saved.selected.title}</h2>{saved.selected.review && <StatusNotice label="재검토 필요" title="근거 정보가 변경되었습니다">프로필 또는 공고가 변경되었습니다. 공식 조건과 내용을 다시 확인해 주세요.</StatusNotice>}<h3>자기소개</h3><p className="user-text">{saved.selected.introduction}</p><h3>지원동기</h3><p className="user-text">{saved.selected.motivation}</p><CheckboxField label="이 지원서의 모든 저장 버전을 삭제할게요." checked={documentConfirmed} onChange={(event) => setDocumentConfirmed(event.target.checked)} /><Button variant="secondary" disabled={!documentConfirmed} onClick={() => { const id = saved.selected!.id; setDocumentConfirmed(false); void request.run(async (api, signal) => { await assertOwner(api, signal, saved.owner); await api.DELETE('/drafts/{document_id}', { signal, params: { path: { document_id: id } } }); return { ...saved, selected: undefined, documents: saved.documents.filter((document) => document.id !== id), total: Math.max(0, saved.total - 1), message: '선택한 지원서의 모든 저장 버전을 삭제했습니다.' } }, onSessionReset) }}>선택한 지원서 삭제</Button></section>}
    </>}
    <div>{saved?.selected && <SavedDraftEditor key={`${saved.selected.id}:${saved.selected.version}`} documentId={saved.selected.id} version={saved.selected.version} opportunityId={saved.selected.opportunityId} onUnavailable={request.clear} />}</div><p role="status">{saved?.message}</p>
  </>
  return actionOnly ? <div className="saved-profile-edit-action">{content}</div>
    : <ServicePage member={!embedded} embedded={embedded} className="saved-materials" title={embedded ? '지원서' : view === 'profile' ? '나의 정보' : view === 'drafts' ? '지원서' : '저장한 자료'}>{content}</ServicePage>
}
