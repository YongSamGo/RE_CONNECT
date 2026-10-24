import { useCallback, useEffect, useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { JourneyRoute } from '../journeys/JourneyRoute'
import { JourneyVoiceInput } from '../voice/JourneyVoiceInput'
import { parseProfileView } from '../profile/server-model'
import { parseMessageResult, profileQuestion } from './model'
import type { MessageInput, MessageResult, ProfileView } from './model'
import { ReadAloud } from '../voice/ReadAloud'

type Attempt = { key: string; body: MessageInput }
type Conversation = { view: ProfileView | null; text: string; question: string | null; notices: string[];
  attempt: Attempt | null; conflict: boolean; ended: boolean; ending: boolean; voice: boolean; transcriptionId: string | null; questionId: string | null }
const empty = (): Conversation => ({ view: null, text: '', question: null, notices: [], attempt: null, conflict: false, ended: false, ending: false, voice: false, transcriptionId: null, questionId: null })
// These responses cannot establish whether the server committed. Retain the exact key and body.
const ambiguous = new Set(['NETWORK_ERROR', 'TIMEOUT', 'INVALID_RESPONSE', 'HTTP_ERROR', 'INTERNAL_ERROR', 'SERVICE_UNAVAILABLE', 'REQUEST_IN_PROGRESS', 'CANCELLED'])
const inaccessible = new Set(['NOT_FOUND', 'SESSION_EXPIRED', 'UNAUTHENTICATED', 'CONSENT_REQUIRED'])

export function JourneyConversationRoute() {
  return <JourneyRoute page="conversation">{id => <JourneyConversation key={id} journeyId={id} />}</JourneyRoute>
}

export function JourneyConversation({ journeyId }: { journeyId: string }) {
  const scope = useMemoryScope(empty)
  const read = useRequest<ProfileView>()
  const send = useRequest<MessageResult>()
  const end = useRequest<boolean>()
  const accessFailure = useMemoryScope<ApiError | null>(() => null)
  const navigate = useNavigate()
  const questionRef = useRef<HTMLHeadingElement>(null)
  const submitLock = useRef<symbol | null>(null)
  const state = scope.value
  const sending = send.state.status === 'pending'
  const pending = sending || read.state.status === 'pending' || end.state.status === 'pending'
  const clear = scope.clear
  const clearRead = read.clear, clearSend = send.clear, clearEnd = end.clear, setAccessFailure = accessFailure.setValue
  const accessLost = useCallback((error: ApiError) => {
    clear(); clearRead(); clearSend(); clearEnd(); submitLock.current = null; setAccessFailure(error)
  }, [clear, clearRead, clearSend, clearEnd, setAccessFailure])
  useEffect(() => {
    const failure = [send.state, read.state, end.state].find(state => state.status === 'error' && inaccessible.has(state.error.code))
    if (failure?.status === 'error') accessLost(failure.error)
  }, [send.state, read.state, end.state, accessLost])
  useEffect(() => { if (!state.voice) document.getElementById('conversation-message-input')?.focus() }, [state.voice])
  useEffect(() => {
    const resetLock = () => { submitLock.current = null }
    window.addEventListener('pagehide', resetLock)
    return () => { resetLock(); window.removeEventListener('pagehide', resetLock) }
  }, [])

  function load() {
    if (pending || state.attempt) return
    accessFailure.clear()
    send.clear()
    void read.run(async (api, signal) => {
      await api.GET('/me', { signal })
      return parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
    }, view => scope.setValue(previous => ({ ...previous, view, question: profileQuestion(view), questionId: null, notices: [], conflict: false, ended: false })))
  }
  function submit() {
    if (!state.view || pending || submitLock.current || state.conflict || state.ending || state.ended || state.voice || !state.text.trim()) return
    const token = Symbol()
    submitLock.current = token
    const attempt = state.attempt ?? { key: crypto.randomUUID(), body: { text: state.text, transcription_id: state.transcriptionId, base_revision: state.view.revision } }
    scope.setValue(previous => ({ ...previous, attempt }))
    void send.run(async (api, signal) => {
      try {
        return parseMessageResult(required((await api.POST('/journeys/{journey_id}/messages', {
          params: { path: { journey_id: journeyId }, header: { 'Idempotency-Key': attempt.key } }, body: attempt.body, signal,
        })).data), attempt.body.base_revision)
      } catch (error) {
        if (!signal.aborted && error instanceof ApiError && !ambiguous.has(error.code)) {
          scope.setValue(previous => ({ ...previous, attempt: null, conflict: error.code === 'VERSION_CONFLICT' }))
        }
        throw error
      }
    }, result => {
      scope.setValue(previous => {
        if (!previous.view || result.revision <= previous.view.revision) return { ...previous, attempt: null, conflict: true }
        return { ...previous, view: result.profile, text: '', transcriptionId: null, voice: false, attempt: null, conflict: false,
          question: result.assistant_message?.text ?? null, questionId: result.assistant_message?.message_id ?? null, notices: result.notices, ended: result.next_step === 'review_profile' }
      })
      questionRef.current?.focus()
    }).finally(() => { if (submitLock.current === token) submitLock.current = null })
  }
  function deleteJourney() {
    read.clear(); send.clear()
    void end.run(async (api, signal) => {
      const response = await api.DELETE('/journeys/{journey_id}', { params: { path: { journey_id: journeyId } }, signal })
      if (response.response.status !== 204) throw new ApiError('INVALID_RESPONSE')
      return true
    }, () => { clear(); navigate('/', { replace: true }) })
  }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">03 · 경험 이야기</p><h1>한 가지씩 이야기해 주세요</h1><p>AI가 정리한 내용은 초안입니다. 직접 확인하고 고칠 수 있어요.</p></header>
    <p><Link className="button secondary" to={`/journeys/${journeyId}/profile`}>언제든 프로필 확인하기</Link></p>
    <p>희망 지역·활동 유형과 다른 조건은 프로필 화면에서 직접 선택해 주세요. 프로필로 이동하면 아직 보내지 않은 입력은 지워집니다. 대화 기록은 이 화면에서 복원하지 않습니다.</p>
    <Button disabled={pending || !!state.attempt} onClick={load}>{state.view ? '최신 프로필 상태 확인' : '체험 대화 준비하기'}</Button>
    {accessFailure.value && <RequestError error={accessFailure.value} />}
    {read.state.status === 'error' && <RequestError error={read.state.error} />}
    {send.state.status === 'error' && <RequestError error={send.state.error} />}
    {end.state.status === 'error' && <RequestError error={end.state.error} />}
    {state.conflict && <StatusNotice title="최신 프로필을 확인해 주세요">적은 내용은 유지했습니다. 최신 프로필 상태를 확인한 뒤 다시 보낼 수 있어요.</StatusNotice>}
    {state.view && <>
      {state.view.confirmed && <p>수정한 초안은 아직 확정하지 않았습니다. 재확정 전 추천·자격은 이전 확정 프로필 기준입니다.</p>}
      <section className="panel"><h2 ref={questionRef} tabIndex={-1}>{state.question ?? '프로필 내용을 확인해 주세요'}</h2>
        {state.questionId && !pending && !state.voice && !state.ending && <ReadAloud key={state.questionId} target={{ kind: 'journey_message', journey_id: journeyId, message_id: state.questionId }} label="이 질문 읽어주기" />}
        <p role="status">{state.ended ? '초안에 반영했습니다. 프로필에서 내용을 확인하고 직접 확정해 주세요.' : sending ? '경험을 정리하고 있어요. 프로필 화면으로 이동할 수 있습니다.' : ''}</p>
        {state.notices.map((notice, index) => <p key={index} className="user-text">{notice}</p>)}
        {state.attempt && !sending && <p>처리 여부를 아직 확인하지 못했습니다. 같은 내용과 요청 번호로 결과를 다시 확인합니다. 화면을 떠나면 대기 상태가 지워지며, 서버 처리가 끝났을 수도 있습니다.</p>}
        {!state.ended && <form onSubmit={event => { event.preventDefault(); submit() }}>
          <TextAreaField id="conversation-message-input" label="내가 해온 일" value={state.text} rows={6} maxLength={2000} disabled={pending || !!state.attempt || state.ending || state.voice}
            onChange={event => scope.setValue(previous => ({ ...previous, text: event.target.value }))} hint="연락처·주민등록번호·상세 병력은 적지 마세요. 보내기 전에 내용을 확인해 주세요." />
          <Button type="submit" pending={sending} disabled={pending || state.conflict || state.ending || state.voice || !state.text.trim()}>{state.attempt ? '같은 요청의 처리 결과 다시 확인' : '확인한 내용 보내기'}</Button>
        </form>}
        {sending && <Button variant="secondary" onClick={() => { send.clear(); submitLock.current = null }}>응답 기다리기 중지</Button>}
        <p>응답 기다리기를 중지해도 서버 처리가 끝났을 수 있습니다. 초안은 자동 확정되지 않습니다.</p>
      </section>
      {!state.ended && <>
        {!state.voice && <Button variant="secondary" disabled={pending || !!state.attempt || state.ending} onClick={() => scope.setValue(previous => ({ ...previous, voice: true }))}>말로 입력하고 전사 확인</Button>}
        {state.transcriptionId && !state.voice && <p>음성에서 확인한 문장입니다. 입력칸에서 더 고친 내용만 보냅니다.</p>}
        {state.voice && <><JourneyVoiceInput journeyId={journeyId} onAccessLost={accessLost} replaceRequired={!!state.text.trim()}
          onUseText={(text, transcriptionId) => scope.setValue(previous => ({ ...previous, text, transcriptionId, voice: false }))} />
          <Button variant="secondary" onClick={() => scope.setValue(previous => ({ ...previous, voice: false }))}>음성 입력 닫고 원래 글로 돌아가기</Button></>}
      </>}
      <Button variant="secondary" disabled={end.state.status === 'pending'} onClick={() => scope.setValue(previous => ({ ...previous, voice: false, ending: true }))}>종료하고 삭제</Button>
    </>}
    {state.ending && <section className="panel" aria-label="체험 삭제 확인"><h2>체험 임시 자료를 삭제할까요?</h2><p>이 체험의 대화·초안·확정본·역할 선택과 진행 결과를 삭제합니다.</p>
      <Button pending={end.state.status === 'pending'} onClick={deleteJourney}>체험 임시 자료 삭제 확인</Button>
      <Button variant="secondary" disabled={end.state.status === 'pending'} onClick={() => scope.setValue(previous => ({ ...previous, ending: false }))}>계속 작성하기</Button></section>}
  </div>
}
