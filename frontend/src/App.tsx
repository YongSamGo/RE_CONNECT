import { Component, lazy, Suspense, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, Route, Routes, matchPath, useLocation, useNavigate } from 'react-router-dom'
import { Button } from './ui/Button'
import { TextAreaField } from './ui/Fields'
import { useMemoryScope } from './state/useMemoryScope'
import { Home } from './features/home/Home'
import { consentNotices } from './features/consent/notice-content'
import { PublicOpportunities } from './features/public-opportunities/PublicOpportunities'
import { PublicOpportunityDetail } from './features/public-opportunities/PublicOpportunityDetail'
import { ManualPreparation } from './features/preparation/ManualPreparation'
import { OfficialPreparation } from './features/preparation/OfficialPreparation'
import { JourneyDraftPreparationRoute } from './features/preparation/JourneyDraftEditor'
import { emptyManualDraft } from './features/preparation/model'
import type { ManualDraft } from './features/preparation/model'
import { AccountPage } from './features/account/AccountPage'
import { LoginPage } from './features/account/LoginPage'
import { AuthResult } from './features/account/AuthResult'
import { PendingSave } from './features/account/PendingSave'
import { BeginSaveRoute } from './features/account/BeginSave'
import { SavedMaterials } from './features/account/SavedMaterials'
import { VoicePreview } from './features/voice/VoicePreview'
import { ProfilePreview } from './features/profile/ProfilePreview'
import { JourneyConversationRoute } from './features/conversation/JourneyConversation'
import { JourneyRecommendationsRoute } from './features/recommendations/JourneyRecommendations'
import { JourneyProfileRoute } from './features/profile/JourneyProfile'
import { StartJourney } from './features/journeys/StartJourney'
import { emptyPreferences } from './features/profile/model'
import type { ProfilePreferences } from './features/profile/model'
import './App.css'

const AdminPage = lazy(() => import('./features/admin/AdminPage').then(module => ({ default: module.AdminPage })))

// Preview-only memory. Never represents server consent, identity or confirmation.
type Preview = { consent: boolean; experience: string; draft: ManualDraft; preferences: ProfilePreferences }
const emptyPreview = (): Preview => ({ consent: false, experience: '', draft: emptyManualDraft(), preferences: emptyPreferences() })
const screens = [
  { path: '/', id: 'UX01', title: '시작' },
  { path: '/consent', id: 'UX02', title: 'AI 처리 안내' },
  { path: '/conversation', id: 'UX03', title: '경험 이야기' },
  { path: '/transcription', id: 'UX04', title: '음성 확인' },
  { path: '/profile', id: 'UX05', title: '프로필 확인' },
  { path: '/opportunities', id: 'UX06', title: '공고 살펴보기' },
  { path: '/opportunities/preview', id: 'UX07', title: '공고 상세' },
  { path: '/preparation', id: 'UX08', title: '신청 준비' },
  { path: '/me', id: 'UX09', title: '내 정보' },
  { path: '/admin', id: 'UX10', title: '운영자' },
] as const

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <main className="error-page"><h1>화면을 표시하지 못했습니다</h1><p role="alert">새로 시작해 주세요. 저장하지 않은 입력은 사라집니다.</p><a className="button primary" href="/">새로 시작하기</a></main>
    return this.props.children
  }
}

function Heading({ step, title, children }: { step: string; title: string; children: ReactNode }) {
  return <header className="page-heading"><p className="eyebrow">{step}</p><h1>{title}</h1><p>{children}</p></header>
}

function Consent() {
  const [selected, setSelected] = useState<number | null>(null)
  const dialogRef = useRef<HTMLDialogElement>(null)
  const notice = selected === null ? null : consentNotices[selected]
  useEffect(() => {
    if (selected !== null && dialogRef.current && !dialogRef.current.open) dialogRef.current.showModal()
  }, [selected])
  return <div className="consent-stage"><header className="consent-heading"><h1>시작하기 전에 확인해주세요</h1><p className="consent-introduction">여러분의 이야기를 AI가 듣고 정리합니다.<br />본인이나 다른 사람의 연락처·주민등록번호, 건강·병력 등 불필요한 개인정보는 입력하거나 말하지 마세요.</p></header>
    <div className="consent-topics">{consentNotices.map((item, index) => <div className="consent-topic" key={item.title}><span>{item.title}</span><button type="button" className="consent-topic-detail" aria-label={`${item.title} 자세히 보기`} onClick={() => setSelected(index)}>자세히 보기</button></div>)}</div>
    <dialog ref={dialogRef} className="consent-dialog" aria-labelledby="consent-dialog-title" onClose={() => setSelected(null)}>
      {notice && <>
        <header className="consent-dialog-header">
          <h2 id="consent-dialog-title" tabIndex={-1} autoFocus>{notice.title}</h2>
          <button type="button" className="consent-dialog-close" onClick={() => dialogRef.current?.close()}>닫기</button>
        </header>
        <div className="consent-dialog-content" tabIndex={0} role="region" aria-label={`${notice.title} 상세 안내`}>
          <p>{notice.summary}</p>
          {notice.sections.map(section => <section key={section.heading}>
            <h3>{section.heading}</h3>
            {section.paragraphs.map(paragraph => <p key={paragraph}>{paragraph}</p>)}
          </section>)}
        </div>
      </>}
    </dialog>
    <div className="consent-start"><button type="button" className="button primary" disabled>동의하고 대화 시작하기</button><Link className="consent-browse" to="/opportunities">일단 둘러볼래요</Link></div>
  </div>
}

