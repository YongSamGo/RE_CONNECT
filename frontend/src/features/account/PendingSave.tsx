import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { useEntryAction } from '../../state/useEntryAction'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { invalid, record, timestamp } from '../public-opportunities/catalog'
import { parseSession } from './session'
import { StorageConsent } from './notices'
import { ServicePage } from '../../ui/ServicePage'

type Intent = components['schemas']['PendingSaveIntent']
export type SaveInput = { owner: string; profile: components['schemas']['JourneyProfileSource']; base: number | null; consent: string | null }
type Pending = { owner: string; intent: Omit<Intent, 'expires_at' | 'save_intent_id'> & { save_intent_id: string | null };
  direct?: SaveInput; consent: string | null; checked: boolean; replace: boolean; key: string; started: boolean;
  profile: number | null; cancelled: boolean }
type Result = { message: string; next: Pending | null }
const positive = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value < 2 ** 31 ? value : invalid()

export function PendingSave({ input, embedded = false, autoLoad = false }: { input?: SaveInput; embedded?: boolean; autoLoad?: boolean }) {
  const scope = useMemoryScope<Pending | null>(() => null)
  const setPending = scope.setValue
  const clearPending = scope.clear
  const request = useRequest<Result>()
  const pending = scope.value
  const busy = request.state.status === 'pending'
  const accept = (result: Result) => setPending(result.next)

  useEffect(() => {
    if (!input) return
    setPending({ owner: input.owner, direct: input,
      intent: { save_intent_id: null, targets: { profile: true, draft: false }, existing_saved_profile_version: input.base },
      consent: input.consent, checked: false, replace: false, key: crypto.randomUUID(), started: false,
      profile: null, cancelled: false })
  }, [input, setPending])
  useEffect(() => {
    if (request.state.status === 'error' && ['UNAUTHENTICATED', 'SESSION_EXPIRED'].includes(request.state.error.code)) clearPending()
  }, [request.state, clearPending])

  const load = () => request.run(async (api, signal) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || !me.user) throw new ApiError('UNAUTHENTICATED', 401)
    const intent = me.pending_save_intent
    if (!intent || Date.parse(intent.expires_at) <= Date.now()) {
      return { next: null, message: '저장할 자료가 없습니다.' }
    }
    if (intent.targets.draft) {
      await api.DELETE('/auth/save-intents/{save_intent_id}', { signal, params: { path: { save_intent_id: intent.save_intent_id } } })
      return { next: null, message: '지원서 보관 기능은 제공하지 않습니다. 확정한 경험은 나의 정보에서 저장할 수 있어요.' }
    }
    return { next: { owner: me.user.id, intent,
      consent: me.consents.find(value => value.purpose === 'storage')?.notice_version ?? null,
      checked: false, replace: false, key: crypto.randomUUID(), started: false, profile: null, cancelled: false },
      message: '저장할 프로필을 확인해 주세요.' }
  }, accept)
  useEntryAction(load, autoLoad && !input, 'pending-profile-save')

  const current = async (api: Parameters<Parameters<typeof request.run>[0]>[0], signal: AbortSignal, expected: Pending, checkConsent = true) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || me.user?.id !== expected.owner) throw new ApiError('SESSION_EXPIRED', 401)
    if (checkConsent && (!expected.consent || !me.consents.some(value => value.purpose === 'storage' && value.notice_version === expected.consent))) {
      throw new ApiError('CONSENT_REQUIRED', 403)
    }
  }

  const save = () => {
    if (!pending || busy || !pending.checked || (pending.intent.existing_saved_profile_version !== null && !pending.replace)) return
    scope.setValue({ ...pending, started: true })
    void request.run(async (api, signal) => {
      await current(api, signal, pending)
      const result = record(required((await api.POST('/profiles/me/versions', { signal,
        params: { header: { 'Idempotency-Key': pending.key } }, body: {
          source: pending.direct?.profile ?? { type: 'save_intent', save_intent_id: pending.intent.save_intent_id ?? invalid() },
          base_saved_version: pending.intent.existing_saved_profile_version,
        },
      })).data))
      const version = positive(result.version)
      if (typeof result.created !== 'boolean' || !timestamp(result.saved_at)
        || (result.replaced_version !== null && positive(result.replaced_version) < 1)) return invalid()
      await current(api, signal, pending)
      return { next: { ...pending, started: true, profile: version }, message: '경험을 저장했습니다.' }
    }, accept)
  }
  const cancel = () => {
    if (!pending || busy) return
    void request.run(async (api, signal) => {
      await current(api, signal, pending, false)
      if (pending.intent.save_intent_id !== null) await api.DELETE('/auth/save-intents/{save_intent_id}', { signal, params: { path: { save_intent_id: pending.intent.save_intent_id } } })
      await current(api, signal, pending, false)
      return { next: { ...pending, cancelled: true }, message: '저장을 취소했습니다.' }
    }, accept)
  }

  const finished = !!pending && (pending.cancelled || pending.profile !== null)
  return <ServicePage embedded className="save-page" title={finished && !pending?.cancelled ? '경험을 저장했어요' : '저장한 프로필'}>
    {!pending && <p>저장한 경험을 확인해 주세요.</p>}
    {!pending && <Button pending={busy} onClick={() => void load()}>저장 자료 확인</Button>}
    {pending && <section className="panel">
      <h2>확정한 경험 저장</h2>
      {pending.intent.existing_saved_profile_version !== null && <p>저장된 프로필을 새 내용으로 바꿉니다.</p>}
      {!pending.consent && !finished && <><StatusNotice title="저장 동의가 필요해요">안내문을 읽고 동의한 뒤 저장할 수 있어요.</StatusNotice>
        <StorageConsent owner={pending.owner} onGranted={version => scope.setValue(previous => previous && !previous.cancelled && previous.owner === pending.owner ? { ...previous, consent: version, checked: false, replace: false } : previous)} /></>}
      {!finished && <>
        <CheckboxField label="확정한 경험을 저장할게요." checked={pending.checked} disabled={busy || pending.started} onChange={event => scope.setValue({ ...pending, checked: event.target.checked })} />
        {pending.intent.existing_saved_profile_version !== null && <CheckboxField label="기존 프로필을 새 내용으로 바꾸는 것을 확인했어요." checked={pending.replace} disabled={busy || pending.started} onChange={event => scope.setValue({ ...pending, replace: event.target.checked })} />}
        <div className="actions"><Button pending={busy} disabled={!pending.consent || !pending.checked || (pending.intent.existing_saved_profile_version !== null && !pending.replace) || pending.profile !== null} onClick={save}>{pending.started && pending.profile === null ? '저장 결과 다시 확인' : '이대로 저장하기'}</Button>
          <Button variant="secondary" disabled={busy} onClick={cancel}>취소</Button></div>
      </>}
      {pending.profile !== null && <p role="status">프로필을 저장했습니다.</p>}
    </section>}
    {request.state.status === 'error' && <><RequestError error={request.state.error} /><p>응답을 받지 못했으면 같은 요청으로 다시 확인해 주세요.</p></>}
    {request.state.status === 'success' && <p role="status">{request.state.data.message}</p>}
    {!embedded && <Link className="text-link" to="/me">나의 정보로 이동</Link>}
  </ServicePage>
}
