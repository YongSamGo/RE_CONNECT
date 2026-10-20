import { useCallback, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { StatusNotice } from '../../ui/StatusNotice'

type Resources = { generation: number; mounted: boolean; busy: boolean; recorder: MediaRecorder | null; stream: MediaStream | null; timer: ReturnType<typeof setInterval> | null; url: string | null; chunks: Blob[]; size: number; player: HTMLAudioElement | null }
const maxBytes = 6 * 1024 * 1024
const formats = ['audio/webm;codecs=opus', 'audio/mp4;codecs=mp4a.40.2', 'audio/mp4']

export function VoicePreview({ onUseText }: { onUseText: (text: string) => void }) {
  const text = useMemoryScope(() => '')
  const clearText = text.clear
  const [status, setStatus] = useState<'idle' | 'permission' | 'recording' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [seconds, setSeconds] = useState(0)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const resources = useRef<Resources>({ generation: 0, mounted: true, busy: false, recorder: null, stream: null, timer: null, url: null, chunks: [], size: 0, player: null })

  const release = useCallback(() => {
    const current = resources.current
    if (current.player) { current.player.pause(); current.player.removeAttribute('src'); current.player.load(); current.player = null }
    current.generation += 1
    current.busy = false
    if (current.timer) clearInterval(current.timer)
    current.timer = null
    if (current.recorder) {
      current.recorder.ondataavailable = null
      current.recorder.onstop = null
      current.recorder.onerror = null
      if (current.recorder.state !== 'inactive') current.recorder.stop()
    }
    current.recorder = null
    current.stream?.getTracks().forEach((track) => { track.onended = null; track.stop() })
    current.stream = null
    if (current.url) URL.revokeObjectURL(current.url)
    current.url = null
    current.chunks = []
    current.size = 0
  }, [])
  function reset() {
    release(); text.clear(); setAudioUrl(null); setSeconds(0); setError(''); setStatus('idle')
  }
  useEffect(() => {
    const current = resources.current
    current.mounted = true
    const clear = () => { release(); clearText(); setAudioUrl(null); setSeconds(0); setError(''); setStatus('idle') }
    const restore = (event: PageTransitionEvent) => { if (event.persisted) clear() }
    window.addEventListener('pagehide', clear)
    window.addEventListener('pageshow', restore)
    return () => { current.mounted = false; release(); window.removeEventListener('pagehide', clear); window.removeEventListener('pageshow', restore) }
  }, [clearText, release])

  async function start() {
    const current = resources.current
    if (current.busy) return
    release(); setAudioUrl(null); setSeconds(0); setError(''); setStatus('idle')
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') { setError('이 브라우저에서는 녹음을 사용할 수 없어요. 글로 작성해 주세요.'); setStatus('error'); return }
    const mimeType = formats.find((format) => MediaRecorder.isTypeSupported(format))
    if (!mimeType) { setError('지원하는 녹음 형식이 없어요. 글로 작성해 주세요.'); setStatus('error'); return }
    const generation = current.generation
    current.busy = true
    setStatus('permission')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!current.mounted || generation !== current.generation) { stream.getTracks().forEach((track) => track.stop()); return }
      current.stream = stream
      const recorder = new MediaRecorder(stream, { mimeType })
      current.recorder = recorder
      const valid = () => current.mounted && generation === current.generation
      const fail = (message: string) => { if (!valid()) return; release(); setAudioUrl(null); setError(message); setStatus('error') }
      recorder.ondataavailable = (event) => {
        if (!valid() || !event.data.size) return
        current.size += event.data.size
        if (current.size > maxBytes) { fail('녹음 크기가 6MiB를 넘어 삭제했어요. 더 짧게 녹음하거나 글로 작성해 주세요.'); return }
        current.chunks.push(event.data)
      }
      recorder.onerror = () => fail('녹음하지 못했어요. 다시 녹음하거나 글로 작성해 주세요.')
      recorder.onstop = () => {
        if (!valid()) return
        if (current.timer) clearInterval(current.timer)
        current.timer = null
        current.stream?.getTracks().forEach((track) => { track.onended = null; track.stop() })
        current.stream = null
        current.recorder = null
        current.busy = false
        if (!current.size) { fail('녹음된 소리가 없어요. 다시 녹음하거나 글로 작성해 주세요.'); return }
        current.url = URL.createObjectURL(new Blob(current.chunks, { type: mimeType }))
        current.chunks = []
        setAudioUrl(current.url)
        setStatus('ready')
      }
      stream.getTracks().forEach((track) => { track.onended = () => fail('마이크 연결이 끊겨 녹음을 삭제했어요. 글로 작성하거나 다시 녹음해 주세요.') })
      recorder.start(250)
      const started = performance.now()
      current.timer = setInterval(() => {
        if (!valid()) return
        const elapsed = Math.floor((performance.now() - started) / 1000)
        setSeconds(Math.min(elapsed, 90))
        if (elapsed >= 90 && recorder.state === 'recording') recorder.stop()
      }, 250)
      setStatus('recording')
    } catch {
      if (!current.mounted || generation !== current.generation) return
      release(); setError('마이크 권한이 없거나 녹음을 시작하지 못했어요. 권한을 확인하거나 글로 작성해 주세요.'); setStatus('error')
    }
  }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">음성 입력 미리보기</p><h1>말로 경험을 연습해 봐요</h1><p>녹음 시작을 누르면 브라우저에 마이크 권한을 요청합니다.</p></header>
    <StatusNotice label="기기 내 녹음 연습" title="음성 인식은 아직 연결되지 않았어요">녹음은 현재 화면에서만 재생하며 서버에 보내지 않습니다. 자동 전사 결과는 제공하지 않습니다. 가상의 경험만 녹음해 주세요. 최대 90초·6MiB이며 화면을 떠나면 녹음이 삭제됩니다.</StatusNotice>
    <section className="panel"><h2>녹음하고 들어보기</h2><p role="status">{status === 'permission' ? '마이크 권한을 확인하고 있어요.' : status === 'recording' ? `녹음 중 · ${seconds} / 90초` : status === 'ready' ? '녹음이 끝났어요. 아래에서 들어볼 수 있습니다.' : '녹음은 시작 버튼을 누른 뒤에만 진행합니다.'}</p>
      <div className="actions"><Button disabled={status === 'permission' || status === 'recording'} onClick={() => void start()}>{audioUrl ? '다시 녹음하기' : '녹음 시작하기'}</Button>{status === 'recording' && <Button variant="secondary" onClick={() => { const recorder = resources.current.recorder; if (recorder?.state === 'recording') recorder.stop() }}>녹음 마치기</Button>}<Button variant="secondary" onClick={reset}>녹음·입력 취소하고 삭제</Button></div>
      {audioUrl && <audio ref={(element) => { if (element) resources.current.player = element }} className="voice-player" src={audioUrl} controls aria-label="내 녹음 들어보기" />}
      {status === 'error' && <StatusNotice kind="error" title="녹음을 사용할 수 없어요">{error}</StatusNotice>}
    </section>
    <section className="panel"><h2>직접 글로 확인하기</h2><TextAreaField label="확인한 경험 문장" value={text.value} onChange={(event) => text.setValue(event.target.value)} maxLength={2000} hint="자동 전사가 아닙니다. 녹음한 내용을 직접 적거나 글로 입력해 주세요. 기존 경험 입력을 이 문장으로 바꿉니다." /><Button disabled={!text.value.trim()} onClick={() => { const confirmed = text.value; reset(); onUseText(confirmed) }}>이 문장을 경험 입력에 사용하기</Button></section>
    <Link className="text-link" to="/conversation">글로 작성하는 화면으로 →</Link>
  </div>
}