function Conversation({ preview, onChange }: { preview: Preview; onChange: (value: string) => void }) {
  return <div className="conversation-stage"><div className="reading-width"><Heading step="경험 입력" title="어떤 일을 해오셨나요?">어디에서 어떤 일을 맡았는지 한 가지 적어 주세요.</Heading>
    <section className="panel experience-editor">
      <TextAreaField id="experience" label="내가 해온 일" value={preview.experience} onChange={(event) => onChange(event.target.value)} maxLength={2000} rows={6} hint="연락처나 주민등록번호, 상세 병력은 적지 마세요." placeholder="예: 동네 도서관에서 책을 정리하고 방문자를 안내했어요." />
      <div className="actions"><Link className="button primary" to="/profile">작성한 내용 확인하기</Link><Link className="text-link" to="/transcription">음성 입력 안내</Link></div></section>
    <p className="quiet">지금은 직접 적은 내용만 확인할 수 있어요. AI 정리는 아직 연결되지 않았어요.</p></div></div>
}

export default function App() {
  const { value: preview, setValue: setPreview, clear: clearPreview } = useMemoryScope<Preview>(emptyPreview)
  const [notice, setNotice] = useState('')
  const [largeText, setLargeText] = useState(() => {
    try { return localStorage.getItem('reconnect-large-text') === 'on' } catch { return false }
  })
  useEffect(() => {
    document.documentElement.classList.toggle('large-text', largeText)
    return () => document.documentElement.classList.remove('large-text')
  }, [largeText])
  const location = useLocation()
  const previousPath = useRef(location.pathname)
  const [endingKey, setEndingKey] = useState<string | null>(null)
  const navigate = useNavigate()
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const current = screens.find((screen) => screen.path === location.pathname)
      ?? (location.pathname === '/start' ? screens[1] : undefined)
      ?? (matchPath('/opportunities/:id/preparation', location.pathname) ? screens[7] : undefined)
      ?? (matchPath('/opportunities/:id', location.pathname) ? screens[6] : undefined)
      ?? (matchPath('/admin/*', location.pathname) ? screens[9] : undefined)
      ?? (matchPath('/journeys/:journeyId/conversation', location.pathname) ? screens[2] : undefined)
      ?? (matchPath('/journeys/:journeyId/recommendations', location.pathname) || location.pathname === '/recommendations' ? screens[5] : undefined)
      ?? (matchPath('/journeys/:journeyId/profile', location.pathname) ? screens[4] : undefined)
      ?? (matchPath('/journeys/:journeyId/save', location.pathname) || matchPath('/journeys/:journeyId/drafts/:draftId/save', location.pathname) ? screens[8] : undefined)
      ?? (matchPath('/journeys/:journeyId/opportunities/:opportunityId/preparation', location.pathname) || matchPath('/preparation/:legacyId', location.pathname) ? screens[7] : undefined)
      ?? (location.pathname === '/login' ? { title: '로그인' } : undefined)
      ?? (location.pathname === '/me/save' || location.pathname === '/me/saved' ? screens[8] : undefined)
      ?? (location.pathname === '/auth/result' ? screens[8] : undefined)
    document.title = `${current?.title ?? '페이지를 찾을 수 없어요'} | 다시잇다`
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname
      window.scrollTo(0, 0)
      mainRef.current?.focus({ preventScroll: true })
    }
  }, [location.pathname])
  useEffect(() => {
    // React memory can survive a full-page departure via the back/forward cache.
    const clearOnLeave = () => setNotice('')
    const clearOnRestore = (event: PageTransitionEvent) => { if (event.persisted) clearOnLeave() }
    window.addEventListener('pagehide', clearOnLeave)
    window.addEventListener('pageshow', clearOnRestore)
    return () => { window.removeEventListener('pagehide', clearOnLeave); window.removeEventListener('pageshow', clearOnRestore) }
  }, [])
  const endPreview = () => { setEndingKey(location.key); clearPreview(); setNotice('입력한 내용을 삭제했습니다. 새로 시작할 수 있어요.'); navigate('/', { replace: true }) }
  // End navigation may finish after state clears. Keep the guard pointed home
  // during that transition so an old route cannot redirect back to consent.
  const requirePreview = (children: ReactNode) => preview.consent ? children : <Navigate to={endingKey === location.key ? '/' : '/consent'} replace />
  return <>
    <a className="skip-link" href="#main">본문으로 바로가기</a>
    <header className="site-header"><Link className="brand" to="/" aria-label="다시잇다 시작 화면">다시잇다</Link><div className="header-actions">{location.pathname !== '/' && <Link className="text-size-toggle header-back" to="/">뒤로가기</Link>}<button type="button" className="text-size-toggle" aria-pressed={largeText} onClick={() => { const next = !largeText; setLargeText(next); try { localStorage.setItem('reconnect-large-text', next ? 'on' : 'off') } catch { /* Keep the choice for this visit. */ } }}>큰 글씨 보기</button><Link className="text-size-toggle header-login" to="/login">로그인</Link></div></header>
    {preview.consent && <div className="preview-toolbar"><p>지금 적는 내용은 새로고침하면 사라져요.</p><Button variant="compact" onClick={endPreview}>종료하고 삭제</Button></div>}
    <div className="status-line" role="status">{location.pathname === '/' || location.pathname === '/me' ? notice : ''}</div>
    <main id="main" ref={mainRef} tabIndex={-1}><Routes>
      <Route path="/" element={<Home />} />
      <Route path="/start" element={<StartJourney onStart={clearPreview} />} />
      <Route path="/consent" element={<Consent />} />
      <Route path="/conversation" element={requirePreview(<Conversation preview={preview} onChange={(value) => setPreview((previous) => ({ ...previous, experience: value, preferences: { ...previous.preferences, reviewed: false }, draft: { ...previous.draft, reviewed: false } }))} />)} />
      <Route path="/transcription" element={requirePreview(<VoicePreview onUseText={(experience) => { setPreview((previous) => ({ ...previous, experience, preferences: { ...previous.preferences, reviewed: false }, draft: { ...previous.draft, reviewed: false } })); navigate('/conversation') }} />)} />
      <Route path="/profile" element={requirePreview(<ProfilePreview experience={preview.experience} preferences={preview.preferences} onChange={(preferences) => setPreview((previous) => ({ ...previous, preferences, draft: { ...previous.draft, reviewed: false } }))} />)} />
      <Route path="/journeys/:journeyId/conversation" element={<JourneyConversationRoute />} />
      <Route path="/journeys/:journeyId/recommendations" element={<JourneyRecommendationsRoute />} />
      <Route path="/journeys/:journeyId/opportunities/:opportunityId/preparation" element={<JourneyDraftPreparationRoute />} />
      <Route path="/journeys/:journeyId/profile" element={<JourneyProfileRoute />} />
      <Route path="/opportunities" element={<PublicOpportunities />} />
      <Route path="/opportunities/:id" element={<PublicOpportunityDetail />} />
      <Route path="/opportunities/:id/preparation" element={<OfficialPreparation />} />
      <Route path="/preparation" element={requirePreview(<ManualPreparation draft={preview.draft} onChange={(draft) => setPreview((previous) => ({ ...previous, draft }))} />)} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/me" element={<AccountPage onSessionReset={clearPreview} onLogout={() => { clearPreview(); setNotice('현재 세션이 종료되어 입력 내용을 지웠습니다.') }} />} />
      <Route path="/auth/result" element={<AuthResult />} />
      <Route path="/me/save" element={<PendingSave />} />
      <Route path="/journeys/:journeyId/save" element={<BeginSaveRoute />} />
      <Route path="/journeys/:journeyId/drafts/:draftId/save" element={<BeginSaveRoute />} />
      <Route path="/me/saved" element={<SavedMaterials onSessionReset={clearPreview} />} />
      <Route path="/my" element={<Navigate to="/me" replace />} />
      <Route path="/transcript" element={<Navigate to="/transcription" replace />} />
      <Route path="/preparation/:legacyId" element={<div className="reading-width"><Heading step="주소 안내" title="작성 화면이 변경되었어요">아래에서 직접 작성 화면이나 공개 공고로 이동해 주세요. 이 주소는 특정 공고의 신청 준비 화면이 아닙니다.</Heading><div className="actions"><Link className="button primary" to="/preparation">직접 작성 화면으로 이동</Link><Link className="text-link" to="/opportunities">공개 공고 살펴보기</Link></div></div>} />
      <Route path="/recommendations" element={<div className="reading-width"><Heading step="추천 안내" title="추천은 확정 프로필 연동 후 제공해요">공고 탐색과 프로필 화면을 이용해 주세요.</Heading><div className="actions"><Link className="button primary" to="/opportunities">공개 공고 살펴보기</Link><Link className="text-link" to="/profile">프로필 화면으로</Link></div></div>} />
      <Route path="/admin/*" element={<Suspense fallback={<p className="reading-width quiet" role="status">운영 화면을 불러오고 있어요.</p>}><AdminPage /></Suspense>} />
      <Route path="*" element={<div className="reading-width"><Heading step="주소 확인" title="페이지를 찾을 수 없어요">주소를 확인하거나 시작 화면으로 돌아가 주세요.</Heading><Link className="button primary" to="/">시작 화면으로</Link></div>} />
    </Routes></main>
  </>
}
