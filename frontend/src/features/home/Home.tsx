import './home.css'
import { useRef } from 'react'
import { Link } from 'react-router-dom'

const videos = import.meta.glob<string>('./media/intro.{mp4,webm}', { eager: true, query: '?url', import: 'default' })
const captions = import.meta.glob<string>('./media/intro.ko.vtt', { eager: true, query: '?url', import: 'default' })
const video = videos['./media/intro.mp4'] ?? videos['./media/intro.webm']
const caption = captions['./media/intro.ko.vtt']

export function Home() {
  const ambientRef = useRef<HTMLVideoElement>(null)
  const playerRef = useRef<HTMLVideoElement>(null)

  function syncAmbient() {
    const ambient = ambientRef.current
    const player = playerRef.current
    if (!ambient || !player) return
    if (Math.abs(ambient.currentTime - player.currentTime) > 0.1) ambient.currentTime = player.currentTime
    if (player.paused || player.ended) ambient.pause()
    else void ambient.play().catch(() => {})
  }

  return <>
    <div className="home-stage">
    {video && <video ref={ambientRef} className="home-ambient" src={video} muted playsInline preload="metadata" aria-hidden="true" tabIndex={-1} />}
    <section className="home-video" aria-label="다시잇다 소개">
      {video && <video ref={playerRef} className="home-player" controls preload="metadata" aria-label="다시잇다 소개 영상" src={video} onPlay={syncAmbient} onPause={syncAmbient} onSeeked={syncAmbient}>
        {caption && <track kind="captions" src={caption} srcLang="ko" label="한국어" default />}
      </video>}
      <div className="hero-copy">
        <h1>여러분의 이야기를 들려주세요</h1>
        <p className="hero-description">여러분의 이야기가 곧 새로운 기회가 됩니다</p>
      </div>
      <div className="hero-actions" aria-label="시작 메뉴">
        <Link className="button primary home-start" to="/start">시작하기</Link>
        <Link className="button secondary home-opportunities-button" to="/opportunities">모집 공고 살펴보기</Link>
      </div>
    </section>
  </div>
  </>
}
