import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import type { components } from '../../api/schema'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseSession } from './session'

// These values describe navigation only. Authentication and save completion
// must never be inferred from this untrusted query string.
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
  useEffect(() => {
    if (!me) return
    const expiries = [me.pending_save_intent?.expires_at, me.user?.reauth_until]
      .filter((value): value is string => !!value).map(Date.parse).filter(value => value > checkedAt)
    // Also expire a plain session preview: /me is a snapshot, not a durable
    // authorization. Server-side guards still protect every actual operation.
    const deadline = Math.min(checkedAt + 60000, ...expiries)
    const timer = window.setTimeout(clear, Math.max(0, deadline - Date.now()))
    return () => window.clearTimeout(timer)
  }, [me, checkedAt, clear])
  const pending = me?.authenticated && me.pending_save_intent
    && Date.parse(me.pending_save_intent.expires_at) > checkedAt ? me.pending_save_intent : null
  const reauthenticated = me?.authenticated && me.user?.reauth_until
    && Date.parse(me.user.reauth_until) > checkedAt
  return <div className="reading-width">
    <header className="page-heading"><p className="eyebrow">로그인 후 돌아온 화면</p><h1>현재 로그인 상태를 확인해요</h1><p>현재 로그인 상태를 서버에서 확인해 주세요. 로그인 후에도 자료 저장은 따로 확인해야 해요.</p></header>
    {!result ? <StatusNotice title="돌아온 주소를 확인할 수 없어요">내 정보 화면에서 현재 상태를 확인해 주세요.</StatusNotice> : <>
      {result.status === 'cancelled' && <StatusNotice title="요청이 취소되어 돌아왔어요">필요하면 현재 로그인 상태를 확인해 주세요.</StatusNotice>}
      {result.status === 'failed' && <StatusNotice title="요청 결과를 확인해야 해요">현재 상태를 확인한 뒤 다시 진행해 주세요.</StatusNotice>}
      {result.status === 'expired' && <StatusNotice title="요청 시간이 지났어요">이전 요청으로 저장을 계속하지 않습니다. 현재 상태를 확인해 주세요.</StatusNotice>}
      <section className="panel"><Button pending={state.status === 'pending'} onClick={() => void request.run(async (api, signal) => ({ me: parseSession(required((await api.GET('/me', { signal })).data)), checkedAt: Date.now() }))}>서버에서 현재 상태 확인</Button>
        {state.status === 'pending' && <p role="status">서버의 현재 세션을 확인하고 있어요.</p>}
        {state.status === 'error' && <RequestError error={state.error} />}
        <p className="visually-hidden" role="status">{me ? me.authenticated ? '로그인 상태를 확인했어요.' : '현재 로그인하지 않은 상태입니다.' : ''}</p>
        {me && <div className="account-result">{me.authenticated ? <>
          <h2>로그인 상태를 확인했어요</h2>
          {result.purpose === 'reauth' && <p>{reauthenticated ? '서버에서 유효한 재인증을 확인했습니다. 탈퇴는 내 정보에서 별도로 확인하고 요청해 주세요.' : '현재 유효한 재인증이 확인되지 않았습니다. 탈퇴하려면 내 정보에서 다시 재인증해 주세요.'}</p>}
          {pending ? <>
            <h3>저장 대기 자료가 있어요</h3>
            <p>{pending.targets.draft ? '프로필과 지원서를 함께 저장하는 요청입니다. 프로필도 저장 대상에 포함됩니다.' : '확정 프로필을 저장하는 요청입니다.'}</p>
            {pending.existing_saved_profile_version !== null && <p>기존 저장 프로필이 있습니다. 교체 여부를 직접 확인해야 합니다.</p>}
            <p>로그인만으로 자료를 저장하지는 않았어요. 저장 대기 화면에서 안내문과 동의 내용, 저장 대상을 직접 확인해 주세요.</p>
            <Link className="button secondary" to="/me/save">저장 대기 자료 확인</Link>
          </> : <p>계속할 수 있는 저장 대기 요청이 없습니다. 저장된 자료는 내 정보에서 따로 조회해 주세요.</p>}
          <p>대화는 새로 시작합니다. 이전 대화나 저장하지 않은 입력을 복원하지 않습니다.</p>
        </> : <p>현재 로그인하지 않은 상태입니다. 로그인이나 저장 완료를 확인할 수 없습니다.</p>}</div>}
      </section>
    </>}
    <StatusNotice title="운영 안내문 게시를 확인해 주세요">운영 주체와 문의처, 보관 및 삭제 정책이 확정 게시되기 전에는 새 로그인과 동의를 제공하지 않아요.</StatusNotice>
    <div className="actions"><Link className="button primary" to="/me">내 정보로 이동</Link><Link className="text-link" to="/">시작 화면으로</Link></div>
  </div>
}
