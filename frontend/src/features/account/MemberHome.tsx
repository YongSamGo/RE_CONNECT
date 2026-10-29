import { useEntryAction } from '../../state/useEntryAction'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { Button } from '../../ui/Button'
import { ServicePage } from '../../ui/ServicePage'
import { RequestError } from '../../ui/StatusNotice'
import { required, useRequest } from '../../state/useRequest'
import { parseSession } from './session'
import { ApiError } from '../../api/errors'
import { parseSavedProfile } from './saved-profile-model'
import { provinces } from '../public-opportunities/catalog'
import { AccountPage } from './AccountPage'
import { SavedMaterials } from './SavedMaterials'

type MemberProfile = ReturnType<typeof parseSavedProfile>
type MemberSummary = { session: components['schemas']['Me']; profile: MemberProfile }
const activityLabels = { employment: '취업 및 공공일자리', volunteering: '봉사' }
const paidLabels = { paid: '보수 있음', unpaid: '무보수', any: '상관없음' }
const weekdays = ['월요일', '화요일', '수요일', '목요일', '금요일', '토요일', '일요일']

function profileNarrative(profile: NonNullable<MemberProfile>['content']) {
  const sentences = profile.experiences
    .map(experience => experience.description.trim())
    .filter(Boolean)
  if (profile.skills.length) sentences.push(`정리한 역량은 ${profile.skills.join(', ')}예요.`)
  const regions = [...new Set(profile.preferred_regions.map(region => provinces[region.province]))]
  const activities = profile.activity_types.map(activity => activityLabels[activity])
  if (regions.length || activities.length) {
    const where = regions.length ? `${regions.join(', ')}에서 ` : ''
    const what = activities.length ? `${activities.join(', ')} 활동` : '활동'
    sentences.push(`앞으로 ${where}${what}을 희망해요.`)
  }
  return sentences.join(' ')
}

export function MemberHome() {
  const request = useRequest<MemberSummary>()
  const load = () => request.run(async (api, signal) => {
    const session = parseSession(required((await api.GET('/me', { signal })).data))
    const profile = session.authenticated
      ? parseSavedProfile(required((await api.GET('/profiles/me', { signal })).data))
      : null
    if (session.authenticated) {
      const current = parseSession(required((await api.GET('/me', { signal })).data))
      if (!current.authenticated || current.user?.id !== session.user?.id) throw new ApiError('SESSION_EXPIRED', 401)
    }
    return { session, profile }
  })
  useEntryAction(load)
  const state = request.state
  const profile = state.status === 'success' ? state.data.profile?.content : null
  return <ServicePage title="나의 정보" className="member-home">
    {state.status === 'pending' && <p role="status">나의 정보를 확인하고 있어요.</p>}
    {state.status === 'error' && <RequestError error={state.error} actions={<Button onClick={() => void load()}>다시 확인하기</Button>} />}
    {state.status === 'success' && (!state.data.session.authenticated ? <div className="service-entry">
      <p>회원 정보를 보려면 로그인해 주세요.</p>
      <Link className="button primary" to="/login">로그인하기</Link>
    </div> : <>
      {!profile ? <div className="service-entry"><p>아직 정보가 없습니다.</p><Link className="button primary" to="/start">나의 경험 이야기하기</Link></div> : <section className="panel member-profile-overview">
        <header className="member-profile-heading"><h2>저장한 프로필</h2><SavedMaterials resumeLabel="수정하기" /></header>
          {profileNarrative(profile) && <p className="member-profile-narrative">{profileNarrative(profile)}</p>}
          {(profile.birth_year !== null || profile.residence_region) && <dl className="member-profile-facts">
            {profile.birth_year !== null && <div><dt>출생 연도</dt><dd>{profile.birth_year}년</dd></div>}
            {profile.residence_region && <div><dt>거주 지역</dt><dd>{provinces[profile.residence_region.province]}</dd></div>}
          </dl>}
          <section className="member-profile-section">
            <h3>내 경험</h3>
            {profile.experiences.length ? <ul className="member-experience-list">{profile.experiences.map(experience => <li key={experience.id}><p>{experience.description}</p>{experience.duration_note && <span>활동 기간 {experience.duration_note}</span>}</li>)}</ul> : <p>저장한 경험이 없습니다.</p>}
          </section>
          {profile.skills.length > 0 && <section className="member-profile-section"><h3>보유 역량</h3><ul className="member-profile-tags">{profile.skills.map(skill => <li key={skill}>{skill}</li>)}</ul></section>}
          <dl className="member-profile-facts">
            {profile.preferred_regions.length > 0 && <div><dt>희망 지역</dt><dd>{[...new Set(profile.preferred_regions.map(region => provinces[region.province]))].join(', ')}</dd></div>}
            {profile.activity_types.length > 0 && <div><dt>희망 활동</dt><dd>{profile.activity_types.map(activity => activityLabels[activity]).join(', ')}</dd></div>}
            {profile.paid_preference && <div><dt>보수 희망</dt><dd>{paidLabels[profile.paid_preference]}</dd></div>}
            {profile.available_weekdays && <div><dt>가능한 요일</dt><dd>{profile.available_weekdays.map(day => weekdays[day - 1]).join(', ')}</dd></div>}
            {profile.hours_per_week !== null && <div><dt>주당 가능 시간</dt><dd>{profile.hours_per_week}시간</dd></div>}
            {profile.certifications && profile.certifications.length > 0 && <div><dt>자격</dt><dd>{profile.certifications.join(', ')}</dd></div>}
            {profile.completed_courses && profile.completed_courses.length > 0 && <div><dt>이수 과정</dt><dd>{profile.completed_courses.join(', ')}</dd></div>}
            {profile.mobility_note && <div><dt>이동 관련 참고</dt><dd>{profile.mobility_note}</dd></div>}
            {profile.activity_constraints && profile.activity_constraints.length > 0 && <div><dt>활동 참고</dt><dd>{profile.activity_constraints.join(', ')}</dd></div>}
          </dl>
      </section>}
      <AccountPage autoLoad embedded onLogout={() => window.location.replace('/')} />
    </>)}
  </ServicePage>
}
