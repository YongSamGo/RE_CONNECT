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

export function AccountPage({ onLogout, autoLoad = false, embedded = false }: { onLogout?: () => void; onSessionReset?: () => void; autoLoad?: boolean; embedded?: boolean }) {
  const request = useRequest<Result>()
  const [showWithdrawal, setShowWithdrawal] = useState(false)
  const [deleteAccount, setDeleteAccount] = useState(false)
  const state = request.state
  const me = state.status === 'success' ? state.data.me : null
  const pending = state.status === 'pending'
  const check = () => request.run(async (api, signal) => ({ me: parseSession(required((await api.GET('/me', { signal })).data)) }))
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
          <Button variant="secondary" className="danger-button" aria-expanded={showWithdrawal} onClick={() => { setShowWithdrawal(value => !value); setDeleteAccount(false) }}>회원 탈퇴</Button>
        </div>
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
