import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ServicePage } from '../../ui/ServicePage'
import { OpportunityListCard } from '../opportunities/OpportunityListCard'
import './flow-prototypes.css'

type AuthStep = 'choice' | 'waiting' | 'confirmed'
type OpportunityStep = 'list' | 'detail' | 'application' | 'ready' | 'official'

const demoOpportunities = [
  { title: '도서관 자료 정리 지원 봉사', organization: '서울나눔도서관', region: '서울특별시 마포구', schedule: '주 2회, 회당 3시간', deadline: '11월 30일까지', description: '도서관 자료를 정리하고 방문객이 필요한 공간과 자료를 찾도록 안내합니다.', reason: '경험 이야기에서 정리한 자료 분류와 방문객 안내 역량이 이 활동의 주요 내용과 맞닿아 있어요.', introduction: '도서관에서 자료를 정리하고 방문객의 이용을 도왔습니다.', motivation: '제가 해 온 자료 정리와 안내 경험을 살려 지역 주민에게 도움이 되고 싶습니다.' },
  { title: '디지털 생활 안내 도우미', organization: '우리동네 복지센터', region: '서울특별시 은평구', schedule: '주 3회, 회당 2시간', deadline: '12월 12일까지', description: '스마트폰의 기본 기능과 공공 서비스를 이용하는 방법을 방문객에게 안내합니다.', reason: '사람들에게 필요한 정보를 차근차근 알려 준 경험이 디지털 생활 안내 활동과 연결돼요.', introduction: '방문객이 필요한 정보를 이해하기 쉽게 설명하고 이용을 도왔습니다.', motivation: '설명과 안내 경험을 활용해 지역 주민의 디지털 서비스 이용을 돕고 싶습니다.' },
  { title: '지역 문화 행사 운영 지원', organization: '마을문화재단', region: '인천광역시', schedule: '행사 일정에 따라 활동', deadline: '상시 모집', description: '지역 주민을 위한 문화 행사에서 안내와 현장 운영을 돕습니다.', reason: '여러 사람과 협력하고 맡은 일을 꾸준히 해 온 경험이 현장 운영에 도움이 될 수 있어요.', introduction: '여러 사람과 역할을 나눠 행사를 준비하고 현장을 지원했습니다.', motivation: '협력 경험을 살려 지역 문화 행사에 참여하는 주민을 돕고 싶습니다.' },
]

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
  const [step, setStep] = useState<OpportunityStep>('list')
  const [selected, setSelected] = useState(0)
  const [introduction, setIntroduction] = useState(demoOpportunities[0].introduction)
  const [motivation, setMotivation] = useState(demoOpportunities[0].motivation)
  const opportunity = demoOpportunities[selected]
  const openDetail = (index: number) => {
    const next = demoOpportunities[index]
    setSelected(index)
    setIntroduction(next.introduction)
    setMotivation(next.motivation)
    setStep('detail')
  }
  return <ServicePage title={step === 'list' ? recommended ? '다시잇다가 추천하는 공고입니다' : '공고를 살펴보세요' : step === 'detail' ? '공고 내용을 확인해 주세요' : step === 'application' ? '지원 내용을 작성해요' : step === 'ready' ? '신청 준비를 마쳤어요' : '공식 신청처에서 제출해 주세요'} description={step === 'list' ? recommended ? '경험과 연결되는 공고를 살펴보세요.' : '관심 있는 공고를 선택해 자세한 내용을 확인해 보세요.' : undefined} className="flow-prototype opportunity-flow-prototype">
    {step === 'detail' && <button className="flow-back-button" type="button" onClick={() => setStep('list')}>뒤로가기</button>}
    {step === 'application' && <button className="flow-back-button" type="button" onClick={() => setStep('detail')}>뒤로가기</button>}
    {step === 'ready' && <button className="flow-back-button" type="button" onClick={() => setStep('application')}>뒤로가기</button>}
    {step === 'official' && <button className="flow-back-button" type="button" onClick={() => setStep('ready')}>뒤로가기</button>}
    {step === 'list' && <ol className="shared-opportunity-list flow-opportunity-list" aria-label={recommended ? '추천 공고 목록' : '전체 공고 목록'}>
      {demoOpportunities.map((item, index) => <OpportunityListCard key={item.title} title={item.title} organization={item.organization}
        tags={[item.region, item.schedule, item.deadline]} onDetail={() => openDetail(index)} />)}
    </ol>}
    {step === 'detail' && <article className="flow-detail-panel">
      <p className="flow-state-label">모집 중</p><h2>{opportunity.title}</h2><p>{opportunity.organization}</p>
      <dl><div><dt>활동 지역</dt><dd>{opportunity.region}</dd></div><div><dt>활동 일정</dt><dd>{opportunity.schedule}</dd></div><div><dt>신청 마감</dt><dd>{opportunity.deadline}</dd></div></dl>
      {recommended && <section className="flow-recommendation-reason"><h3>AI 추천 이유</h3><p>{opportunity.reason}</p><p>경험 이야기와 공고 내용을 바탕으로 한 예시 설명입니다. 최종 지원 자격을 판단하지 않습니다.</p></section>}
      <section><h3>활동 내용</h3><p>{opportunity.description}</p></section>
      <section><h3>신청 방법</h3><p>지원 내용을 확인한 뒤 공식 신청처에서 직접 제출합니다.</p></section>
      <div className="actions"><button className="button primary" type="button" onClick={() => setStep('application')}>지원서 작성하기</button></div>
    </article>}
    {step === 'application' && <section className="flow-application-panel">
      <div className="flow-selected-opportunity"><span>선택한 공고</span><strong>{opportunity.title}</strong><span>{opportunity.organization}</span></div>
      <label className="form-field"><span>자기소개</span><textarea rows={4} value={introduction} onChange={event => setIntroduction(event.target.value)} /></label>
      <label className="form-field"><span>지원 동기</span><textarea rows={4} value={motivation} onChange={event => setMotivation(event.target.value)} /></label>
      <p className="quiet">작성한 내용은 직접 확인하고 다듬어 주세요. 실제 제출은 공식 신청처에서 진행합니다.</p>
      <div className="actions"><button className="button primary" type="button" disabled={!introduction.trim() || !motivation.trim()} onClick={() => setStep('ready')}>작성 내용 확인하기</button></div>
    </section>}
    {step === 'ready' && <section className="flow-ready-panel" aria-live="polite">
      <h2>지원 내용을 확인했어요</h2><p><strong>{opportunity.title}</strong>에 제출할 내용을 준비했습니다.</p>
      <div className="flow-answer-preview"><h3>자기소개</h3><p>{introduction}</p><h3>지원 동기</h3><p>{motivation}</p></div>
      <p>아직 신청이 제출되지는 않았어요. 공고의 공식 신청처에서 내용을 제출해 주세요.</p>
      <div className="actions"><button className="button primary" type="button" onClick={() => setStep('official')}>공식 신청처 안내 확인하기</button></div>
    </section>}
    {step === 'official' && <section className="flow-ready-panel" aria-live="polite">
      <p className="flow-state-label">공식 신청 단계</p><h2>{opportunity.title}</h2>
      <p>{`지원서 내용을 가지고 ${opportunity.organization}의 공식 신청처에서 직접 제출해 주세요.`}</p>
      <div className="flow-answer-preview"><h3>제출 전 확인</h3><p>이름과 연락처를 포함해 신청서 내용을 다시 확인해 주세요.</p><p>다시잇다는 지원 내용을 기관에 대신 보내지 않습니다.</p></div>
      <p>이 시안에서는 실제 신청처로 이동하거나 지원 내용을 제출하지 않습니다.</p>
    </section>}
    <p className="flow-prototype-note">더미 공고를 사용한 개발용 화면입니다. 지원 내용은 저장되거나 실제 기관에 제출되지 않습니다.</p>
  </ServicePage>
}
