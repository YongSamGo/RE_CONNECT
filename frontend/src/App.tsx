import { Component, startTransition, useEffect, useRef, useState, type ReactNode } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { OpportunityDetail, OpportunityList, PreparationPage } from './OpportunityPages'
import type { ApplicationDraft } from './application'
import { canConfirm, emptyProfile, type Activity, type Profile } from './journey'

const activityNames: Record<Activity, string> = { employment: '취업·공공일자리', volunteering: '봉사' }
const steps = ['경험 이야기', '프로필 확인', '기회 탐색']

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() {
    if (this.state.failed) return <main className="error-page"><h1>화면을 불러오지 못했어요</h1>
      <p>새로 시작하면 입력 중인 내용은 지워집니다.</p><a className="button" href="/">새로 시작하기</a></main>
    return this.props.children
  }
}

function PageFocus() {
  const { pathname } = useLocation()
  useEffect(() => {
    document.querySelector<HTMLElement>('main')?.focus()
    window.scrollTo?.(0, 0)
  }, [pathname])
  return null
}

function Progress({ current }: { current: number }) {
  return <ol className="progress" aria-label="체험 진행 단계">{steps.map((step, index) =>
    <li key={step} aria-current={index === current ? 'step' : undefined} className={index <= current ? 'active' : ''}>
      <span>{index < current ? '✓' : `0${index + 1}`}</span>{step}
    </li>)}</ol>
}

function Home() {
  return <>
    <section className="hero">
      <div className="hero-copy"><p className="eyebrow">경험은 사라지지 않으니까</p>
        <h1>살아온 시간만큼,<br />이어질 기회도 <em>많으니까.</em></h1>
        <p className="hero-description">일하며 쌓은 노하우도, 누군가를 돌본 시간도.<br />당신의 경험에서 새로운 시작을 함께 찾아요.</p>
        <Link className="button" to="/consent">내 경험 이야기하기 <span aria-hidden="true">↗</span></Link>
        <p className="small-note">회원가입 없이 · 내 속도에 맞게 · 한 질문씩</p>
      </div>
      <div className="hero-art" aria-hidden="true">
        <div className="art-orbit" /><div className="art-sun" />
        <div className="art-window"><span className="art-caption">MY NEXT CHAPTER</span><div className="art-arch" /><div className="art-path" /></div>
        <div className="art-tag tag-one">차곡차곡 쌓아온 경험</div><div className="art-tag tag-two">다시, 나답게 시작하기 <span>↗</span></div>
        <span className="art-spark">✳</span>
      </div>
    </section>
    <section className="journey-intro" aria-labelledby="how-title">
      <div className="section-heading"><div><p className="eyebrow">작은 이야기에서, 새로운 일상으로</p><h2 id="how-title">시작은 어렵지 않아요</h2></div>
        <Link className="text-link" to="/opportunities">공개 공고 먼저 둘러보기 <span aria-hidden="true">→</span></Link></div>
      <div className="intro-grid">{[
        ['01', '나의 이야기를 들려주세요', '해본 일, 좋아하는 일. 편안하게 한 가지씩 적어주세요.', '↗'],
        ['02', '내 경험을 직접 확인해요', '정리한 내용을 고치고, 나에게 맞는 활동을 선택해요.', '✓'],
        ['03', '다음 기회를 살펴봐요', '공고의 조건과 준비할 것을 확인하고 공식 신청처로 이어가요.', '↗'],
      ].map(([number, title, text, icon]) => <article className="intro-card" key={number}><div className="card-top"><span>{number}</span><b aria-hidden="true">{icon}</b></div><h3>{title}</h3><p>{text}</p></article>)}</div>
    </section>
    <aside className="trust-note"><span className="trust-icon" aria-hidden="true">♡</span><div><strong>이야기의 주인은 언제나 당신이에요.</strong><p>직접 확인한 정보로 다음 단계를 이어가요. 저장은 별도의 동의를 받은 뒤에만 진행해요.</p></div></aside>
  </>
}

