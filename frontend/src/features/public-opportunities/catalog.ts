import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'

export type Opportunity = components['schemas']['OpportunitySummary']
export type OpportunityList = components['schemas']['OpportunityList']
export type Province = components['schemas']['Province']
export const provinces = { seoul: '서울', gyeonggi: '경기', incheon: '인천' } satisfies Record<Province, string>
export type Search = { q: string; province: Province | ''; activity_type: Opportunity['activity_type'] | '' }

const invalid = (): never => { throw new ApiError('INVALID_RESPONSE') }
function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : invalid()
}
function text(value: unknown, max: number): string {
  return typeof value === 'string' && value.trim().length > 0 && value.length <= max ? value : invalid()
}
function integer(value: unknown, min: number): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min ? value : invalid()
}
function nullableBoolean(value: unknown): boolean | null {
  return value === null || typeof value === 'boolean' ? value : invalid()
}
function province(value: unknown): Province {
  return value === 'seoul' || value === 'gyeonggi' || value === 'incheon' ? value : invalid()
}
function date(value: unknown): string | null {
  if (value === null) return null
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return invalid()
  const parsed = new Date(`${value}T00:00:00Z`)
  return Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value ? value : invalid()
}
function timestamp(value: unknown): string | null {
  if (value === null) return null
  if (typeof value !== 'string' || !/^\d{4}-\d{2}-\d{2}T(?:[01]\d|2[0-3]):[0-5]\d:[0-5]\d(?:\.\d{1,9})?(?:Z|[+-](?:[01]\d|2[0-3]):[0-5]\d)$/.test(value)) return invalid()
  date(value.slice(0, 10))
  return Number.isFinite(Date.parse(value)) ? value : invalid()
}
function koreanDate(value: string): string {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value))
  const part = (type: string) => parts.find((item) => item.type === type)!.value
  return `${part('year')}-${part('month')}-${part('day')}`
}
function opportunity(value: unknown): Opportunity {
  const item = record(value)
  const id = text(item.id, 36)
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id)) return invalid()
  if (item.activity_type !== 'employment' && item.activity_type !== 'volunteering') return invalid()
  // Closed items violate the public-list contract. Do not silently discard them
  // while keeping a misleading total/page count from the response.
  if (item.recruitment_status !== 'open' && item.recruitment_status !== 'unknown') return invalid()
  if (typeof item.change_pending !== 'boolean') return invalid()
  const region = item.activity_region === null ? null : record(item.activity_region)
  if (region && region.district !== null && (typeof region.district !== 'string' || !/^[a-z0-9_]{2,40}$/.test(region.district))) return invalid()
  const deadline_date = date(item.deadline_date)
  const deadline_at = timestamp(item.deadline_at)
  if (deadline_date && deadline_at && deadline_date !== koreanDate(deadline_at)) return invalid()
  return {
    id, version: integer(item.version, 1), title: text(item.title, 200), organization_name: text(item.organization_name, 200),
    activity_type: item.activity_type, is_public_job: nullableBoolean(item.is_public_job),
    activity_region: region ? { province: province(region.province), district: region.district as string | null } : null,
    remote_allowed: nullableBoolean(item.remote_allowed), paid: nullableBoolean(item.paid), deadline_date, deadline_at,
    recruitment_status: item.recruitment_status, change_pending: item.change_pending,
  }
}

/** Project public-view boundary, not a replacement for the backend schema/review. */
export function parseList(value: unknown, requestedPage: number): OpportunityList {
  const list = record(value)
  const page = integer(list.page, 1)
  const page_size = integer(list.page_size, 1)
  const total = integer(list.total, 0)
  if (page !== requestedPage || page_size !== 20 || !Array.isArray(list.items) || list.items.length > page_size || total < list.items.length) return invalid()
  const items = list.items.map(opportunity)
  if (new Set(items.map((item) => item.id)).size !== items.length) return invalid()
  return { items, page, page_size, total }
}

export function deadlineLabel(item: Opportunity): string {
  if (item.deadline_at) {
    return `${new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(item.deadline_at))} 마감 (한국시간)`
  }
  return item.deadline_date ? `${item.deadline_date} 마감 · 정확한 마감 시각 확인 필요` : '마감일 확인 필요'
}

export function searchDescription(search: Search): string {
  return [search.q ? `검색어: ${search.q}` : '검색어 전체', search.province ? provinces[search.province] : '지역 전체', search.activity_type === 'employment' ? '취업·공공일자리' : search.activity_type === 'volunteering' ? '봉사' : '활동 유형 전체'].join(' · ')
}
