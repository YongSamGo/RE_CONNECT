import { Link } from 'react-router-dom'
import { JourneyNavigation, ServicePage } from '../../ui/ServicePage'

export function ConversationEntry() {
  return <ServicePage title="경험을 들려주세요" description="대화를 시작하기 전에 정보 이용 안내를 확인해 주세요.">
    <JourneyNavigation current="conversation" />
    <div className="service-entry"><h2>어떤 이야기를 나누나요?</h2><p>일하거나 활동하면서 쌓은 경험을 한 가지씩 이야기합니다.</p>
      <Link className="button primary" to="/start">대화 시작하기</Link></div>
  </ServicePage>
}
