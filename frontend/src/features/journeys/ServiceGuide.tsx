import { ConsentTopics } from '../consent/ConsentTopics'
import { ServicePage } from '../../ui/ServicePage'

export function ServiceGuide() {
  return <ServicePage title="이용약관 및 정보 처리">
    <ConsentTopics />
  </ServicePage>
}
