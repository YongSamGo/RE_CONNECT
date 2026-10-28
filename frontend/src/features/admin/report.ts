import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'

export type ReportSnapshot = components['schemas']['AdminReport']
export const reportTypes = { already_closed: '이미 모집 종료', wrong_requirements: '지원 조건 오류', wrong_schedule_or_location: '일정, 장소 오류', wrong_application_method: '접수 방법 오류', broken_link: '링크 오류', other: '기타' } satisfies Record<ReportSnapshot['type'], string>
function version(value: unknown): number { return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 ? value : invalid() }
function text(value: unknown, max: number): string { return typeof value === 'string' && value.length <= max ? value : invalid() }
const nullable = (value: unknown) => value === null ? null : text(value, 500)
function id(value: unknown): string { return typeof value === 'string' && isOpportunityId(value) ? value : invalid() }
export function parseReport(value: unknown): ReportSnapshot {
  const item = record(value), opportunity = record(item.opportunity)
  if (typeof item.type !== 'string' || !Object.hasOwn(reportTypes, item.type)
    || typeof item.status !== 'string' || !['received', 'in_progress', 'resolved', 'dismissed'].includes(item.status)) return invalid()
  const created = timestamp(item.created_at), updated = timestamp(item.updated_at)
  if (!created || !updated) return invalid()
  const resolution = nullable(item.resolution_note)
  if ((item.status === 'resolved' || item.status === 'dismissed') && !resolution?.trim()) return invalid()
  return {
    report_id: id(item.report_id), version: version(item.version), opportunity: { id: id(opportunity.id), version: version(opportunity.version) },
    opportunity_title: text(item.opportunity_title, 200), type: item.type as ReportSnapshot['type'], note: nullable(item.note),
    status: item.status as ReportSnapshot['status'], resolution_note: resolution, created_at: created, updated_at: updated,
  }
}
