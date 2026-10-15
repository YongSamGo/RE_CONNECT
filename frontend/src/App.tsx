import { Component, useEffect, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import './App.css'

// Preview-only memory. Never represents server consent, identity or confirmation.
type Preview = { consent: boolean; experience: string }
const emptyPreview = (): Preview => ({ consent: false, experience: '' })
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
  return <section className="notice"><span className="badge">연결 준비 중</span><h2>{title}</h2><p>{children}</p></section>
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
      <h2>지금은 화면 미리보기예요</h2><p>AI·서버·회원 저장은 연결되지 않았습니다. 아래에서 입력한 내용은 이 화면의 메모리에서만 사용하며 새로고침하거나 종료하면 사라집니다. 실제 개인정보는 입력하지 마세요.</p>
      <p className="policy-draft">안내문 초안 · 운영 주체, 문의처, AWS 리전과 실제 보관·삭제 안내는 확인 후 확정해야 합니다. 이 선택은 운영 서비스의 처리 동의로 기록되지 않습니다.</p>
      <form onSubmit={(event) => { event.preventDefault(); if (checked) onStart() }}><label className="checkbox-label"><input type="checkbox" checked={checked} onChange={(event) => setChecked(event.target.checked)} />안내를 확인했고, 가상의 경험으로 화면을 살펴볼게요.</label>
        <div className="actions"><button className="button primary" disabled={!checked}>미리보기 시작하기 <span aria-hidden="true">→</span></button><Link to="/opportunities">공고 화면 살펴보기</Link></div></form>
    </section></div>
}

function Conversation({ preview, onChange }: { preview: Preview; onChange: (value: string) => void }) {
  return <div className="reading-width"><Heading step="01 · 경험 이야기" title="어떤 일을 해오셨나요?">직장 밖에서 해온 일도 좋아요. 한 가지 경험부터 적어 주세요.</Heading>
    <section className="panel"><p className="question">예를 들어, 동네 시설을 관리하거나 이웃에게 무언가를 가르쳐 준 경험이 있나요?</p>
      <label htmlFor="experience">내가 해온 일</label><textarea id="experience" value={preview.experience} onChange={(event) => onChange(event.target.value)} maxLength={2000} rows={6} aria-describedby="experience-help experience-length" placeholder="가상의 경험을 적어보세요. 예: 동네 도서관에서 책 정리를 도왔어요." />
      <div className="input-meta"><p id="experience-help">연락처·주민등록번호·상세 병력은 적지 마세요.</p><p id="experience-length">{preview.experience.length.toLocaleString('ko-KR')} / 2,000자</p></div>
      <div className="actions"><Link className="button primary" to="/profile">작성한 내용 확인하기 <span aria-hidden="true">→</span></Link><Link to="/transcription">음성 입력 안내</Link></div></section>
    <Pending title="대화와 AI 정리는 연결 준비 중이에요">현재는 직접 적은 경험만 확인할 수 있습니다. 다음 질문과 프로필 추출은 서버 연결 후 제공됩니다.</Pending></div>
}

function Profile({ experience }: { experience: string }) {
  return <div className="reading-width"><Heading step="02 · 프로필 확인" title="내 경험을 다시 살펴봐요">직접 적은 내용을 확인해 주세요. 아직 확정된 프로필은 아닙니다.</Heading>
    <section className="panel"><h2>내가 적은 경험</h2>{experience.trim() ? <p className="user-text">{experience}</p> : <p>아직 적은 경험이 없어요. 떠오르는 경험부터 한 가지 적어보세요.</p>}<Link className="button secondary" to="/conversation">경험 수정하기</Link></section>
    <Pending title="프로필 확정은 연결 준비 중이에요">경험·희망 활동 지역·활동 유형을 확인하고 서버에서 확정한 뒤 역할과 추천을 제공할 예정입니다. 현재 화면은 정보를 확정하거나 저장하지 않습니다.</Pending><Link className="text-link" to="/opportunities">공개 공고 화면 살펴보기 →</Link></div>
}

function Opportunities() {
  return <div className="reading-width"><Heading step="기회 살펴보기" title="나의 다음 기회를 찾아봐요">취업·공공일자리와 봉사 기회를 살펴보는 공간입니다.</Heading>
    <Pending title="아직 연결된 공고가 없어요">현재는 공개 공고 API와 검수 자료가 연결되지 않았습니다. 실제 공고가 연결되면 출처·모집 상태·공식 신청 안내를 함께 표시합니다.</Pending>
    <section className="panel"><h2>맞춤 추천은 프로필 확인 후에</h2><p>나의 경험과 희망 활동 지역, 활동 유형을 직접 확정하면 조건에 맞는 공고와 확인할 사항을 안내합니다.</p><Link className="button secondary" to="/consent">경험 이야기부터 시작하기</Link></section></div>
}

