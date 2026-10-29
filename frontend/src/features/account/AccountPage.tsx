import { useEntryAction } from '../../state/useEntryAction'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from './session'
import { ServicePage } from '../../ui/ServicePage'

type Me = components['schemas']['Me']
type Result = { me: Me; message?: string }

export function AccountPage({ onLogout, onSessionReset, autoLoad = false, embedded = false }: { onLogout?: () => void; onSessionReset?: () => void; autoLoad?: boolean; embedded?: boolean }) {
  const request = useRequest<Result>()
  const [showWithdrawal, setShowWithdrawal] = useState(false)
  const [deleteAccount, setDeleteAccount] = useState(false)
  const [showConsents, setShowConsents] = useState(false)
  const [confirmation, setConfirmation] = useState<'storage' | 'ai_processing' | null>(null)
  const state = request.state
  const me = state.status === 'success' ? state.data.me : null
  const pending = state.status === 'pending'
  const check = () => {
    setConfirmation(null)
    setDeleteAccount(false)
    return request.run(async (api, signal) => ({ me: parseSession(required((await api.GET('/me', { signal })).data)) }))
  }
  useEntryAction(check, autoLoad)

  const logout = () => request.run(async (api, signal) => {
    await api.POST('/auth/logout', { signal })
    const next = parseSession(required((await api.GET('/me', { signal })).data))
    if (next.authenticated) throw new ApiError('INVALID_RESPONSE')
    return { me: next, message: '로그아웃했습니다.' }
  }, onLogout)

  const content = <div className="account-settings">
      {pending && <p role="status">계정 정보를 확인하고 있어요.</p>}
      {state.status === 'error' && <RequestError error={state.error} actions={<Button variant="secondary" onClick={() => void check()}>다시 확인하기</Button>} />}
      {state.status === 'success' && !me?.authenticated && <div className="service-entry"><p>계정 설정을 보려면 로그인해 주세요.</p><Link className="button primary" to="/login">로그인하기</Link></div>}
      {me?.authenticated && <>
        <div className="account-actions">
          <Button variant="secondary" pending={pending} onClick={() => void logout()}>로그아웃</Button>
          <Button variant="secondary" aria-expanded={showConsents} onClick={() => { setShowConsents(value => !value); setConfirmation(null) }}>동의 관리</Button>
          <Button variant="secondary" className="danger-button" aria-expanded={showWithdrawal} onClick={() => { setShowWithdrawal(value => !value); setDeleteAccount(false) }}>회원 탈퇴</Button>
        </div>
        {showConsents && <section className="account-section">
          <h2>동의 관리</h2>
          <p>저장 동의를 철회하면 저장 프로필의 모든 버전과 연결된 지원서가 삭제됩니다. AI 처리 동의를 철회하면 임시 체험을 종료하며 저장한 프로필은 유지합니다. 두 경우 모두 다른 기기의 로그인 세션과 기존 임시 체험이 종료됩니다.</p>
          <p>현재 동의: {me.consents.length ? me.consents.map(consent => consent.purpose === 'storage' ? '회원 저장' : 'AI 처리').join(', ') : '없음'}</p>
          {(['storage', 'ai_processing'] as const).map(purpose => <div key={purpose}>
            <CheckboxField label={purpose === 'storage' ? '회원 저장 동의 철회와 자료 삭제를 확인했어요.' : 'AI 처리 동의 철회와 임시 체험 종료를 확인했어요.'} checked={confirmation === purpose} onChange={event => setConfirmation(event.target.checked ? purpose : null)} />
            <Button variant="secondary" disabled={confirmation !== purpose} onClick={() => {
              setConfirmation(null)
              void request.run(async (api, signal) => {
                const current = parseSession(required((await api.GET('/me', { signal })).data))
                if (!current.authenticated || current.user?.id !== me.user?.id) {
                  onSessionReset?.()
                  throw new ApiError('SESSION_EXPIRED', 401)
                }
                await api.POST('/consents/withdraw', { signal, body: { purpose } })
                try {
                  return { me: parseSession(required((await api.GET('/me', { signal })).data)), message: '동의를 철회했습니다.' }
                } finally {
                  // The write succeeded even if its follow-up read fails.
                  // Reload the enclosing profile so deleted data cannot linger.
                  if (!signal.aborted) onSessionReset?.()
                }
              })
            }}>{purpose === 'storage' ? '회원 저장 동의 철회' : 'AI 처리 동의 철회'}</Button>
          </div>)}
        </section>}
        {showWithdrawal && <section className="account-withdrawal">
          <p>탈퇴하면 계정 연결과 동의 기록, 저장 자료, 모든 로그인 세션과 체험을 삭제합니다. 탈퇴 처리를 위해 삭제에 필요한 최소 이력은 30일 보관합니다. 카카오에서 다시 인증한 뒤 5분 안에 진행해 주세요.</p>
          <a className="text-link" href="/api/v1/auth/kakao/start?purpose=reauth">카카오에서 다시 인증</a>
          <CheckboxField label="회원 탈퇴와 저장 자료 삭제를 확인했어요." checked={deleteAccount} onChange={event => setDeleteAccount(event.target.checked)} />
          <Button variant="secondary" className="danger-button" pending={pending} disabled={!deleteAccount || !me.user?.reauth_until} onClick={() => {
            setDeleteAccount(false)
            void request.run(async (api, signal) => {
              await api.DELETE('/me', { signal })
              const next = parseSession(required((await api.GET('/me', { signal })).data))
              if (next.authenticated) throw new ApiError('INVALID_RESPONSE')
              return { me: next, message: '회원 탈퇴를 완료했습니다.' }
            }, onLogout)
          }}>탈퇴하기</Button>
        </section>}
      </>}
      <p role="status">{state.status === 'success' ? state.data.message : ''}</p>
  </div>
  return <ServicePage member={!embedded} embedded={embedded} title="계정 설정" className="account-settings-page">{content}</ServicePage>
}
