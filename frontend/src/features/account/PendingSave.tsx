import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'
import { parseSession } from './session'
import { StorageConsent } from './notices'

type Intent = components['schemas']['PendingSaveIntent']
export type SaveInput = { owner: string; profile: components['schemas']['JourneyProfileSource'];
  draft: components['schemas']['JourneyDraftSource'] | null; base: number | null; consent: string | null }
type Pending = { owner: string; intent: Omit<Intent, 'expires_at' | 'save_intent_id'> & { save_intent_id: string | null };
  direct?: SaveInput; consent: string | null; checked: boolean; replace: boolean;
  profileKey: string; draftKey: string; started: boolean; profile: number | null; document: string | null; cancelled: boolean }
const positive = (value: unknown) => typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 && value < 2 ** 31 ? value : invalid()

export function PendingSave({ input }: { input?: SaveInput }) {
  const scope = useMemoryScope<Pending | null>(() => null)
  const request = useRequest<string>()
  const pending = scope.value
  const busy = request.state.status === 'pending'
  const clear = scope.clear
  const update = scope.setValue
  useEffect(() => {
    if (input) update({ owner: input.owner, direct: input,
      intent: { save_intent_id: null, targets: { profile: true, draft: input.draft !== null }, existing_saved_profile_version: input.base },
      consent: input.consent, checked: false, replace: false, profileKey: crypto.randomUUID(), draftKey: crypto.randomUUID(),
      started: false, profile: null, document: null, cancelled: false })
  }, [input, update])
  useEffect(() => {
    if (request.state.status === 'error' && ['UNAUTHENTICATED', 'SESSION_EXPIRED'].includes(request.state.error.code)) clear()
  }, [request.state, clear])
  const load = () => request.run(async (api, signal) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || !me.user) throw new ApiError('UNAUTHENTICATED', 401)
    if (!me.pending_save_intent || Date.parse(me.pending_save_intent.expires_at) <= Date.now()) {
      clear(); return '계속할 수 있는 저장 대기가 없습니다. 저장된 자료를 따로 확인해 주세요.'
    }
    scope.setValue({ owner: me.user.id, intent: me.pending_save_intent,
      consent: me.consents.find(value => value.purpose === 'storage')?.notice_version ?? null,
      checked: false, replace: false, profileKey: crypto.randomUUID(), draftKey: crypto.randomUUID(),
      started: false, profile: null, document: null, cancelled: false })
    return '현재 세션의 저장 대기를 확인했습니다.'
  })
  // Every write re-checks the currently bound member; a cookie rotation must
  // not apply a previous screen's choice to another user's current session.
  const current = async (api: Parameters<Parameters<typeof request.run>[0]>[0], signal: AbortSignal, expected: Pending, consent = true) => {
    const me = parseSession(required((await api.GET('/me', { signal })).data))
    if (!me.authenticated || me.user?.id !== expected.owner) throw new ApiError('SESSION_EXPIRED', 401)
    if (consent && (!expected.consent || !me.consents.some(value => value.purpose === 'storage' && value.notice_version === expected.consent))) throw new ApiError('CONSENT_REQUIRED', 403)
  }
  const saveProfile = () => {
    if (!pending || busy || !pending.checked || (pending.intent.existing_saved_profile_version !== null && !pending.replace)) return
    // Freeze this exact input/key before sending. A lost response must retry
    // the same operation, even if /me no longer has a consumed intent.
    scope.setValue({ ...pending, started: true })
    void request.run(async (api, signal) => {
      await current(api, signal, pending)
      const result = record(required((await api.POST('/profiles/me/versions', { signal,
        params: { header: { 'Idempotency-Key': pending.profileKey } }, body: {
          source: pending.direct?.profile ?? { type: 'save_intent', save_intent_id: pending.intent.save_intent_id ?? invalid() },
          base_saved_version: pending.intent.existing_saved_profile_version,
        },
      })).data))
      const version = positive(result.version)
      if (typeof result.created !== 'boolean' || !timestamp(result.saved_at)
        || (result.replaced_version !== null && positive(result.replaced_version) < 1)) return invalid()
      await current(api, signal, pending)
      scope.setValue({ ...pending, started: true, profile: version })
      return pending.intent.targets.draft ? '프로필 저장을 확인했습니다. 지원서는 아직 저장하지 않았습니다.' : '프로필 저장을 완료했습니다.'
    })
  }
  const saveDraft = () => {
    if (!pending || busy || pending.profile === null || !pending.intent.targets.draft || pending.document) return
    void request.run(async (api, signal) => {
      await current(api, signal, pending)
      const result = record(required((await api.POST('/drafts', { signal, params: { header: { 'Idempotency-Key': pending.draftKey } }, body: {
        source: pending.direct?.draft ?? { type: 'save_intent', save_intent_id: pending.intent.save_intent_id ?? invalid() }, document_id: null, base_document_version: null,
      } })).data))
      if (typeof result.document_id !== 'string' || !isOpportunityId(result.document_id)
        || positive(result.profile_version) !== pending.profile || !timestamp(result.saved_at)) return invalid()
      positive(result.version)
      await current(api, signal, pending)
      scope.setValue({ ...pending, document: result.document_id })
      return '프로필과 지원서 저장을 모두 완료했습니다.'
    })
  }
  const cancel = () => {
    if (!pending || busy) return
    void request.run(async (api, signal) => {
      await current(api, signal, pending, false)
      if (pending.intent.save_intent_id !== null) await api.DELETE('/auth/save-intents/{save_intent_id}', { signal, params: { path: { save_intent_id: pending.intent.save_intent_id } } })
      await current(api, signal, pending, false)
      scope.setValue({ ...pending, cancelled: true })
      return '남아 있는 저장 대기를 취소했습니다. 이미 저장한 자료와 로그인 상태는 유지합니다.'
    })
  }
  const finished = !!pending && (pending.cancelled || pending.document !== null || (!pending.intent.targets.draft && pending.profile !== null))
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">회원 저장</p><h1>저장할 자료를 직접 확인해요</h1><p>로그인과 자료 저장은 별개입니다. 저장 버튼을 누르기 전에는 저장하지 않습니다.</p></header>
    {!pending && <Button pending={busy} onClick={() => void load()}>현재 저장 대기 확인</Button>}
    {pending && <section className="panel"><h2>{pending.intent.targets.draft ? '프로필과 지원서 함께 저장' : '확정 프로필 저장'}</h2>
      <p>{pending.intent.targets.draft ? '지원서의 근거로 프로필도 저장합니다. 먼저 프로필을 저장하고, 다음 버튼으로 지원서를 저장합니다.' : '직접 확인한 확정 프로필만 저장합니다.'}</p>
      {pending.intent.existing_saved_profile_version !== null && <p>기존 저장 프로필 {pending.intent.existing_saved_profile_version}번이 있습니다. 내용이 같으면 연결하고, 다르면 확인한 기준 버전에서 새 버전으로 저장합니다.</p>}
      {!pending.consent && !finished && <><StatusNotice title="저장 동의가 필요해요">서버가 게시한 현재 안내문을 읽고 동의해야 저장할 수 있습니다. 안내문이 미정이면 동의·저장을 제공하지 않습니다.</StatusNotice>
        <StorageConsent owner={pending.owner} onGranted={version => scope.setValue(previous => previous && !previous.cancelled && previous.owner === pending.owner && previous.intent.save_intent_id === pending.intent.save_intent_id ? { ...previous, consent: version, checked: false, replace: false } : previous)} /></>}
      {!finished && <>
        <CheckboxField label={pending.intent.targets.draft ? '프로필과 지원서 모두 저장 대상임을 확인했어요.' : '확정 프로필 저장을 확인했어요.'} checked={pending.checked} disabled={busy || pending.started} onChange={event => scope.setValue({ ...pending, checked: event.target.checked })} />
        {pending.intent.existing_saved_profile_version !== null && <CheckboxField label="기존 저장 프로필 기준으로 교체 여부를 확인했어요." checked={pending.replace} disabled={busy || pending.started} onChange={event => scope.setValue({ ...pending, replace: event.target.checked })} />}
        <Button pending={busy} disabled={!pending.consent || !pending.checked || (pending.intent.existing_saved_profile_version !== null && !pending.replace) || pending.profile !== null} onClick={saveProfile}>{pending.started && pending.profile === null ? '같은 요청으로 프로필 저장 재확인' : '확인한 프로필 저장'}</Button>
        {pending.intent.targets.draft && <Button pending={busy} disabled={!pending.consent || pending.profile === null} onClick={saveDraft}>프로필에 연결해 지원서 저장 · 실패 시 재확인</Button>}
        <Button variant="secondary" disabled={busy} onClick={cancel}>남은 저장 대기 취소</Button>
      </>}
      {pending.profile !== null && <p>프로필 {pending.profile}번의 저장을 확인했습니다.{pending.intent.targets.draft && !pending.document ? ' 지원서는 아직 저장 완료로 확인되지 않았습니다.' : ''}</p>}
    </section>}
    {request.state.status === 'error' && <><RequestError error={request.state.error} /><p>응답이 없으면 실제 저장됐을 수도 있습니다. 같은 요청으로 재확인하거나 저장 자료를 조회해 주세요. 만료·충돌이면 현재 자료를 확인한 뒤 새로 시작해 주세요.</p></>}
    {request.state.status === 'success' && <p role="status">{request.state.data}</p>}
    <div className="actions"><Link className="button secondary" to="/me/saved">저장한 자료 확인</Link><Link className="text-link" to="/me">내 정보로 이동</Link></div>
  </div>
}
