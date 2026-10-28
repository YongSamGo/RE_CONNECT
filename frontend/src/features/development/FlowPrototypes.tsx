import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ServicePage } from '../../ui/ServicePage'
import { OpportunityListCard } from '../opportunities/OpportunityListCard'
import { demoOpportunities } from './demo-opportunities'
import './flow-prototypes.css'

type AuthStep = 'choice' | 'waiting' | 'confirmed'
type OpportunityStep = 'list' | 'detail' | 'application'

function safeApplicationUrl(value: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' ? url.href : null
  } catch {
    return null
  }
}

export function KakaoFlowPrototype() {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [step, setStep] = useState<AuthStep>('choice')
  return <ServicePage title="카카오로 시작하기" description="로그인하거나 처음 가입하는 과정을 확인해 보세요." className="flow-prototype">
    <section className="flow-prototype-panel" aria-live="polite">
      {step === 'choice' && <>
        <div className="flow-choice-tabs" role="group" aria-label="이용 방법 선택">
          <button type="button" aria-pressed={mode === 'login'} onClick={() => setMode('login')}>로그인</button>
          <button type="button" aria-pressed={mode === 'signup'} onClick={() => setMode('signup')}>회원가입</button>
        </div>
        <div className="flow-kakao-mark" aria-hidden="true">K</div>
        <h2>{mode === 'login' ? '카카오 계정으로 로그인해요' : '카카오 계정으로 가입해요'}</h2>
        <p>{mode === 'login' ? '카카오 인증을 마치면 다시잇다 이용을 이어갈 수 있어요.' : '처음 이용하시면 카카오 인증 후 회원으로 시작할 수 있어요.'}</p>
        <button className="button primary flow-kakao-action" type="button" onClick={() => setStep('waiting')}>카카오로 {mode === 'login' ? '로그인' : '가입하기'}</button>
      </>}
      {step === 'waiting' && <>
        <div className="flow-kakao-mark" aria-hidden="true">K</div>
        <h2>카카오 인증을 확인해 주세요</h2>
        <p>카카오 화면에서 본인 확인을 마친 뒤 다시잇다로 돌아오면 아래 버튼을 눌러 주세요.</p>
        <button className="button primary flow-kakao-action" type="button" onClick={() => setStep('confirmed')}>인증 완료 확인</button>
        <button className="text-link" type="button" onClick={() => setStep('choice')}>로그인 화면으로 돌아가기</button>
      </>}
      {step === 'confirmed' && <>
        <p className="flow-state-label">인증 확인</p>
        <h2>다시잇다 이용을 시작할 수 있어요</h2>
        <p>로그인과 회원가입 다음에는 경험 이야기로 이어집니다.</p>
        <Link className="button primary" to="/dev/conversation">경험 이야기 시작하기</Link>
      </>}
    </section>
    <p className="flow-prototype-note">개발용 화면입니다. 카카오 인증이나 회원 가입을 실제로 처리하지 않습니다.</p>
  </ServicePage>
}

