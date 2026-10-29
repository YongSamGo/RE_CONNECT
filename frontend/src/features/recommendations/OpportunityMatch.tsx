import { useEntryAction } from '../../state/useEntryAction'
import { Link } from 'react-router-dom'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { parseProfileView } from '../profile/server-model'
import { EligibilityCheck } from './JourneyRecommendations'
import { parseRecommendations } from './model'
import type { ProfileRef, Recommendations } from './model'

type Match = { profile: ProfileRef | null; item: Recommendations['items'][number] | null }

export function OpportunityMatch({ journeyId, opportunity }: { journeyId: string; opportunity: { id: string; version: number } }) {
  const request = useRequest<Match>()
  const load = () => request.run(async (api, signal) => {
    const view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { signal, params: { path: { journey_id: journeyId } } })).data))
    if (!view.confirmed || view.has_unconfirmed_changes) return { profile: null, item: null }
    const profile: ProfileRef = { kind: 'journey', id: journeyId, version: view.confirmed.version }
    const result = parseRecommendations(required((await api.POST('/recommendations', { signal, body: { profile, filters: {} } })).data), profile)
    return { profile, item: result.items.find(entry => entry.opportunity.id === opportunity.id && entry.opportunity.version === opportunity.version) ?? null }
  })
  useEntryAction(load, true, `${journeyId}:${opportunity.id}:${opportunity.version}`)
  const state = request.state
  return <section className="opportunity-match" aria-label="내 경험과 공고 비교">
    <div className="opportunity-match-summary"><h2>내 경험과 맞는 점</h2>
    {state.status === 'pending' && <p role="status">확인한 경험과 비교하고 있어요.</p>}
    {state.status === 'error' && <RequestError error={state.error} actions={<Button variant="secondary" onClick={() => void load()}>다시 비교하기</Button>} />}
    {state.status === 'success' && (state.data.profile ? <>
      {state.data.item ? <>
        <p>{state.data.item.matched.skill_tags.length ? `${state.data.item.matched.skill_tags.slice(0, 3).join(', ')} 경험이 연결됩니다.` : '확인한 경험과 관련된 활동입니다.'}</p>
        {state.data.item.eligibility.overall === 'unknown' && <p>지원 전에 확인할 조건이 있어요.</p>}
      </> : <p>현재 추천 목록에는 포함되어 있지 않아요. 필수조건을 확인해 주세요.</p>}
    </> : <p>추천에 사용할 경험을 먼저 확인해 주세요. <Link to={`/journeys/${journeyId}/profile`}>내 경험 확인</Link></p>)}
    </div>
    {state.status === 'success' && state.data.profile && <EligibilityCheck key={`${state.data.profile.version}:${opportunity.version}`} profile={state.data.profile} opportunity={opportunity} onInvalidated={request.clear} actionLabel="자세히 보기" />}
  </section>
}
