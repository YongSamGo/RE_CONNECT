import { Link } from 'react-router-dom'
import { ServicePage } from '../../ui/ServicePage'

const groups = [
  { title: '경험을 이야기하고 정리하기', items: [
    ['/start', '시작 전 안내', '정보가 어떻게 쓰이는지 확인해요'],
    ['/conversation', 'AI와 경험 이야기', '한 가지씩 대화하며 경험을 정리해요'],
  ] },
  { title: '기회를 찾고 신청하기', items: [
    ['/recommendations', '추천 공고', '확정한 경험과 연결되는 기회를 찾아요'],
    ['/opportunities', '전체 공고 탐색', '지역과 활동 유형으로 찾아요'],
  ] },
  { title: '계정 관리', items: [
    ['/login', '로그인', '카카오 계정으로 로그인해요'],
    ['/me', '나의 정보', '회원 정보를 확인하고 편집해요'],
    ['/me/story', '나의 이야기', '정리한 경험과 희망 활동을 확인해요'],
    ['/me/saved', '저장한 공고', '관심 있는 공고를 다시 살펴봐요'],
  ] },
]

export function ServiceGuide() {
  return <ServicePage title="다시잇다 이용 안내" description="경험을 이야기하는 순간부터 새로운 기회를 준비할 때까지, 필요한 단계를 선택해 보세요.">
    {import.meta.env.DEV && <p className="journey-map-guide-link"><Link to="/journey-map">사용자 흐름을 연결선으로 보기</Link></p>}
    <div className="service-guide">{groups.map((group, index) => <section key={group.title} className="service-guide-group">
      <h2><span aria-hidden="true">{index + 1}</span>{group.title}</h2>
      <ul>{group.items.map(([to, title, description]) => <li key={to}><Link to={to}><strong>{title}</strong><span>{description}</span><span className="guide-open" aria-hidden="true">보기</span></Link></li>)}</ul>
    </section>)}</div>
    <p className="quiet">정리한 경험이나 선택한 공고가 있어야 다음 단계를 진행할 수 있어요. 자료가 없으면 해당 화면에서 시작 방법을 안내합니다.</p>
  </ServicePage>
}
