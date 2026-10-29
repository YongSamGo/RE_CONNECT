import './home.css'
import { useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'

const videos = import.meta.glob<string>('./media/intro.{mp4,webm}', { eager: true, query: '?url', import: 'default' })
const captions = import.meta.glob<string>('./media/intro.ko.vtt', { eager: true, query: '?url', import: 'default' })
const video = videos['./media/intro.mp4'] ?? videos['./media/intro.webm']
const caption = captions['./media/intro.ko.vtt']

export function Home() {
  const playerRef = useRef<HTMLVideoElement>(null)
  const ambientRef = useRef<HTMLVideoElement>(null)

  function syncAmbient() {
    const player = playerRef.current
    const ambient = ambientRef.current
    if (!player || !ambient) return
    if (Math.abs(ambient.currentTime - player.currentTime) > 0.2) ambient.currentTime = player.currentTime
    if (player.paused || player.ended) ambient.pause()
    else if (ambient.paused) void ambient.play().catch(() => {})
  }

  useEffect(() => {
    const player = playerRef.current
    if (!player) return
    const retryPlayback = () => {
      if (player.paused) void player.play().catch(() => {})
    }
    document.addEventListener('pointerdown', retryPlayback)
    document.addEventListener('keydown', retryPlayback)
    return () => {
      document.removeEventListener('pointerdown', retryPlayback)
      document.removeEventListener('keydown', retryPlayback)
    }
  }, [])

  return <>
    <div className="home-stage">
    <section className="home-video" aria-label="다시잇다 소개">
      {video && <video ref={ambientRef} className="home-ambient" src={video} muted loop playsInline preload="metadata" aria-hidden="true" tabIndex={-1} />}
      <div className="hero-copy">
        <h1>여러분의 이야기를 들려주세요</h1>
        <p className="hero-description">여러분의 이야기가 곧 새로운 기회가 됩니다</p>
      </div>
      {video && <div className="home-foreground"><video ref={playerRef} className="home-player" autoPlay loop playsInline preload="metadata" aria-label="다시잇다 소개 영상" src={video} onPlay={syncAmbient} onPause={syncAmbient} onSeeked={syncAmbient} onTimeUpdate={syncAmbient}>
        {caption && <track kind="captions" src={caption} srcLang="ko" label="한국어" default />}
      </video></div>}
      <div className="hero-actions" aria-label="시작 메뉴">
        <Link className="button primary home-start" to="/start">시작하기</Link>
        <Link className="button secondary home-opportunities-button" to="/opportunities">모집 공고 살펴보기</Link>
      </div>
    </section>
  </div>
  </>
}
