import { useEffect, useRef, useState } from 'react'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { checkedTime } from '../public-opportunities/detail'
import { auditActions, auditPageSize, auditRange, koreaDateTimeInput, parseAudit } from './audit'
import type { AuditPage, AuditRange } from './audit'
import './admin.css'

const rangeError = '시작, 종료 시간을 확인해 주세요. 종료는 시작 이후이며 조회 범위는 최대 30일입니다.'

export function AuditPanel({ onBack }: { onBack: () => void }) {
  const [initialTime] = useState(() => Date.now())
  const [from, setFrom] = useState(() => koreaDateTimeInput(initialTime - 24 * 60 * 60 * 1000))
  const [to, setTo] = useState(() => koreaDateTimeInput(initialTime))
  const [errors, setErrors] = useState<FieldError[]>([])
  const error = errors.length > 0
  const request = useRequest<AuditPage>()
  const state = request.state
  const pending = state.status === 'pending'
  const result = useRef<HTMLElement>(null)
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])
  useEffect(() => { if (state.status === 'success' || state.status === 'error') result.current?.focus() }, [state.status])
  const load = (range: AuditRange, page = 1) => request.run(async (api, signal) => parseAudit(required((await api.GET('/admin/audit', { signal, params: { query: { ...range, page, page_size: auditPageSize } } })).data), page, range))
  return <>
    <section className="panel audit-panel"><h2 className="review-heading" ref={headingRef} tabIndex={-1}>최소 감사 기록 조회</h2><p>조회 범위는 최대 30일이며 아래 시간은 한국시간입니다. 개인 본문, 인증 코드, 토큰은 표시하지 않습니다.</p>
      <form onSubmit={(event) => { event.preventDefault(); const range = auditRange(from, to); setErrors(range ? [] : [{ fieldId: 'audit-from', message: rangeError }]); if (range) void load(range) }}>
        <FormErrorSummary errors={errors} />
        <label htmlFor="audit-from">조회 시작 (한국시간)</label><input id="audit-from" type="datetime-local" value={from} required disabled={pending} aria-invalid={error || undefined} aria-describedby={error ? 'audit-range-error' : undefined} onChange={(event) => { setFrom(event.target.value); setErrors([]); request.clear() }} />
        <label htmlFor="audit-to">조회 종료 (한국시간)</label><input id="audit-to" type="datetime-local" value={to} required disabled={pending} aria-invalid={error || undefined} aria-describedby={error ? 'audit-range-error' : undefined} onChange={(event) => { setTo(event.target.value); setErrors([]); request.clear() }} />
        {error && <p className="field-error" id="audit-range-error">{rangeError}</p>}
        <div className="actions"><Button type="submit" pending={pending}>감사 기록 불러오기</Button>{pending && <Button variant="secondary" onClick={request.clear}>감사 조회 취소</Button>}</div>
      </form>
    </section>
    <section ref={result} tabIndex={-1} aria-label="감사 기록 조회 결과">
      {pending && <p role="status">감사 기록을 확인하고 있습니다.</p>}
      {state.status === 'error' && <RequestError error={state.error} />}
      {state.status === 'success' && <div className="panel"><p>{checkedTime(state.data.range.from)} ~ {checkedTime(state.data.range.to)} (한국시간)</p>
        {state.data.rows.length === 0 ? <StatusNotice label="조회 결과" title="이 기간의 감사 기록이 없습니다">기간을 확인하거나 다른 기간을 직접 선택해 주세요.</StatusNotice> : <div className="audit-scroll" role="region" aria-label="감사 기록 표 / 가로로 스크롤할 수 있습니다" tabIndex={0}><table className="audit-table"><caption>운영 감사 기록</caption><thead><tr><th scope="col">시간 (한국시간)</th><th scope="col">행동</th><th scope="col">실행 역할</th><th scope="col">결과</th><th scope="col">대상 종류</th><th scope="col">요청 추적 번호</th></tr></thead><tbody>{state.data.rows.map((row) => <tr key={row.event_id}><td>{checkedTime(row.at)}</td><td>{auditActions[row.action]}</td><td>{{ operator: '운영자', user: '회원', system: '시스템' }[row.actor_role]}</td><td>{{ success: '성공', denied: '거부', failed: '실패' }[row.result]}</td><td>{row.target_type ? { opportunity: '공고', report: '신고', user: '회원' }[row.target_type] : '해당 없음'}</td><td>{row.request_id}</td></tr>)}</tbody></table></div>}
        <div className="actions"><Button variant="secondary" disabled={state.data.page <= 1} onClick={() => void load(state.data.range, state.data.page - 1)}>이전 감사 페이지</Button><p>{state.data.page}페이지 / 전체 {state.data.total}건</p><Button variant="secondary" disabled={state.data.page * auditPageSize >= state.data.total} onClick={() => void load(state.data.range, state.data.page + 1)}>다음 감사 페이지</Button></div>
      </div>}
    </section><Button variant="secondary" onClick={onBack}>운영 목록으로 돌아가기</Button>
  </>
}