function Consent({ onStart }: { onStart: () => void }) {
  const [checked, setChecked] = useState(false)
  return <section className="narrow"><p className="eyebrow">시작하기 전에</p><h1>안심하고 이야기할 수 있도록</h1>
    <p className="lead">지금은 화면 체험 단계예요. 직접 적은 내용을 확인하며 흐름을 살펴볼 수 있어요.</p>
    <div className="panel"><h2>이번 화면 체험에서는</h2><ul className="readable-list"><li>입력은 현재 화면의 메모리에만 유지돼요. 서버나 AI로 보내지 않아요.</li><li>새로고침하거나 ‘종료하고 삭제’를 누르면 입력이 사라져요.</li><li>주민등록번호, 연락처, 상세 병력은 적지 말아주세요.</li></ul></div>
    <div className="notice"><strong>정식 AI 처리 동의는 연동 후 제공해요.</strong><p>정식 서비스의 AI는 서비스 AWS EC2에서 처리할 예정이에요. 실제 AWS 리전, 보관·삭제 조건을 확정한 안내와 별도 동의가 필요해요.</p></div>
    <label className="check-row"><input type="checkbox" checked={checked} onChange={event => setChecked(event.target.checked)} />화면 체험의 입력 처리 방식을 확인했어요.</label>
    <button className="button" disabled={!checked} onClick={onStart}>확인하고 시작하기 <span aria-hidden="true">→</span></button>
  </section>
}

function ProfileFields({ profile, update, step }: { profile: Profile; update: (profile: Profile) => void; step?: number }) {
  return <>
    {(step === undefined || step === 0) && <div className="field"><label htmlFor="experience">기억에 남는 경험</label><textarea id="experience" value={profile.experience} maxLength={2000} rows={5} autoComplete="off" placeholder="예: 식당에서 10년 동안 손님을 맞이하고 식재료를 관리했어요."
      onChange={event => update({ ...profile, experience: event.target.value })} /><p className="field-help">해본 일이나 일상에서 맡았던 역할을 적어주세요. {profile.experience.length.toLocaleString()} / 2,000자</p></div>}
    {(step === undefined || step === 1) && <div className="field"><label htmlFor="region">희망 활동 지역</label><input id="region" value={profile.region} maxLength={100} autoComplete="off" placeholder="예: 서울 성동구" onChange={event => update({ ...profile, region: event.target.value })} /><p className="field-help">상세 주소 대신 시·군·구까지만 적어주세요.</p></div>}
    {(step === undefined || step === 2) && <fieldset><legend>희망 활동 유형 <span className="field-help">여러 개 선택할 수 있어요</span></legend>
      {(Object.keys(activityNames) as Activity[]).map(activity => <label className="check-row option" key={activity}><input type="checkbox" checked={profile.activities.includes(activity)} onChange={event => update({ ...profile, activities: event.target.checked ? [...profile.activities, activity] : profile.activities.filter(value => value !== activity) })} />{activityNames[activity]}</label>)}</fieldset>}
  </>
}

function Conversation({ draft, update }: { draft: Profile; update: (profile: Profile) => void }) {
  const [step, setStep] = useState(0)
  const navigate = useNavigate()
  const heading = useRef<HTMLHeadingElement>(null)
  const questions = ['어떤 일을 해오셨나요?', '어느 지역에서 활동하고 싶으세요?', '어떤 활동을 해보고 싶으세요?']
  const valid = [draft.experience.trim().length > 0, draft.region.trim().length > 0, draft.activities.length > 0][step]
  function next() {
    if (step === 2) navigate('/profile')
    else { setStep(step + 1); heading.current?.focus() }
  }
  return <section className="narrow"><Progress current={0} /><p className="eyebrow">나의 경험 이야기 · {step + 1} / 3</p><h1 ref={heading} tabIndex={-1}>{questions[step]}</h1>
    <p className="lead">거창한 경력이 아니어도 좋아요. 직접 적은 내용을 다음 화면에서 고칠 수 있어요.</p>
    <div className="panel"><ProfileFields profile={draft} update={update} step={step} /></div>
    <p className="field-help">현재는 직접 입력만 가능해요. AI 대화와 음성 입력은 연결 준비 중이에요.</p>
    <div className="actions">{step > 0 && <button className="button secondary" onClick={() => setStep(step - 1)}>이전 질문</button>}<button className="button" disabled={!valid} onClick={next}>{step === 2 ? '내 프로필 확인하기' : '다음 질문'} <span aria-hidden="true">→</span></button></div>
    <Link className="text-link" to="/profile">지금까지 적은 내용 확인하기</Link>
  </section>
}

