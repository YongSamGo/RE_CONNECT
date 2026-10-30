import { useCallback, useEffect, useRef, useState } from 'react'
import { useMemoryScope } from '../../state/useMemoryScope'
import { recordingType, releasePlayer, releaseRecorder, revokeAudioUrl, stopTracks } from './media-resources'

type Resources = { generation: number; mounted: boolean; busy: boolean; recorder: MediaRecorder | null; stream: MediaStream | null; timer: ReturnType<typeof setInterval> | null; url: string | null; chunks: Blob[]; size: number; player: HTMLAudioElement | null }
const maxBytes = 6 * 1024 * 1024

export function useAudioRecorder() {
  const audio = useMemoryScope<Blob | null>(() => null)
  const clearAudio = audio.clear, setAudio = audio.setValue
  const [status, setStatus] = useState<'idle' | 'permission' | 'recording' | 'ready' | 'error'>('idle')
  const [error, setError] = useState('')
  const [seconds, setSeconds] = useState(0)
  const [audioUrl, setAudioUrl] = useState<string | null>(null)
  const resources = useRef<Resources>({ generation: 0, mounted: true, busy: false, recorder: null, stream: null, timer: null, url: null, chunks: [], size: 0, player: null })

  const release = useCallback(() => {
    const current = resources.current
    current.generation += 1
    current.busy = false
    if (current.timer) clearInterval(current.timer)
    current.timer = null
    const { player, recorder, stream, url } = current
    current.player = null
    current.recorder = null
    current.stream = null
    current.url = null
    current.chunks = []
    current.size = 0
    clearAudio()
    releasePlayer(player); releaseRecorder(recorder); stopTracks(stream); revokeAudioUrl(url)
  }, [clearAudio])
  function reset() {
    release(); setAudioUrl(null); setSeconds(0); setError(''); setStatus('idle')
  }
  useEffect(() => {
    const current = resources.current
    current.mounted = true
    const clear = () => { release(); setAudioUrl(null); setSeconds(0); setError(''); setStatus('idle') }
    const restore = (event: PageTransitionEvent) => { if (event.persisted) clear() }
    window.addEventListener('pagehide', clear)
    window.addEventListener('pageshow', restore)
    return () => { current.mounted = false; release(); window.removeEventListener('pagehide', clear); window.removeEventListener('pageshow', restore) }
  }, [release])

  async function start() {
    const current = resources.current
    if (current.busy) return
    release(); setAudioUrl(null); setSeconds(0); setError(''); setStatus('idle')
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined' || typeof MediaRecorder.isTypeSupported !== 'function') { setError('이 브라우저에서는 녹음을 사용할 수 없어요. 글로 작성해 주세요.'); setStatus('error'); return }
    const mimeType = recordingType()
    if (!mimeType) { setError('지원하는 녹음 형식이 없어요. 글로 작성해 주세요.'); setStatus('error'); return }
    const generation = current.generation
    current.busy = true
    setStatus('permission')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!current.mounted || generation !== current.generation) { stopTracks(stream); return }
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
        stopTracks(current.stream)
        current.stream = null
        current.recorder = null
        current.busy = false
        if (!current.size) { fail('녹음된 소리가 없어요. 다시 녹음하거나 글로 작성해 주세요.'); return }
        try {
          const blob = new Blob(current.chunks, { type: mimeType })
          current.url = URL.createObjectURL(blob)
          setAudio(blob)
          current.chunks = []
          setAudioUrl(current.url)
          setStatus('ready')
        } catch { fail('녹음을 확인하지 못했어요. 다시 녹음하거나 글로 작성해 주세요.') }
      }
      stream.getTracks().forEach((track) => { track.onended = () => fail('마이크 연결이 끊겨 녹음을 삭제했어요. 글로 작성하거나 다시 녹음해 주세요.') })
      recorder.start(250)
      const started = performance.now()
      current.timer = setInterval(() => {
        if (!valid()) return
        const elapsed = Math.floor((performance.now() - started) / 1000)
        setSeconds(Math.min(elapsed, 90))
        if (elapsed >= 90 && recorder.state === 'recording') { try { recorder.stop() } catch { fail('녹음을 마치지 못했어요. 다시 녹음하거나 글로 작성해 주세요.') } }
      }, 250)
      setStatus('recording')
    } catch {
      if (!current.mounted || generation !== current.generation) return
      release(); setError('마이크 권한이 없거나 녹음을 시작하지 못했어요. 권한을 확인하거나 글로 작성해 주세요.'); setStatus('error')
    }
  }
  return { status, error, seconds, audioUrl, blob: audio.value, start, reset,
    cleanupForCurrentRecording: () => {
      const generation = resources.current.generation
      return () => { if (generation === resources.current.generation) reset() }
    },
    stop: () => {
      const recorder = resources.current.recorder
      if (recorder?.state !== 'recording') return
      try { recorder.stop() }
      catch { release(); setAudioUrl(null); setError('녹음을 마치지 못했어요. 다시 녹음하거나 글로 작성해 주세요.'); setStatus('error') }
    },
    setPlayer: (element: HTMLAudioElement | null) => { if (element) resources.current.player = element },
  }
}
