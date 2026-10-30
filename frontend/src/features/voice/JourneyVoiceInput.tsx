import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'
import { STOP_QUESTION_AUDIO } from './media-resources'
import { VoicePreview, type VoicePreviewHandle, type VoicePreviewStatus } from './VoicePreview'
import { parseTranscription } from './transcription'
import type { Transcript } from './transcription'

type Attempt = { key: string; blob: Blob; owner: string | null }

export function JourneyVoiceInput({ journeyId, voiceSelected = true, disabled = false, hasAnswer = false, retryAllowed = false, onSelectVoice, onSelectText, onNextQuestion, onRestart, onBusyChange, onUseText, onAccessLost }: {
  journeyId: string; replaceRequired?: boolean; voiceSelected?: boolean; disabled?: boolean; hasAnswer?: boolean; retryAllowed?: boolean; onSelectVoice?: () => void; onSelectText?: () => void;
  onNextQuestion?: () => void; onRestart?: () => void;
  onBusyChange?: (busy: boolean) => void; onUseText: (text: string, id: string) => void; onAccessLost?: (error: ApiError) => void
}) {
  const request = useRequest<Transcript>()
  const recorder = useMemoryScope(() => 0)
  const preview = useRef<VoicePreviewHandle>(null)
  const [recordingStatus, setRecordingStatus] = useState<VoicePreviewStatus>('idle')
  const setRecorderKey = recorder.setValue
  const attempt = useMemoryScope<Attempt | null>(() => null)
  const pending = request.state.status === 'pending'
  const clearAttempt = attempt.clear
  useEffect(() => { onBusyChange?.(pending) }, [pending, onBusyChange])
  useEffect(() => {
    if (request.state.status === 'error' && ['MODEL_UNAVAILABLE', 'AI_TIMEOUT', 'REQUEST_ALREADY_COMPLETED', 'VALIDATION_FAILED'].includes(request.state.error.code)) clearAttempt()
    if (request.state.status === 'error' && ['CONSENT_REQUIRED', 'SESSION_EXPIRED', 'UNAUTHENTICATED', 'NOT_FOUND'].includes(request.state.error.code)) { clearAttempt(); setRecorderKey(value => value + 1); onAccessLost?.(request.state.error) }
  }, [request.state, clearAttempt, setRecorderKey, onAccessLost])
  const cancel = () => { request.clear(); clearAttempt() }
  const cancelRecording = () => {
    cancel()
    setRecorderKey(value => value + 1)
    setRecordingStatus('idle')
    onBusyChange?.(false)
  }
  const transcribe = (blob: Blob) => {
    if (pending || blob.size === 0 || blob.size > 6 * 1024 * 1024) return
    onBusyChange?.(true)
    void request.run(async (api, signal) => {
      const session = parseSession(required((await api.GET('/me', { signal })).data))
      if (!session.consents.some(value => value.purpose === 'ai_processing')) throw new ApiError('CONSENT_REQUIRED', 403)
      const current = attempt.value ?? { key: crypto.randomUUID(), blob, owner: session.user?.id ?? null }
      if (current.owner !== (session.user?.id ?? null)) throw new ApiError('SESSION_EXPIRED', 401)
      if (signal.aborted) throw new ApiError('CANCELLED')
      attempt.setValue(current)
      const response = await api.POST('/journeys/{journey_id}/transcriptions', { signal,
        params: { path: { journey_id: journeyId }, header: { 'Idempotency-Key': current.key } },
        body: { audio: current.blob }, bodySerializer: body => { const data = new FormData(); data.append('audio', body.audio, 'recording'); return data },
      })
      return parseTranscription(required(response.data))
    }, transcript => { clearAttempt(); onUseText(transcript.text, transcript.transcription_id) })
  }
  const recording = recordingStatus === 'recording'
  const busy = pending || recordingStatus === 'permission'
  const retrying = !!attempt.value && request.state.status === 'error'
  const transcriptReady = voiceSelected && request.state.status === 'success'
  const speakDisabled = disabled || (busy && !recording)
  const speak = () => {
    // 말하기를 시작하면 읽어 주던 질문 소리를 멈춘다. 녹음에 질문 소리가 섞이지 않게 한다.
    window.dispatchEvent(new Event(STOP_QUESTION_AUDIO))
    if (!voiceSelected) onSelectVoice?.()
    if (retrying) preview.current?.retryTranscription()
    else { if (recordingStatus === 'ready' || recordingStatus === 'error') onRestart?.(); preview.current?.toggleRecording() }
  }
  const latest = useRef({ speak, enabled: false })
  const speakEnabled = !transcriptReady && !speakDisabled
  useEffect(() => { latest.current = { speak, enabled: speakEnabled } })
  useEffect(() => {
    // 마우스로 버튼을 매번 누르지 않도록 스페이스바로 말하기를 시작·저장한다. 글을 쓰는 칸, 버튼(스페이스로 이미 눌림),
    // 열린 확인 창에서는 가로채지 않는다.
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== 'Space' || event.repeat || event.altKey || event.ctrlKey || event.metaKey || !latest.current.enabled) return
      const target = event.target instanceof HTMLElement ? event.target : null
      if (target?.closest('input, textarea, select, button, a, [contenteditable="true"], dialog[open]') || document.querySelector('dialog[open]')) return
      event.preventDefault()
      latest.current.speak()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])
  return <section className="conversation-voice-input" aria-label="답변 입력 방식">
    <div className="conversation-input-choice" id="conversation-speak" role="group" aria-label="답변 입력 방식">
      {!transcriptReady && <Button variant={voiceSelected ? 'primary' : 'secondary'} aria-pressed={voiceSelected} aria-keyshortcuts="Space" disabled={speakDisabled} onClick={speak}>{recording ? '말한 내용 저장하기' : retrying ? '같은 녹음 다시 확인' : recordingStatus === 'permission' ? '마이크 확인 중' : '말하기'}</Button>}
      <Button variant={!voiceSelected ? 'primary' : 'secondary'} aria-pressed={!voiceSelected} disabled={disabled} onClick={() => { cancelRecording(); onSelectText?.() }}>글로 답하기</Button>
      {(busy || recording) && <Button variant="secondary" onClick={cancelRecording}>음성 입력 취소</Button>}
    </div>
    {!transcriptReady && !speakDisabled && <p className="conversation-voice-hint">스페이스바를 눌러도 {recording ? '말한 내용을 저장할' : '말하기를 시작할'} 수 있어요.</p>}
    <div className="conversation-voice-mode" hidden={!voiceSelected}>
      <VoicePreview ref={preview} embedded key={recorder.value} onStatusChange={setRecordingStatus} transcription={{ pending, onRequest: transcribe, onReset: cancel, onBusyChange }} />
    </div>
    {pending && <p role="status">말씀을 글로 바꾸고 있어요.</p>}
    {transcriptReady && <div className="conversation-voice-followup">
      <Button variant="secondary" disabled={disabled || busy} onClick={() => { onRestart?.(); preview.current?.toggleRecording() }}>다시 말하기</Button>
      <Button disabled={busy || (!retryAllowed && (disabled || !hasAnswer))} onClick={onNextQuestion}>{retryAllowed ? '같은 요청 결과 다시 확인' : '다음 질문'}</Button>
    </div>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    {request.state.status === 'success' && <p role="status">말씀하신 내용을 글로 바꿔 답변에 넣었어요. 내용을 확인해 주세요.</p>}
  </section>
}
