import { Component, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Button } from './ui/Button'
import { CheckboxField, TextAreaField } from './ui/Fields'
import { StatusNotice } from './ui/StatusNotice'
import { useMemoryScope } from './state/useMemoryScope'
import { PublicOpportunities } from './features/public-opportunities/PublicOpportunities'
import { PublicOpportunityDetail } from './features/public-opportunities/PublicOpportunityDetail'
import { ManualPreparation } from './features/preparation/ManualPreparation'
import { emptyManualDraft } from './features/preparation/model'
import type { ManualDraft } from './features/preparation/model'
import { AccountPage } from './features/account/AccountPage'
import { SavedMaterials } from './features/account/SavedMaterials'
import { AdminPage } from './features/admin/AdminPage'
import { VoicePreview } from './features/voice/VoicePreview'
import { ProfilePreview } from './features/profile/ProfilePreview'
import { emptyPreferences } from './features/profile/model'
import type { ProfilePreferences } from './features/profile/model'
import './App.css'

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
function Pending({ title, children }: { title: string; children: ReactNode }) {
  return <StatusNotice title={title}>{children}</StatusNotice>
}

function Home() {
  return <>
    <section className="hero"><div className="hero-copy"><p className="eyebrow">경험은 이어지고, 기회는 새로워집니다</p>
      <h1>당신의 경험에<br />새로운 <span>쓰임을 잇다.</span></h1>
      <p className="hero-description">해온 일과 좋아하는 일을 이야기해 주세요.<br className="desktop-break" /> 나에게 맞는 일자리와 봉사 기회를 함께 찾아갑니다.</p>
      <div className="actions"><Link className="button primary" to="/consent">내 경험 이야기하기 <span aria-hidden="true">↗</span></Link><Link className="text-link" to="/opportunities">공고부터 살펴보기 <span aria-hidden="true">→</span></Link></div>
      <p className="quiet">회원가입 없이 시작할 수 있어요.</p></div>
      <aside className="journey-card" aria-label="서비스 이용 순서"><div className="card-topline"><span>나의 다음 걸음</span><span aria-hidden="true">✳</span></div>
        <ol><li><span className="step-number">01</span><div><strong>경험을 이야기해요</strong><p>작은 일도 소중한 경험이에요.</p></div></li><li><span className="step-number">02</span><div><strong>내가 직접 확인해요</strong><p>정리된 내용을 고치고 확정해요.</p></div></li><li><span className="step-number">03</span><div><strong>새로운 기회를 만나요</strong><p>조건을 비교하고 신청을 준비해요.</p></div></li></ol>
        <p className="card-footnote">내 속도에 맞춰, 한 걸음씩.</p></aside></section>
    <section className="principles" aria-labelledby="principles-heading"><div><p className="eyebrow">처음이어도 괜찮아요</p><h2 id="principles-heading">다시 시작하는 길,<br />이렇게 함께해요.</h2></div>
      <article><span className="principle-icon" aria-hidden="true">가</span><h3>쉽게, 한 가지씩</h3><p>한 번에 한 질문으로 경험을 정리해요. 언제든 확인 화면으로 이동할 수 있어요.</p></article>
      <article><span className="principle-icon" aria-hidden="true">✓</span><h3>결정은 내가 직접</h3><p>AI가 정리한 내용은 초안이에요. 내가 확인하고 확정한 정보만 사용해요.</p></article>
      <article><span className="principle-icon" aria-hidden="true">↗</span><h3>신청은 공식 안내에서</h3><p>서류와 조건을 함께 살펴보고, 실제 신청은 공식 신청처에서 진행해요.</p></article></section>
  </>
}

