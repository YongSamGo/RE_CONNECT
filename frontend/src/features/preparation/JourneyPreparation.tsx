import { useEffect, useRef } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { UnavailablePage } from '../../ui/UnavailablePage'
import { JourneyRoute } from '../journeys/JourneyRoute'
import { parseProfileView } from '../profile/server-model'
import type { ProfileView } from '../profile/server-model'
import { isOpportunityId } from '../public-opportunities/catalog'
import { parseDetail } from '../public-opportunities/detail'
import { OfficialPreparationContent } from './OfficialPreparation'
import { parsePreparation } from './official'
import type { Preparation } from './official'
import { parseDraft, parseExistingDraft, reviewLabels } from './drafts'
import type { DraftCreate, JourneyDraft } from './drafts'
import { DraftReadAloud } from '../voice/DraftReadAloud'

type Context = { profile: ProfileView; preparation: Preparation }
type Editor = { remote: JourneyDraft; introduction: string; motivation: string; dirty: boolean; reviewed: boolean }
type Attempt = { key: string; body: DraftCreate }
type Memory = { context: Context | null; editor: Editor | null; attempt: Attempt | null; ending: boolean }
const empty = (): Memory => ({ context: null, editor: null, attempt: null, ending: false })
const ambiguous = new Set(['NETWORK_ERROR', 'TIMEOUT', 'INVALID_RESPONSE', 'HTTP_ERROR', 'INTERNAL_ERROR', 'SERVICE_UNAVAILABLE', 'REQUEST_IN_PROGRESS', 'CANCELLED'])
async function publicRead<T>(action: Promise<T>): Promise<T> {
  try { return await action }
  catch (error) { if (error instanceof ApiError && error.code === 'NOT_FOUND') throw new ApiError('OPPORTUNITY_NOT_AVAILABLE'); throw error }
}

export function JourneyPreparationRoute() {
  const { opportunityId = '' } = useParams()
  return isOpportunityId(opportunityId) ? <JourneyRoute page={`opportunities/${opportunityId}/preparation`}>{journeyId =>
    <JourneyPreparation key={`${journeyId}:${opportunityId}`} journeyId={journeyId} opportunityId={opportunityId} />}</JourneyRoute>
    : <UnavailablePage title="공고 주소를 확인해 주세요">추천 화면에서 공고를 다시 선택해 주세요.</UnavailablePage>
}

