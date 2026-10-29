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
import { NoticeText } from './notices'
import { PendingSave } from './PendingSave'
import type { SaveInput } from './PendingSave'

type Choice = { body: components['schemas']['SaveIntentCreate']; notices: components['schemas']['NoticeCatalog'];
  member: SaveInput | null; key: string; checked: boolean; started: boolean; intent: string | null; cancelled: boolean }
type Result = { message: string; next: Choice }
const positive = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value < 2 ** 31 ? value : invalid()

export function BeginSaveRoute() {
  const { journeyId, draftId } = useParams()
  if (!journeyId || !isOpportunityId(journeyId) || (draftId !== undefined && !isOpportunityId(draftId))) return <UnavailablePage title="저장할 자료 주소를 확인해 주세요">프로필 또는 승인 지원서 화면에서 다시 진행해 주세요.</UnavailablePage>
  return <BeginSave key={`${journeyId}:${draftId ?? ''}`} journeyId={journeyId} draftId={draftId} />
}

function BeginSave({ journeyId, draftId }: { journeyId: string; draftId?: string }) {
  const scope = useMemoryScope<Choice | null>(() => null)
  const request = useRequest<Result>()
  const accept = (result: Result) => scope.setValue(result.next)
  const value = scope.value, busy = request.state.status === 'pending'
  const load = () => request.run(async (api, signal) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    const notices = parseNotices(required((await api.GET('/consents/notices', { signal })).data))
    const view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { signal, params: { path: { journey_id: journeyId } } })).data))
    if (!view.confirmed || view.has_unconfirmed_changes) throw new ApiError('PROFILE_NOT_CONFIRMED', 409)
    let draft: components['schemas']['SaveIntentCreate']['draft'] = null
    if (draftId) {
      const item = record(required((await api.GET('/journeys/{journey_id}/drafts/{draft_id}', { signal, params: { path: { journey_id: journeyId, draft_id: draftId } } })).data))
      if (item.draft_id !== draftId || positive(item.profile_version) !== view.confirmed.version) return invalid()
      if (!timestamp(item.approved_at) || !Array.isArray(item.review_reasons) || item.review_reasons.length) throw new ApiError('DRAFT_NOT_APPROVED', 409)
      draft = { draft_id: draftId, revision: positive(item.revision) }
    }
    let member: SaveInput | null = null
    if (me.authenticated && me.user) {
      const saved = record(required((await api.GET('/profiles/me', { signal })).data)).saved
      member = { owner: me.user.id, profile: { type: 'journey', journey_id: journeyId, version: view.confirmed.version },
        draft: draft ? { type: 'journey', journey_id: journeyId, ...draft } : null,
        base: saved === null ? null : positive(record(saved).version), consent: me.consents.find(item => item.purpose === 'storage')?.notice_version ?? null }
    }
    return { next: { body: { journey_id: journeyId, profile: { version: view.confirmed.version }, draft }, notices, member,
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
        || targets.profile !== true || targets.draft !== (value.body.draft !== null)) return invalid()
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
  if (value?.member) return <PendingSave input={value.member} />
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">회원 저장 준비</p><h1>{draftId ? '프로필과 지원서를 함께 저장할까요?' : '확정 프로필을 회원 저장할까요?'}</h1><p>서버에서 자료의 확정과 승인 상태를 확인해요. 로그인 후 저장 여부는 따로 선택해요.</p></header>
    {!value && <Button pending={busy} onClick={() => void load()}>서버에서 저장 대상 확인</Button>}
    {value && !value.cancelled && <section className="panel">
      <h2>확인된 저장 대상</h2><p>{value.body.profile && `확정 프로필 ${value.body.profile.version}번`}{value.body.draft ? ` · 승인한 지원서 수정본 ${value.body.draft.revision}번` : ''}</p><p>본문은 이전 화면에서 확인해 주세요. 이 화면에서는 저장 대상과 상태를 확인합니다.</p>
      <p>{value.body.draft ? '지원서의 근거로 프로필도 함께 저장합니다. 로그인 후 두 자료를 명시적으로 선택하고 순서대로 저장합니다.' : '직접 확정한 프로필을 로그인 후 별도로 저장합니다.'}</p>
      {value.notices.storage && value.notices.login_available ? <>
        <NoticeText notice={value.notices.storage} />
        <p>아래 확인은 저장 동의가 아닙니다. 로그인 후 현재 안내문으로 따로 동의하고 저장을 선택합니다.</p>
        <CheckboxField label={draftId ? '프로필도 포함된 묶음 저장 준비를 확인했어요.' : '확정 프로필의 저장 준비를 확인했어요.'} checked={value.checked} disabled={busy || value.started} onChange={event => scope.setValue({ ...value, checked: event.target.checked })} />
        <div className="actions">{!value.intent ? <Button pending={busy} disabled={!value.checked} onClick={prepare}>{value.started ? '같은 요청으로 저장 대기 재확인' : '확인한 자료로 로그인 준비'}</Button> : <a className="button primary" href="/api/v1/auth/kakao/start?purpose=save">카카오 로그인 후 저장 선택</a>}</div>
      </> : <StatusNotice title="회원 저장 시작 준비 중이에요">확정 운영 안내문과 로그인 제공자 연결이 모두 준비되면 제공합니다. 실제 저장 동의나 저장을 진행하지 않습니다.</StatusNotice>}
      <div className="actions"><Button variant="secondary" disabled={busy} onClick={cancel}>저장 준비 취소</Button></div>
    </section>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    {request.state.status === 'success' && <p role="status">{request.state.data.message}</p>}
    <Link className="text-link" to={`/journeys/${journeyId}/profile`}>확정 프로필 확인 화면으로</Link>
  </div>
}
