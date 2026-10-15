import type { Opportunity, OpportunityList } from './catalog'

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
