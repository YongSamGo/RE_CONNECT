import { Component, Suspense, lazy, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, Navigate, Route, Routes, matchPath, useLocation, useNavigate, useParams } from 'react-router-dom'
import { Home } from './features/home/Home'
import { PublicOpportunities } from './features/public-opportunities/PublicOpportunities'
import { PublicCatalogProvider } from './features/public-opportunities/PublicCatalogState'
import { PublicOpportunityDetail } from './features/public-opportunities/PublicOpportunityDetail'
import { JourneyDraftApplicationRoute } from './features/preparation/JourneyDraftEditor'
import { AccountHeaderActions } from './features/account/AccountHeaderActions'
import { LoginPage } from './features/account/LoginPage'
import { AuthResult } from './features/account/AuthResult'
import { JourneyConversation, JourneyConversationRoute } from './features/conversation/JourneyConversation'
import { JourneyRecommendations, JourneyRecommendationsRoute } from './features/recommendations/JourneyRecommendations'
import { StartJourney } from './features/journeys/StartJourney'
import { JourneyProfile, JourneyProfileRoute } from './features/profile/JourneyProfile'
import { MemberHome } from './features/account/MemberHome'
import { PendingSave } from './features/account/PendingSave'
import { BeginSaveRoute } from './features/account/BeginSave'
import { KakaoFlowPrototype, OpportunityApplicationFlowPrototype } from './features/development/FlowPrototypes'
import { ServiceGuide } from './features/journeys/ServiceGuide'
import { JourneyMap } from './features/journeys/JourneyMap'
import { ScreenReview } from './features/development/ScreenReview'
import { reviewHref, screens as reviewScreens } from './features/development/review-screens'
import { ConversationEntry } from './features/journeys/ServiceEntries'
import './App.css'

const AdminPage = lazy(() => import('./features/admin/AdminPage').then(({ AdminPage }) => ({ default: AdminPage })))

function LegacyJourneyPreparationRedirect() {
  const { journeyId, opportunityId } = useParams()
  return <Navigate to={journeyId && opportunityId ? `/journeys/${journeyId}/opportunities/${opportunityId}/application` : '/recommendations'} replace />
}

function LegacyOpportunityPreparationRedirect() {
  const { id } = useParams()
  return <Navigate to={id ? `/opportunities/${id}` : '/opportunities'} replace />
}

function AuthReturn() {
  const { search } = useLocation()
  const status = new URLSearchParams(search).get('status')
  return status === 'success' ? <Navigate to="/me" replace /> : <AuthResult />
}

const screens = [
  { path: '/', id: 'UX01', title: '시작' },
  { path: '/consent', id: 'UX02', title: 'AI 처리 안내' },
  { path: '/conversation', id: 'UX03', title: '경험 이야기' },
  { path: '/transcription', id: 'UX04', title: '음성 확인' },
  { path: '/profile', id: 'UX05', title: '프로필 확인' },
  { path: '/opportunities', id: 'UX06', title: '공고 살펴보기' },
  { path: '/opportunities/preview', id: 'UX07', title: '공고 상세' },
  { path: '/me', id: 'UX08', title: '나의 정보' },
  { path: '/me/story', id: 'UX10', title: '나의 이야기' },
  { path: '/me/saved', id: 'UX11', title: '저장한 공고' },
  { path: '/admin', id: 'UX09', title: '운영자' },
] as const

function DevelopmentNavigation() {
  const { pathname, search } = useLocation()
  const isReview = window.location.hostname === '127.0.0.1' && window.location.port === '5190'
  const key = pathname === '/' ? 'home' : pathname === '/start' ? 'start'
    : pathname === '/dev/conversation' || matchPath('/journeys/:journeyId/conversation', pathname) ? 'conversation'
    : pathname === '/dev/profile' || matchPath('/journeys/:journeyId/profile', pathname) ? 'profile'
    : matchPath('/journeys/:journeyId/recommendations', pathname) ? 'recommendations'
    : pathname === '/opportunities' ? (new URLSearchParams(search).get('browse') === 'all' ? 'catalog' : 'filter')
    : matchPath('/opportunities/:id', pathname) ? 'detail'
    : matchPath('/journeys/:journeyId/opportunities/:opportunityId/application', pathname) ? 'application'
    : pathname === '/me/save' || matchPath('/journeys/:journeyId/save', pathname) ? 'save'
    : pathname === '/me' || pathname === '/me/saved' || pathname === '/me/settings' ? 'member'
    : pathname === '/auth/result' ? 'auth'
    : pathname === '/login' ? 'login' : pathname === '/guide' ? 'guide' : undefined
  const index = key ? reviewScreens.findIndex(([screen]) => screen === key) : -1
  const atList = pathname === '/dev/screens'
  const reviewLink = (screen: string, label: string) => <a href={reviewHref(screen)} onClick={event => { event.currentTarget.href = reviewHref(screen) }}>{label}</a>
  return <nav className="development-navigation" aria-label="개발용 화면 이동">
    <span>개발용 화면 이동{isReview && index >= 0 ? ` ${index + 1} / ${reviewScreens.length}` : ''}</span>
    {isReview && index >= 0 && (index > 0 ? reviewLink(reviewScreens[index - 1][0], '이전 화면') : <Link to="/dev/screens">이전 화면</Link>)}
    {isReview && (atList || index >= 0 && index < reviewScreens.length - 1) && reviewLink(reviewScreens[atList ? 0 : index + 1][0], '다음 화면')}
    <Link to="/dev/screens">작업한 화면 보기</Link>
  </nav>
}

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