function Consent({ onStart }: { onStart: () => void }) {
  const [checked, setChecked] = useState(false)
  return <div className="reading-width"><Heading step="시작하기 전에" title="내 정보가 어떻게 쓰이나요?">내용을 읽고, 편한 방법을 선택해 주세요.</Heading>
    <section className="panel"><h2>AI는 경험 정리를 도와요</h2><p>운영 서비스에서는 AWS EC2 안의 자체 AI 모델이 대화·음성 인식·읽어주기를 처리할 예정입니다. 사용자 기기 안에서만 처리되는 방식은 아닙니다.</p>
      <h2>확정과 저장은 따로예요</h2><p>AI가 만든 초안은 직접 고치고 확정합니다. 회원 저장은 별도의 로그인과 저장 동의 후에만 진행합니다.</p>
      <h2>지금은 화면 미리보기예요</h2><p>개인 체험의 AI 처리·서버 보관·회원 저장은 연결되지 않았습니다. 아래에서 입력한 내용은 이 화면의 메모리에서만 사용하며 새로고침하거나 종료하면 사라집니다. 실제 개인정보는 입력하지 마세요.</p>
      <p className="policy-draft">안내문 초안 · 운영 주체, 문의처, AWS 리전과 실제 보관·삭제 안내는 확인 후 확정해야 합니다. 이 선택은 운영 서비스의 처리 동의로 기록되지 않습니다.</p>
      <form onSubmit={(event) => { event.preventDefault(); if (checked) onStart() }}>
        <CheckboxField label="안내를 확인했고, 가상의 경험으로 화면을 살펴볼게요." checked={checked} onChange={(event) => setChecked(event.target.checked)} />
        <div className="actions"><Button type="submit" disabled={!checked}>미리보기 시작하기 <span aria-hidden="true">→</span></Button><Link className="text-link" to="/opportunities">공고 화면 살펴보기</Link></div></form>
    </section></div>
}

function Conversation({ preview, onChange }: { preview: Preview; onChange: (value: string) => void }) {
  return <div className="reading-width"><Heading step="01 · 경험 이야기" title="어떤 일을 해오셨나요?">직장 밖에서 해온 일도 좋아요. 한 가지 경험부터 적어 주세요.</Heading>
    <section className="panel"><p className="question">예를 들어, 동네 시설을 관리하거나 이웃에게 무언가를 가르쳐 준 경험이 있나요?</p>
      <TextAreaField id="experience" label="내가 해온 일" value={preview.experience} onChange={(event) => onChange(event.target.value)} maxLength={2000} rows={6} hint="연락처·주민등록번호·상세 병력은 적지 마세요." placeholder="가상의 경험을 적어보세요. 예: 동네 도서관에서 책 정리를 도왔어요." />
      <div className="actions"><Link className="button primary" to="/profile">작성한 내용 확인하기 <span aria-hidden="true">→</span></Link><Link className="text-link" to="/transcription">음성 입력 안내</Link></div></section>
    <Pending title="대화와 AI 정리는 연결 준비 중이에요">현재는 직접 적은 경험만 확인할 수 있습니다. 다음 질문과 프로필 추출은 서버 연결 후 제공됩니다.</Pending></div>
}

