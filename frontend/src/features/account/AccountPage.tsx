import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseSession } from './session'
import { LoginEntry } from './notices'
import { ServicePage } from '../../ui/ServicePage'
import { AccountOverview } from './AccountOverview'

type Me = components['schemas']['Me']
type Result = { me: Me; message?: string }

export function AccountPage({ onLogout, onSessionReset }: { onLogout?: () => void; onSessionReset?: () => void }) {
  const request = useRequest<Result>()
  const [remove, setRemove] = useState(false)
  const [withdrawAI, setWithdrawAI] = useState(false)
  const [deleteAccount, setDeleteAccount] = useState(false)
  const state = request.state
  const me = state.status === 'success' ? state.data.me : null
  const pending = state.status === 'pending'
  const check = () => request.run(async (api, signal) => ({ me: parseSession(required((await api.GET('/me', { signal })).data)) }))
  return <ServicePage member title="나의 정보" description="내 경험과 저장한 자료, 동의 내역을 관리해요."><div className="account-content">
    {me?.authenticated && <AccountOverview />}
    {!me?.authenticated && <LoginEntry />}
    <StatusNotice title="로그인과 저장 동의는 별개예요">서버에 확정 안내문이 게시돼야 새 로그인과 동의를 제공해요. 아래 관리 기능은 서버에서 확인한 현재 회원에게만 적용돼요.</StatusNotice>
    <div className="panel account-management"><Button variant="secondary" pending={pending} onClick={() => { setRemove(false); setWithdrawAI(false); setDeleteAccount(false); void check() }}>내 로그인 상태 확인</Button>
      {pending && <p role="status">서버의 로그인 상태를 확인하고 있어요.</p>}
      {state.status === 'error' && <RequestError error={state.error} />}
      {me && (!me.authenticated ? <p>로그인하지 않은 상태입니다. 현재 로그인 안내에서 이용 가능 여부를 확인해 주세요.</p> : <>
        <section className="account-section"><h2>현재 로그인 상태</h2><p>회원 세션이 확인되었습니다. 대화는 새로 시작하며 저장하지 않은 입력은 회원 자료에 포함되지 않습니다.</p>
        <h3>현재 동의</h3>{me.consents.length ? <ul>{me.consents.map((consent) => <li key={consent.purpose}>{consent.purpose === 'storage' ? '회원 저장' : 'AI 처리'} / 안내문 {consent.notice_version}</li>)}</ul> : <p>현재 유효한 동의가 없습니다.</p>}
        <div className="actions"><Link className="button secondary" to="/me/saved">저장한 자료 조회</Link>
        {me.user?.roles.includes('operator') && <Link className="button secondary" to="/admin">운영자 관리 화면</Link>}</div>
        <div className="actions"><Button variant="secondary" onClick={() => void request.run(async (api, signal) => { await api.POST('/auth/logout', { signal }); const me = parseSession(required((await api.GET('/me', { signal })).data)); if (me.authenticated) throw new ApiError('INVALID_RESPONSE'); return { me, message: '로그아웃 요청이 완료되었습니다.' } }, onLogout)}>로그아웃</Button></div></section>
        <section className="account-section"><h2>회원 저장 동의 철회</h2><p>철회하면 저장 프로필의 모든 버전과 지원서가 삭제됩니다.</p>
        <p>삭제하거나 동의를 철회하면 다른 기기를 포함한 기존 임시 체험과 로그인 세션을 종료해요. 이 화면은 새 회원 세션으로 전환하며 다른 기기는 다시 로그인해야 합니다.</p>
        <CheckboxField label="저장 동의를 철회하고 저장 자료를 삭제할게요." checked={remove} onChange={(event) => setRemove(event.target.checked)} />
        <Button variant="secondary" disabled={!remove} onClick={() => { setRemove(false); void request.run(async (api, signal) => { await api.POST('/consents/withdraw', { signal, body: { purpose: 'storage' } }); return { me: parseSession(required((await api.GET('/me', { signal })).data)), message: '회원 저장 동의를 철회했습니다. 저장 프로필과 지원서 삭제를 완료했습니다.' } }, onSessionReset) }}>동의 철회하고 저장 자료 삭제</Button></section>
        <section className="account-section"><h2>AI 처리 동의 철회</h2><p>진행 중인 체험과 임시 자료를 지워요. 이미 회원 자료로 저장한 프로필과 지원서는 유지해요.</p>
        <CheckboxField label="AI 처리 동의를 철회하고 임시 체험을 종료할게요." checked={withdrawAI} onChange={event => setWithdrawAI(event.target.checked)} />
        <Button variant="secondary" disabled={!withdrawAI} onClick={() => { setWithdrawAI(false); void request.run(async (api, signal) => {
          await api.POST('/consents/withdraw', { signal, body: { purpose: 'ai_processing' } })
          return { me: parseSession(required((await api.GET('/me', { signal })).data)), message: 'AI 처리 동의를 철회하고 임시 체험을 종료했습니다.' }
        }, onSessionReset) }}>AI 동의 철회하고 임시 체험 종료</Button></section>
        <section className="account-section"><h2>회원 탈퇴</h2><p>계정 연결과 동의, 저장 자료, 모든 로그인 세션과 체험을 지워요. 복구 시 삭제를 다시 적용하는 데 필요한 최소 이력만 30일 남겨요. 탈퇴하려면 5분 이내에 카카오에서 다시 인증해야 해요.</p>
        <a className="text-link" href="/api/v1/auth/kakao/start?purpose=reauth">카카오에서 내 계정 재인증</a>
        <CheckboxField label="회원 탈퇴와 모든 저장 자료 삭제를 확인했어요." checked={deleteAccount} onChange={event => setDeleteAccount(event.target.checked)} />
        <Button variant="secondary" disabled={!deleteAccount || !me.user?.reauth_until} onClick={() => {
          setDeleteAccount(false); void request.run(async (api, signal) => {
            await api.DELETE('/me', { signal })
            const next = parseSession(required((await api.GET('/me', { signal })).data))
            if (next.authenticated) throw new ApiError('INVALID_RESPONSE')
            return { me: next, message: '회원 탈퇴와 저장 자료 삭제를 완료했습니다.' }
          }, onLogout)
        }}>재인증한 계정 탈퇴</Button></section>
      </>)}
      <p role="status">{state.status === 'success' ? state.data.message : ''}</p>
    </div><Link className="text-link account-home-link" to="/">시작 화면으로</Link>
  </div></ServicePage>
}
