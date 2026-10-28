import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { components } from '../../api/schema'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'
import { invalid, isOpportunityId, record, text } from '../public-opportunities/catalog'
import { OpportunityReview } from './OpportunityReview'
import { AuditPanel } from './AuditPanel'
import { OpportunityEditor } from './OpportunityEditor'
import { ReportReview } from './ReportReview'
import { parseReport } from './report'
import type { ReportSnapshot } from './report'

type Me = components['schemas']['Me']
type Row = { id: string; version: number; title: string; status: string; report?: ReportSnapshot }
type View = { kind: 'opportunities' | 'reports'; rows: Row[]; page: number; total: number } | { kind: 'operations'; models: { name: string; state: string }[]; sources: { name: string; stale: boolean }[] | null }
const version = (value: unknown): number => typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : invalid()
function parseRows(data: unknown, kind: 'opportunities' | 'reports'): View {
  const item = record(data)
  if (!Array.isArray(item.items) || typeof item.total !== 'number' || !Number.isSafeInteger(item.total) || item.total < 0) return invalid()
  return { kind, page: version(item.page), total: item.total, rows: item.items.map((value) => {
    if (kind === 'reports') {
      const report = parseReport(value)
      return { id: report.report_id, version: report.version, title: report.opportunity_title, status: report.status, report }
    }
    const row = record(value)
    const id = text(row.id, 36)
    if (!isOpportunityId(id)) return invalid()
    const status = row.review_status
    const allowed = ['pending', 'approved', 'rejected', 'hidden']
    if (typeof status !== 'string' || !allowed.includes(status)) return invalid()
    return { id, version: version(row.version), title: text(row.title, 200), status }
  }) }
}
const statuses: Record<string, string> = { pending: '검수 대기', approved: '공개 승인', rejected: '반려', hidden: '비공개', received: '신고 접수', in_progress: '처리 중', resolved: '해결로 종결', dismissed: '조치 없이 종결' }