const pendingScreens = {
  voice: { step: '음성 입력', title: '말로 경험을 이야기하기', heading: '음성 입력은 연결 준비 중이에요', body: '녹음·전사 확인은 음성 서비스 연결 후 제공됩니다. 현재는 마이크에 접근하지 않습니다.', link: '/conversation', action: '글로 작성하기' },
  detail: { step: '공고 상세', title: '공고의 조건을 함께 확인해요', heading: '아직 조회할 공고가 없어요', body: '공식 원문·자격 조건·접수 방법·오류 신고는 검수한 공고 연결 후 제공됩니다.', link: '/opportunities', action: '공고 화면으로' },
  preparation: { step: '03 · 신청 준비', title: '신청 전, 차근차근 준비해요', heading: '신청 준비는 연결 준비 중이에요', body: '검수한 공고의 서류 안내와 확정 프로필을 연결한 뒤 지원서 작성·수정·승인·복사를 제공합니다. 공식 신청처 이동은 신청 완료를 의미하지 않습니다.', link: '/opportunities', action: '공고 화면으로' },
  me: { step: '내 정보', title: '저장한 자료를 관리해요', heading: '로그인과 저장은 연결 준비 중이에요', body: '카카오 인증과 별도 저장 동의 연결 후 내 저장 자료를 조회·삭제할 수 있습니다. 미리보기의 입력은 회원 자료로 저장되지 않습니다.', link: '/', action: '시작 화면으로' },
  admin: { step: '운영자', title: '운영자 인증이 필요해요', heading: '운영자 화면은 연결 준비 중이에요', body: '서버의 운영자 권한과 MFA 확인 후 공고 검수·신고·운영 상태를 제공합니다. 현재 화면은 관리 데이터 조회나 변경을 수행하지 않습니다.', link: '/', action: '시작 화면으로' },
}
function Placeholder({ kind }: { kind: keyof typeof pendingScreens }) {
  const content = pendingScreens[kind]
  return <div className="reading-width"><Heading step={content.step} title={content.title}>필요한 기능을 순서대로 준비하고 있습니다.</Heading><Pending title={content.heading}>{content.body}</Pending><Link className="button secondary" to={content.link}>{content.action}</Link></div>
}

export default function App() {
  const [preview, setPreview] = useState<Preview>(emptyPreview)
  const [notice, setNotice] = useState('')
  const location = useLocation()
  const navigate = useNavigate()
  const mainRef = useRef<HTMLElement>(null)
  useEffect(() => {
    const current = screens.find((screen) => screen.path === location.pathname)
      ?? (location.pathname.startsWith('/opportunities/') ? screens[6] : undefined)
      ?? (location.pathname.startsWith('/admin/') ? screens[9] : undefined)
    document.title = `${current?.title ?? '페이지를 찾을 수 없어요'} · 다시잇다`
    mainRef.current?.focus({ preventScroll: true })
  }, [location.pathname])
  useEffect(() => {
    // React memory can survive a full-page departure via the back/forward cache.
    const clearOnLeave = () => { setPreview(emptyPreview()); setNotice('') }
    const clearOnRestore = (event: PageTransitionEvent) => { if (event.persisted) clearOnLeave() }
    window.addEventListener('pagehide', clearOnLeave)
    window.addEventListener('pageshow', clearOnRestore)
    return () => { window.removeEventListener('pagehide', clearOnLeave); window.removeEventListener('pageshow', clearOnRestore) }
  }, [])
  const endPreview = () => { setPreview(emptyPreview()); setNotice('미리보기 입력을 삭제했습니다. 새로 시작할 수 있어요.'); navigate('/') }
  // End navigation may finish after state clears. Keep the guard pointed home
  // during that transition so an old route cannot redirect back to consent.
  const requirePreview = (children: ReactNode) => preview.consent ? children : <Navigate to={notice ? '/' : '/consent'} replace />
  return <>
    <a className="skip-link" href="#main">본문으로 바로가기</a>
    <div className="preview-banner">개발 중인 화면 미리보기 <span>· AI·공고·로그인 미연결 · 가상 정보로 살펴보세요</span></div>
    <header className="site-header"><Link className="brand" to="/" aria-label="다시잇다 시작 화면"><span className="brand-symbol" aria-hidden="true">↗</span>다시잇다<span className="brand-subtitle">경험과 기회를 잇다</span></Link><nav aria-label="주요 메뉴"><NavLink to="/opportunities">공고 살펴보기</NavLink><NavLink to="/me">내 정보</NavLink></nav></header>
    {preview.consent && <div className="preview-toolbar"><p>지금 적는 내용은 새로고침하면 사라져요.</p><button className="button compact" onClick={endPreview}>종료하고 삭제</button></div>}
    <div className="status-line" role="status">{notice}</div>
    <main id="main" ref={mainRef} tabIndex={-1}><Routes>
      <Route path="/" element={<Home />} />
      <Route path="/consent" element={<Consent onStart={() => { setPreview({ ...emptyPreview(), consent: true }); setNotice(''); navigate('/conversation') }} />} />
      <Route path="/conversation" element={requirePreview(<Conversation preview={preview} onChange={(value) => setPreview((previous) => ({ ...previous, experience: value }))} />)} />
      <Route path="/transcription" element={requirePreview(<Placeholder kind="voice" />)} />
      <Route path="/profile" element={requirePreview(<Profile experience={preview.experience} />)} />
      <Route path="/opportunities" element={<Opportunities />} />
      <Route path="/opportunities/:id" element={<Placeholder kind="detail" />} />
      <Route path="/preparation" element={requirePreview(<Placeholder kind="preparation" />)} />
      <Route path="/me" element={<Placeholder kind="me" />} />
      <Route path="/admin/*" element={<Placeholder kind="admin" />} />
      <Route path="*" element={<div className="reading-width"><Heading step="주소 확인" title="페이지를 찾을 수 없어요">주소를 확인하거나 시작 화면으로 돌아가 주세요.</Heading><Link className="button primary" to="/">시작 화면으로</Link></div>} />
    </Routes></main>
    <footer className="site-footer"><p><strong>다시잇다</strong><span>당신의 다음 걸음을 응원합니다.</span></p><p>신청은 공식 신청처에서 직접 진행합니다.</p><details className="screen-map"><summary>개발 화면 목록</summary><nav aria-label="개발 화면 목록">{screens.map((screen) => <Link key={screen.id} to={screen.path}>{screen.id} · {screen.title}</Link>)}</nav></details></footer>
  </>
}
