import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, text, timestamp } from '../public-opportunities/catalog'

type Event = components['schemas']['AuditEvent']
export const auditActions = {
  'opportunity.create': '공고 등록', 'opportunity.update': '공고 수정', 'opportunity.approve': '공고 승인',
  'opportunity.reject': '공고 반려', 'opportunity.hide': '공고 비공개', 'opportunity.close': '모집 종료',
  'report.update': '신고 처리', 'mfa.verify': '추가 인증 성공', 'mfa.fail': '추가 인증 실패',
  'mfa.lock': '추가 인증 잠금', 'mfa.enroll': '추가 인증 등록', 'mfa.reset': '추가 인증 초기화', 'role.grant': '권한 부여', 'role.revoke': '권한 회수', 'access.denied': '접근 거부',
} satisfies Record<Event['action'], string>
export type AuditRange = { from: string; to: string }
export type AuditRow = Pick<Event, 'event_id' | 'at' | 'action' | 'actor_role' | 'result' | 'target_type' | 'request_id'>
export type AuditPage = { rows: AuditRow[]; page: number; total: number; range: AuditRange }
export const auditPageSize = 20

/** Inputs are explicitly Korea time, independent of the browser's OS timezone. */
export function auditRange(from: string, to: string): AuditRange | null {
  const format = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/
  if (!format.test(from) || !format.test(to)) return null
  try {
    const start = timestamp(`${from}:00+09:00`)
    const end = timestamp(`${to}:00+09:00`)
    if (!start || !end) return null
    const duration = Date.parse(end) - Date.parse(start)
    return duration > 0 && duration <= 30 * 24 * 60 * 60 * 1000 ? { from: start, to: end } : null
  } catch { return null }
}
export function koreaDateTimeInput(time: number): string {
  return new Date(time + 9 * 60 * 60 * 1000).toISOString().slice(0, 16)
}
export function parseAudit(value: unknown, requestedPage: number, range: AuditRange): AuditPage {
  const data = record(value)
  if (data.page !== requestedPage || data.page_size !== auditPageSize || typeof data.total !== 'number'
    || !Number.isSafeInteger(data.total) || data.total < 0 || !Array.isArray(data.items) || data.items.length > auditPageSize || data.total < data.items.length) return invalid()
  const rows = data.items.map((value): AuditRow => {
    const event = record(value)
    const id = text(event.event_id, 36)
    const at = timestamp(event.at)
    const requestId = text(event.request_id, 84)
    if (!isOpportunityId(id) || !at || Date.parse(at) < Date.parse(range.from) || Date.parse(at) > Date.parse(range.to)
      || typeof event.action !== 'string' || !Object.hasOwn(auditActions, event.action)
      || typeof event.actor_role !== 'string' || !['operator', 'user', 'system'].includes(event.actor_role)
      || typeof event.result !== 'string' || !['success', 'denied', 'failed'].includes(event.result)
      || (event.target_type !== null && (typeof event.target_type !== 'string' || !['opportunity', 'report', 'user'].includes(event.target_type)))
      || !/^req_[A-Za-z0-9_-]{1,80}$/.test(requestId)) return invalid()
    // Deliberately omit actor/target IDs and every unknown field, including bodies.
    return { event_id: id, at, action: event.action as Event['action'], actor_role: event.actor_role as Event['actor_role'], result: event.result as Event['result'], target_type: event.target_type as Event['target_type'], request_id: requestId }
  })
  if (new Set(rows.map((row) => row.event_id)).size !== rows.length) return invalid()
  return { rows, page: requestedPage, total: data.total, range }
}
