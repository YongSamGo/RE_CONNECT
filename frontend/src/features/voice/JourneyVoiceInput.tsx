import { useEffect } from 'react'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'
import { VoicePreview } from './VoicePreview'
import { parseTranscription } from './transcription'
import type { Transcript } from './transcription'

type Attempt = { key: string; blob: Blob; owner: string | null }

export function JourneyVoiceInput({ journeyId, replaceRequired, onUseText, onAccessLost }: { journeyId: string; replaceRequired: boolean; onUseText: (text: string, id: string) => void; onAccessLost?: (error: ApiError) => void }) {
  const request = useRequest<Transcript>()
  const recorder = useMemoryScope(() => 0)
  const setRecorderKey = recorder.setValue
  const attempt = useMemoryScope<Attempt | null>(() => null)
  const result = useMemoryScope<{ transcript: Transcript | null; text: string; replace: boolean }>(() => ({ transcript: null, text: '', replace: false }))
  const pending = request.state.status === 'pending'
  const clearAttempt = attempt.clear, clearResult = result.clear
  useEffect(() => {
    if (request.state.status === 'error' && ['MODEL_UNAVAILABLE', 'AI_TIMEOUT', 'REQUEST_ALREADY_COMPLETED', 'VALIDATION_FAILED'].includes(request.state.error.code)) clearAttempt()
    if (request.state.status === 'error' && ['CONSENT_REQUIRED', 'SESSION_EXPIRED', 'UNAUTHENTICATED', 'NOT_FOUND'].includes(request.state.error.code)) { clearAttempt(); clearResult(); setRecorderKey(value => value + 1); onAccessLost?.(request.state.error) }
  }, [request.state, clearAttempt, clearResult, setRecorderKey, onAccessLost])
  const cancel = () => { request.clear(); clearAttempt(); clearResult() }
  const transcribe = (blob: Blob) => {
    if (pending || blob.size === 0 || blob.size > 6 * 1024 * 1024) return
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
    }, transcript => { clearAttempt(); result.setValue({ transcript, text: transcript.text, replace: false }) })
  }
  return <section aria-label="체험 음성 전사"><VoicePreview key={recorder.value} transcription={{ pending, onRequest: transcribe, onReset: cancel }} />
    {pending && <Button variant="secondary" onClick={request.clear}>전사 응답 기다리기 중지</Button>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    <p>응답을 받지 못했거나 기다리기를 중지한 뒤에는 같은 녹음과 요청 번호로 확인해요. 새 녹음을 선택하면 기다리던 요청의 참조를 지워요.</p>
    {result.value.transcript && <section className="panel"><h3>전사 내용을 직접 확인해 주세요</h3>
      <TextAreaField label="글로 바꾼 내용 확인과 수정" value={result.value.text} maxLength={2000} disabled={pending} onChange={event => result.setValue({ ...result.value, text: event.target.value })} />
      {replaceRequired && <CheckboxField label="현재 경험 입력을 확인한 전사 문장으로 바꿀게요." checked={result.value.replace} onChange={event => result.setValue({ ...result.value, replace: event.target.checked })} />}
      <Button disabled={pending || !result.value.text.trim() || (replaceRequired && !result.value.replace)} onClick={() => { const value = result.value; if (value.transcript) { cancel(); setRecorderKey(key => key + 1); onUseText(value.text, value.transcript.transcription_id) } }}>확인한 전사 문장을 입력란으로 가져오기</Button>
      <p>입력란으로 가져와도 대화를 보내거나 프로필을 확정하지 않습니다.</p>
    </section>}
  </section>
}
