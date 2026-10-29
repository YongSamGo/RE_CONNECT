import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseNotices } from './notices-model'
import { parseSession } from './session'

type Notice = components['schemas']['PublishedNotice']
export function NoticeText({ notice }: { notice: Notice }) {
  return <section className="panel published-notice"><h3>{notice.title}</h3><p>안내문 버전 {notice.version}</p><dl>
    <dt>운영 주체</dt><dd>{notice.controller}</dd><dt>문의처</dt><dd>{notice.contact}</dd>
    <dt>AWS 처리 리전</dt><dd>{notice.aws_region}</dd></dl>
    <p className="notice-body">{notice.body}</p><h4>보관 안내</h4><p className="notice-body">{notice.retention}</p>
    <h4>삭제 안내</h4><p className="notice-body">{notice.deletion}</p></section>
}

export function LoginEntry({ compact = false }: { compact?: boolean }) {
  const request = useRequest<components['schemas']['NoticeCatalog']>()
  const checked = useMemoryScope(() => false)
  const catalog = request.state.status === 'success' ? request.state.data : null
  return <section className={compact ? 'login-entry' : 'panel account-login'} aria-label={compact ? '카카오 로그인' : undefined}>
    {!compact && <><h2>카카오 로그인</h2><p>카카오 계정으로 로그인하려면 먼저 로그인 안내를 확인해 주세요.</p></>}
    <Button className={compact ? 'login-kakao-button' : ''} pending={request.state.status === 'pending'} onClick={() => { checked.clear(); void request.run(async (api, signal) => parseNotices(required((await api.GET('/consents/notices', { signal })).data))) }}>{compact ? '카카오로 로그인' : '현재 로그인 안내 확인'}</Button>
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    {catalog && (catalog.storage && catalog.login_available ? <>
      <NoticeText notice={catalog.storage} /><p>로그인만으로 체험 자료를 저장하지 않아요. 회원 저장 동의와 자료 저장은 따로 선택해요.</p>
      <CheckboxField label="안내를 읽고 카카오 로그인을 진행할게요." checked={checked.value} onChange={event => checked.setValue(event.target.checked)} />
      {checked.value && <a className="button primary" href="/api/v1/auth/kakao/start?purpose=login">카카오에서 로그인</a>}
    </> : <StatusNotice title="새 로그인 준비 중이에요">확정 운영 안내문과 로그인 제공자 연결이 모두 준비된 뒤 제공합니다.</StatusNotice>)}
  </section>
}

export function StorageConsent({ owner, onGranted }: { owner: string; onGranted: (version: string) => void }) {
  const read = useRequest<components['schemas']['NoticeCatalog']>()
  const grant = useRequest<string>()
  const checked = useMemoryScope(() => false)
  const notice = read.state.status === 'success' ? read.state.data.storage : null
  const busy = read.state.status === 'pending' || grant.state.status === 'pending'
  return <section><Button pending={busy} onClick={() => { checked.clear(); grant.clear(); void read.run(async (api, signal) => parseNotices(required((await api.GET('/consents/notices', { signal })).data))) }}>현재 회원 저장 안내 확인</Button>
    {read.state.status === 'error' && <RequestError error={read.state.error} />}
    {read.state.status === 'success' && (!notice ? <StatusNotice title="저장 안내문이 아직 게시되지 않았어요">운영 주체와 문의처, 리전, 보관 및 삭제 정책이 확정된 후 동의를 제공해요.</StatusNotice> : <>
      <NoticeText notice={notice} />
      <CheckboxField label="위 안내문을 읽고 회원 저장에 동의합니다." checked={checked.value} disabled={busy} onChange={event => checked.setValue(event.target.checked)} />
      <Button pending={busy} disabled={!checked.value} onClick={() => {
        if (!checked.value || !notice || busy) return
        void grant.run(async (api, signal) => {
          const before = parseSession(required((await api.GET('/me', { signal })).data))
          if (!before.authenticated || before.user?.id !== owner) throw new ApiError('SESSION_EXPIRED', 401)
          await api.POST('/consents', { signal, body: { purpose: 'storage', notice_version: notice.version } })
          const after = parseSession(required((await api.GET('/me', { signal })).data))
          if (!after.authenticated || after.user?.id !== owner) throw new ApiError('SESSION_EXPIRED', 401)
          if (!after.consents.some(value => value.purpose === 'storage' && value.notice_version === notice.version)) throw new ApiError('CONSENT_REQUIRED', 403)
          return notice.version
        }, onGranted)
      }}>읽은 안내문으로 회원 저장 동의</Button>
    </>)}
    {grant.state.status === 'error' && <RequestError error={grant.state.error} />}
  </section>
}
