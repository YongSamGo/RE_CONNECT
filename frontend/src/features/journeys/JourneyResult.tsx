import { Link } from 'react-router-dom'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { JourneyNavigation, ServicePage } from '../../ui/ServicePage'
import { RequestError } from '../../ui/StatusNotice'
import { ProfileSummary } from '../profile/ProfileSummary'
import { parseProfileView } from '../profile/server-model'
import type { ProfileView } from '../profile/server-model'
import { JourneyRoute } from './JourneyRoute'
import { JourneyProfile } from '../profile/JourneyProfile'

export function JourneyResultRoute() {
  return <JourneyRoute page="results">{id => <JourneyProfile key={id} journeyId={id} />}</JourneyRoute>
}

export function JourneyResult({ journeyId }: { journeyId?: string }) {
  const request = useRequest<ProfileView>()
  const { state } = request
  const view = state.status === 'success' ? state.data : null
  const confirmed = !!view?.confirmed && !view.has_unconfirmed_changes
  function load() {
    if (!journeyId) return
    void request.run(async (api, signal) => parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { signal, params: { path: { journey_id: journeyId } } })).data)))
  }
  return <ServicePage title="정리한 경험 확인" description="정리한 내용을 확인하고 필요한 부분을 수정해 주세요.">
    <JourneyNavigation current="results" journeyId={journeyId} />
    {journeyId && <Button variant="secondary" pending={state.status === 'pending'} onClick={load}>정리한 경험 불러오기</Button>}
    {state.status === 'pending' && <p role="status">이야기에서 정리한 경험을 확인하고 있어요.</p>}
    {state.status === 'error' && <RequestError error={state.error} />}
    {view ? <><p className="service-state">{confirmed ? '확정한 프로필' : '확인 중인 초안'}</p><ProfileSummary content={view.draft} />
      <div className="actions"><Link className="button primary" to={`/journeys/${journeyId}/profile`}>{confirmed ? '프로필 확인, 수정' : '내용 확인하고 프로필 확정'}</Link>
      {confirmed && <Link className="button secondary" to={`/journeys/${journeyId}/recommendations`}>추천 공고 확인하기</Link>}</div>
      {confirmed && <Link className="text-link" to={`/journeys/${journeyId}/save`}>이 프로필 저장하기</Link>}
      <p className="quiet">프로필 확정과 회원 저장은 별개예요. 내용을 수정하면 다시 확정해 주세요.</p>
    </> : !journeyId ? <div className="service-entry"><h2>아직 정리한 경험이 없습니다</h2><p>대화를 시작하면 정리한 내용을 확인할 수 있습니다.</p>
      <Link className="button primary" to="/start">경험 이야기하기</Link></div> : state.status === 'idle' ? <p>대화에서 정리한 내용을 불러와 확인해 주세요.</p> : null}
  </ServicePage>
}
