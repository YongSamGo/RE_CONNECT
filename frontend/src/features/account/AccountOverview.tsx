import { Link } from 'react-router-dom'

export function AccountOverview() {
  return <section className="member-overview" aria-labelledby="member-overview-title">
    <h2 id="member-overview-title">내 경험 관리</h2>
    <p>저장한 프로필을 확인하거나 경험을 새로 정리할 수 있습니다.</p>
    <div className="member-overview-links">
      <Link to="/me/profile"><strong>내 프로필 확인</strong><span>정리해 둔 경험과 희망 활동</span></Link>
      <Link to="/start"><strong>새로운 경험 이야기</strong><span>AI와 한 가지씩 이야기하기</span></Link>
    </div>
  </section>
}