export default function App() {
  const [notice, setNotice] = useState('')
  const [largeText, setLargeText] = useState(() => {
    try { return localStorage.getItem('reconnect-large-text') === 'on' } catch { return false }
  })
  const [highContrast, setHighContrast] = useState(() => {
    try { return localStorage.getItem('reconnect-high-contrast') === 'on' } catch { return false }
  })
  useEffect(() => {
    document.documentElement.classList.toggle('large-text', largeText)
    return () => document.documentElement.classList.remove('large-text')
  }, [largeText])
  useEffect(() => {
    document.documentElement.classList.toggle('high-contrast', highContrast)
    return () => document.documentElement.classList.remove('high-contrast')
  }, [highContrast])
  const location = useLocation()
  const navigate = useNavigate()
  const applicationRoute = matchPath('/journeys/:journeyId/opportunities/:opportunityId/application', location.pathname)
  const previousPath = useRef(location.pathname)
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const entryTitles: Record<string, string> = { '/guide': '이용 안내', '/journey-map': '이용 흐름 지도', '/voice': '음성 입력', '/dev/screens': '개발용 화면 확인', '/dev/profile': '내 경험 확인', '/me/settings': '계정 설정', '/me/save': '자료 저장', '/me/saved': '지원서' }
    const current = (entryTitles[location.pathname] ? { title: entryTitles[location.pathname] } : undefined) ?? screens.find((screen) => screen.path === location.pathname)
      ?? (location.pathname === '/start' ? screens[1] : undefined)
      ?? (import.meta.env.DEV && location.pathname === '/dev/conversation' ? screens[2] : undefined)
      ?? (matchPath('/opportunities/:id/preparation', location.pathname) ? screens[6] : undefined)
      ?? (matchPath('/opportunities/:id', location.pathname) ? screens[6] : undefined)
      ?? (matchPath('/admin/*', location.pathname) ? screens[8] : undefined)
      ?? (matchPath('/journeys/:journeyId/conversation', location.pathname) ? screens[2] : undefined)
      ?? (matchPath('/journeys/:journeyId/recommendations', location.pathname) || location.pathname === '/recommendations' ? screens[5] : undefined)
      ?? (matchPath('/journeys/:journeyId/profile', location.pathname) ? { title: '내 경험 확인' } : undefined)
      ?? (matchPath('/journeys/:journeyId/opportunities/:opportunityId/application', location.pathname) ? { title: '다음 내용으로 지원서를 작성할게요' } : undefined)
      ?? (location.pathname === '/login' ? { title: '로그인' } : undefined)
      ?? (location.pathname === '/me/profile' || location.pathname === '/me/story' ? { title: '나의 정보' } : undefined)
      ?? (location.pathname === '/auth/result' ? { title: '로그인 결과' } : undefined)
      ?? (location.pathname === '/dev/kakao-flow' ? { title: '카카오 로그인 흐름' } : undefined)
      ?? (location.pathname === '/dev/opportunity-flow' ? { title: '공고 신청 흐름' } : undefined)
      ?? (location.pathname === '/dev/recommendations' ? { title: '경험 기반 추천 공고' } : undefined)
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
  return <div className={`app-shell${import.meta.env.DEV ? ' development-mode' : ''}`}>
    <a className="skip-link" href="#main">본문으로 바로가기</a>
    <header className="site-header"><Link className="brand" to="/" aria-label="다시잇다 시작 화면"><img src="/brand/symbols/dasieitda-symbol.png" alt="" /><span className="brand-name">다시잇다</span></Link><div className="header-actions">{location.pathname !== '/' && <button type="button" className="text-size-toggle header-back" onClick={() => { if (applicationRoute?.params.journeyId && applicationRoute.params.opportunityId) navigate(`/opportunities/${applicationRoute.params.opportunityId}?journeyId=${applicationRoute.params.journeyId}`); else if (window.history.state?.idx > 0) navigate(-1); else navigate("/") }}>뒤로가기</button>}<Link className="text-size-toggle header-terms" to="/guide#terms">이용약관 및 정보 처리</Link><button type="button" className="text-size-toggle" aria-pressed={largeText} onClick={() => { const next = !largeText; setLargeText(next); try { localStorage.setItem('reconnect-large-text', next ? 'on' : 'off') } catch { /* Keep the choice for this visit. */ } }}>큰 글씨 보기</button><button type="button" className="text-size-toggle" aria-pressed={highContrast} onClick={() => { const next = !highContrast; setHighContrast(next); try { localStorage.setItem('reconnect-high-contrast', next ? 'on' : 'off') } catch { /* Keep the choice for this visit. */ } }}>선명하게 보기</button><AccountHeaderActions /></div></header>
    <div className="status-line" role="status">{location.pathname === '/' || location.pathname === '/me' ? notice : ''}</div>
    <main id="main" ref={mainRef} className={location.pathname === '/journey-map' ? 'journey-map-main' : undefined} tabIndex={-1}><PublicCatalogProvider><Routes>
      <Route path="/" element={<Home />} />
      <Route path="/start" element={<StartJourney onStart={() => setNotice('')} />} />
      <Route path="/consent" element={<Navigate to="/start" replace />} />
      <Route path="/guide" element={<ServiceGuide />} />
      {import.meta.env.DEV && <Route path="/journey-map" element={<JourneyMap />} />}
      {import.meta.env.DEV && <Route path="/dev/screens" element={<ScreenReview />} />}
      <Route path="/conversation" element={<ConversationEntry />} />
      {import.meta.env.DEV && <Route path="/dev/conversation" element={<JourneyConversation journeyId="12345678-1234-1234-1234-123456789012" />} />}
      {import.meta.env.DEV && <Route path="/dev/profile" element={<JourneyProfile journeyId="12345678-1234-1234-1234-123456789012" autoLoad />} />}
      {import.meta.env.DEV && <Route path="/dev/recommendations" element={<OpportunityApplicationFlowPrototype recommended />} />}
      {import.meta.env.DEV && <Route path="/dev/kakao-flow" element={<KakaoFlowPrototype />} />}
      {import.meta.env.DEV && <Route path="/dev/opportunity-flow" element={<OpportunityApplicationFlowPrototype />} />}
      <Route path="/voice" element={<Navigate to="/conversation" replace />} />
      <Route path="/transcription" element={<Navigate to="/conversation" replace />} />
      <Route path="/results" element={<Navigate to="/recommendations" replace />} />
      <Route path="/profile/review" element={<Navigate to="/recommendations" replace />} />
      <Route path="/eligibility" element={<Navigate to="/recommendations" replace />} />
      <Route path="/application" element={<Navigate to="/recommendations" replace />} />
      <Route path="/save" element={<Navigate to="/me" replace />} />
      <Route path="/save/result" element={<Navigate to="/me" replace />} />
      <Route path="/profile" element={<Navigate to="/me/story" replace />} />
      <Route path="/journeys/:journeyId/conversation" element={<JourneyConversationRoute />} />
      <Route path="/journeys/:journeyId/results" element={<JourneyProfileRoute />} />
      <Route path="/journeys/:journeyId/recommendations" element={<JourneyRecommendationsRoute />} />
      <Route path="/journeys/:journeyId/opportunities/:opportunityId/preparation" element={<LegacyJourneyPreparationRedirect />} />
      <Route path="/journeys/:journeyId/opportunities/:opportunityId/application" element={<JourneyDraftApplicationRoute />} />
      <Route path="/journeys/:journeyId/profile" element={<JourneyProfileRoute />} />
      <Route path="/opportunities" element={<PublicOpportunities />} />
      <Route path="/opportunities/detail" element={<Navigate to="/start" replace />} />
      <Route path="/opportunities/:id" element={<PublicOpportunityDetail />} />
      <Route path="/opportunities/:id/preparation" element={<LegacyOpportunityPreparationRedirect />} />
      <Route path="/preparation" element={<Navigate to="/opportunities" replace />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/me" element={<MemberHome />} />
      <Route path="/me/story" element={<Navigate to="/me" replace />} />
      <Route path="/me/settings" element={<Navigate to="/me" replace />} />
      <Route path="/me/profile" element={<Navigate to="/me" replace />} />
      <Route path="/auth/result" element={<AuthReturn />} />
      <Route path="/me/save" element={<PendingSave autoLoad />} />
      <Route path="/journeys/:journeyId/save" element={<BeginSaveRoute />} />
      <Route path="/journeys/:journeyId/drafts/:draftId/save" element={<Navigate to="/me" replace />} />
      <Route path="/me/saved" element={<Navigate to="/me" replace />} />
      <Route path="/my" element={<Navigate to="/me" replace />} />
      <Route path="/transcript" element={<Navigate to="/transcription" replace />} />
      <Route path="/preparation/:legacyId" element={<Navigate to="/opportunities" replace />} />
      <Route path="/recommendations" element={<JourneyRecommendations />} />
      <Route path="/admin/*" element={<Suspense fallback={<p className="reading-width quiet" role="status">운영 화면을 불러오고 있어요.</p>}><AdminPage /></Suspense>} />
      <Route path="*" element={<div className="reading-width"><Heading step="주소 확인" title="페이지를 찾을 수 없어요">주소를 확인하거나 시작 화면으로 돌아가 주세요.</Heading><Link className="button primary" to="/">시작 화면으로</Link></div>} />
    </Routes></PublicCatalogProvider></main>
    {import.meta.env.DEV && <DevelopmentNavigation />}
  </div>
}