export default function App() {
  const { value: preview, setValue: setPreview, clear: clearPreview } = useMemoryScope<Preview>(emptyPreview)
  const [notice, setNotice] = useState('')
  const location = useLocation()
  const previousPath = useRef(location.pathname)
  const [ending, setEnding] = useState(false)
  const navigate = useNavigate()
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const current = screens.find((screen) => screen.path === location.pathname)
      ?? (location.pathname.startsWith('/opportunities/') ? screens[6] : undefined)
      ?? (location.pathname.startsWith('/admin/') ? screens[9] : undefined)
      ?? (location.pathname.startsWith('/me/') ? screens[8] : undefined)
    document.title = `${current?.title ?? '페이지를 찾을 수 없어요'} · 다시잇다`
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname
      window.scrollTo(0, 0)
      mainRef.current?.focus({ preventScroll: true })
      if (ending && location.pathname === '/') setEnding(false)
      else setNotice('')
    }
  }, [location.pathname, ending])
  useEffect(() => {
    // React memory can survive a full-page departure via the back/forward cache.
    const clearOnLeave = () => setNotice('')
    const clearOnRestore = (event: PageTransitionEvent) => { if (event.persisted) clearOnLeave() }
    window.addEventListener('pagehide', clearOnLeave)
    window.addEventListener('pageshow', clearOnRestore)
    return () => { window.removeEventListener('pagehide', clearOnLeave); window.removeEventListener('pageshow', clearOnRestore) }
  }, [])
  const endPreview = () => { setEnding(true); clearPreview(); setNotice('미리보기 입력을 삭제했습니다. 새로 시작할 수 있어요.'); navigate('/') }
  // End navigation may finish after state clears. Keep the guard pointed home
  // during that transition so an old route cannot redirect back to consent.
  const requirePreview = (children: ReactNode) => preview.consent ? children : <Navigate to={ending ? '/' : '/consent'} replace />
  return <>
    <a className="skip-link" href="#main">본문으로 바로가기</a>
    <div className="preview-banner">개발 중인 서비스 <span>· 개인 체험은 가상 정보로 살펴보세요 · AI·로그인 미연결</span></div>
    <header className="site-header"><Link className="brand" to="/" aria-label="다시잇다 시작 화면"><span className="brand-symbol" aria-hidden="true">↗</span>다시잇다<span className="brand-subtitle">경험과 기회를 잇다</span></Link><nav aria-label="주요 메뉴"><NavLink to="/opportunities">공고 살펴보기</NavLink><NavLink to="/me">내 정보</NavLink></nav></header>
    {preview.consent && <div className="preview-toolbar"><p>지금 적는 내용은 새로고침하면 사라져요.</p><Button variant="compact" onClick={endPreview}>종료하고 삭제</Button></div>}
    <div className="status-line" role="status">{notice}</div>
    <main id="main" ref={mainRef} tabIndex={-1}><Routes>
      <Route path="/" element={<Home />} />
      <Route path="/consent" element={<Consent onStart={() => { clearPreview(); setPreview({ ...emptyPreview(), consent: true }); setNotice(''); navigate('/conversation') }} />} />
      <Route path="/conversation" element={requirePreview(<Conversation preview={preview} onChange={(value) => setPreview((previous) => ({ ...previous, experience: value, preferences: { ...previous.preferences, reviewed: false }, draft: { ...previous.draft, reviewed: false } }))} />)} />
      <Route path="/transcription" element={requirePreview(<VoicePreview onUseText={(experience) => { setPreview((previous) => ({ ...previous, experience, preferences: { ...previous.preferences, reviewed: false }, draft: { ...previous.draft, reviewed: false } })); navigate('/conversation') }} />)} />
      <Route path="/profile" element={requirePreview(<ProfilePreview experience={preview.experience} preferences={preview.preferences} onChange={(preferences) => setPreview((previous) => ({ ...previous, preferences, draft: { ...previous.draft, reviewed: false } }))} />)} />
      <Route path="/opportunities" element={<PublicOpportunities />} />
      <Route path="/opportunities/:id" element={<PublicOpportunityDetail />} />
      <Route path="/preparation" element={requirePreview(<ManualPreparation draft={preview.draft} onChange={(draft) => setPreview((previous) => ({ ...previous, draft }))} />)} />
      <Route path="/me" element={<AccountPage onLogout={() => { clearPreview(); setNotice('로그아웃 후 미리보기 입력을 삭제했습니다.') }} />} />
      <Route path="/me/saved" element={<SavedMaterials />} />
      <Route path="/admin/*" element={<AdminPage />} />
      <Route path="*" element={<div className="reading-width"><Heading step="주소 확인" title="페이지를 찾을 수 없어요">주소를 확인하거나 시작 화면으로 돌아가 주세요.</Heading><Link className="button primary" to="/">시작 화면으로</Link></div>} />
    </Routes></main>
    <footer className="site-footer"><p><strong>다시잇다</strong><span>당신의 다음 걸음을 응원합니다.</span></p><p>신청은 공식 신청처에서 직접 진행합니다.</p><details className="screen-map"><summary>개발 화면 목록</summary><nav aria-label="개발 화면 목록">{screens.map((screen) => <Link key={screen.id} to={screen.path}>{screen.id} · {screen.title}</Link>)}</nav></details></footer>
  </>
}
