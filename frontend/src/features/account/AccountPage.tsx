import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseSession } from './session'

type Me = components['schemas']['Me']
type Result = { me: Me; message?: string }

export function AccountPage({ onLogout }: { onLogout?: () => void }) {
  const request = useRequest<Result>()
  const [remove, setRemove] = useState(false)
  const state = request.state
  const me = state.status === 'success' ? state.data.me : null
  const pending = state.status === 'pending'
  const check = () => request.run(async (api, signal) => ({ me: parseSession(required((await api.GET('/me', { signal })).data)) }))
  return <div className="reading-width">
    <header className="page-heading"><p className="eyebrow">내 정보</p><h1>내 정보와 동의를 관리해요</h1><p>서버에서 확인한 현재 세션으로만 자료에 접근합니다.</p></header>
    <StatusNotice title="로그인·저장 운영 준비 중이에요">백엔드와 운영 안내문이 확정되지 않았습니다. 미리보기 입력은 회원 자료가 아닙니다. 아래 조회는 실제 서버에 요청하며 연결되지 않으면 오류를 안내합니다.</StatusNotice>
    <div className="panel"><Button pending={pending} onClick={() => { setRemove(false); void check() }}>내 로그인 상태 확인</Button>
      {pending && <p role="status">서버의 로그인 상태를 확인하고 있어요.</p>}
      {state.status === 'error' && <RequestError error={state.error} />}
      {me && (!me.authenticated ? <p>로그인하지 않은 상태입니다. 운영 안내문 확정 후 카카오 로그인을 제공합니다.</p> : <>
        <h2>현재 로그인 상태</h2><p>회원 세션이 확인되었습니다. 대화는 새로 시작하며 저장하지 않은 미리보기는 회원 자료에 포함되지 않습니다.</p>
        <h3>현재 동의</h3>{me.consents.length ? <ul>{me.consents.map((consent) => <li key={consent.purpose}>{consent.purpose === 'storage' ? '회원 저장' : 'AI 처리'} · 안내문 {consent.notice_version}</li>)}</ul> : <p>현재 유효한 동의가 없습니다.</p>}
        <Link className="button secondary" to="/me/saved">저장한 자료 조회</Link>
        <div className="actions"><Button variant="secondary" onClick={() => void request.run(async (api, signal) => { await api.POST('/auth/logout', { signal }); const me = parseSession(required((await api.GET('/me', { signal })).data)); if (me.authenticated) throw new ApiError('INVALID_RESPONSE'); return { me, message: '로그아웃 요청이 완료되었습니다.' } }, onLogout)}>로그아웃</Button></div>
        <h3>회원 저장 동의 철회</h3><p>철회하면 저장 프로필의 모든 버전과 지원서가 삭제됩니다.</p>
        <CheckboxField label="저장 동의를 철회하고 저장 자료를 삭제할게요." checked={remove} onChange={(event) => setRemove(event.target.checked)} />
        <Button variant="secondary" disabled={!remove} onClick={() => { setRemove(false); void request.run(async (api, signal) => { await api.POST('/consents/withdraw', { signal, body: { purpose: 'storage' } }); return { me: parseSession(required((await api.GET('/me', { signal })).data)), message: '회원 저장 동의를 철회했습니다. 저장 프로필과 지원서 삭제 요청이 완료되었습니다.' } }) }}>동의 철회하고 저장 자료 삭제</Button>
        <p>회원 탈퇴는 카카오 재인증과 운영 안내문 확정 후 연결합니다.</p>
      </>)}
      <p role="status">{state.status === 'success' ? state.data.message : ''}</p>
    </div><Link className="text-link" to="/">시작 화면으로 →</Link>
  </div>
}
