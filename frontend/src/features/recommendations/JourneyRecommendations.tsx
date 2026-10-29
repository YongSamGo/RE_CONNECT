import { useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { JourneyRoute } from '../journeys/JourneyRoute'
import { minimumErrors, parseProfileView } from '../profile/server-model'
import type { ProfileView } from '../profile/server-model'
import { ProfileSummary } from '../profile/ProfileSummary'
import { deadlineLabel, provinces } from '../public-opportunities/catalog'
import { checkedTime } from '../public-opportunities/detail'
import { OpportunityListCard } from '../opportunities/OpportunityListCard'
import { demoOpportunities } from '../development/demo-opportunities'
import { eligibilityLabels, parseEligibility, parseRecommendations } from './model'
import type { Eligibility, ProfileRef, Recommendations } from './model'
import { ServicePage } from '../../ui/ServicePage'
import './recommendation-screen.css'

const reasonLabels = { missing_profile_value: '확정 프로필 정보가 부족합니다.', unclear_requirement: '원문 조건 또는 명칭의 해석을 확인해야 합니다.',
  age_boundary: '나이 경계에 해당해 확인이 필요합니다.', reference_date_missing: '조건의 기준일이 없습니다.', unsupported_group: '조건 조합을 확인해야 합니다.' }
const fieldLabels = { age: '출생 연도', residence_region: '거주 지역', certification: '자격증', completed_course: '수료 교육', weekday: '가능 요일', hours_per_week: '주당 가능 시간', other: '기타 조건' }

function userValue(value: Eligibility['conditions'][number]['user_value']): string {
  if (value === null) return '미확인'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '없음으로 확인'
  if (typeof value === 'object') return `${provinces[value.province]}${value.district ? ` / ${value.district}` : ' 전체'}`
  return String(value)
}

export function EligibilityCheck({ profile, opportunity, onInvalidated, actionLabel = '이 공고의 필수조건 자세히 대조' }: { profile: ProfileRef; opportunity: { id: string; version: number }; onInvalidated?: (error: ApiError) => void; actionLabel?: string }) {
  const request = useRequest<Eligibility>()
  const resultRef = useRef<HTMLDivElement>(null)
  const state = request.state
  useEffect(() => { if (state.status === 'success' || state.status === 'error') resultRef.current?.focus({ preventScroll: true }) }, [state.status])
  useEffect(() => {
    if (state.status === 'error' && ['NOT_FOUND', 'SESSION_EXPIRED', 'UNAUTHENTICATED', 'CONSENT_REQUIRED', 'VERSION_CONFLICT', 'OPPORTUNITY_NOT_AVAILABLE'].includes(state.error.code)) onInvalidated?.(state.error)
  }, [state, onInvalidated])
  const check = () => void request.run(async (api, signal) => parseEligibility(required((await api.POST('/opportunities/{opportunity_id}/eligibility', {
    params: { path: { opportunity_id: opportunity.id } }, body: { profile, opportunity_version: opportunity.version }, signal,
  })).data), profile, opportunity))
  return <section aria-label="개인 자격 대조"><Button variant="secondary" pending={state.status === 'pending'} onClick={check}>{actionLabel}</Button>
    <div className={state.status === 'success' ? 'eligibility-results' : undefined} ref={resultRef} tabIndex={-1}>
      {state.status === 'error' && <RequestError error={state.error} />}
      {state.status === 'success' && <>
        <h4>필수조건 대조: {eligibilityLabels[state.data.overall]}</h4>
        <p>확정 프로필 {profile.version}번 / 공고 {opportunity.version}번 / {checkedTime(state.data.evaluated_at)} 대조. 지원 자격의 최종 결정이나 선발 보장이 아닙니다.</p>
        {state.data.no_requirements && <p>검수된 공고에 명시된 필수조건이 없습니다. 공식 안내도 확인해 주세요.</p>}
        <ul className="eligibility-conditions">{state.data.conditions.map(condition => <li key={condition.requirement_id}>
          <strong>{eligibilityLabels[condition.result]}</strong><p className="user-text">원문 조건: {condition.source_evidence}</p>
          <p>대조한 확정 {fieldLabels[condition.field]}: {userValue(condition.user_value)}</p>
          {condition.review_reason && <p>{reasonLabels[condition.review_reason]}</p>}
        </li>)}</ul>
        {state.data.groups.length > 0 && <><p>원문의 조건 묶음 결과입니다. 개별 조건의 결과와 종합 결과가 다를 수 있습니다.</p><ul>{state.data.groups.map((group, index) => <li key={group.group_id}>
          조건 묶음 {index + 1}: {group.operator === 'and' ? '모두 충족(AND)' : '하나 이상 충족(OR)'}: {eligibilityLabels[group.result]}
        </li>)}</ul></>}
      </>}
    </div>
  </section>
}

export function JourneyRecommendationsRoute() {
  return <JourneyRoute page="recommendations">{id => <JourneyRecommendations key={id} journeyId={id} />}</JourneyRoute>
}

export function JourneyRecommendations({ journeyId, preview = false }: { journeyId?: string; preview?: boolean }) {
  const request = useRequest<Recommendations>()
  const profileRequest = useRequest<{ view: ProfileView; missing: string[] }>()
  const { value: profileView, setValue: setProfileView } = useMemoryScope<ProfileView | null>(() => null)
  const { value: missing, setValue: setMissing } = useMemoryScope<string[]>(() => [])
  const resultRef = useRef<HTMLElement>(null)
  const state = request.state
  const profileState = profileRequest.state
  const pending = state.status === 'pending' || profileState.status === 'pending'

  const loadRecommendations = useCallback((view: ProfileView) => {
    if (!journeyId || !view.confirmed || view.has_unconfirmed_changes) return
    const profile: ProfileRef = { kind: 'journey', id: journeyId, version: view.confirmed.version }
    void request.run(async (api, signal) => {
      await api.GET('/me', { signal })
      return parseRecommendations(required((await api.POST('/recommendations', { body: { profile, filters: {} }, signal })).data), profile)
    })
  // useRequest.run is intentionally omitted: its wrapper is recreated each render.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [journeyId])

  const readProfile = useCallback((confirm: boolean) => {
    if (!journeyId) return
    setMissing([])
    void profileRequest.run(async (api, signal): Promise<{ view: ProfileView; missing: string[] }> => {
      await api.GET('/me', { signal })
      let view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
      if (confirm && (!view.confirmed || view.has_unconfirmed_changes)) {
        const errors = minimumErrors(view.draft)
        if (errors.length) return { view, missing: errors.map(error => error.message) }
        await api.POST('/journeys/{journey_id}/profile/confirm', { params: { path: { journey_id: journeyId } }, body: { base_revision: view.revision }, signal })
        view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
      }
      return { view, missing: [] as string[] }
    }, result => {
      setProfileView(result.view)
      setMissing(result.missing)
      if (!result.missing.length && result.view.confirmed && !result.view.has_unconfirmed_changes) loadRecommendations(result.view)
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [journeyId, loadRecommendations])

  useEffect(() => { if (!preview) readProfile(false) }, [preview, readProfile])
  useEffect(() => { if (state.status === 'error') resultRef.current?.focus({ preventScroll: true }) }, [state.status])

  const cards = preview ? demoOpportunities.map(item => ({ id: item.id, version: 1, title: item.title, organization: item.organization, activity: item.activity, region: item.region, deadline: item.deadline, to: '/dev/opportunity-flow?source=recommendation' })) : state.status === 'success' ? state.data.items.map(item => ({
    id: item.opportunity.id,
    version: item.opportunity.version,
    title: item.opportunity.title,
    organization: item.opportunity.organization_name,
    activity: item.opportunity.activity_type === 'employment' ? '취업 및 공공일자리' : '봉사',
    region: item.opportunity.activity_region ? provinces[item.opportunity.activity_region.province] : '지역 확인 필요',
    deadline: deadlineLabel(item.opportunity),
    to: `/opportunities/${item.opportunity.id}${journeyId ? `?journeyId=${encodeURIComponent(journeyId)}` : ''}`,
  })) : []

  if (!journeyId && !preview) return <ServicePage title="나에게 맞는 공고 찾기"><div className="service-entry"><p>경험을 정리하고 확인하면 관련 공고를 추천받을 수 있어요.</p><Link className="button primary" to="/start">경험 이야기하기</Link><Link className="text-link" to="/opportunities?browse=all">전체 공고 둘러보기</Link></div></ServicePage>

  return <ServicePage title="다시잇다가 추천하는 공고입니다" className={`recommendation-page${preview ? ' recommendation-preview' : ''}`}>
    {profileState.status === 'pending' && <StatusNotice kind="loading" title="경험을 확인하고 있어요">잠시만 기다려 주세요.</StatusNotice>}
    {profileState.status === 'error' && <RequestError error={profileState.error} actions={<Button onClick={() => readProfile(false)}>다시 확인하기</Button>} />}
    {profileView && (!profileView.confirmed || profileView.has_unconfirmed_changes) && <section className="recommendation-profile-check">
      <h2>추천에 사용할 경험을 확인해 주세요</h2>
      <ProfileSummary content={profileView.draft} />
      {missing.map(message => <p role="alert" key={message}>{message}</p>)}
      <div className="actions"><Link className="button primary" to={`/journeys/${journeyId}/profile`}>내 경험 확인하고 수정하기</Link></div>
    </section>}
    {state.status === 'error' && <RequestError error={state.error} actions={<Button pending={pending} onClick={() => readProfile(false)}>추천 다시 확인하기</Button>} />}
    <section className="recommendation-scroll-panel" ref={resultRef} tabIndex={-1} aria-label="추천 공고 목록">
      {!preview && state.status === 'pending' && <p role="status">추천 공고를 불러오고 있어요.</p>}
      {!preview && (profileState.status === 'pending' || state.status === 'pending') && <ol className="recommendation-cards recommendation-card-skeletons" aria-hidden="true">
        {[1, 2, 3].map(index => <li key={index}><article className="recommendation-card recommendation-card-skeleton">
          <span className="skeleton-line skeleton-title" /><span className="skeleton-line skeleton-meta" />
          <span className="skeleton-line skeleton-description" /><span className="skeleton-action" />
        </article></li>)}
      </ol>}
      {!preview && state.status === 'success' && <>
        {state.data.items.length === 0 && <StatusNotice label="추천 결과" title="현재 조건에 연결되는 추천이 없어요" actions={<Link className="button secondary" to="/opportunities?browse=all">전체 공고 둘러보기</Link>}>경험을 보완하거나 다른 공고를 살펴보세요.</StatusNotice>}
      </>}
      {(preview || state.status === 'success' && state.data.items.length > 0) && <>
        <ol className="shared-opportunity-list">{cards.map(item => <OpportunityListCard key={`${item.id}:${item.version}`} title={item.title} organization={item.organization}
          tags={[item.activity, item.region, item.deadline]} to={item.to} state={{ journeyId }} />)}</ol>
      </>}
    </section>
  </ServicePage>
}