function ProfilePage({ draft, confirmed, update, confirm }: { draft: Profile; confirmed: Profile | null; update: (profile: Profile) => void; confirm: () => void }) {
  const [message, setMessage] = useState('')
  const changed = confirmed !== null && JSON.stringify(draft) !== JSON.stringify(confirmed)
  return <section className="narrow"><Progress current={1} /><p className="eyebrow">내가 확인하고, 내가 결정해요</p><h1>내 경험이 잘 담겼나요?</h1><p className="lead">직접 작성한 프로필이에요. 내용을 고친 뒤 확정해주세요.</p>
    {changed && <p className="notice">수정 중이에요. 다시 확정하기 전까지 이전 확정 프로필을 유지해요.</p>}
    <form onSubmit={event => { event.preventDefault(); if (canConfirm(draft)) { confirm(); setMessage('프로필을 확정했어요. 영구 저장은 하지 않았어요.') } }}>
      <div className="panel"><ProfileFields profile={draft} update={update} /></div>
      {!canConfirm(draft) && <p className="field-help">경험, 희망 활동 지역, 활동 유형을 모두 입력하면 확정할 수 있어요.</p>}
      <div className="actions"><Link className="button secondary" to="/conversation">이야기로 돌아가기</Link><button className="button" disabled={!canConfirm(draft)}>{confirmed ? '프로필 다시 확정하기' : '이 내용으로 확정하기'}</button></div>
    </form>
    <p role="status">{message}</p>
    {confirmed && <div className="panel"><h2>다음은 기회를 살펴볼 차례예요</h2><p>역할 후보와 추천 근거는 서버 연동 후 제공해요.</p><Link className="button" to="/recommendations">기회 탐색으로 이동 <span aria-hidden="true">→</span></Link></div>}
  </section>
}

function EmptyPage({ eyebrow, title, children, to = '/', action = '시작 화면으로' }: { eyebrow: string; title: string; children: ReactNode; to?: string; action?: string }) {
  return <section className="narrow"><p className="eyebrow">{eyebrow}</p><h1>{title}</h1><div className="panel empty-state"><span aria-hidden="true" className="empty-symbol">↗</span>{children}</div><Link className="button secondary" to={to}>{action}</Link></section>
}

