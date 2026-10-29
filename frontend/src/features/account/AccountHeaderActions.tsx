import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { createApiClient } from '../../api/client'
import { required } from '../../state/useRequest'
import { parseSession } from './session'

export function AccountHeaderActions() {
  const api = useMemo(() => createApiClient(), [])
  const [authenticated, setAuthenticated] = useState<boolean | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const controller = new AbortController()
    void api.GET('/me', { signal: controller.signal }).then(({ data }) => {
      setAuthenticated(parseSession(required(data)).authenticated)
    }).catch(() => { if (!controller.signal.aborted) setAuthenticated(false) })
    return () => controller.abort()
  }, [api])

  async function logout() {
    setPending(true)
    setError('')
    try {
      await api.POST('/auth/logout')
      const current = parseSession(required((await api.GET('/me')).data))
      if (current.authenticated) throw new ApiError('INVALID_RESPONSE')
      window.location.replace('/')
    } catch {
      setPending(false)
      setError('로그아웃하지 못했습니다. 잠시 후 다시 시도해 주세요.')
    }
  }

  if (authenticated === null) return <span className="header-session-status" role="status">로그인 상태 확인 중</span>
  if (!authenticated) return <Link className="text-size-toggle header-login" to="/login">로그인</Link>
  return <>
    <Link className="text-size-toggle" to="/me">나의 정보 보기</Link>
    <button type="button" className="text-size-toggle" disabled={pending} onClick={() => void logout()}>{pending ? '로그아웃 중' : '로그아웃'}</button>
    {error && <span role="alert" className="header-session-error">{error}</span>}
  </>
}