export function OpportunityApplicationFlowPrototype({ recommended = false }: { recommended?: boolean }) {
  const [searchParams] = useSearchParams()
  const selectedFromUrl = demoOpportunities.findIndex(item => item.id === searchParams.get('opportunity'))
  const [step, setStep] = useState<OpportunityStep>(selectedFromUrl >= 0 ? 'detail' : 'list')
  const [selected, setSelected] = useState(selectedFromUrl >= 0 ? selectedFromUrl : 0)
  const [name, setName] = useState('홍길동')
  const [phone, setPhone] = useState('010-0000-0000')
  const [introduction, setIntroduction] = useState('')
  const [motivation, setMotivation] = useState('')
  const [reviewOpen, setReviewOpen] = useState(false)
  const [reviewed, setReviewed] = useState(false)
  const [officialNotice, setOfficialNotice] = useState('')
  const reviewTrigger = useRef<HTMLButtonElement>(null)
  const opportunity = demoOpportunities[selected]
  const officialApplicationUrl = safeApplicationUrl(opportunity.officialApplicationUrl)
  const openDetail = (index: number) => {
    setSelected(index)
    setName('홍길동')
    setPhone('010-0000-0000')
    setIntroduction('')
    setMotivation('')
    setOfficialNotice('')
    setStep('detail')
  }
  const title = step === 'list' ? recommended ? '다시잇다가 추천하는 공고입니다' : '공고를 살펴보세요'
    : step === 'detail' ? '공고 내용을 확인해 주세요' : '지원 내용을 작성해요'
  const closeReview = () => {
    setReviewOpen(false)
    requestAnimationFrame(() => reviewTrigger.current?.focus())
  }
  const downloadDraft = () => {
    const contents = `${opportunity.title}\n${opportunity.organization}\n\n신청자 정보\n이름: ${name}\n연락처: ${phone}\n\n자기소개\n${introduction}\n\n지원 동기\n${motivation}\n`
    const url = URL.createObjectURL(new Blob([contents], { type: 'text/plain;charset=utf-8' }))
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `${opportunity.id}-지원서.txt`
    anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }

  return <ServicePage title={title}
    description={step === 'list' ? '관심 있는 공고를 선택해 자세한 내용을 확인해 보세요.'
      : step === 'application' ? '작성한 내용은 이 화면에서만 다루며, 기관에 제출하기 전에 다시 확인할 수 있어요.' : undefined}
    className="flow-prototype opportunity-flow-prototype">
    {step === 'list' && <ol className="shared-opportunity-list flow-opportunity-list" aria-label={recommended ? '추천 공고 목록' : '전체 공고 목록'}>
      {demoOpportunities.map((item, index) => <OpportunityListCard key={item.id} title={item.title} organization={item.organization}
        tags={[item.region, item.schedule, item.deadline]} onDetail={() => openDetail(index)} />)}</ol>}
    {step === 'detail' && <article className="flow-detail-panel">
      <p className="flow-state-label">모집 중</p><h2>{opportunity.title}</h2><p>{opportunity.organization}</p>
      <dl><div><dt>활동 분야</dt><dd>{opportunity.activity}</dd></div><div><dt>활동 지역</dt><dd>{opportunity.region}</dd></div><div><dt>활동 일정</dt><dd>{opportunity.schedule}</dd></div><div><dt>신청 마감</dt><dd>{opportunity.deadline}</dd></div></dl>
      {recommended && <section className="flow-recommendation-reason"><h3>추천 이유</h3><p>{opportunity.recommendationReason}</p></section>}
      <section><h3>활동 내용</h3><p>{opportunity.description}</p></section>
      <section><h3>참여 조건</h3><ul>{opportunity.requirements.map(requirement => <li key={requirement}>{requirement}</li>)}</ul></section>
      <section><h3>신청 방법</h3><p>지원 내용을 작성하고 확인한 뒤 기관의 공식 신청처에서 제출합니다.</p></section>
      <div className="actions"><button className="button primary" type="button" onClick={() => setStep('application')}>지원서 작성하기</button></div>
    </article>}
    {step === 'application' && <section className="flow-application-panel">
      <div className="flow-selected-opportunity"><span>선택한 공고</span><strong>{opportunity.title}</strong><span>{opportunity.organization}</span></div>
      <h2>신청자 정보</h2>
      <label className="form-field"><span>이름</span><input value={name} onChange={event => setName(event.target.value)} autoComplete="name" /></label>
      <label className="form-field"><span>연락처</span><input type="tel" value={phone} onChange={event => setPhone(event.target.value)} autoComplete="tel" /></label>
      <h2>지원 내용</h2>
      <div className="flow-profile-facts"><h3>초안에 참고할 프로필 정보</h3><ul>{opportunity.profileFacts.map(fact => <li key={fact}>{fact}</li>)}</ul>
        <button className="button secondary" type="button" onClick={() => setIntroduction(opportunity.introduction)}>자기소개 초안 만들기</button>
        <p>이 화면은 예시 프로필로 만든 초안을 보여줍니다. 실제 서비스에서는 확정한 프로필을 바탕으로 초안을 만들어요.</p></div>
      <label className="form-field"><span>자기소개</span><textarea rows={4} value={introduction} onChange={event => setIntroduction(event.target.value)} /></label>
      <label className="form-field"><span>지원 동기</span><textarea rows={4} value={motivation} onChange={event => setMotivation(event.target.value)} /></label>
      <p className="quiet">지원 동기는 직접 작성해 주세요. 예시 정보는 저장되거나 전송되지 않습니다.</p>
      <div className="actions"><button ref={reviewTrigger} className="button primary" type="button" disabled={!name.trim() || !phone.trim() || !introduction.trim() || !motivation.trim()} onClick={() => { setReviewed(false); setReviewOpen(true) }}>작성 내용 확인하기</button></div>
    </section>}
    {reviewOpen && <div className="flow-review-backdrop" onMouseDown={event => { if (event.target === event.currentTarget) closeReview() }}>
      <section className="flow-review-dialog" role="dialog" aria-modal="true" aria-labelledby="flow-review-title"
        onKeyDown={event => {
          if (event.key === 'Escape') { closeReview(); return }
          if (event.key !== 'Tab') return
          const controls = [...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled), a[href], input:not(:disabled)')]
          const first = controls[0], last = controls.at(-1)
          if (!first || !last) return
          if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
          else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
        }}>
        <button className="flow-review-close" type="button" onClick={closeReview} autoFocus aria-label="확인 창 닫기">닫기</button>
        <p className="flow-state-label">제출 전 확인</p><h2 id="flow-review-title">신청 내용을 확인해 주세요</h2><p><strong>{opportunity.title}</strong><br />{opportunity.organization}</p>
        <div className="flow-answer-preview"><h3>신청자 정보</h3><p>{name}<br />{phone}</p><h3>자기소개</h3><p>{introduction}</p><h3>지원 동기</h3><p>{motivation}</p></div>
        <label className="flow-review-check"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} /> 작성한 내용이 맞는지 확인했어요.</label>
        <div className="actions flow-review-actions"><button className="button secondary" type="button" onClick={downloadDraft}>문서 다운로드</button>
          {officialApplicationUrl && reviewed
            ? <a className="button primary" href={officialApplicationUrl} target="_blank" rel="noopener noreferrer">공식 신청처로 이동</a>
            : <button className="button primary" type="button" disabled={!reviewed} onClick={() => setOfficialNotice('더미 공고에는 공식 신청처 주소가 연결되지 않았습니다.')}>공식 신청처로 이동</button>}</div>
        <p className="quiet">이 시안에서는 신청 내용이 전송되지 않습니다. 실제 공고로 바꾸면 해당 공고의 공식 신청처로 연결합니다.</p>
        {officialNotice && <p role="status" className="flow-official-notice">{officialNotice}</p>}
      </section>
    </div>}
    <p className="flow-prototype-note">예시 공고를 사용한 개발용 화면입니다. 작성 내용은 저장되지 않으며 실제 기관에 제출되지 않습니다.</p>
  </ServicePage>
}
