import { useState } from 'react'
import { ServicePage } from '../../ui/ServicePage'

import { reviewHref, reviewScenario, screens } from './review-screens'

export function ScreenReview() {
  const [scenario, setScenario] = useState(reviewScenario)
  return <ServicePage title="개발용 화면 확인" className="screen-review">
    <p>현재 구현한 화면을 예시 자료로 확인합니다. 실제 AI나 회원 자료를 사용하지 않습니다.</p>
    <label htmlFor="review-scenario">확인할 상태</label>
    <select id="review-scenario" value={scenario} onChange={event => { const value = event.target.value; setScenario(value); try { sessionStorage.setItem('screen-review-scenario', value) } catch { /* Selection remains available for this page. */ } }}>
      <option value="normal">정상 흐름</option><option value="empty">첫 이용과 자료 없음</option>
      <option value="loading">처리 중</option><option value="failure">요청 실패</option>
      <option value="expired">이용 시간 만료</option><option value="closed">공고 마감</option><option value="changed">공고 변경 검토</option>
    </select>
    <p className="quiet">수정 후 이탈은 지원서나 경험을 수정한 다음 뒤로가기를 눌러 확인할 수 있습니다.</p>
    <p className="quiet">공고 마감과 변경은 공고 상세나 지원서에서 확인해 주세요. 처리 상태는 자료를 요청할 때 적용됩니다.</p>
    <ul className="review-screen-list">{screens.map(([key, title, description]) => <li key={key}>
      <a href={reviewHref(key, scenario)}><strong>{title}</strong><span>{description}</span></a>
    </li>)}</ul>
    <details><summary>기존 흐름 시안과 운영 화면</summary><ul>
      <li><a href="/dev/opportunity-flow">공고 탐색과 지원 흐름 시안</a></li>
      <li><a href="/dev/recommendations">추천 공고 흐름 시안</a></li>
      <li><a href="/dev/kakao-flow">카카오 로그인 흐름 시안</a></li>
      <li><a href="/journey-map">전체 이용 흐름 지도</a></li>
      <li><a href="/admin">운영 화면 진입</a> (운영자 인증 필요)</li>
    </ul></details>
    <details><summary>검수 서버 실행 방법</summary><p>프론트 폴더에서 npm run dev:review를 실행합니다. 일반 개발 서버와 별도로 5190 포트에서 열리며 예시 API만 사용합니다.</p></details>
  </ServicePage>
}
