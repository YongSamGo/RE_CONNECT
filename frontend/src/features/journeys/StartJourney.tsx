import { useRef } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import type { components } from '../../api/schema'
import { csrfToken } from '../../api/client'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseNotices } from '../account/notices-model'
import { NoticeText } from '../account/notices'
import { parseSession } from '../account/session'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'

type Ready = { notice: components['schemas']['PublishedNotice'] | null; owner: string | null; csrf: string }
type Attempt = { key: string; version: string; csrf: string; owner: string | null }
const ambiguous = new Set(['NETWORK_ERROR', 'TIMEOUT', 'INVALID_RESPONSE', 'HTTP_ERROR', 'INTERNAL_ERROR', 'SERVICE_UNAVAILABLE', 'REQUEST_IN_PROGRESS', 'CANCELLED'])
const currentToken = () => csrfToken(document.cookie, window.location.href)

function createdJourney(value: unknown): string {
  const result = record(value)
  const expiry = timestamp(result.expires_at), idle = timestamp(result.idle_expires_at)
  if (typeof result.journey_id !== 'string' || !isOpportunityId(result.journey_id)
    || !expiry || !idle || Date.parse(idle) <= Date.now() || Date.parse(expiry) < Date.parse(idle)
    || !Number.isSafeInteger(result.revision) || Number(result.revision) < 1 || result.confirmed !== null) return invalid()
  return result.journey_id
}

export function StartJourney({ onStart }: { onStart: () => void }) {
  const read = useRequest<Ready>()
  const start = useRequest<string>()
  const checked = useMemoryScope(() => false)
  const attempt = useMemoryScope<Attempt | null>(() => null)
  const submitting = useRef(false)
  const navigate = useNavigate()
  const ready = read.state.status === 'success' ? read.state.data : null
  const busy = read.state.status === 'pending' || start.state.status === 'pending'

  function begin() {
    if (!checked.value || !ready?.notice || busy || submitting.current) return
    submitting.current = true
    const current = attempt.value ?? { key: crypto.randomUUID(), version: ready.notice.version, csrf: ready.csrf, owner: ready.owner }
    attempt.setValue(current)
    void start.run(async (api, signal) => {
      const ensureSession = () => { if (currentToken() !== current.csrf) throw new ApiError('SESSION_EXPIRED', 401) }
      try {
        ensureSession()
        const before = parseSession(required((await api.GET('/me', { signal })).data))
        ensureSession()
        if ((before.user?.id ?? null) !== current.owner) throw new ApiError('SESSION_EXPIRED', 401)
        if (!before.consents.some(item => item.purpose === 'ai_processing' && item.notice_version === current.version)) {
          await api.POST('/consents', { signal, body: { purpose: 'ai_processing', notice_version: current.version } })
        }
        ensureSession()
        const after = parseSession(required((await api.GET('/me', { signal })).data))
        ensureSession()
        if ((after.user?.id ?? null) !== current.owner) throw new ApiError('SESSION_EXPIRED', 401)
        if (!after.consents.some(item => item.purpose === 'ai_processing' && item.notice_version === current.version)) throw new ApiError('CONSENT_REQUIRED', 403)
        const result = await api.POST('/journeys', { signal, params: { header: { 'Idempotency-Key': current.key } },
          body: { ai_notice_version: current.version, saved_profile: null } })
        ensureSession()
        return createdJourney(required(result.data))
      } catch (error) {
        if (!(error instanceof ApiError) || !ambiguous.has(error.code)) {
          attempt.clear(); checked.clear(); read.clear()
        }
        throw error
      } finally { submitting.current = false }
    }, id => { onStart(); navigate(`/journeys/${id}/conversation`, { replace: true }) })
  }

  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">시작하기 전에</p>
    <h1>내 정보가 어떻게 쓰이나요?</h1><p>현재 게시된 AI 처리 안내를 읽고 체험 시작 여부를 선택해 주세요.</p></header>
    <Button pending={busy} disabled={attempt.value !== null} onClick={() => {
      checked.clear(); start.clear()
      void read.run(async (api, signal) => {
        const me = parseSession(required((await api.GET('/me', { signal })).data))
        const token = currentToken()
        if (!token) throw new ApiError('CSRF_MISSING')
        const catalog = parseNotices(required((await api.GET('/consents/notices', { signal })).data))
        if (currentToken() !== token) throw new ApiError('SESSION_EXPIRED', 401)
        return { notice: catalog.ai_processing, owner: me.user?.id ?? null, csrf: token }
      })
    }}>현재 AI 처리 안내 확인</Button>
    {read.state.status === 'error' && <RequestError error={read.state.error} />}
    {ready && (ready.notice ? <>
      <NoticeText notice={ready.notice} />
      <p>체험 자료는 임시로 처리됩니다. 회원 저장은 로그인과 별도의 저장 동의 후 직접 선택합니다. 저장한 프로필을 자동으로 가져오지 않습니다.</p>
      <CheckboxField label="위 안내문을 읽고 AI 처리에 동의하며 새 체험을 시작할게요." checked={checked.value} disabled={busy} onChange={event => checked.setValue(event.target.checked)} />
      <Button pending={busy} disabled={!checked.value} onClick={begin}>{attempt.value ? '같은 요청으로 시작 결과 다시 확인' : '동의하고 새 체험 시작하기'}</Button>
    </> : <StatusNotice title="AI 처리 안내가 아직 준비되지 않았어요">운영 안내문이 게시된 뒤 실제 체험을 시작할 수 있습니다. 공고는 동의 없이 살펴볼 수 있어요.</StatusNotice>)}
    {start.state.status === 'error' && <RequestError error={start.state.error} />}
    {attempt.value && start.state.status === 'error' && <p role="status">서버에서 체험이 생성되었을 수 있습니다. 같은 요청으로 결과를 확인하며 새 체험을 중복 생성하지 않습니다.</p>}
    <div className="actions"><Link className="text-link" to="/opportunities">공고부터 살펴보기</Link><Link className="text-link" to="/consent">가상 경험으로 화면 미리보기</Link></div>
  </div>
}
