import { useEntryAction } from '../../state/useEntryAction'
import { Link, useParams } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { UnavailablePage } from '../../ui/UnavailablePage'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'
import { parseProfileView } from '../profile/server-model'
import { parseSession } from './session'
import { parseNotices } from './notices-model'
import { PendingSave } from './PendingSave'
import type { SaveInput } from './PendingSave'
import { EmptySection, ServicePage } from '../../ui/ServicePage'

type Choice = { body: components['schemas']['SaveIntentCreate']; notices: components['schemas']['NoticeCatalog'];
  member: SaveInput | null; key: string; checked: boolean; started: boolean; intent: string | null; cancelled: boolean }
type Result = { message: string; next: Choice }
const positive = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value < 2 ** 31 ? value : invalid()

export function BeginSaveRoute() {
  const { journeyId } = useParams()
  if (!journeyId || !isOpportunityId(journeyId)) return <UnavailablePage title="저장할 프로필 주소를 확인해 주세요">확정한 경험 화면에서 다시 진행해 주세요.</UnavailablePage>
  return <BeginSave key={journeyId} journeyId={journeyId} />
}

export function BeginSave({ journeyId, embedded = false }: { journeyId: string; embedded?: boolean }) {
  const scope = useMemoryScope<Choice | null>(() => null)
  const request = useRequest<Result>()
  const accept = (result: Result) => scope.setValue(result.next)
  const value = scope.value, busy = request.state.status === 'pending'
  const load = () => request.run(async (api, signal) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    const notices = parseNotices(required((await api.GET('/consents/notices', { signal })).data))
    const view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { signal, params: { path: { journey_id: journeyId } } })).data))
    if (!view.confirmed || view.has_unconfirmed_changes) throw new ApiError('PROFILE_NOT_CONFIRMED', 409)
    let member: SaveInput | null = null
    if (me.authenticated && me.user) {
      const saved = record(required((await api.GET('/profiles/me', { signal })).data)).saved
      member = { owner: me.user.id, profile: { type: 'journey', journey_id: journeyId, version: view.confirmed.version },
        base: saved === null ? null : positive(record(saved).version), consent: me.consents.find(item => item.purpose === 'storage')?.notice_version ?? null }
    }
    return { next: { body: { journey_id: journeyId, profile: { version: view.confirmed.version }, draft: null }, notices, member,
      key: crypto.randomUUID(), checked: false, started: false, intent: null, cancelled: false }, message: '서버에서 확정하거나 승인한 자료를 확인했어요.' }
  }, accept)
  const prepare = () => {
    if (!value || busy || !value.checked || !value.notices.storage || !value.notices.login_available || value.cancelled) return
    scope.setValue({ ...value, started: true })
    void request.run(async (api, signal) => {
      const me = parseSession(required((await api.GET('/me', { signal })).data))
      if (me.authenticated) throw new ApiError('ALREADY_SIGNED_IN', 409)
      const result = record(required((await api.POST('/auth/save-intents', { signal, params: { header: { 'Idempotency-Key': value.key } }, body: value.body })).data))
      const targets = record(result.targets)
      if (typeof result.save_intent_id !== 'string' || !isOpportunityId(result.save_intent_id) || !timestamp(result.expires_at)
        || targets.profile !== true || targets.draft !== false) return invalid()
      return { next: { ...value, started: true, intent: result.save_intent_id }, message: '로그인용 저장 대기를 준비했습니다. 아직 회원 저장하지 않았습니다.' }
    }, accept)
  }
  const cancel = () => {
    if (!value || busy) return
    void request.run(async (api, signal) => {
      if (value.intent) await api.DELETE('/auth/save-intents/{save_intent_id}', { signal, params: { path: { save_intent_id: value.intent } } })
      return { next: { ...value, cancelled: true }, message: '선택한 저장 준비를 취소했습니다. 대화와 확정 자료는 유지합니다.' }
    }, accept)
  }
  useEntryAction(load, embedded)
  if (value?.member) return <PendingSave input={value.member} embedded={embedded} />
  return <ServicePage embedded={embedded} title="내 경험 저장">
    {!value && !embedded && <EmptySection title="확정한 경험"><p>확인한 경험을 계정에 저장할 수 있어요.</p></EmptySection>}
    {!value && <Button pending={busy} onClick={() => void load()}>저장할 자료 확인</Button>}
    {value && !value.cancelled && <section className="panel">
      <h3>확정한 경험</h3>
      <p>로그인 후 저장 동의와 저장 여부를 선택할 수 있어요.</p>
      {value.notices.storage && value.notices.login_available ? <>
        <p>아래 확인은 저장 동의가 아닙니다. 로그인 후 현재 안내문으로 따로 동의하고 저장을 선택합니다.</p>
        <CheckboxField label="확정한 경험을 저장할 준비가 됐어요." checked={value.checked} disabled={busy || value.started} onChange={event => scope.setValue({ ...value, checked: event.target.checked })} />
        <div className="actions">{!value.intent ? <Button pending={busy} disabled={!value.checked} onClick={prepare}>{value.started ? '같은 요청으로 저장 대기 재확인' : '확인한 자료로 로그인 준비'}</Button> : <a className="button primary" href="/api/v1/auth/kakao/start?purpose=save">카카오 로그인 후 저장 선택</a>}</div>
      </> : <StatusNotice title="회원 저장 시작 준비 중이에요">확정 운영 안내문과 로그인 제공자 연결이 모두 준비되면 제공합니다. 실제 저장 동의나 저장을 진행하지 않습니다.</StatusNotice>}
      <div className="actions"><Button variant="secondary" disabled={busy} onClick={cancel}>저장 준비 취소</Button></div>
    </section>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    {request.state.status === 'success' && <p role="status">{request.state.data.message}</p>}
    <Link className="text-link" to={`/journeys/${journeyId}/profile`}>확정 프로필 확인 화면으로</Link>
  </ServicePage>
}
