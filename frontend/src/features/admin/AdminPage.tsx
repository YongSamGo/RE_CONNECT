import { useState } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'
import { invalid, isOpportunityId, record, text } from '../public-opportunities/catalog'
import { OpportunityReview } from './OpportunityReview'

type Me = components['schemas']['Me']
type Row = { id: string; version: number; title: string; status: string; note: string | null }
type View = { kind: 'opportunities' | 'reports'; rows: Row[]; page: number; total: number } | { kind: 'operations'; models: { name: string; state: string }[]; sources: { name: string; stale: boolean }[] }
const version = (value: unknown): number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : invalid()
function parseRows(data: unknown, kind: 'opportunities' | 'reports'): View {
  const item = record(data)
  if (!Array.isArray(item.items) || typeof item.total !== 'number' || !Number.isSafeInteger(item.total) || item.total < 0) return invalid()
  return { kind, page: version(item.page), total: item.total, rows: item.items.map((value) => {
    const row = record(value)
    const id = text(kind === 'reports' ? row.report_id : row.id, 36)
    if (!isOpportunityId(id)) return invalid()
    const status = kind === 'reports' ? row.status : row.review_status
    const allowed = kind === 'reports' ? ['received', 'in_progress', 'resolved', 'dismissed'] : ['pending', 'approved', 'rejected', 'hidden']
    if (typeof status !== 'string' || !allowed.includes(status)) return invalid()
    return { id, version: version(row.version), title: text(kind === 'reports' ? row.opportunity_title : row.title, 200), status, note: kind === 'reports' && row.note !== null ? text(row.note, 1000) : null }
  }) }
}
const statuses: Record<string, string> = { pending: '검수 대기', approved: '공개 승인', rejected: '반려', hidden: '비공개', received: '신고 접수', in_progress: '처리 중', resolved: '해결', dismissed: '종결' }

