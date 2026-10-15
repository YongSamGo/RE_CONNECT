import { useState } from 'react'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { invalid, record, text } from '../public-opportunities/catalog'
import { officialLink } from '../public-opportunities/detail'

type Content = { title: string; description: string | null; instructions: string; requirements: string[]; documents: string[] | null; source: string }
type Review = { version: number; status: string; content: Content; previous: Content | null; changed: string[]; important: boolean }
function content(value: unknown): Content {
  const item = record(value)
  if (!Array.isArray(item.requirements) || (item.required_documents !== null && !Array.isArray(item.required_documents))) return invalid()
  return { title: text(item.title, 200), description: item.description_text === null ? null : text(item.description_text, 5000), instructions: text(item.application_instructions, 2000), source: text(item.source_url, 2048), requirements: item.requirements.map((value) => text(record(value).source_evidence, 1000)), documents: item.required_documents === null ? null : item.required_documents.map((value) => text(value, 200)) }
}
function ShowContent({ value, title }: { value: Content; title: string }) {
  const source = officialLink(value.source)
  return <section><h3>{title} · {value.title}</h3><p className="user-text">{value.description ?? '설명 없음'}</p><h4>조건 원문</h4><ul>{value.requirements.map((value, index) => <li key={index}>{value}</li>)}</ul><h4>필요 서류</h4>{value.documents === null ? <p>서류 확인 필요</p> : <ul>{value.documents.map((value, index) => <li key={index}>{value}</li>)}</ul>}<h4>신청 방법</h4><p className="user-text">{value.instructions}</p>{source ? <a href={source.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">공식 원문 · {source.host} (새 창)</a> : <p>확인된 공식 상세 주소가 없어 승인할 수 없습니다.</p>}</section>
}
export function OpportunityReview({ id, version }: { id: string; version: number }) {
  const request = useRequest<Review>()
  const mutation = useRequest<string>()
  const [note, setNote] = useState('')
  const [checked, setChecked] = useState(false)
  const data = request.state.status === 'success' ? request.state.data : null
  const pending = request.state.status === 'pending' || mutation.state.status === 'pending'
  function submit(action: 'approve' | 'hide') {
    if (!data || !checked || !note.trim() || pending || mutation.state.status === 'success') return
    void mutation.run(async (api, signal) => {
      const body = { base_version: data!.version, note: note.trim() }
      if (action === 'approve') await api.POST('/admin/opportunities/{opportunity_id}/approve', { signal, params: { path: { opportunity_id: id } }, body })
      else await api.POST('/admin/opportunities/{opportunity_id}/hide', { signal, params: { path: { opportunity_id: id } }, body })
      return '서버가 처리를 완료했습니다. 최신 목록을 다시 조회해 주세요.'
    })
  }
  return <section className="panel"><h2>원문·공개본 비교</h2><Button disabled={pending} onClick={() => { setChecked(false); mutation.clear(); void request.run(async (api, signal) => {
    const result = record(required((await api.GET('/admin/opportunities/{opportunity_id}', { signal, params: { path: { opportunity_id: id } } })).data))
    if (result.id !== id || result.version !== version || typeof result.important_change !== 'boolean' || !Array.isArray(result.changed_fields)
      || !['pending', 'approved', 'rejected', 'hidden'].includes(String(result.review_status))) return invalid()
    return { version, status: String(result.review_status), content: content(result.content), previous: result.published_content === null ? null : content(result.published_content), changed: result.changed_fields.map((value) => text(value, 100)), important: result.important_change }
  }) }}>선택한 버전 원문·변경 불러오기</Button>
  {request.state.status === 'error' && <RequestError error={request.state.error} />}
  {data && <><p>{data.important ? '중요 변경 검수 대기' : '중요 변경 표시 없음'} · 검토 버전 {data.version}</p><p>변경 항목: {data.changed.join(', ') || '공개본 대비 변경 항목 없음'}</p><ShowContent value={data.content} title="검토할 내용" />{data.previous && <ShowContent value={data.previous} title="현재 공개본" />}
    <TextAreaField label="공식 원문 확인 근거와 검수 메모" value={note} maxLength={1000} onChange={(event) => setNote(event.target.value)} hint="개인정보·OTP·비밀값을 적지 마세요." />
    <CheckboxField label="공식 원문과 변경 항목을 비교해 확인했습니다." checked={checked} onChange={(event) => setChecked(event.target.checked)} />
    <div className="actions"><Button disabled={pending || !checked || !note.trim() || data.status !== 'pending' || !officialLink(data.content.source) || mutation.state.status === 'success'} onClick={() => submit('approve')}>검토한 버전 승인</Button><Button variant="secondary" disabled={pending || !checked || !note.trim() || mutation.state.status === 'success'} onClick={() => submit('hide')}>공고 비공개</Button></div>
  </>}
  {mutation.state.status === 'error' && <RequestError error={mutation.state.error} />}<p role="status">{mutation.state.status === 'success' ? mutation.state.data : ''}</p></section>
}
