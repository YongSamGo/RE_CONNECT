import { useEffect, useRef, useState } from 'react'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'
import { releasePlayer, revokeAudioUrl, STOP_QUESTION_AUDIO } from '../voice/media-resources'

export function QuestionAudio({ question, journeyId, messageId, autoPlay = false }: { question: string; journeyId: string; messageId: string | null; autoPlay?: boolean }) {
  const [volume, setVolume] = useState(1)
  const [error, setError] = useState('')
  const [segment, setSegment] = useState(0)
  const [count, setCount] = useState<number | null>(null)
  const rate = useRef(1)
  const audio = useRef<HTMLAudioElement | null>(null)
  const utterance = useRef<SpeechSynthesisUtterance | null>(null)
  const request = useRequest<{ blob: Blob; count: number }>()
  const blob = request.state.status === 'success' ? request.state.data.blob : null
  function stopSpeaking() {
    if (utterance.current) {
      utterance.current.onerror = null
      utterance.current = null
      try { window.speechSynthesis?.cancel() } catch { /* Already invalidated; keep text controls usable. */ }
    }
  }
  function stopAll() { request.clear(); releasePlayer(audio.current); audio.current = null; stopSpeaking(); setError('') }
  function speakLocally(speed: number, quiet = false) {
    if (!('speechSynthesis' in window) || typeof SpeechSynthesisUtterance === 'undefined') {
      if (!quiet) setError('이 기기에서는 질문을 읽어줄 수 없습니다. 화면의 글을 확인해 주세요.')
      return
    }
    try {
      const message = new SpeechSynthesisUtterance(question)
      utterance.current = message
      // 기기 안에서 읽는 한국어 음성을 먼저 고른다. 없으면 브라우저가 언어로 고른다.
      const voices = (typeof window.speechSynthesis.getVoices === 'function' ? window.speechSynthesis.getVoices() ?? [] : []).filter(voice => voice.lang.toLowerCase().startsWith('ko'))
      const voice = voices.find(voice => voice.localService) ?? voices[0]
      if (voice) message.voice = voice
      message.lang = 'ko-KR'; message.rate = speed; message.volume = volume
      // 자동 읽기는 브라우저가 막아도(not-allowed) 오류를 띄우지 않는다. 버튼으로 다시 들을 수 있다.
      message.onerror = event => { if (!quiet && utterance.current === message && event.error !== 'interrupted' && event.error !== 'canceled') setError('소리를 재생하지 못했습니다. 화면의 글을 확인해 주세요.') }
      window.speechSynthesis.speak(message)
    } catch { if (!quiet) setError('소리를 재생하지 못했습니다. 화면의 글을 확인해 주세요.') }
  }
  useEffect(() => {
    const stop = () => stopSpeaking()
    window.addEventListener('pagehide', stop)
    return () => { window.removeEventListener('pagehide', stop); stop() }
  }, [question])
  useEffect(() => {
    const stop = () => stopAll()
    window.addEventListener(STOP_QUESTION_AUDIO, stop)
    return () => window.removeEventListener(STOP_QUESTION_AUDIO, stop)
  // stopAll은 현재 재생 참조만 정리한다.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    // 새 질문은 기기 음성으로 바로 읽는다. 서버 음성은 공유 추론 슬롯과 일일 한도를 쓰므로 '다시 듣기'에서만 부른다.
    if (autoPlay) speakLocally(1, true)
  // 질문마다 컴포넌트를 새로 만들므로 처음 한 번만 읽는다.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  useEffect(() => {
    if (!blob) return
    let url: string | null = null
    let player: HTMLAudioElement | null = null
    let active = true
    const failed = () => { if (active) setError('소리를 재생하지 못했습니다. 화면의 글을 확인해 주세요.') }
    try {
      url = URL.createObjectURL(blob)
      player = new Audio(url)
      audio.current = player
      player.volume = volume
      player.playbackRate = rate.current
      player.onerror = failed
      void player.play().catch(failed)
    } catch { failed() }
    return () => { active = false; releasePlayer(player); revokeAudioUrl(url); if (audio.current === player) audio.current = null }
  // Volume changes are applied to the existing player below.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [blob])
  useEffect(() => { if (audio.current) audio.current.volume = volume }, [volume])

  function listen(speed: number, part = 0) {
    if (request.state.status === 'pending') return
    request.clear()
    releasePlayer(audio.current)
    audio.current = null
    stopSpeaking()
    setError('')
    rate.current = speed
    setSegment(part)
    if (!messageId) {
      speakLocally(speed)
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
      {count !== null && segment + 1 < count && <Button variant="secondary" disabled={pending} onClick={() => listen(rate.current, segment + 1)}>다음 부분 듣기</Button>}
      <Button variant="secondary" onClick={stopAll}>듣기 중지</Button></div>
    <div className="question-volume" id="question-volume">
      <label htmlFor="question-volume-range">소리 조절</label><input id="question-volume-range" type="range" min="0" max="1" step="0.1" value={volume} onChange={event => setVolume(Number(event.target.value))} /><span>{Math.round(volume * 100)}%</span>
    </div>
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    {error && <p role="alert">{error}</p>}
  </>
}
