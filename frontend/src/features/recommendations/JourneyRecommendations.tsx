import { useCallback, useEffect, useRef } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { JourneyRoute } from '../journeys/JourneyRoute'
import { parseProfileView } from '../profile/server-model'
import { deadlineLabel, provinces } from '../public-opportunities/catalog'
import { checkedTime } from '../public-opportunities/detail'
import { eligibilityLabels, parseEligibility, parseRecommendations } from './model'
import type { Eligibility, ProfileRef, Recommendations } from './model'

type Filters = { province: '' | keyof typeof provinces; activity: '' | 'employment' | 'volunteering'; paid: '' | 'true' | 'false' }
const emptyFilters = (): Filters => ({ province: '', activity: '', paid: '' })
const reasonLabels = { missing_profile_value: '확정 프로필 정보가 부족합니다.', unclear_requirement: '원문 조건 또는 명칭의 해석을 확인해야 합니다.',
  age_boundary: '나이 경계에 해당해 확인이 필요합니다.', reference_date_missing: '조건의 기준일이 없습니다.', unsupported_group: '조건 조합을 확인해야 합니다.' }
const fieldLabels = { age: '출생 연도', residence_region: '거주 지역', certification: '자격증', completed_course: '수료 교육', weekday: '가능 요일', hours_per_week: '주당 가능 시간', other: '기타 조건' }

function userValue(value: Eligibility['conditions'][number]['user_value']): string {
  if (value === null) return '미확인'
  if (Array.isArray(value)) return value.length ? value.join(', ') : '없음으로 확인'
  if (typeof value === 'object') return `${provinces[value.province]}${value.district ? ` / ${value.district}` : ' 전체'}`
  return String(value)
}

export function EligibilityCheck({ profile, opportunity, onInvalidated }: { profile: ProfileRef; opportunity: { id: string; version: number }; onInvalidated?: (error: ApiError) => void }) {
  const request = useRequest<Eligibility>()
  const resultRef = useRef<HTMLDivElement>(null)
  const state = request.state
  useEffect(() => { if (state.status === 'success' || state.status === 'error') resultRef.current?.focus() }, [state.status])
  useEffect(() => {
    if (state.status === 'error' && ['NOT_FOUND', 'SESSION_EXPIRED', 'UNAUTHENTICATED', 'CONSENT_REQUIRED', 'VERSION_CONFLICT', 'OPPORTUNITY_NOT_AVAILABLE'].includes(state.error.code)) onInvalidated?.(state.error)
  }, [state, onInvalidated])
  const check = () => void request.run(async (api, signal) => parseEligibility(required((await api.POST('/opportunities/{opportunity_id}/eligibility', {
    params: { path: { opportunity_id: opportunity.id } }, body: { profile, opportunity_version: opportunity.version }, signal,
  })).data), profile, opportunity))
  return <section aria-label="개인 자격 대조"><Button variant="secondary" pending={state.status === 'pending'} onClick={check}>이 공고의 필수조건 자세히 대조</Button>
    <div ref={resultRef} tabIndex={-1}>
      {state.status === 'error' && <RequestError error={state.error} />}
      {state.status === 'success' && <>
        <h4>필수조건 대조: {eligibilityLabels[state.data.overall]}</h4>
        <p>확정 프로필 {profile.version}번 · 공고 {opportunity.version}번 · {checkedTime(state.data.evaluated_at)} 대조. 지원 자격의 최종 결정이나 선발 보장이 아닙니다.</p>
        {state.data.no_requirements && <p>검수된 공고에 명시된 필수조건이 없습니다. 공식 안내도 확인해 주세요.</p>}
        <ul>{state.data.conditions.map(condition => <li key={condition.requirement_id}>
          <strong>{eligibilityLabels[condition.result]}</strong><p className="user-text">원문 조건: {condition.source_evidence}</p>
          <p>대조한 확정 {fieldLabels[condition.field]}: {userValue(condition.user_value)}</p>
          {condition.review_reason && <p>{reasonLabels[condition.review_reason]}</p>}
        </li>)}</ul>
        {state.data.groups.length > 0 && <><p>원문의 조건 묶음 결과입니다. 개별 조건의 결과와 종합 결과가 다를 수 있습니다.</p><ul>{state.data.groups.map((group, index) => <li key={group.group_id}>
          조건 묶음 {index + 1} · {group.operator === 'and' ? '모두 충족(AND)' : '하나 이상 충족(OR)'}: {eligibilityLabels[group.result]}
        </li>)}</ul></>}
      </>}
    </div>
  </section>
}

