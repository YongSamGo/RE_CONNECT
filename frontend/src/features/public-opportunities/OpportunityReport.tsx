import { useRef, useState } from 'react'
import type { components } from '../../api/schema'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { parseSession } from '../account/session'
import { invalid, isOpportunityId, record, text, timestamp } from './catalog'

type ReportType = components['schemas']['ReportType']
const types: Record<ReportType, string> = { already_closed: '이미 모집이 끝났어요', wrong_requirements: '지원 조건이 달라요', wrong_schedule_or_location: '일정·장소가 달라요', wrong_application_method: '신청 방법이 달라요', broken_link: '공식 링크가 열리지 않아요', other: '그 밖의 오류' }

export function OpportunityReport({ id, version }: { id: string; version: number }) {
  const [type, setType] = useState<ReportType>('already_closed')
  const [note, setNote] = useState('')
  const [error, setError] = useState('')
  const request = useRequest<string>()
  const attempt = useRef<{ body: string; key: string } | null>(null)
  const pending = request.state.status === 'pending'
  async function submit() {
    if (pending) return
    if (note.length > 500) { setError('오류 설명은 500자 이내로 적어 주세요.'); return }
    if (type === 'other' && !note.trim()) { setError('그 밖의 오류를 선택했다면 설명을 적어 주세요.'); return }
    setError('')
    const body: components['schemas']['ReportCreate'] = { opportunity: { id, version }, type, note: note.trim() || null }
    const fingerprint = JSON.stringify(body)
    if (!attempt.current || attempt.current.body !== fingerprint) attempt.current = { body: fingerprint, key: crypto.randomUUID() }
    const key = attempt.current.key
    await request.run(async (api, signal) => {
      // Anonymous users also bootstrap CSRF. No AI/storage consent is recorded.
      parseSession(required((await api.GET('/me', { signal })).data))
      const receipt = record(required((await api.POST('/reports', { signal, body, params: { header: { 'Idempotency-Key': key } } })).data))
      const reportId = text(receipt.report_id, 36)
      if (!isOpportunityId(reportId) || !timestamp(receipt.received_at)) return invalid()
      return '공고 오류 신고를 접수했습니다. 운영자가 내용을 확인합니다.'
    })
  }
  return <details className="panel"><summary>공고 정보 오류 알리기</summary><p>로그인 없이 공고 오류를 알릴 수 있어요. 오류 유형과 설명만 전송하며, 개인정보는 적지 마세요.</p>
    <form onSubmit={(event) => { event.preventDefault(); void submit() }}>
      <label htmlFor="report-type">어떤 정보가 다른가요?</label><select id="report-type" value={type} disabled={pending} onChange={(event) => { setType(event.target.value as ReportType); setError(''); request.clear() }}>{(Object.keys(types) as ReportType[]).map((value) => <option key={value} value={value}>{types[value]}</option>)}</select>
      <TextAreaField label="오류 설명" value={note} maxLength={500} disabled={pending} onChange={(event) => { setNote(event.target.value); setError(''); request.clear() }} error={error} hint="그 밖의 오류는 설명이 필요해요. 이름·연락처·주민등록번호·상세 병력은 적지 마세요." />
      <Button type="submit" pending={pending} disabled={request.state.status === 'success'}>공고 오류 신고 보내기</Button>
    </form>
    {request.state.status === 'error' && <RequestError error={request.state.error} />}<p role="status">{request.state.status === 'success' ? request.state.data : ''}</p>
  </details>
}
