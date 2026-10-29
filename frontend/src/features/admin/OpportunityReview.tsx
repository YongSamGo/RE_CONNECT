import { useEffect, useRef, useState } from 'react'
import type { components } from '../../api/schema'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { invalid, record, text, timestamp } from '../public-opportunities/catalog'
import { officialLink } from '../public-opportunities/detail'
import { parseRequirements } from './editor'
import { RequirementSummary } from './RequirementEditor'

type Content = { title: string; description: string | null; instructions: string; requirements: components['schemas']['Requirement'][]; documents: string[] | null; source: string }
type Review = { version: number; status: string; content: Content; previous: Content | null; changed: string[]; important: boolean }
type RejectReason = components['schemas']['OpportunityRejectRequest']['reason_code']
type CloseBasis = components['schemas']['OpportunityCloseRequest']['basis']
const rejectReasons: Record<RejectReason, string> = { source_unverifiable: '공식 원문·접수 경로 확인 불가', out_of_scope: '지원 지역·유형 범위 밖', recruitment_closed: '이미 모집 종료', duplicate: '중복 공고', insufficient_information: '필수 정보 부족', inappropriate_content: '부적절한 내용', other: '기타 · 설명 필요' }
const closeReasons: Record<CloseBasis, string> = { source_closed: '공식 원문에서 종료 확인', deadline_passed: '접수 마감 경과 확인', organization_notice: '기관의 모집 종료 안내', report_confirmed: '신고 내용 대조 후 종료 확인', other: '기타 · 설명 필요' }
function content(value: unknown): Content {
  const item = record(value)
  if (!Array.isArray(item.requirements) || (item.required_documents !== null && !Array.isArray(item.required_documents))) return invalid()
  return { title: text(item.title, 200), description: item.description_text === null ? null : text(item.description_text, 5000), instructions: text(item.application_instructions, 2000), source: text(item.source_url, 2048), requirements: parseRequirements(item.requirements), documents: item.required_documents === null ? null : item.required_documents.map((value) => text(value, 200)) }
}
function ShowContent({ value, title }: { value: Content; title: string }) {
  const source = officialLink(value.source)
  return <section className="review-source"><h3>{title} · {value.title}</h3><p className="user-text">{value.description ?? '설명 없음'}</p><h4>조건 원문</h4><RequirementSummary items={value.requirements} /><h4>필요 서류</h4>{value.documents === null ? <p>서류 확인 필요</p> : <ul>{value.documents.map((value, index) => <li key={index}>{value}</li>)}</ul>}<h4>신청 방법</h4><p className="user-text">{value.instructions}</p>{source ? <a className="text-link" href={source.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">공식 원문 · {source.host} (새 창)</a> : <p>확인된 공식 상세 주소가 없어 승인할 수 없습니다.</p>}</section>
}
export function OpportunityReview({ id, version }: { id: string; version: number }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])
  const request = useRequest<Review>()
  const mutation = useRequest<string>()
  const [note, setNote] = useState('')
  const [checked, setChecked] = useState(false)
  const [rejectReason, setRejectReason] = useState<RejectReason | ''>('')
  const [closeBasis, setCloseBasis] = useState<CloseBasis | ''>('')
  const data = request.state.status === 'success' ? request.state.data : null
  const pending = request.state.status === 'pending' || mutation.state.status === 'pending'
  const stale = mutation.state.status === 'error' && (mutation.state.error.code === 'VERSION_CONFLICT' || mutation.state.error.code === 'INVALID_STATE_TRANSITION')
  const locked = pending || mutation.state.status === 'success' || stale
  function submit(action: 'approve' | 'hide' | 'reject' | 'close') {
    if (!data || !checked || locked) return
    if ((action === 'approve' || action === 'hide') && !note.trim()) return
    if (action === 'approve' && (data.status !== 'pending' || !officialLink(data.content.source))) return
    if (action === 'reject' && (data.status !== 'pending' || !rejectReason || (rejectReason === 'other' && !note.trim()))) return
    if (action === 'close' && (!closeBasis || (closeBasis === 'other' && !note.trim()))) return
    const selectedVersion = data.version
    void mutation.run(async (api, signal) => {
      const body = { base_version: selectedVersion, note: note.trim() }
      let response: unknown
      if (action === 'approve') response = required((await api.POST('/admin/opportunities/{opportunity_id}/approve', { signal, params: { path: { opportunity_id: id } }, body })).data)
      else if (action === 'hide') response = required((await api.POST('/admin/opportunities/{opportunity_id}/hide', { signal, params: { path: { opportunity_id: id } }, body })).data)
      else if (action === 'reject') response = required((await api.POST('/admin/opportunities/{opportunity_id}/reject', { signal, params: { path: { opportunity_id: id } }, body: { ...body, note: body.note || null, reason_code: rejectReason as RejectReason } })).data)
      else response = required((await api.POST('/admin/opportunities/{opportunity_id}/close', { signal, params: { path: { opportunity_id: id } }, body: { ...body, note: body.note || null, basis: closeBasis as CloseBasis } })).data)
      const result = record(response)
      const expected = action === 'approve' ? 'approved' : action === 'hide' ? 'hidden' : action === 'reject' ? 'rejected' : null
      if (result.id !== id || typeof result.version !== 'number' || !Number.isSafeInteger(result.version) || result.version < selectedVersion
        || (action !== 'close' && result.version !== selectedVersion)
        || !timestamp(result.reviewed_at) || typeof result.review_status !== 'string' || !['pending', 'approved', 'rejected', 'hidden'].includes(result.review_status)
        || (expected && result.review_status !== expected)) return invalid()
      return '서버가 처리를 완료했습니다. 최신 목록을 다시 조회해 주세요.'
    })
  }
  return <section className="panel"><h2 className="review-heading" ref={headingRef} tabIndex={-1}>원문·공개본 비교</h2><Button disabled={pending} onClick={() => { setChecked(false); setNote(''); setRejectReason(''); setCloseBasis(''); mutation.clear(); void request.run(async (api, signal) => {
    const result = record(required((await api.GET('/admin/opportunities/{opportunity_id}', { signal, params: { path: { opportunity_id: id } } })).data))
    if (result.id !== id || result.version !== version || typeof result.important_change !== 'boolean' || !Array.isArray(result.changed_fields)
      || typeof result.review_status !== 'string' || !['pending', 'approved', 'rejected', 'hidden'].includes(result.review_status)) return invalid()
    return { version, status: result.review_status, content: content(result.content), previous: result.published_content === null ? null : content(result.published_content), changed: result.changed_fields.map((value) => text(value, 100)), important: result.important_change }
  }) }}>선택한 버전 원문·변경 불러오기</Button>
  {request.state.status === 'error' && <RequestError error={request.state.error} />}
  {data && <><p>{data.important ? '중요 변경 검수 대기' : '중요 변경 표시 없음'} · 검토 버전 {data.version}</p><p>변경 항목: {data.changed.join(', ') || '공개본 대비 변경 항목 없음'}</p><ShowContent value={data.content} title="검토할 내용" />{data.previous && <ShowContent value={data.previous} title="현재 공개본" />}
    <TextAreaField label="공식 원문 확인 근거와 검수 메모" value={note} maxLength={500} disabled={locked} onChange={(event) => { setNote(event.target.value); setChecked(false) }} hint="승인·비공개·기타 사유에는 메모가 필요합니다. 개인정보·OTP·비밀값을 적지 마세요." />
    <CheckboxField label="공식 원문과 변경 항목을 비교해 확인했습니다." checked={checked} disabled={locked} onChange={(event) => setChecked(event.target.checked)} />
    <div className="actions"><Button disabled={locked || !checked || !note.trim() || data.status !== 'pending' || !officialLink(data.content.source)} onClick={() => submit('approve')}>검토한 버전 승인</Button><Button variant="secondary" disabled={locked || !checked || !note.trim()} onClick={() => submit('hide')}>공고 비공개</Button></div>
    {data.status === 'pending' && <fieldset><legend>검수 대기 공고 반려</legend><label htmlFor="admin-reject-reason">반려 사유</label><select id="admin-reject-reason" disabled={locked} value={rejectReason} onChange={(event) => { setRejectReason(event.target.value as RejectReason | ''); setChecked(false) }}><option value="">사유를 선택해 주세요</option>{(Object.keys(rejectReasons) as RejectReason[]).map((value) => <option key={value} value={value}>{rejectReasons[value]}</option>)}</select><p>반려한 버전은 공개되지 않습니다. 다시 수정하면 새 검수 대기 버전으로 처리해야 합니다.</p><Button variant="secondary" disabled={locked || !checked || !rejectReason || (rejectReason === 'other' && !note.trim())} onClick={() => submit('reject')}>선택한 버전 반려</Button></fieldset>}
    <fieldset><legend>모집 종료 처리</legend><label htmlFor="admin-close-basis">모집 종료 근거</label><select id="admin-close-basis" disabled={locked} value={closeBasis} onChange={(event) => { setCloseBasis(event.target.value as CloseBasis | ''); setChecked(false) }}><option value="">확인한 근거를 선택해 주세요</option>{(Object.keys(closeReasons) as CloseBasis[]).map((value) => <option key={value} value={value}>{closeReasons[value]}</option>)}</select><p>수집 실패나 일시적인 공고 누락만으로 종료 처리하지 마세요. 종료하면 새 추천에서 제외됩니다.</p><Button variant="secondary" disabled={locked || !checked || !closeBasis || (closeBasis === 'other' && !note.trim())} onClick={() => submit('close')}>확인한 공고 모집 종료</Button></fieldset>
  </>}
  {mutation.state.status === 'error' && <RequestError error={mutation.state.error} />}<p role="status">{mutation.state.status === 'success' ? mutation.state.data : ''}</p></section>
}
