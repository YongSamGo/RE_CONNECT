import type { Opportunity, OpportunityList } from './catalog'
import type { components } from '../../api/schema'

// Synthetic contract-shaped data for unit tests only; never imported by the app.
export function sampleOpportunity(changes: Partial<Opportunity> = {}): Opportunity {
  return {
    id: '12345678-1234-1234-1234-123456789001', version: 1,
    title: '가상 도서 정리 봉사', organization_name: '시험용 가상 기관', activity_type: 'volunteering',
    is_public_job: false, activity_region: { province: 'seoul', district: null }, remote_allowed: null,
    paid: null, deadline_date: '2026-10-30', deadline_at: null, recruitment_status: 'open', change_pending: false,
    ...changes,
  }
}
export function sampleList(changes: Partial<OpportunityList> = {}): OpportunityList {
  return { items: [sampleOpportunity()], page: 1, page_size: 20, total: 1, ...changes }
}

export const sourceUrl = 'https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=1234567'
export function sampleDetail(changes: Partial<components['schemas']['Opportunity']> = {}): components['schemas']['Opportunity'] {
  return {
    ...sampleOpportunity(), role_tags: [], skill_tags: [], location_text: null, schedule_text: null,
    hours_per_week: null, compensation_text: null, description_text: null, description_truncated: false,
    requirements: [], required_documents: null, application_method: 'online', application_instructions: '공식 안내에서 확인하세요.',
    source_url: sourceUrl, application_url: sourceUrl, source_checked_at: '2026-10-14T23:30:00Z', reviewed_at: '2026-10-15T09:00:00+09:00',
    ...changes,
  }
}
