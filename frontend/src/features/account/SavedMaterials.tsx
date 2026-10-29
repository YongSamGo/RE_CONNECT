import { useEntryAction } from '../../state/useEntryAction'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { createApiClient, csrfToken } from '../../api/client'
import { useMemoryScope } from '../../state/useMemoryScope'
import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { invalid, isOpportunityId, record } from '../public-opportunities/catalog'
import { parseSession } from './session'

type Api = ReturnType<typeof createApiClient>
type SavedProfile = { owner: string; profileId: string; version: number }
type ImportAttempt = SavedProfile & { notice: string; csrf: string; key: string;
  body: { ai_notice_version: string; saved_profile: { profile_id: string; version: number } } }

export function SavedMaterials({ resumeLabel = '수정하기' }: { resumeLabel?: string; onSessionReset?: () => void } = {}) {
  const navigate = useNavigate()
  const request = useRequest<SavedProfile | null>()
  const importRequest = useRequest<string>()
  const attempt = useMemoryScope<ImportAttempt | null>(() => null)
  const uncertain = useMemoryScope(() => false)
  const saved = request.state.status === 'success' ? request.state.data : null
  const busy = request.state.status === 'pending' || importRequest.state.status === 'pending'

  const load = () => request.run(async (api, signal) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || !me.user) throw new ApiError('UNAUTHENTICATED', 401)
    const response = record(required((await api.GET('/profiles/me', { signal })).data))
    if (response.saved === null) return null
    const profile = record(response.saved)
    const profileId = profile.profile_id
    const version = profile.version
    if (typeof profileId !== 'string' || !isOpportunityId(profileId) || typeof version !== 'number'
      || !Number.isSafeInteger(version) || version < 1) return invalid()
    const current = parseSession(required((await api.GET('/me', { signal })).data))
    if (!current.authenticated || current.user?.id !== me.user.id) throw new ApiError('SESSION_EXPIRED', 401)
    return { owner: me.user.id, profileId, version }
  })
  useEntryAction(load, true, 'saved-profile-edit')

  const clearAttempt = () => { attempt.clear(); uncertain.clear() }
  const assertOwner = async (api: Api, signal: AbortSignal, owner: string, expectedCsrf?: string) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || me.user?.id !== owner) {
      clearAttempt()
      throw new ApiError(me.authenticated ? 'SESSION_EXPIRED' : 'UNAUTHENTICATED', 401)
    }
    if (expectedCsrf !== undefined && csrfToken(document.cookie, window.location.href) !== expectedCsrf) {
      uncertain.setValue(true)
      throw new ApiError('SESSION_EXPIRED', 401)
    }
    return me
  }
  const startEdit = () => {
    if (!saved || busy) return
    void importRequest.run(async (api, signal) => {
      const previous = attempt.value
      const me = await assertOwner(api, signal, saved.owner, previous?.csrf)
      const notice = me.consents.find(item => item.purpose === 'ai_processing')?.notice_version
      if (!notice) throw new ApiError('CONSENT_REQUIRED', 403)
      const csrf = csrfToken(document.cookie, window.location.href)
      if (!csrf) throw new ApiError('CSRF_MISSING')
      if (previous && (previous.owner !== saved.owner || previous.profileId !== saved.profileId
        || previous.version !== saved.version || previous.notice !== notice || previous.csrf !== csrf)) {
        uncertain.setValue(true)
        throw new ApiError('VERSION_CONFLICT', 409)
      }
      const current = previous ?? {
        ...saved, notice, csrf, key: crypto.randomUUID(),
        body: Object.freeze({ ai_notice_version: notice,
          saved_profile: Object.freeze({ profile_id: saved.profileId, version: saved.version }) }),
      }
      attempt.setValue(current)
      try {
        const response = await api.POST('/journeys', { signal,
          params: { header: { 'Idempotency-Key': current.key } }, body: current.body })
        const result = record(required(response.data))
        const id = result.journey_id
        const confirmed = record(result.confirmed)
        if (typeof id !== 'string' || !isOpportunityId(id) || confirmed.version !== 1) return invalid()
        await assertOwner(api, signal, saved.owner, current.csrf)
        return id
      } catch (error) {
        if (!(error instanceof ApiError) || !['NETWORK_ERROR', 'TIMEOUT', 'HTTP_ERROR', 'INVALID_RESPONSE',
          'INTERNAL_ERROR', 'SERVICE_UNAVAILABLE', 'AI_TIMEOUT', 'REQUEST_IN_PROGRESS'].includes(error.code)) {
          attempt.clear()
        } else {
          uncertain.setValue(true)
        }
        throw error
      }
    }, id => { clearAttempt(); navigate(`/journeys/${id}/profile`, { state: { savedProfileBaseVersion: saved.version } }) })
  }

  return <div className="saved-profile-edit-action">
    {request.state.status === 'pending' && <p role="status">프로필을 불러오고 있어요.</p>}
    {request.state.status === 'error' && <RequestError error={request.state.error} actions={<Button variant="secondary" onClick={() => void load()}>다시 확인하기</Button>} />}
    {uncertain.value && <p role="status">이전 요청이 처리됐을 수 있어요. 같은 버튼으로 결과를 다시 확인해 주세요.</p>}
    {importRequest.state.status === 'error' && <RequestError error={importRequest.state.error} />}
    {saved && <Button variant="secondary" pending={busy} onClick={startEdit}>{resumeLabel}</Button>}
  </div>
}
