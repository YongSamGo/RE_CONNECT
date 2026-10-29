// Development-only transport for viewing the real conversation component.
const draft = { schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [], paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: null, activity_constraints: null }
let revision = 1
const view = () => ({ revision, confirmed: null, has_unconfirmed_changes: false, evidence: [], missing_for_recommendation: ['experiences', 'preferred_regions', 'activity_types'], draft })
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } })

export async function previewFetch(request: Request): Promise<Response> {
  const path = new URL(request.url).pathname
  if (request.method === 'GET' && path.endsWith('/me')) return json({})
  if (request.method === 'GET' && path.endsWith('/profile')) return json(view())
  if (request.method === 'POST' && path.endsWith('/messages')) {
    revision += 1
    return json({ revision, user_message_id: '22345678-1234-1234-1234-123456789012', profile: view(), assistant_message: { message_id: '32345678-1234-1234-1234-123456789012', text: '그 일을 하면서 가장 보람 있었던 순간은 언제였나요?', created_at: '2026-10-28T00:00:00Z' }, notices: [], next_step: 'continue' })
  }
  return json({ code: 'SERVICE_UNAVAILABLE' }, 503)
}