export function JourneyRecommendationsRoute() {
  return <JourneyRoute page="recommendations">{id => <JourneyRecommendations key={id} journeyId={id} />}</JourneyRoute>
}

export function JourneyRecommendations({ journeyId }: { journeyId: string }) {
  const filters = useMemoryScope(emptyFilters)
  const request = useRequest<Recommendations | null>()
  const invalidated = useMemoryScope<ApiError | null>(() => null)
  const clearResults = request.clear
  const setInvalidated = invalidated.setValue
  const invalidate = useCallback((error: ApiError) => { clearResults(); setInvalidated(error) }, [clearResults, setInvalidated])
  const resultRef = useRef<HTMLElement>(null)
  const state = request.state
  const pending = state.status === 'pending'
  useEffect(() => { if (state.status === 'success' || state.status === 'error' || invalidated.value) resultRef.current?.focus() }, [state.status, invalidated.value])
  const change = (value: Filters) => { request.clear(); invalidated.clear(); filters.setValue(value) }
  function load() {
    invalidated.clear()
    const selection = filters.value
    void request.run(async (api, signal) => {
      await api.GET('/me', { signal })
      const view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
      if (!view.confirmed) return null
      const profile: ProfileRef = { kind: 'journey', id: journeyId, version: view.confirmed.version }
      const narrowed: components['schemas']['RecommendationRequest']['filters'] = {
        ...(selection.province ? { regions: [{ province: selection.province, district: null }] } : {}),
        ...(selection.activity ? { activity_types: [selection.activity] } : {}), ...(selection.paid ? { paid: selection.paid === 'true' } : {}),
      }
      return parseRecommendations(required((await api.POST('/recommendations', { body: { profile, filters: narrowed }, signal })).data), profile)
    })
  }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">06 · 내 경험과 연결된 기회</p><h1>확정한 경험으로 기회를 찾아봐요</h1><p>추천은 실제 확정 경험의 연결 근거를 보여 줍니다. 선발 가능성이나 성공 확률을 뜻하지 않습니다.</p></header>
    <p><Link to={`/journeys/${journeyId}/profile`}>프로필 확인·수정·역할 제외</Link> · <Link to="/opportunities">프로필 없이 공개 공고 검색</Link></p>
    <form className="panel" onSubmit={event => { event.preventDefault(); load() }}><fieldset disabled={pending}><legend>확정 프로필 안에서 범위 좁히기</legend>
      <p>선택하지 않으면 확정 프로필 조건을 사용합니다. 조건을 자동으로 넓히지 않습니다.</p>
      <label htmlFor="recommend-region">활동 지역 추가 제한</label><select id="recommend-region" value={filters.value.province} onChange={event => change({ ...filters.value, province: event.target.value as Filters['province'] })}>
        <option value="">추가 제한 없음</option>{Object.entries(provinces).map(([id, name]) => <option key={id} value={id}>{name} 전체</option>)}</select>
      <label htmlFor="recommend-activity">활동 유형 추가 제한</label><select id="recommend-activity" value={filters.value.activity} onChange={event => change({ ...filters.value, activity: event.target.value as Filters['activity'] })}>
        <option value="">추가 제한 없음</option><option value="employment">취업·공공일자리</option><option value="volunteering">봉사</option></select>
      <label htmlFor="recommend-paid">보수 추가 제한</label><select id="recommend-paid" value={filters.value.paid} onChange={event => change({ ...filters.value, paid: event.target.value as Filters['paid'] })}>
        <option value="">추가 제한 없음</option><option value="true">유급</option><option value="false">무급</option></select>
      <Button type="submit" pending={pending}>추천 다시 확인하기</Button>
    </fieldset></form>
    {pending && <Button variant="secondary" onClick={request.clear}>조회 취소하기</Button>}
    <section ref={resultRef} tabIndex={-1} aria-label="추천 조회 결과">
      {invalidated.value && <><RequestError error={invalidated.value} /><p>기존 결과를 지웠습니다. 프로필과 공고의 최신 상태로 추천을 다시 확인해 주세요.</p></>}
      {state.status === 'error' && <RequestError error={state.error} />}
      {state.status === 'success' && (state.data === null ? <StatusNotice label="프로필 확인" title="먼저 프로필을 직접 확정해 주세요">프로필에서 경험·희망 지역·활동 유형을 확인하고 확정할 수 있습니다. 대화를 끝낼 필요는 없습니다.</StatusNotice> : <>
        <p>확정 프로필 {state.data.profile.version}번 · {checkedTime(state.data.generated_at)} 조회</p>
        {state.data.based_on_previous_confirmed && <StatusNotice label="프로필 수정 중" title="이전 확정 프로필 기준">수정한 초안은 아직 반영되지 않았습니다. 프로필을 재확정하고 추천을 다시 확인해 주세요.</StatusNotice>}
        {state.data.items.length === 0 && <StatusNotice label="추천 결과" title="현재 조건에 연결되는 추천이 없습니다">필수조건을 완화하지 않았습니다. 선택 필터와 확정 프로필을 직접 확인하거나 공개 공고를 살펴보세요.</StatusNotice>}
        <ol className="opportunity-list">{state.data.items.slice(0, 5).map(item => <li className="panel" key={`${item.opportunity.id}:${item.opportunity.version}`}><article>
          <h2>{item.opportunity.title}</h2><p>{item.opportunity.organization_name} · {item.opportunity.activity_type === 'employment' ? '취업·공공일자리' : '봉사'}</p>
          <p>{item.opportunity.activity_region ? provinces[item.opportunity.activity_region.province] : '지역 확인 필요'}{item.opportunity.remote_allowed === true && ' · 원격 가능'} · {deadlineLabel(item.opportunity)}</p>
          <h3>내 경험과 연결된 근거</h3><p>확정 경험 {item.matched.experience_ids.length}개와 연결했습니다.</p>
          {item.matched.skill_tags.length > 0 && <p className="user-text">연결 역량: {item.matched.skill_tags.join(', ')}</p>}
          {item.matched.keywords.length > 0 && <p className="user-text">겹치는 표현: {item.matched.keywords.join(', ')}</p>}
          {item.matched.role_ids.length > 0 && <p>연결된 역할 {item.matched.role_ids.length}개</p>}
          <p>필수조건: {item.eligibility.no_requirements ? '원문에 명시된 필수조건 없음' : eligibilityLabels[item.eligibility.overall]}
            {item.eligibility.needs_review_count > 0 && ` · 확인할 조건 ${item.eligibility.needs_review_count}개`}</p>
          <EligibilityCheck profile={state.data!.profile} opportunity={item.opportunity} onInvalidated={invalidate} />
          <Link className="button secondary" to={`/opportunities/${item.opportunity.id}`}>최신 상세·공식 원문·오류 신고 확인</Link>
          <Link className="button secondary" to={`/journeys/${journeyId}/opportunities/${item.opportunity.id}/preparation`}>확정 경험으로 신청 준비</Link>
        </article></li>)}</ol>
        <p>공고의 모집 상태와 조건은 바뀔 수 있습니다. 상세와 공식 원문을 다시 확인해 주세요. 실제 신청은 공식 신청처에서 직접 진행합니다.</p>
      </>)}
    </section>
  </div>
}
