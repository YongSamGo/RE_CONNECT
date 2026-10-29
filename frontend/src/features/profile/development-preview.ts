import type { ProfileView } from './server-model'

// Explicit development route only. Never used as a fallback for a real request.
export function createProfilePreviewFetch() {
  let revision = 1
  let draft: ProfileView['draft'] = {
    schema_version: 1,
    experiences: [{ id: '42345678-1234-1234-1234-123456789012', description: '도서관에서 책을 정리하고 방문객에게 이용 방법을 안내했습니다.', duration_note: '3년', skill_tags: ['자료 정리', '이용 안내'] }],
    skills: ['자료 정리', '이용 안내'], preferred_regions: [{ province: 'seoul', district: null }], activity_types: ['volunteering'],
    paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null,
    certifications: null, completed_courses: null, activity_constraints: null,
  }
  const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })
  return async (request: Request): Promise<Response> => {
    const path = new URL(request.url).pathname
    if (request.method === 'GET' && path.endsWith('/me')) return json({})
    if (request.method === 'GET' && path.endsWith('/profile')) return json({ revision, draft, confirmed: null, has_unconfirmed_changes: false, evidence: [], missing_for_recommendation: [] })
    if (request.method === 'PATCH' && path.endsWith('/profile')) {
      const body = await request.json() as { draft: ProfileView['draft']; base_revision: number }
      if (body.base_revision !== revision) return json({ code: 'VERSION_CONFLICT' }, 409)
      draft = { ...body.draft, experiences: body.draft.experiences.map(item => ({ ...item, id: item.id ?? crypto.randomUUID() })) }
      revision += 1
      return json({})
    }
    // Confirmation, account storage and deletion require the real service.
    return json({ code: 'SERVICE_UNAVAILABLE' }, 503)
  }
}
