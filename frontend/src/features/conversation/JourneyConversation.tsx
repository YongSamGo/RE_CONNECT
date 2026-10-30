import { UnsavedChangesGuard } from '../../ui/UnsavedChangesGuard'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { useEntryAction } from '../../state/useEntryAction'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { JourneyRoute } from '../journeys/JourneyRoute'
import { JourneyVoiceInput } from '../voice/JourneyVoiceInput'
import { parseProfileView } from '../profile/server-model'
import { parseMessageResult, profileQuestion } from './model'
import type { MessageInput, MessageResult, ProfileView } from './model'
import { ConversationSurface, ServicePage } from '../../ui/ServicePage'
import { QuestionAudio } from './QuestionAudio'
import { ConversationGuide } from './ConversationGuide'
import { ConversationRegionPicker } from './ConversationRegionPicker'
import './conversation-task.css'

type Attempt = { key: string; body: MessageInput }
type Conversation = { view: ProfileView | null; text: string; question: string | null; notices: string[];
  attempt: Attempt | null; conflict: boolean; ended: boolean; voice: boolean; voiceBusy: boolean; transcriptionId: string | null; questionId: string | null }
const empty = (): Conversation => ({ view: null, text: '', question: null, notices: [], attempt: null, conflict: false, ended: false, voice: true, voiceBusy: false, transcriptionId: null, questionId: null })
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
  const accessFailure = useMemoryScope<ApiError | null>(() => null)
  const location = useLocation()
  const [newJourney] = useState(() => location.state?.newJourney === true || (import.meta.env.DEV && location.pathname === '/dev/conversation'))
  const [showGuide, setShowGuide] = useState(newJourney)
  const questionRef = useRef<HTMLHeadingElement>(null)
  const confirmDialog = useRef<HTMLDialogElement>(null)
  const previousReadStatus = useRef(read.state.status)
  const presentedQuestion = useRef(false)
  const submitLock = useRef<symbol | null>(null)
  const state = scope.value
  const sending = send.state.status === 'pending'
  const requestPending = sending || read.state.status === 'pending'
  const pending = requestPending || state.voiceBusy
  // 음성 인식이 지명을 잘못 들어도 고칠 수 있게, 희망 지역을 묻는 동안 목록 선택을 함께 둔다.
  const askingRegion = !!state.view && !state.ended && !!state.question?.includes('지역') && state.view.draft.preferred_regions.length === 0
  const setScopedValue = scope.setValue
  const voiceBusyChanged = useCallback((voiceBusy: boolean) => setScopedValue(previous => previous.voiceBusy === voiceBusy ? previous : { ...previous, voiceBusy }), [setScopedValue])
  const clear = scope.clear
  const clearRead = read.clear, clearSend = send.clear, setAccessFailure = accessFailure.setValue
  const accessLost = useCallback((error: ApiError) => {
    clear(); clearRead(); clearSend(); submitLock.current = null; setAccessFailure(error)
  }, [clear, clearRead, clearSend, setAccessFailure])
  useEffect(() => {
    const failure = [send.state, read.state].find(state => state.status === 'error' && inaccessible.has(state.error.code))
    if (failure?.status === 'error') accessLost(failure.error)
  }, [send.state, read.state, accessLost])
  useEffect(() => { if (!state.voice && state.transcriptionId) document.getElementById('conversation-message-input')?.focus() }, [state.voice, state.transcriptionId])
  useEffect(() => {
    const justLoaded = previousReadStatus.current !== 'success' && read.state.status === 'success'
    previousReadStatus.current = read.state.status
    if (justLoaded && (!state.voice || !presentedQuestion.current)) questionRef.current?.focus()
    if (justLoaded && questionRef.current) presentedQuestion.current = true
  }, [read.state.status, state.voice])
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
  useEntryAction(load, newJourney, journeyId)
  function submit() {
    if (!state.view || pending || submitLock.current || state.conflict || state.ended || !state.text.trim()) return
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
        return { ...previous, view: result.profile, text: '', transcriptionId: null, attempt: null, conflict: false,
          question: result.assistant_message?.text ?? null, questionId: result.assistant_message?.message_id ?? null, notices: result.notices, ended: result.next_step === 'review_profile' }
      })
      questionRef.current?.focus()
    }).finally(() => { if (submitLock.current === token) submitLock.current = null })
  }
  return <ServicePage title="경험 이야기하기" className="conversation-task"><UnsavedChangesGuard dirty={!!state.text.trim()} /><div className="service-conversation journey-conversation">
    {!state.view && (!newJourney || read.state.status === 'error') && <Button variant="secondary" disabled={pending || !!state.attempt} onClick={load}>체험 대화 준비하기</Button>}
    {newJourney && read.state.status === 'pending' && <p role="status">질문을 준비하고 있습니다.</p>}
    {accessFailure.value && <RequestError error={accessFailure.value} />}
    {read.state.status === 'error' && <RequestError error={read.state.error} />}
    {send.state.status === 'error' && <RequestError error={send.state.error} />}
    {state.conflict && <StatusNotice title="최신 프로필을 확인해 주세요" actions={<Button disabled={pending} onClick={load}>최신 프로필 상태 확인</Button>}>적은 내용은 유지했습니다. 최신 프로필 상태를 확인한 뒤 다시 보낼 수 있어요.</StatusNotice>}
    {state.view && <>
      {state.view.confirmed && <p>수정한 초안은 아직 확정하지 않았습니다. 다시 확정하기 전의 추천은 이전 확정 프로필 기준이에요.</p>}
      <ConversationSurface><section className="conversation-question"><h2 id="conversation-question" ref={questionRef} tabIndex={-1}>{state.question ?? '프로필 내용을 확인해 주세요'}</h2>
        {!state.ended && state.question && <QuestionAudio key={state.questionId ?? state.question} question={state.question} journeyId={journeyId} messageId={state.questionId} />}
        <p role="status">{state.ended ? '초안에 반영했습니다. 프로필에서 내용을 확인하고 직접 확정해 주세요.' : sending ? '경험을 정리하고 있어요. 프로필 화면으로 이동할 수 있습니다.' : ''}</p>
        {(state.ended || (!sending && state.view.draft.experiences.length > 0)) && <div className="actions"><Link className={state.ended ? "button primary" : "button secondary"} to={`/journeys/${journeyId}/profile`}>정리한 경험 확인하기</Link></div>}
        {state.notices.map((notice, index) => <p key={index} className="user-text">{notice}</p>)}
        {state.attempt && !sending && <p>처리 여부를 아직 확인하지 못했습니다. 같은 내용과 요청 번호로 결과를 다시 확인합니다. 화면을 떠나면 대기 상태가 지워지며, 서버 처리가 끝났을 수도 있습니다.</p>}
        {state.attempt && !sending && <Button disabled={pending} onClick={submit}>같은 요청 결과 다시 확인</Button>}
        {sending && <Button variant="secondary" onClick={() => { send.clear(); submitLock.current = null }}>응답 기다리기 중지</Button>}
        {sending && <p>응답 기다리기를 중지해도 서버 처리가 끝났을 수 있습니다. 초안은 자동 확정되지 않습니다.</p>}
        {sending && <Link className="button secondary" to={`/journeys/${journeyId}/profile`}>정리한 경험 확인하기</Link>}
      </section></ConversationSurface>
      {!state.ended && <JourneyVoiceInput key={state.questionId ?? state.question ?? 'question'} journeyId={journeyId} voiceSelected={state.voice} hasAnswer={!!state.text.trim()} disabled={requestPending || !!state.attempt}
        retryAllowed={!!state.attempt && !requestPending}
        onSelectVoice={() => scope.setValue(previous => ({ ...previous, voice: true }))}
        onSelectText={() => { scope.setValue(previous => ({ ...previous, voice: false })); requestAnimationFrame(() => document.getElementById('conversation-message-input')?.focus()) }}
        onNextQuestion={() => confirmDialog.current?.showModal()} onRestart={() => scope.setValue(previous => ({ ...previous, transcriptionId: null }))} onBusyChange={voiceBusyChanged} onAccessLost={accessLost}
        onUseText={(text, transcriptionId) => scope.setValue(previous => ({ ...previous, text, transcriptionId, voice: true }))} />}
      {!state.ended && <section className="conversation-answer" aria-label="답변 입력">
        <form onSubmit={event => { event.preventDefault(); confirmDialog.current?.showModal() }}>
          <TextAreaField id="conversation-message-input" label={state.transcriptionId ? '말씀하신 내용 확인' : '내 답변'} value={state.text} rows={4} maxLength={2000} disabled={pending || !!state.attempt}
            onChange={event => scope.setValue(previous => ({ ...previous, text: event.target.value }))} />
          {askingRegion && <ConversationRegionPicker disabled={pending || !!state.attempt} onInsert={place => scope.setValue(previous => {
            const text = previous.text.trim()
            return text.includes(place) ? previous : { ...previous, text: text ? `${text}, ${place}` : place }
          })} />}
          {!(state.voice && state.transcriptionId) && <Button type="submit" pending={sending} disabled={pending || state.conflict || !state.text.trim()}>완료하기</Button>}
        </form>
        <dialog ref={confirmDialog} className="conversation-confirm-dialog" aria-labelledby="conversation-confirm-title" onCancel={event => { if (sending) event.preventDefault() }}>
          <h2 id="conversation-confirm-title">답변 내용을 확인해 주세요</h2>
          <section><h3>질문</h3><p>{state.question}</p></section>
          <section><h3>내 답변</h3><p className="conversation-confirm-answer">{state.text}</p></section>
          <p>이 내용이 맞나요?</p>
          <div className="actions">
            <Button variant="secondary" disabled={sending || !!state.attempt} onClick={() => { confirmDialog.current?.close(); requestAnimationFrame(() => document.getElementById('conversation-message-input')?.focus()) }}>내용 고치기</Button>
            <Button pending={sending} pendingLabel="답변을 반영하고 있어요" onClick={() => { confirmDialog.current?.close(); submit() }}>{state.attempt ? '같은 요청 결과 다시 확인' : '네, 완료하기'}</Button>
          </div>
        </dialog>
      </section>}
    </>}
    {showGuide && state.view && state.question && !state.ended && <ConversationGuide onClose={() => { setShowGuide(false); questionRef.current?.focus() }} />}
  </div></ServicePage>
}
