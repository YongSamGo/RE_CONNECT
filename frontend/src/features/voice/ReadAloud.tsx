import { useEffect, useRef, useState } from 'react'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'

export function ReadAloud({ target, label }: { target: components['schemas']['SpeechTarget']; label: string }) {
  const request = useRequest<Blob>()
  const [failed, setFailed] = useState(false)
  const [playing, setPlaying] = useState(false)
  const audio = useRef<HTMLAudioElement | null>(null)
  const state = request.state
  const blob = state.status === 'success' ? state.data : null
  useEffect(() => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const player = new Audio(url)
    audio.current = player
    let active = true
    player.onended = () => { if (active) setPlaying(false) }
    const failure = () => { if (active) { setPlaying(false); setFailed(true) } }
    player.onerror = failure
    void player.play().then(() => { if (active) setPlaying(true) }).catch(failure)
    return () => { active = false; player.onended = null; player.onerror = null; player.pause(); player.removeAttribute('src'); player.load(); URL.revokeObjectURL(url); if (audio.current === player) audio.current = null }
  }, [blob])
  const pending = state.status === 'pending'
  return <div className="read-aloud"><div className="actions"><Button variant="secondary" pending={pending} disabled={!!blob && playing} pendingLabel="읽을 소리를 준비하고 있어요…" onClick={() => { setFailed(false); setPlaying(false); void request.run(async (api, signal) => {
    const session = parseSession(required((await api.GET('/me', { signal })).data))
    if (!session.consents.some((consent) => consent.purpose === 'ai_processing')) throw new ApiError('CONSENT_REQUIRED', 403)
    const options = { signal, body: { target, segment: 0 }, params: { header: { 'Idempotency-Key': crypto.randomUUID() } }, parseAs: 'blob' } as const
    const response = await api.POST<'/speech', typeof options>('/speech', options)
    const result = required(response.data)
    if (!(result instanceof Blob) || result.type.split(';')[0] !== 'audio/wav' || result.size === 0) throw new ApiError('INVALID_RESPONSE')
    return result
  }) }}>{label}</Button>{(pending || blob) && <Button variant="secondary" onClick={() => { audio.current?.pause(); setPlaying(false); setFailed(false); request.clear() }}>읽어주기 중지</Button>}</div>
    <p role="status">{blob && playing ? '읽어주기를 재생하고 있어요.' : ''}</p>
    {state.status === 'error' && <RequestError error={state.error} />}
    {blob && failed && <p role="alert">소리를 재생하지 못했어요. 화면의 글을 계속 읽거나 다시 시도해 주세요.</p>}
    <p className="quiet">서버에서 AI 처리 동의가 확인된 경우에만 요청합니다. 현재 동의문·음성 서버 연결은 준비 중입니다.</p>
  </div>
}