export function JourneyPreparation({ journeyId, opportunityId }: { journeyId: string; opportunityId: string }) {
  const scope = useMemoryScope(empty)
  const contextRequest = useRequest<Context>()
  const draftRequest = useRequest<JourneyDraft>()
  const copyRequest = useRequest<{ copied: boolean; body: string }>()
  const endRequest = useRequest<boolean>()
  const accessFailure = useMemoryScope<ApiError | null>(() => null)
  const lock = useRef<symbol | null>(null)
  const resultRef = useRef<HTMLHeadingElement>(null)
  const navigate = useNavigate()
  const state = scope.value, editor = state.editor, context = state.context
  const pending = [contextRequest.state, draftRequest.state, copyRequest.state, endRequest.state].some(value => value.status === 'pending')
  const clear = scope.clear
  const clearContext = contextRequest.clear, clearDraft = draftRequest.clear, clearCopy = copyRequest.clear, clearEnd = endRequest.clear
  const setAccessFailure = accessFailure.setValue
  useEffect(() => {
    const failure = [contextRequest.state, draftRequest.state, copyRequest.state, endRequest.state].find(value => value.status === 'error'
      && ['SESSION_EXPIRED', 'UNAUTHENTICATED', 'NOT_FOUND'].includes(value.error.code))
    if (failure?.status === 'error') {
      setAccessFailure(failure.error); clear(); clearContext(); clearDraft(); clearCopy(); clearEnd(); lock.current = null
    }
  }, [contextRequest.state, draftRequest.state, copyRequest.state, endRequest.state, clear, clearContext, clearDraft, clearCopy, clearEnd, setAccessFailure])
  useEffect(() => { resultRef.current?.focus() }, [editor?.remote.draft_id, editor?.remote.revision])
  useEffect(() => {
    const reset = () => { lock.current = null }
    window.addEventListener('pagehide', reset)
    return () => { reset(); window.removeEventListener('pagehide', reset) }
  }, [])
  function apply(remote: JourneyDraft) {
    copyRequest.clear()
    scope.setValue(previous => ({ ...previous, editor: { remote, introduction: remote.self_introduction, motivation: remote.motivation, dirty: false, reviewed: false }, attempt: null }))
    resultRef.current?.focus()
  }
  function loadContext() {
    if (pending || state.attempt) return
    accessFailure.clear()
    copyRequest.clear()
    scope.setValue(previous => ({ ...previous, context: null }))
    void contextRequest.run(async (api, signal) => {
      await api.GET('/me', { signal })
      const profile = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
      const preparation = parsePreparation(required((await publicRead(api.GET('/opportunities/{opportunity_id}/preparation', { params: { path: { opportunity_id: opportunityId } }, signal }))).data), opportunityId)
      return { profile, preparation }
    }, context => scope.setValue(previous => ({ ...previous, context })))
  }
  function create(mode: 'generate' | 'manual', fresh = false) {
    if (!context?.profile.confirmed || pending || lock.current || editor?.dirty || state.ending) return
    const token = Symbol(); lock.current = token
    const attempt = !fresh && state.attempt ? state.attempt : { key: crypto.randomUUID(), body: {
      mode, profile_version: context.profile.confirmed.version, opportunity: context.preparation.opportunity, saved_document: null,
    } }
    scope.setValue(previous => ({ ...previous, attempt }))
    copyRequest.clear()
    void draftRequest.run(async (api, signal) => {
      try {
        const remote = parseDraft(required((await api.POST('/journeys/{journey_id}/drafts', { params: { path: { journey_id: journeyId }, header: { 'Idempotency-Key': attempt.key } }, body: attempt.body, signal })).data), opportunityId)
        if (remote.revision !== 1 || remote.approved_at !== null || remote.profile_version !== attempt.body.profile_version
          || remote.opportunity.version !== attempt.body.opportunity.version || remote.mode !== attempt.body.mode) throw new ApiError('INVALID_RESPONSE')
        if (editor?.remote.draft_id === remote.draft_id && remote.revision <= editor.remote.revision) throw new ApiError('VERSION_CONFLICT')
        return remote
      } catch (error) {
        if (!signal.aborted && error instanceof ApiError && !ambiguous.has(error.code)) scope.setValue(previous => ({ ...previous, attempt: null }))
        throw error
      }
    }, apply).finally(() => { if (lock.current === token) lock.current = null })
  }
  const path = { journey_id: journeyId, draft_id: editor?.remote.draft_id ?? '' }
  function edit(field: 'introduction' | 'motivation', value: string) {
    if (!editor || pending || state.attempt) return
    copyRequest.clear()
    scope.setValue(previous => ({ ...previous, editor: { ...editor, [field]: value, dirty: true, reviewed: false } }))
  }
  function save() {
    if (!editor || pending || !editor.dirty || state.attempt || state.ending) return
    const introduction = editor.introduction.replace(/\r\n/g, '\n').normalize('NFC'), motivation = editor.motivation.replace(/\r\n/g, '\n').normalize('NFC')
    void draftRequest.run(async (api, signal) => {
      const remote = parseExistingDraft(required((await api.PATCH('/journeys/{journey_id}/drafts/{draft_id}', { params: { path }, signal,
        body: { self_introduction: introduction, motivation, base_revision: editor.remote.revision } })).data), editor.remote)
      if (remote.revision !== editor.remote.revision + 1 || remote.approved_at !== null || remote.self_introduction !== introduction || remote.motivation !== motivation) throw new ApiError('INVALID_RESPONSE')
      return remote
    }, apply)
  }
  function reloadDraft() {
    if (!editor || pending || state.attempt) return
    void draftRequest.run(async (api, signal) => parseExistingDraft(required((await api.GET('/journeys/{journey_id}/drafts/{draft_id}', { params: { path }, signal })).data), editor.remote), apply)
  }
  function approve() {
    if (!editor || pending || editor.dirty || !editor.reviewed || editor.remote.review_reasons.length || state.attempt || state.ending) return
    void draftRequest.run(async (api, signal) => {
      const remote = parseExistingDraft(required((await api.POST('/journeys/{journey_id}/drafts/{draft_id}/approve', { params: { path }, body: { base_revision: editor.remote.revision }, signal })).data), editor.remote)
      if (remote.revision !== editor.remote.revision + 1 || !remote.approved_at || remote.review_reasons.length
        || remote.self_introduction !== editor.introduction || remote.motivation !== editor.motivation) throw new ApiError('INVALID_RESPONSE')
      return remote
    }, apply)
  }
  function copy() {
    if (!editor || pending || editor.dirty || !editor.remote.approved_at || editor.remote.review_reasons.length || state.attempt || state.ending) return
    void copyRequest.run(async (api, signal) => {
      const current = parseExistingDraft(required((await api.GET('/journeys/{journey_id}/drafts/{draft_id}', { params: { path }, signal })).data), editor.remote)
      const profile = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
      const opportunity = parseDetail(required((await publicRead(api.GET('/opportunities/{opportunity_id}', { params: { path: { opportunity_id: opportunityId } }, signal }))).data), opportunityId)
      if (current.revision !== editor.remote.revision || !current.approved_at || current.review_reasons.length
        || current.self_introduction !== editor.introduction || current.motivation !== editor.motivation || current.profile_version !== profile.confirmed?.version
        || current.opportunity.version !== opportunity.version || opportunity.recruitment_status !== 'open' || opportunity.change_pending) throw new ApiError('VERSION_CONFLICT')
      const age = Date.now() - Date.parse(opportunity.source_checked_at)
      if (age < 0 || age > 48 * 60 * 60 * 1000) throw new ApiError('OPPORTUNITY_NOT_AVAILABLE')
      if (signal.aborted) throw new ApiError('CANCELLED')
      const body = `자기소개\n${current.self_introduction}\n\n지원동기\n${current.motivation}`
      try { if (!navigator.clipboard?.writeText) return { copied: false, body }; await navigator.clipboard.writeText(body); return { copied: true, body } }
      catch { return { copied: false, body } }
    })
  }
  function end() {
    contextRequest.clear(); draftRequest.clear(); copyRequest.clear(); lock.current = null
    void endRequest.run(async (api, signal) => {
      const result = await api.DELETE('/journeys/{journey_id}', { params: { path: { journey_id: journeyId } }, signal })
      if (result.response.status !== 204) throw new ApiError('INVALID_RESPONSE')
      return true
    }, () => { clear(); navigate('/', { replace: true }) })
  }
  const available = context?.preparation.recruitment_status === 'open' && !context.preparation.change_pending
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">체험 신청 준비</p><h1>공식 안내를 보고 내 말로 준비해요</h1><p>초안 반영과 내용 승인, 회원 저장, 공식 신청처에서의 신청은 따로 진행해요.</p></header>
    <nav className="context-links" aria-label="관련 화면"><Link to={`/journeys/${journeyId}/profile`}>프로필 확인</Link><Link to={`/journeys/${journeyId}/recommendations`}>추천으로 돌아가기</Link></nav>
    <Button pending={contextRequest.state.status === 'pending'} disabled={pending || !!state.attempt} onClick={loadContext}>최신 준비 안내와 확정 프로필 확인</Button>
    {accessFailure.value && <RequestError error={accessFailure.value} />}
    {[contextRequest.state, draftRequest.state, copyRequest.state, endRequest.state].map((request, index) => request.status === 'error' && <RequestError key={index} error={request.error} />)}
    {context && <>
      <OfficialPreparationContent key={`${context.preparation.opportunity.version}:${contextRequest.state.status}`} item={context.preparation} showDraftNotice={false} />
      {!context.profile.confirmed && <StatusNotice title="프로필을 먼저 확정해 주세요">경험과 희망 지역, 활동 유형을 직접 확인하고 확정하면 이 공고의 지원서를 만들 수 있어요.</StatusNotice>}
      {context.profile.confirmed && <section className="panel"><h2>지원서 초안 만들기</h2><p>확정 프로필 {context.profile.confirmed.version}번 / 공고 {context.preparation.opportunity.version}번. 새 초안을 만들어도 기존 서버 초안은 체험 종료 전까지 남습니다.</p>
        {editor?.dirty && <p>작성 중인 내용을 먼저 초안에 반영하거나 서버 본문을 다시 불러온 뒤 새 초안을 만들 수 있어요.</p>}
        {state.attempt && <p>같은 요청의 처리 결과를 다시 확인할 수 있어요. 기다리기를 중지해도 서버 처리가 끝났을 수 있습니다.</p>}
        <div className="actions"><Button disabled={pending || !!editor?.dirty || !available || !!state.attempt} onClick={() => create('generate')}>확정 경험으로 새 초안 생성</Button>
        <Button variant="secondary" disabled={pending || !!editor?.dirty || !available || !!state.attempt} onClick={() => create('manual')}>새 빈 초안으로 직접 작성</Button>
        {state.attempt && <><Button disabled={pending} onClick={() => create(state.attempt!.body.mode as 'generate' | 'manual')}>같은 생성 요청 결과 확인</Button>
          <Button variant="secondary" disabled={pending || !!editor?.dirty || !available} onClick={() => create('manual', true)}>기다리던 결과 대신 새 빈 초안 작성</Button>
          {editor && <Button variant="secondary" onClick={() => { draftRequest.clear(); lock.current = null; scope.setValue(previous => ({ ...previous, attempt: null })) }}>대기 결과를 버리고 기존 본문 계속 편집</Button>}</>}
        {draftRequest.state.status === 'pending' && <Button variant="secondary" onClick={() => { draftRequest.clear(); lock.current = null }}>응답 기다리기 중지</Button>}</div>
      </section>}
    </>}
    {editor && <section className="panel"><h2 ref={resultRef} tabIndex={-1}>지원서 내용을 확인해 주세요</h2><p>지원서 리비전 {editor.remote.revision} / 원래 확정 프로필 {editor.remote.profile_version}번 / 공고 {editor.remote.opportunity.version}번</p>
      {editor.remote.review_reasons.map(reason => <p key={reason}>{reviewLabels[reason]} 기존 본문은 자동으로 바뀌지 않습니다.</p>)}
      {editor.remote.warnings.map((warning, index) => <p className="user-text" key={index}>{warning}</p>)}
      <TextAreaField label="자기소개" value={editor.introduction} rows={6} maxLength={2000} disabled={pending || !!state.attempt || state.ending} onChange={event => edit('introduction', event.target.value)} hint="직접 확인한 경험만 적어 주세요. 연락처나 주민등록번호, 상세 병력은 적지 마세요." />
      <TextAreaField label="지원동기" value={editor.motivation} rows={6} maxLength={2000} disabled={pending || !!state.attempt || state.ending} onChange={event => edit('motivation', event.target.value)} />
      {!editor.dirty && !pending && !state.attempt && !state.ending && <DraftReadAloud key={`${editor.remote.draft_id}:${editor.remote.revision}`} journeyId={journeyId} draft={editor.remote} />}
      <div className="actions"><Button disabled={pending || !editor.dirty || !!state.attempt || state.ending} onClick={save}>현재 편집을 초안에 반영</Button>
      <Button variant="secondary" disabled={pending || !!state.attempt} onClick={reloadDraft}>{editor.dirty ? '화면 편집 버리고 서버 본문 불러오기' : '서버 본문과 재검토 사유 다시 확인'}</Button>
      </div>
      <CheckboxField label="두 항목을 읽고 내 경험과 뜻에 맞는지 확인했어요." checked={editor.reviewed} disabled={pending || editor.dirty || !!state.attempt} onChange={event => scope.setValue(previous => ({ ...previous, editor: { ...editor, reviewed: event.target.checked } }))} />
      <Button disabled={pending || editor.dirty || !editor.reviewed || !!editor.remote.review_reasons.length || !!state.attempt || state.ending} onClick={approve}>확인한 이 리비전 승인</Button>
      <p role="status">{editor.dirty ? '반영하지 않은 편집입니다. 이전 승인은 이 편집에 적용되지 않습니다.' : editor.remote.approved_at ? '서버에서 이 리비전의 사용자 승인을 확인했습니다. 회원 저장이나 신청 완료는 아닙니다.' : '아직 사용자 승인 전입니다.'}</p>
      <Button disabled={pending || editor.dirty || !editor.remote.approved_at || !!editor.remote.review_reasons.length || !!state.attempt || state.ending} onClick={copy}>승인본 최신 상태 확인하고 복사</Button>
      {copyRequest.state.status === 'success' && <><TextAreaField label="최신 상태를 확인한 복사 내용" value={copyRequest.state.data.body} readOnly rows={10} id="journey-copy" />
        <p role="status">{copyRequest.state.data.copied ? '내용을 복사했어요. 자료 저장이나 신청 접수가 완료된 것은 아니에요.' : '자동 복사를 완료하지 못했습니다. 내용을 선택해 기기의 복사 기능을 사용해 주세요.'}</p>
        {!copyRequest.state.data.copied && <Button variant="secondary" onClick={() => { const field = document.getElementById('journey-copy') as HTMLTextAreaElement | null; field?.focus(); field?.select() }}>복사할 내용 전체 선택</Button>}</>}
      <p>복사 전에 서버의 승인 리비전·본문·확정 프로필·공고를 다시 조회합니다. 복사한 내용은 체험을 끝내도 기기 클립보드에 남을 수 있어요.</p>
      <p>화면을 떠나면 아직 반영하지 않은 입력은 사라집니다.</p>
    </section>}
    {context && <Button variant="secondary" disabled={endRequest.state.status === 'pending'} onClick={() => scope.setValue(previous => ({ ...previous, ending: true }))}>종료하고 삭제</Button>}
    {state.ending && <section className="panel" aria-label="체험 삭제 확인"><h2>체험 임시 자료를 삭제할까요?</h2><p>대화와 프로필, 모든 임시 지원서를 삭제해요.</p><Button pending={endRequest.state.status === 'pending'} onClick={end}>체험 임시 자료 삭제 확인</Button><Button variant="secondary" disabled={endRequest.state.status === 'pending'} onClick={() => scope.setValue(previous => ({ ...previous, ending: false }))}>계속 작성하기</Button></section>}
  </div>
}
