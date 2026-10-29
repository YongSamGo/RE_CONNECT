import { Link } from 'react-router-dom'
import { ServicePage } from '../../ui/ServicePage'

const examples = [
  { title: '도서관 자료 정리 지원 봉사', organization: '서울나눔도서관', activity: '봉사', region: '서울특별시 마포구', schedule: '주 2회, 오전 활동' },
  { title: '디지털 생활 안내 도우미', organization: '우리동네 복지센터', activity: '공공일자리', region: '서울특별시 은평구', schedule: '주 3회, 하루 4시간' },
  { title: '지역 문화 행사 운영 지원', organization: '마을문화재단', activity: '봉사', region: '경기도 고양시', schedule: '행사 일정에 따라 활동' },
]

export function SavedOpportunities() {
  return <ServicePage member title="저장한 공고" className="saved-opportunities-page">
    <section className="saved-opportunity-list" aria-label="저장한 공고 목록">
      {examples.map(item => <article className="saved-opportunity-card" key={item.title}>
        <span className="saved-opportunity-example">예시 공고</span>
        <h2>{item.title}</h2>
        <p className="saved-opportunity-organization">{item.organization}</p>
        <ul className="saved-opportunity-tags" aria-label={`${item.title} 정보`}>
          <li>{item.activity}</li><li>{item.region}</li><li>{item.schedule}</li>
        </ul>
      </article>)}
    </section>
    <div className="saved-opportunities-action"><Link className="button primary" to="/opportunities">공고 살펴보기</Link></div>
  </ServicePage>
}
