import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { ServicePage } from '../../ui/ServicePage'
import { RequestError } from '../../ui/StatusNotice'
import { ProfileSummary } from '../profile/ProfileSummary'
import { parseRegionCatalog } from '../regions/catalog'
import type { RegionCatalog } from '../regions/catalog'
import { parseSession } from './session'
import { parseSavedProfile } from './saved-profile-model'

type Loaded = { profile: components['schemas']['SavedProfile'] | null; catalog: RegionCatalog }
export function MemberProfile() {
  const request = useRequest<Loaded>()
  const { state } = request
  const pending = state.status === 'pending'
  function load() {
    void request.run(async (api, signal) => {
      const owner = parseSession(required((await api.GET('/me', { signal })).data))
      if (!owner.authenticated || !owner.user) throw new ApiError('UNAUTHENTICATED', 401)
      const profile = parseSavedProfile(required((await api.GET('/profiles/me', { signal })).data))
      const catalog = parseRegionCatalog(required((await api.GET('/regions', { signal })).data))
      const current = parseSession(required((await api.GET('/me', { signal })).data))
      if (!current.authenticated || current.user?.id !== owner.user.id) throw new ApiError('SESSION_EXPIRED', 401)
      return { profile, catalog }
    })
  }
  return <ServicePage member title="내 프로필" description="저장한 경험과 희망 활동을 확인합니다.">
    <Button variant="secondary" pending={pending} onClick={load}>{state.status === 'success' ? '프로필 다시 불러오기' : '저장한 프로필 불러오기'}</Button>
    {pending && <p role="status">저장한 프로필을 확인하고 있어요.</p>}
    {state.status === 'error' && <><RequestError error={state.error} />{state.error.code === 'UNAUTHENTICATED' && <Link className="text-link" to="/login">로그인하기</Link>}</>}
    {state.status === 'idle' && <div className="service-empty"><h2>저장한 프로필 확인</h2><p>로그인한 계정에 저장한 프로필을 불러옵니다. 저장하지 않은 내용은 포함되지 않습니다.</p></div>}
    {state.status === 'success' && (state.data.profile ? <>
      <p className="quiet">저장한 프로필 / {new Date(state.data.profile.saved_at).toLocaleDateString('ko-KR')} 저장</p>
      <ProfileSummary content={state.data.profile.content} catalog={state.data.catalog} />
      <div className="actions"><Link className="button primary" to="/me/saved">프로필 편집, 저장 자료 관리</Link><Link className="text-link" to="/opportunities">공고 살펴보기</Link></div>
      <p className="quiet">프로필 편집은 저장한 자료 화면에서 새 체험을 시작해 진행해요. 변경한 내용은 다시 저장해야 반영됩니다.</p>
    </> : <div className="service-empty"><h2>아직 저장한 프로필이 없어요</h2><p>경험을 이야기하고 정리한 내용을 확인한 뒤, 내 프로필로 저장해 보세요.</p><Link className="button primary" to="/start">내 경험 이야기하기</Link></div>)}
  </ServicePage>
}