export function App() {
  const [started, setStarted] = useState(false)
  const [draft, setDraft] = useState<Profile>(emptyProfile)
  const [confirmed, setConfirmed] = useState<Profile | null>(null)
  const [largeText, setLargeText] = useState(false)
  const [ending, setEnding] = useState(false)
  const [examples, setExamples] = useState(false)
  const [preparationChecks, setPreparationChecks] = useState<Record<string, string[]>>({})
  const [applications, setApplications] = useState<Record<string, ApplicationDraft>>({})
  const [profileVersion, setProfileVersion] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()
  const cancelButton = useRef<HTMLButtonElement>(null)
  function reset() {
    // Change route and prerequisites together so guards do not redirect during deletion.
    startTransition(() => {
      navigate('/')
      setDraft(emptyProfile()); setConfirmed(null); setStarted(false); setEnding(false)
      setExamples(false); setPreparationChecks({})
      setApplications({}); setProfileVersion(0)
    })
  }
  function gate(page: ReactNode) { return started ? page : <Navigate to="/consent" replace /> }
  return <div className={largeText ? 'app large-text' : 'app'}>
    <a className="skip-link" href="#main">본문으로 바로가기</a><PageFocus />
    <div className="preview-banner">프론트엔드 화면 체험 <span>· AI·로그인·실제 공고는 연결 준비 중이에요</span></div>
    <header className="header"><Link className="brand" to="/" aria-label="다시잇다 시작 화면"><span className="brand-mark" aria-hidden="true">↗</span>다시잇다<span className="brand-dot">.</span></Link>
      <nav aria-label="주요 메뉴"><NavLink to="/" end>시작하기</NavLink><NavLink to="/opportunities">기회 둘러보기</NavLink><NavLink to="/my">내 정보</NavLink></nav>
      <div className="header-actions"><button className="text-size" aria-label="큰 글씨" aria-pressed={largeText} onClick={() => setLargeText(!largeText)}>가<span aria-hidden="true">＋</span><span className="text-size-label"> 큰 글씨</span></button>{(started || examples) && <button className="exit-button" onClick={() => { setEnding(true); setTimeout(() => cancelButton.current?.focus(), 0) }}>종료하고 삭제</button>}</div>
    </header>
    <main id="main" tabIndex={-1} key={location.pathname}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/consent" element={<Consent onStart={() => { setStarted(true); navigate('/conversation') }} />} />
        <Route path="/conversation" element={gate(<Conversation draft={draft} update={setDraft} />)} />
        <Route path="/transcript" element={gate(<EmptyPage eyebrow="전사 확인" title="음성 입력을 준비하고 있어요" to="/conversation" action="직접 입력하기"><p>음성 인식 연결 후, 전사된 내용을 수정하고 보내는 화면을 제공해요.</p></EmptyPage>)} />
        <Route path="/profile" element={gate(<ProfilePage draft={draft} confirmed={confirmed} update={setDraft} confirm={() => { setConfirmed({ ...draft, activities: [...draft.activities] }); setProfileVersion(previous => previous + 1) }} />)} />
        <Route path="/recommendations" element={confirmed ? <EmptyPage eyebrow="기회 탐색" title="내 경험과 이어질 기회" to="/profile" action="프로필 확인하기">{JSON.stringify(draft) !== JSON.stringify(confirmed) && <p className="notice">이전 확정 프로필 기준이에요. 수정 내용은 다시 확정해주세요.</p>}<p>검수한 실제 공고가 아직 연결되지 않았어요.</p><p>추천과 자격 판단은 공고·역할 API가 연결된 뒤 제공해요.</p><Link className="text-link" to="/opportunities">공고 탐색 화면 살펴보기 →</Link></EmptyPage> : <Navigate to="/profile" replace />} />
        <Route path="/opportunities" element={<OpportunityList examples={examples} showExamples={() => setExamples(true)} />} />
        <Route path="/opportunities/:id" element={<OpportunityDetail examples={examples} />} />
        <Route path="/preparation/:id" element={<PreparationPage examples={examples} checks={preparationChecks} update={(id, checked) => setPreparationChecks(previous => ({ ...previous, [id]: checked }))} applications={applications} updateApplication={(id, application) => setApplications(previous => ({ ...previous, [id]: application }))} profile={confirmed} profileVersion={profileVersion} />} />
        <Route path="/my" element={<EmptyPage eyebrow="내 정보" title="저장한 자료를 한곳에서"><p>카카오 로그인과 별도 저장 동의는 연결 준비 중이에요.</p><p>이번 화면 체험에서 입력한 내용은 영구 저장되지 않아요.</p></EmptyPage>} />
        <Route path="/admin" element={<EmptyPage eyebrow="운영자" title="운영자 연결 준비 중"><p>운영 기능은 아직 제공하지 않아요. 서버에서 권한과 추가 인증을 확인한 뒤 연결할 예정이에요.</p></EmptyPage>} />
        <Route path="*" element={<EmptyPage eyebrow="페이지를 찾을 수 없어요" title="다시 시작해볼까요?"><p>주소를 확인하거나 시작 화면으로 이동해주세요.</p></EmptyPage>} />
      </Routes>
    </main>
    <footer><Link className="brand footer-brand" to="/">다시잇다.</Link><p>당신의 경험이, 누군가에게는 새로운 가능성.</p><span>2026 RE_CONNECT</span></footer>
    {ending && <div className="dialog-backdrop"><div role="alertdialog" aria-modal="true" aria-labelledby="end-title" aria-describedby="end-description" className="panel dialog" onKeyDown={event => {
      if (event.key === 'Escape') { setEnding(false); setTimeout(() => document.querySelector<HTMLButtonElement>('.exit-button')?.focus(), 0) }
      if (event.key === 'Tab') { event.preventDefault(); const buttons = event.currentTarget.querySelectorAll('button'); (document.activeElement === buttons[0] ? buttons[1] : buttons[0]).focus() }
    }}><h2 id="end-title">체험을 종료할까요?</h2><p id="end-description">현재 입력한 경험과 프로필, 준비 체크, 지원서가 화면 메모리에서 지워져요. 다시 복원할 수 없어요. 직접 복사한 클립보드 내용은 지워지지 않아요.</p><div className="actions"><button ref={cancelButton} className="button secondary" onClick={() => { setEnding(false); setTimeout(() => document.querySelector<HTMLButtonElement>('.exit-button')?.focus(), 0) }}>계속 작성하기</button><button className="button" onClick={reset}>종료하고 삭제</button></div></div></div>}
  </div>
}
