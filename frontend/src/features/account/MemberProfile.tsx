import { Link } from 'react-router-dom'
import { ServicePage } from '../../ui/ServicePage'

const story = {
  title: '도서관 자료 정리와 방문객 안내',
  description: '지역 도서관에서 자료를 정리하고 방문객이 필요한 곳을 찾도록 안내했습니다. 맡은 일을 꾸준히 살피며 이용하는 분들이 편하게 머물 수 있도록 도왔습니다.',
  interests: ['서울특별시 마포구', '봉사', '주 8시간'],
  skills: ['자료 정리', '방문객 안내', '꾸준한 업무 수행'],
}

export function MemberProfile() {
  return <ServicePage member title="나의 이야기" className="member-story-page">
    {story ? <article className="generated-profile-card member-story-card" tabIndex={0} aria-label="정리한 경험과 희망 활동">
      <h2>{story.title}</h2>
      <p>{story.description}</p>
      <section><h3>앞으로 하고 싶은 활동</h3>
        <ul className="generated-profile-tags">{story.interests.map(item => <li key={item}>{item}</li>)}</ul>
      </section>
      <section><h3>경험에서 찾은 역량</h3>
        <ul className="generated-profile-tags">{story.skills.map(item => <li key={item}>{item}</li>)}</ul>
      </section>
    </article> : <section className="member-story-empty">
      <h2>아직 정리한 이야기가 없어요</h2>
    </section>}
    <div className="member-story-cta"><Link className="button primary" to="/start">{story ? '나에게 맞는 공고 찾기' : '지금 경험 이야기하러 가기'}</Link></div>
  </ServicePage>
}
