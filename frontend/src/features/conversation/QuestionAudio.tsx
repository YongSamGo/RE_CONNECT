import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'

export function QuestionAudio({ question, journeyId, messageId }: { question: string; journeyId: string; messageId: string | null }) {
  const [volume, setVolume] = useState(1)
  const [error, setError] = useState('')
  const [segment, setSegment] = useState(0)
  const [count, setCount] = useState<number | null>(null)
  const rate = useRef(1)
  const audio = useRef<HTMLAudioElement | null>(null)
  const request = useRequest<{ blob: Blob; count: number }>()
  const blob = request.state.status === 'success' ? request.state.data.blob : null
  useEffect(() => () => { window.speechSynthesis?.cancel() }, [question])
  useEffect(() => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const player = new Audio(url)
    audio.current = player
    player.volume = volume
    player.playbackRate = rate.current
    let active = true
    void player.play().catch(() => { if (active) setError('소리를 재생하지 못했습니다. 화면의 글을 확인해 주세요.') })
    return () => { active = false; player.pause(); player.removeAttribute('src'); player.load(); URL.revokeObjectURL(url); if (audio.current === player) audio.current = null }
  // Volume changes are applied to the existing player below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blob])
  useEffect(() => { if (audio.current) audio.current.volume = volume }, [volume])

  function listen(speed: number, part = 0) {
    setError('')
    rate.current = speed
    setSegment(part)
    if (!messageId) {
      if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
        setError('이 기기에서는 질문을 읽어줄 수 없습니다. 화면의 글을 확인해 주세요.')
        return
      }
      window.speechSynthesis.cancel()
      const message = new SpeechSynthesisUtterance(question)
      message.lang = 'ko-KR'; message.rate = speed; message.volume = volume
      message.onerror = event => { if (event.error !== 'interrupted' && event.error !== 'canceled') setError('소리를 재생하지 못했습니다. 화면의 글을 확인해 주세요.') }
      window.speechSynthesis.speak(message)
      return
    }
    void request.run(async (api, signal) => {
      const session = parseSession(required((await api.GET('/me', { signal })).data))
      if (!session.consents.some(consent => consent.purpose === 'ai_processing')) throw new ApiError('CONSENT_REQUIRED', 403)
      const options = { signal, body: { target: { kind: 'journey_message', journey_id: journeyId, message_id: messageId }, segment: part }, params: { header: { 'Idempotency-Key': crypto.randomUUID() } }, parseAs: 'blob' } as const
      const response = await api.POST<'/speech', typeof options>('/speech', options)
      const value = required(response.data)
      const raw = response.response.headers.get('X-Speech-Segment-Count')
      const total = raw && /^[1-9]\d*$/.test(raw) ? Number(raw) : NaN
      if (!(value instanceof Blob) || value.type.split(';')[0] !== 'audio/wav' || !value.size || !Number.isSafeInteger(total) || part >= total || (count !== null && count !== total)) throw new ApiError('INVALID_RESPONSE')
      return { blob: value, count: total }
    }, result => setCount(result.count))
  }
  const pending = request.state.status === 'pending'
  return <>
    <div className="question-audio-actions" id="question-audio-actions"><Button variant="secondary" pending={pending} onClick={() => listen(1)}>다시 듣기</Button><Button variant="secondary" disabled={pending} onClick={() => listen(0.75)}>천천히 듣기</Button>
      {count !== null && segment + 1 < count && <Button variant="secondary" disabled={pending} onClick={() => listen(rate.current, segment + 1)}>다음 부분 듣기</Button>}</div>
    <div className="question-volume" id="question-volume">
      <label htmlFor="question-volume-range">소리 조절</label><input id="question-volume-range" type="range" min="0" max="1" step="0.1" value={volume} onChange={event => setVolume(Number(event.target.value))} /><span>{Math.round(volume * 100)}%</span>
    </div>
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    {error && <p role="alert">{error}</p>}
  </>
}
