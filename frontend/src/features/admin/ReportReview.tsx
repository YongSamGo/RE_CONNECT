import { Link } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { RequestError } from '../../ui/StatusNotice'
import { checkedTime } from '../public-opportunities/detail'
import { parseReport, reportTypes } from './report'
import type { ReportSnapshot } from './report'

const statuses = { received: '신고 접수', in_progress: '처리 중', resolved: '해결로 종결', dismissed: '조치 없이 종결' }
export function ReportReview({ report, onRefresh }: { report: ReportSnapshot; onRefresh: () => void }) {
  const form = useMemoryScope<{ note: string; checked: boolean; errors: FieldError[] }>(() => ({ note: '', checked: false, errors: [] }))
  const latest = useMemoryScope<ReportSnapshot | null>(() => null)
  const request = useRequest<ReportSnapshot>()
  const current = latest.value ?? report
  const pending = request.state.status === 'pending'
  const stale = request.state.status === 'error' && ['VERSION_CONFLICT', 'INVALID_STATE_TRANSITION'].includes(request.state.error.code)
  const terminal = current.status === 'resolved' || current.status === 'dismissed'
  const locked = pending || stale || terminal
  async function submit(status: 'in_progress' | 'resolved' | 'dismissed') {
    if (locked || (current.status === 'received' ? status !== 'in_progress' : status === 'in_progress')) return
    const errors: FieldError[] = []
    if (form.value.note.length > 500 || (status !== 'in_progress' && !form.value.note.trim())) errors.push({ fieldId: 'report-resolution', message: '종결 사유를 500자 이내로 적어 주세요.' })
    if (!form.value.checked) errors.push({ fieldId: 'report-reviewed', message: '신고 내용과 처리 근거를 확인해 주세요.' })
    if (errors.length) { form.setValue((previous) => ({ ...previous, errors })); return }
    const body = { base_version: current.version, status, resolution_note: form.value.note.trim() || null }
    await request.run(async (api, signal) => {
      const result = parseReport(required((await api.PATCH('/admin/reports/{report_id}', { signal, params: { path: { report_id: current.report_id } }, body })).data))
      if (result.report_id !== current.report_id || result.opportunity.id !== current.opportunity.id || result.opportunity.version !== current.opportunity.version
        || result.type !== current.type || result.version <= current.version || result.status !== status) throw new ApiError('INVALID_RESPONSE')
      return result
    }, (result) => { latest.setValue(result); form.clear() })
  }
  return <section className="panel"><h2>{current.opportunity_title} 신고 검토</h2>
    <p>{reportTypes[current.type]} · {statuses[current.status]} · 처리 버전 {current.version}</p>
    <p>신고 대상 공고 버전 {current.opportunity.version} · 접수: {checkedTime(current.created_at)} (한국시간)</p>
    <h3>신고 설명</h3><p className="user-text">{current.note || '추가 설명 없음'}</p>
    <Link className="text-link" to={`/opportunities/${current.opportunity.id}`}>현재 공개 공고 살펴보기 →</Link>
    <p>신고 종결은 공고 수정·모집 종료를 대신하지 않습니다. 필요한 공고 변경은 별도로 검수해 주세요.</p>
    {current.resolution_note && <><h3>기록된 처리 메모</h3><p className="user-text">{current.resolution_note}</p></>}
    {!terminal && <><FormErrorSummary errors={form.value.errors} />
      <TextAreaField id="report-resolution" label="신고 처리 근거와 종결 사유" value={form.value.note} maxLength={500} disabled={locked} error={form.value.errors.find((error) => error.fieldId === 'report-resolution')?.message} hint="해결·조치 없이 종결에는 사유가 필요합니다. 개인정보·인증 코드·비밀값은 적지 마세요." onChange={(event) => form.setValue((previous) => ({ ...previous, note: event.target.value, checked: false, errors: [] }))} />
      <CheckboxField id="report-reviewed" label="신고 내용과 처리 근거를 확인했습니다." checked={form.value.checked} disabled={locked} error={form.value.errors.find((error) => error.fieldId === 'report-reviewed')?.message} onChange={(event) => form.setValue((previous) => ({ ...previous, checked: event.target.checked, errors: [] }))} />
      <div className="actions">{current.status === 'received' ? <Button pending={pending} disabled={locked} onClick={() => void submit('in_progress')}>처리 시작</Button> : <><Button pending={pending} disabled={locked} onClick={() => void submit('resolved')}>해결로 종결</Button><Button variant="secondary" disabled={locked} onClick={() => void submit('dismissed')}>조치 없이 종결</Button></>}</div>
    </>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    <p role="status">{request.state.status === 'success' ? `서버가 신고를 ${statuses[current.status]} 상태로 처리했습니다. 처리 버전 ${current.version}입니다.` : ''}</p>
    {terminal && <p>종결된 신고입니다. 추가 상태 변경은 제공하지 않습니다.</p>}
    {stale && <p>편집 메모는 유지했습니다. 최신 목록을 조회한 뒤 신고 상태를 다시 확인해 주세요.</p>}
    <Button variant="secondary" disabled={pending} onClick={onRefresh}>최신 신고 목록 다시 조회</Button>
  </section>
}
