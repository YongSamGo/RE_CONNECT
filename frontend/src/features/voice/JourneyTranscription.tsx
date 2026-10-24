import { useEffect } from 'react'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { parseTranscription } from './transcription'
import type { Transcript } from './transcription'
import { AudioRecorderControls } from './AudioRecorderControls'
import { useAudioRecorder } from './useAudioRecorder'

export function JourneyTranscription({ journeyId, onUseText, onClose, onAccessLost }: {
  journeyId: string; onUseText: (text: string, transcriptionId: string | null) => void; onClose: () => void; onAccessLost: (error: ApiError) => void
}) {
  const recorder = useAudioRecorder()
  const text = useMemoryScope(() => ({ value: '', transcriptionId: null as string | null }))
  const request = useRequest<Transcript>()
  const pending = request.state.status === 'pending'
  useEffect(() => {
    if (request.state.status === 'error' && ['NOT_FOUND', 'UNAUTHENTICATED', 'SESSION_EXPIRED', 'CONSENT_REQUIRED'].includes(request.state.error.code)) onAccessLost(request.state.error)
  }, [request.state, onAccessLost])
  function reset() { request.clear(); recorder.reset(); text.clear() }
  function upload() {
    if (!recorder.blob || pending) return
    const blob = recorder.blob, cleanup = recorder.cleanupForCurrentRecording()
    void request.run(async (api, signal) => {
      try {
        const result = await api.POST('/journeys/{journey_id}/transcriptions', {
          params: { path: { journey_id: journeyId }, header: { 'Idempotency-Key': crypto.randomUUID() } }, body: { audio: blob }, signal,
          bodySerializer: body => { const form = new FormData(); form.set('audio', body.audio, blob.type.startsWith('audio/mp4') ? 'recording.m4a' : 'recording.webm'); return form },
        })
        return parseTranscription(required(result.data))
      } finally { cleanup() }
    }, result => text.setValue({ value: result.text, transcriptionId: result.transcription_id }))
  }
  return <section aria-label="녹음·전사 확인"><h2>말로 입력하고 글로 확인해요</h2>
    <p>최대 90초·6MiB입니다. 마이크는 녹음 시작을 누를 때만 켜집니다. 연락처·주민등록번호·상세 병력은 말하지 마세요.</p>
    <AudioRecorderControls recorder={recorder} onReset={reset} disabled={pending} />
    <Button pending={pending} disabled={!recorder.blob || recorder.status !== 'ready'} onClick={upload}>이 녹음을 서버에 보내 전사</Button>
    <p>이 버튼을 눌러야 내부 음성 서비스로 보냅니다. 원본은 전사 성공·실패·취소 뒤 기기에서 정리합니다. 새 전사를 받으면 아래 확인 문장이 바뀝니다.</p>
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    <TextAreaField label="보내기 전에 고칠 전사 문장" value={text.value.value} onChange={event => text.setValue(previous => ({ ...previous, value: event.target.value }))} disabled={pending} maxLength={2000} rows={6}
      hint="전사는 자동으로 프로필에 쓰지 않습니다. 잘못 인식한 말을 고치거나 직접 작성한 뒤 사용해 주세요." />
    <Button disabled={pending || !text.value.value.trim()} onClick={() => { const confirmed = text.value; reset(); onUseText(confirmed.value, confirmed.transcriptionId) }}>이 수정 문장을 입력칸에 사용하기</Button>
    <Button variant="secondary" onClick={() => { reset(); onClose() }}>음성 입력 닫고 원래 글로 돌아가기</Button>
    <p>전사에 실패하면 원본은 다시 보내지 않습니다. 새로 녹음하거나 직접 적을 수 있어요. 기다리기 중지가 서버 처리 종료를 보장하지는 않습니다.</p>
  </section>
}