function AdminWorkspace() {
  const request = useRequest<View>()
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Row | null>(null)
  const [note, setNote] = useState('')
  const mutation = useRequest<string>()
  const state = request.state
  const pending = state.status === 'pending' || mutation.state.status === 'pending'
  const load = (kind: 'opportunities' | 'reports', page = 1) => {
    setSelected(null); setNote(''); mutation.clear()
    void request.run(async (api, signal) => kind === 'opportunities'
      ? parseRows(required((await api.GET('/admin/opportunities', { signal, params: { query: { q: query.trim() || undefined, page, page_size: 10 } } })).data), kind)
      : parseRows(required((await api.GET('/admin/reports', { signal, params: { query: { page, page_size: 10 } } })).data), kind))
  }
  function review() {
    if (!selected || !note.trim() || pending) return
    const row = selected
    void mutation.run(async (api, signal) => {
      await api.PATCH('/admin/reports/{report_id}', { signal, params: { path: { report_id: row.id } }, body: { base_version: row.version, status: row.status === 'received' ? 'in_progress' : 'resolved', resolution_note: note.trim() } })
      return '서버가 처리를 완료했습니다. 목록을 다시 조회해 최신 버전을 확인해 주세요.'
    })
  }
  return <>
    <section className="panel"><h2>운영 자료 조회</h2><form onSubmit={(event) => { event.preventDefault(); load('opportunities') }}><label htmlFor="admin-query">공고 제목 검색</label><input id="admin-query" value={query} maxLength={100} onChange={(event) => setQuery(event.target.value)} /><div className="actions"><Button type="submit" disabled={pending}>공고 목록 조회</Button><Button variant="secondary" disabled={pending} onClick={() => load('reports')}>신고 목록 조회</Button><Button variant="secondary" disabled={pending} onClick={() => { setSelected(null); mutation.clear(); void request.run(async (api, signal) => {
      const item = record(required((await api.GET('/admin/operations', { signal })).data))
      const models = record(item.models)
      if (!Array.isArray(item.sources)) return invalid()
      return { kind: 'operations', models: ['llm', 'stt', 'tts'].map((name) => { const value = models[name]; if (value !== 'ok' && value !== 'loading' && value !== 'fail') return invalid(); return { name, state: value } }), sources: item.sources.map((value) => { const source = record(value); if (typeof source.stale !== 'boolean') return invalid(); return { name: text(source.name, 200), stale: source.stale } }) }
    }) }}>수집·모델 상태 조회</Button></div></form></section>
    {pending && <p role="status">서버에 요청하고 있어요.</p>}
    {state.status === 'error' && <RequestError error={state.error} />}
    {state.status === 'success' && (state.data.kind === 'operations' ? <section className="panel"><h2>수집·모델 상태</h2><ul>{state.data.models.map((model) => <li key={model.name}>{model.name}: {model.state === 'ok' ? '정상' : model.state === 'loading' ? '준비 중' : '장애'}</li>)}</ul><ul>{state.data.sources.map((source, index) => <li key={index}>{source.name}: {source.stale ? '출처 갱신 지연 · 추천 보류' : '갱신 지연 없음'}</li>)}</ul></section> : <section className="panel"><h2>{state.data.kind === 'reports' ? '신고 목록' : '공고 목록'}</h2>
      {state.data.rows.length ? <ul>{state.data.rows.map((row) => <li key={row.id}><p>{row.title} · {statuses[row.status]} · 버전 {row.version}</p><Button variant="secondary" disabled={pending} onClick={() => { setSelected(row); setNote(''); mutation.clear() }}>검토 선택 · {row.title}</Button></li>)}</ul> : <p>조회 결과가 없습니다.</p>}
      <div className="actions"><Button variant="secondary" disabled={pending || state.data.page <= 1} onClick={() => { if (state.data.kind !== 'operations') load(state.data.kind, state.data.page - 1) }}>이전 페이지</Button><p>{state.data.page}페이지 · 전체 {state.data.total}건</p><Button variant="secondary" disabled={pending || state.data.page * 10 >= state.data.total} onClick={() => { if (state.data.kind !== 'operations') load(state.data.kind, state.data.page + 1) }}>다음 페이지</Button></div>
    </section>)}
    {selected && state.status === 'success' && state.data.kind === 'opportunities' && <OpportunityReview key={`${selected.id}:${selected.version}`} id={selected.id} version={selected.version} />}
    {selected && state.status === 'success' && state.data.kind === 'reports' && <section className="panel"><h2>{selected.title} 검토</h2><p>선택한 버전은 {selected.version}입니다. 충돌이 발생하면 목록을 새로 조회한 뒤 다시 검토해 주세요.</p><h3>신고 설명</h3><p className="user-text">{selected.note ?? '추가 설명 없음'}</p>
      <TextAreaField label="검토 근거와 처리 메모" value={note} onChange={(event) => { setNote(event.target.value); mutation.clear() }} maxLength={1000} hint="공식 원문과 변경 내용을 확인하고 기록하세요. 개인정보·OTP·비밀값은 적지 마세요." />
      <div className="actions"><Button disabled={pending || !note.trim() || !['received', 'in_progress'].includes(selected.status) || mutation.state.status === 'success'} onClick={review}>{selected.status === 'received' ? '처리 시작' : '해결로 처리'}</Button></div>
    </section>}
    {mutation.state.status === 'error' && <RequestError error={mutation.state.error} />}
    <p role="status">{mutation.state.status === 'success' ? mutation.state.data : ''}</p>
    <StatusNotice title="전체 운영 기능은 서버 검증 대기 중이에요">등록·수정·반려·종료와 감사 기록은 운영 계약과 실제 서버를 대조한 뒤 연결합니다. 공고 승인·비공개·신고 처리는 서버 권한·MFA·버전 검증을 통과해야 합니다.</StatusNotice>
  </>
}

export function AdminPage() {
  const request = useRequest<Me>()
  const otp = useMemoryScope(() => '')
  const state = request.state
  const session = state.status === 'success' ? state.data : null
  const operator = session?.authenticated && session.user?.roles.includes('operator')
  const pending = state.status === 'pending'
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">운영자</p><h1>운영자 접근을 확인해요</h1><p>서버의 운영자 역할과 MFA 확인이 필요합니다.</p></header>
    <Button pending={pending} onClick={() => void request.run(async (api, signal) => parseSession(required((await api.GET('/me', { signal })).data)))}>운영자 접근 확인</Button>
    {state.status === 'error' && <RequestError error={state.error} />}
    {session && !operator && <StatusNotice kind="error" title="운영자 권한이 필요합니다">현재 세션으로는 운영 자료를 조회하거나 변경할 수 없습니다.</StatusNotice>}
    {operator && !session.user?.mfa_verified && <section className="panel"><h2>추가 인증</h2><form onSubmit={(event) => { event.preventDefault(); const code = otp.value; if (!/^\d{6}$/.test(code)) return; otp.clear(); void request.run(async (api, signal) => { await api.POST('/admin/mfa/verify', { signal, body: { otp: code } }); return parseSession(required((await api.GET('/me', { signal })).data)) }) }}><label htmlFor="admin-otp">인증 앱의 6자리 코드</label><input id="admin-otp" type="password" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={otp.value} onChange={(event) => otp.setValue(event.target.value)} /><Button type="submit" disabled={!/^\d{6}$/.test(otp.value) || pending}>추가 인증 확인</Button></form></section>}
    {operator && session.user?.mfa_verified && <AdminWorkspace />}
    <Link className="text-link" to="/">시작 화면으로 →</Link>
  </div>
}
