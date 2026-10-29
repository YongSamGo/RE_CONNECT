import type { Page } from '@playwright/test'
import { sampleDetail, sampleList } from '../src/features/public-opportunities/test-fixtures'

export const journeyId = '22345678-1234-4234-9234-123456789012'
const experienceId = '32345678-1234-4234-9234-123456789012'
const draftId = '42345678-1234-4234-9234-123456789012'
const stamp = '2026-10-18T00:00:00Z'
const notice = { version: 'fixture-ai', title: '가상 AI 처리 안내', controller: '가상 운영 주체', contact: '시험 문의처', aws_region: '시험 리전', body: '화면 검사용 안내입니다.', retention: '체험 동안 보관', deletion: '만료 후 삭제' }
export const sampleId = sampleDetail().id

// Browser fixtures exercise the real UI and request contracts without a live AI,
// identity provider, or any user data. Unexpected endpoints fail visibly.
export async function mockServiceApi(page: Page, member = false) {
  let granted = false, revision = 1, complete = false, confirmed = false
  let application = { draft_id: draftId, revision: 1, mode: 'generate', profile_version: 1, opportunity: { id: sampleId, version: 1 }, self_introduction: '도서관에서 책을 정리하고 방문객을 안내한 경험이 있습니다.', motivation: '경험을 살려 도서관 봉사에 참여하고 싶습니다.', approved_at: null as string | null, review_reasons: [], warnings: [] }
  const profile = () => ({ revision, confirmed: confirmed ? { version: 1, confirmed_at: stamp } : null, has_unconfirmed_changes: false, missing_for_recommendation: complete ? [] : ['experiences','preferred_regions','activity_types'], evidence: [], draft: {
    schema_version: 1, experiences: complete ? [{ id: experienceId, description: '도서관에서 책을 정리하고 방문객을 안내했습니다.', duration_note: '3년', skill_tags: ['자료 정리'] }] : [], skills: [], preferred_regions: complete ? [{ province: 'seoul', district: null }] : [], activity_types: complete ? ['volunteering'] : [], paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: [], activity_constraints: null,
  } })
  await page.context().addCookies([{ name: 'rc_csrf', value: 'browser-fixture', url: 'http://127.0.0.1:5178' }])
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname
    let data: unknown
    let status = 200
    if (path === '/api/v1/me') data = { authenticated: member, user: member ? { id: journeyId, roles: ['user'], mfa_verified: false, reauth_until: null } : null, pending_save_intent: null, consents: granted ? [{ purpose: 'ai_processing', notice_version: notice.version, granted_at: stamp }] : [] }
    else if (path === '/api/v1/profiles/me') data = { saved: null }
    else if (path === '/api/v1/consents/notices') data = { ai_processing: notice, storage: null, login_available: false }
    else if (path === '/api/v1/consents') { granted = true; status = 201; data = { purpose: 'ai_processing', notice_version: notice.version, granted_at: stamp } }
    else if (path === '/api/v1/journeys') { status = 201; data = { journey_id: journeyId, revision: 1, confirmed: null, expires_at: new Date(Date.now()+7200000).toISOString(), idle_expires_at: new Date(Date.now()+1800000).toISOString() } }
    else if (path.endsWith('/messages')) { complete = true; revision++; data = { revision, user_message_id: experienceId, profile: profile(), assistant_message: null, notices: [], next_step: 'review_profile' } }
    else if (path.endsWith('/profile/confirm')) { confirmed = true; revision++; data = {} }
    else if (path.endsWith('/profile')) data = profile()
    else if (path.endsWith('/role-exclusions')) data = { revision, role_ids: [] }
    else if (path.endsWith('/roles')) data = { revision, profile_version: 1, items: [] }
    else if (path === '/api/v1/recommendations') data = { profile: { kind: 'journey', id: journeyId, version: 1 }, generated_at: stamp, based_on_previous_confirmed: false, items: [{ rank: 1, opportunity: sampleDetail(), matched: { experience_ids: [experienceId], skill_tags: ['자료 정리'], keywords: [], role_ids: [] }, eligibility: { overall: 'satisfied', no_requirements: true, needs_review_count: 0 } }] }
    else if (path.endsWith('/preparation')) data = { opportunity: { id: sampleId, version: 1 }, application_method: 'online', application_instructions: '공식 신청처에서 접수해 주세요.', application_url: sampleDetail().application_url, source_url: sampleDetail().source_url, required_documents: [], deadline_date: null, deadline_at: null, recruitment_status: 'open', change_pending: false }
    else if (path.endsWith('/drafts') && request.method() === 'POST') { status = 201; data = application }
    else if (path.endsWith('/approve')) { application = { ...application, revision: application.revision+1, approved_at: stamp }; data = application }
    else if (path.endsWith(draftId)) { if (request.method() === 'PATCH') { const body=request.postDataJSON(); application={...application,revision:application.revision+1,self_introduction:body.self_introduction,motivation:body.motivation} } data=application }
    else if (path === '/api/v1/opportunities') data=sampleList()
    else if (path === `/api/v1/opportunities/${sampleId}`) data=sampleDetail()
    else { status=404; data={code:'NOT_FOUND'} }
    await route.fulfill({status,json:data})
  })
}