function AdminWorkspace() {
  const [auditOpen, setAuditOpen] = useState(false)
  const [editor, setEditor] = useState<{ target?: { id: string; version: number } } | null>(null)
  const request = useRequest<View>()
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState<Row | null>(null)
  const workspaceHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (!auditOpen && !editor) workspaceHeading.current?.focus() }, [auditOpen, editor])
  const state = request.state
  const pending = state.status === 'pending'
  const load = (kind: 'opportunities' | 'reports', page = 1) => {
    setSelected(null)
    void request.run(async (api, signal) => kind === 'opportunities'
      ? parseRows(required((await api.GET('/admin/opportunities', { signal, params: { query: { q: query.trim() || undefined, page, page_size: 10 } } })).data), kind)
      : parseRows(required((await api.GET('/admin/reports', { signal, params: { query: { page, page_size: 10 } } })).data), kind))
  }
  if (auditOpen) return <AuditPanel onBack={() => setAuditOpen(false)} />
  if (editor) return <OpportunityEditor key={editor.target ? `${editor.target.id}:${editor.target.version}` : 'create'} target={editor.target} onBack={() => setEditor(null)} />
  return <>
    <div className="actions"><Button variant="secondary" disabled={pending} onClick={() => { request.clear(); setSelected(null); setEditor({}) }}>새 공고 등록</Button><Button variant="secondary" disabled={pending} onClick={() => { request.clear(); setSelected(null); setQuery(''); setAuditOpen(true) }}>감사 기록 조회</Button></div>
    <section className="panel"><h2 className="review-heading" ref={workspaceHeading} tabIndex={-1}>운영 자료 조회</h2><form onSubmit={(event) => { event.preventDefault(); load('opportunities') }}><label htmlFor="admin-query">공고 제목 검색</label><input id="admin-query" value={query} maxLength={100} onChange={(event) => setQuery(event.target.value)} /><div className="actions"><Button type="submit" disabled={pending}>공고 목록 조회</Button><Button variant="secondary" disabled={pending} onClick={() => load('reports')}>신고 목록 조회</Button><Button variant="secondary" disabled={pending} onClick={() => { setSelected(null); void request.run(async (api, signal) => {
      const item = record(required((await api.GET('/admin/operations', { signal })).data))
      const models = record(item.models)
      // DB를 읽지 못하면 sources는 null이다. 나머지 상태는 그대로 보여 준다.
      if (item.sources !== null && !Array.isArray(item.sources)) return invalid()
      return { kind: 'operations', models: ['llm', 'stt', 'tts'].map((name) => { const value = models[name]; if (value !== 'ok' && value !== 'loading' && value !== 'fail') return invalid(); return { name, state: value } }), sources: item.sources === null ? null : item.sources.map((value) => { const source = record(value); if (typeof source.stale !== 'boolean') return invalid(); return { name: text(source.name, 200), stale: source.stale } }) }
    }) }}>수집, 모델 상태 조회</Button></div></form></section>
    {pending && <p role="status">서버에 요청하고 있어요.</p>}
    {state.status === 'error' && <RequestError error={state.error} />}
    {state.status === 'success' && (state.data.kind === 'operations' ? <section className="panel"><h2>수집, 모델 상태</h2><ul>{state.data.models.map((model) => <li key={model.name}>{model.name}: {model.state === 'ok' ? '정상' : model.state === 'loading' ? '준비 중' : '장애'}</li>)}</ul>{state.data.sources === null ? <p>출처 수집 상태를 읽지 못했습니다.</p> : <ul>{state.data.sources.map((source, index) => <li key={index}>{source.name}: {source.stale ? '48시간 넘게 수집 성공 없음' : '최근 48시간 안에 수집 성공'}</li>)}</ul>}</section> : <section className="panel"><h2>{state.data.kind === 'reports' ? '신고 목록' : '공고 목록'}</h2>
      {state.data.rows.length ? <ul className="admin-result-list">{state.data.rows.map((row) => <li key={row.id}><p>{row.title} / {statuses[row.status]} / 버전 {row.version}</p><Button variant="secondary" disabled={pending} onClick={() => setSelected(row)}>검토 선택 / {row.title}</Button></li>)}</ul> : <p>조회 결과가 없습니다.</p>}
      <div className="actions"><Button variant="secondary" disabled={pending || state.data.page <= 1} onClick={() => { if (state.data.kind !== 'operations') load(state.data.kind, state.data.page - 1) }}>이전 페이지</Button><p>{state.data.page}페이지 / 전체 {state.data.total}건</p><Button variant="secondary" disabled={pending || state.data.page * 10 >= state.data.total} onClick={() => { if (state.data.kind !== 'operations') load(state.data.kind, state.data.page + 1) }}>다음 페이지</Button></div>
    </section>)}
    {selected && state.status === 'success' && state.data.kind === 'opportunities' && <><Button variant="secondary" onClick={() => { const target = { id: selected.id, version: selected.version }; request.clear(); setSelected(null); setEditor({ target }) }}>선택한 공고 수정</Button><OpportunityReview key={`${selected.id}:${selected.version}`} id={selected.id} version={selected.version} /></>}
    {selected?.report && state.status === 'success' && state.data.kind === 'reports' && <ReportReview key={`${selected.id}:${selected.version}`} report={selected.report} onRefresh={() => load('reports')} />}
    <StatusNotice label="처리 전 확인" title="공식 원문과 최신 상태를 확인해 주세요">공고의 공개, 비공개, 종료와 신고 처리는 이용자에게 영향을 줍니다. 변경 사항과 처리 근거를 확인한 뒤 진행해 주세요.</StatusNotice>
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
    {operator && !session.user?.mfa_verified && <section className="panel"><h2>추가 인증</h2><form onSubmit={(event) => { event.preventDefault(); const code = otp.value; if (!/^\d{6}$/.test(code)) return; otp.clear(); void request.run(async (api, signal) => { await api.POST('/admin/mfa/verify', { signal, body: { otp: code } }); return parseSession(required((await api.GET('/me', { signal })).data)) }) }}><label htmlFor="admin-otp">인증 앱의 6자리 코드</label><input id="admin-otp" type="password" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6} value={otp.value} onChange={(event) => otp.setValue(event.target.value)} /><div className="actions"><Button type="submit" disabled={!/^\d{6}$/.test(otp.value) || pending}>추가 인증 확인</Button></div></form></section>}
    {operator && session.user?.mfa_verified && <AdminWorkspace />}
    <Link className="text-link" to="/">시작 화면으로 →</Link>
  </div>
}
