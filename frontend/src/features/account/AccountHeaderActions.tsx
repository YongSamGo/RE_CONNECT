import { Link } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { required, useRequest } from '../../state/useRequest'
import { useEntryAction } from '../../state/useEntryAction'
import { parseSession } from './session'

export function AccountHeaderActions() {
  const session = useRequest<boolean>()
  const logout = useRequest<true>()
  const check = () => {
    logout.clear()
    return session.run(async (api, signal) => parseSession(required((await api.GET('/me', { signal })).data)).authenticated)
  }
  useEntryAction(check)
  const pending = session.state.status === 'pending' || logout.state.status === 'pending'
  const signOut = () => {
    void logout.run(async (api, signal) => {
      await api.POST('/auth/logout', { signal })
      const current = parseSession(required((await api.GET('/me', { signal })).data))
      if (current.authenticated) throw new ApiError('INVALID_RESPONSE')
      return true
    }, () => window.location.replace('/'))
  }

  if (session.state.status === 'pending') return <span className="header-session-status" role="status">로그인 상태 확인 중</span>
  if (session.state.status !== 'success') return <>
    {session.state.status === 'error' && <span role="status" className="header-session-error">로그인 상태를 확인하지 못했습니다.</span>}
    <button type="button" className="text-size-toggle" disabled={pending} onClick={() => void check()}>로그인 상태 다시 확인</button>
  </>
  if (!session.state.data) return <Link className="text-size-toggle header-login" to="/login">로그인</Link>
  return <>
    <Link className="text-size-toggle" to="/me">나의 정보 보기</Link>
    <button type="button" className="text-size-toggle" disabled={pending} onClick={signOut}>{pending ? '로그아웃 중' : '로그아웃'}</button>
    {logout.state.status === 'error' && <><span role="alert" className="header-session-error">로그아웃 결과를 확인하지 못했습니다. 로그인 상태를 다시 확인해 주세요.</span><button type="button" className="text-size-toggle" onClick={() => void check()}>로그인 상태 다시 확인</button></>}
  </>
}
