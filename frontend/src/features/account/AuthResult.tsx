import { useEntryAction } from '../../state/useEntryAction'
import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import type { components } from '../../api/schema'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseSession } from './session'
import { ServicePage } from '../../ui/ServicePage'

// These values describe navigation only. Authentication must never be inferred
// from this untrusted query string.
function resultQuery(search: string) {
  const query = new URLSearchParams(search)
  const purpose = query.get('purpose')
  const status = query.get('status')
  if ([...query.keys()].length !== 2 || query.getAll('purpose').length !== 1
    || query.getAll('status').length !== 1
    || !['login', 'save', 'reauth'].includes(purpose ?? '')
    || !['success', 'cancelled', 'failed', 'expired'].includes(status ?? '')) return null
  return { purpose, status }
}

export function AuthResult() {
  const location = useLocation()
  // A changed callback URL gets a fresh request scope, including when returning
  // through browser history without leaving the SPA.
  return <Result key={location.key + location.search} search={location.search} />
}

function Result({ search }: { search: string }) {
  const result = resultQuery(search)
  const request = useRequest<{ me: components['schemas']['Me']; checkedAt: number }>()
  const state = request.state
  const me = state.status === 'success' ? state.data.me : null
  const checkedAt = state.status === 'success' ? state.data.checkedAt : 0
  const clear = request.clear
  const check = () => request.run(async (api, signal) => ({ me: parseSession(required((await api.GET('/me', { signal })).data)), checkedAt: Date.now() }))
  useEntryAction(check, !!result, search)
  useEffect(() => {
    if (!me) return
    const expiries = [me.user?.reauth_until, me.pending_save_intent?.expires_at]
      .filter((value): value is string => !!value).map(Date.parse).filter(value => value > checkedAt)
    // Also expire a plain session preview: /me is a snapshot, not a durable
    // authorization. Server-side guards still protect every actual operation.
    const deadline = Math.min(checkedAt + 60000, ...expiries)
    const timer = window.setTimeout(clear, Math.max(0, deadline - Date.now()))
    return () => window.clearTimeout(timer)
  }, [me, checkedAt, clear])
  const reauthenticated = me?.authenticated && me.user?.reauth_until
    && Date.parse(me.user.reauth_until) > checkedAt
  return <ServicePage title="로그인 확인" className="auth-result-page">
    {!result ? <StatusNotice title="돌아온 주소를 확인할 수 없어요">나의 정보 화면에서 현재 상태를 확인해 주세요.</StatusNotice> : <>
      {result.status === 'cancelled' && <StatusNotice title="요청이 취소되어 돌아왔어요">필요하면 현재 로그인 상태를 확인해 주세요.</StatusNotice>}
      {result.status === 'failed' && <StatusNotice title="요청 결과를 확인해야 해요">현재 상태를 확인한 뒤 다시 진행해 주세요.</StatusNotice>}
      {result.status === 'expired' && <StatusNotice title="요청 시간이 지났어요">현재 로그인 상태를 확인해 주세요.</StatusNotice>}
      <section className="panel">{!me && <Button pending={state.status === 'pending'} onClick={() => void check()}>로그인 상태 다시 확인</Button>}
        {state.status === 'pending' && <p role="status">서버의 현재 세션을 확인하고 있어요.</p>}
        {state.status === 'error' && <RequestError error={state.error} />}
        <p className="visually-hidden" role="status">{me ? me.authenticated ? '로그인 상태를 확인했어요.' : '현재 로그인하지 않은 상태입니다.' : ''}</p>
        {me && <div className="account-result">{me.authenticated ? <>
          <h2>로그인 상태를 확인했어요</h2>
          {result.purpose === 'reauth' && <p>{reauthenticated ? '서버에서 유효한 재인증을 확인했습니다. 탈퇴는 나의 정보에서 별도로 확인하고 요청해 주세요.' : '현재 유효한 재인증이 확인되지 않았습니다. 탈퇴하려면 나의 정보에서 다시 재인증해 주세요.'}</p>}
          <p>대화는 새로 시작합니다. 이전 대화나 저장하지 않은 입력을 복원하지 않습니다.</p>
          {me.pending_save_intent && Date.parse(me.pending_save_intent.expires_at) > checkedAt
            && <p><Link className="button secondary" to="/me/save">저장 대기 자료 확인</Link></p>}
        </> : <p>현재 로그인하지 않은 상태입니다.</p>}</div>}
      </section>
    </>}
    <div className="actions"><Link className="button primary" to="/me">나의 정보로 이동</Link><Link className="text-link" to="/">시작 화면으로</Link></div>
  </ServicePage>
}
