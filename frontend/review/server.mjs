import { createServer } from 'vite'
import { randomUUID } from 'node:crypto'

// Loopback-only review fixtures. This middleware never forwards API requests.
const J = '12345678-1234-1234-1234-123456789012'
const O = '12345678-1234-1234-1234-123456789001'
const E = '12345678-1234-1234-1234-123456789002'
const D = '12345678-1234-1234-1234-123456789003'
const U = '12345678-1234-1234-1234-123456789004'
const I = '12345678-1234-1234-1234-123456789005'
const now = () => new Date().toISOString()
const future = () => new Date(Date.now() + 3600000).toISOString()
const states = new Set(['normal', 'empty', 'loading', 'failure', 'expired', 'closed', 'changed'])
const routes = {
  home: '/', start: '/start', conversation: '/dev/conversation', profile: `/journeys/${J}/profile`,
  recommendations: `/journeys/${J}/recommendations`, filter: '/opportunities', catalog: '/opportunities?browse=all',
  detail: `/opportunities/${O}`, application: `/journeys/${J}/opportunities/${O}/application`,
  save: '/me/save', member: '/me', story: '/me', drafts: '/me', settings: '/me', auth: '/me', login: '/login', guide: '/guide',
}
const sessions = new Map()
function fixture(screen = 'member', state = 'normal') {
  return { screen, state, authenticated: true, saved: state !== 'empty', documents: state !== 'empty',
    revision: 1, consent: true, pending: true, profileChanged: false,
    content: { schema_version: 1, experiences: [{ id: E, description: '도서관에서 책을 정리하고 방문객을 안내했습니다.', duration_note: '3년', skill_tags: ['자료 정리', '이용 안내'] }],
      skills: ['자료 정리', '이용 안내'], preferred_regions: [{ province: 'seoul', district: null }], activity_types: ['volunteering'],
      paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null,
      birth_year: null, certifications: null, completed_courses: null, activity_constraints: null },
    draft: { draft_id: D, revision: 1, mode: 'generate', profile_version: 1, opportunity: { id: O, version: 1 },
      self_introduction: '도서관에서 3년 동안 책을 정리하고 방문객을 안내했습니다. 자료를 분류하고 이용자의 질문에 응대해 온 경험이 있습니다.',
      motivation: '책 정리와 방문객 안내 경험을 살려 도서관 봉사에 참여하고 싶습니다. 이용자들이 필요한 자료를 편하게 찾을 수 있도록 돕겠습니다.',
      approved_at: null, review_reasons: [], warnings: ['예시 초안입니다. 실제 AI 생성 결과가 아닙니다.'] },
  }
}
function opportunity(s, index = 0) {
  return { id: index ? `12345678-1234-1234-1234-${String(123456789001 + index)}` : O, version: 1,
    title: ['도서관 자료 정리 봉사', '문화센터 방문객 안내', '마을 기록 정리 봉사'][index], organization_name: '화면 확인용 예시 기관',
    activity_type: 'volunteering', is_public_job: false, activity_region: { province: 'seoul', district: null },
    remote_allowed: false, paid: false, deadline_date: null, deadline_at: null,
    recruitment_status: s.state === 'closed' ? 'closed' : 'open', change_pending: s.state === 'changed' }
}
function profile(s) {
  const empty = s.state === 'empty' && s.screen === 'profile'
  return { revision: s.revision, confirmed: empty ? null : { version: 1, confirmed_at: now() }, has_unconfirmed_changes: s.profileChanged,
    missing_for_recommendation: empty ? ['experiences', 'preferred_regions', 'activity_types'] : [], evidence: [],
    draft: empty ? { ...s.content, experiences: [], skills: [], preferred_regions: [], activity_types: [] } : s.content }
}
function me(s) { return { authenticated: s.authenticated, user: s.authenticated ? { id: U, roles: ['user'], mfa_verified: false, reauth_until: null } : null,
  consents: s.consent ? ['ai_processing', 'storage'].map(purpose => ({ purpose, notice_version: `review-${purpose === 'storage' ? 'storage' : 'ai'}`, granted_at: now() })) : [],
  pending_save_intent: s.pending && s.state !== 'empty' ? { save_intent_id: I, expires_at: future(), targets: { profile: true, draft: true }, existing_saved_profile_version: s.saved ? 1 : null } : null } }
function notice(version, title) { return { version, title, controller: '개발 화면 검수', contact: '예시 문의처', aws_region: '예시 리전', body: '검수용 예시 안내입니다. 실제 동의나 개인정보 저장을 수행하지 않습니다.', retention: '검수 서버 메모리에서만 유지합니다.', deletion: '서버 종료 시 삭제합니다.' } }
function json(res, value, status = 200) { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store' }); res.end(JSON.stringify(value)) }
function error(res, code, status) { json(res, { code, message: '개발 검수용 상태입니다.' }, status) }
async function body(req) { let data = ''; for await (const chunk of req) { data += chunk; if (data.length > 100000) throw new Error('Request too large') } return data ? JSON.parse(data) : {} }
const plugin = {
  name: 'local-screen-review',
  transformIndexHtml(html, ctx) {
    const auto = ctx.originalUrl?.includes('/application') ? `<script>history.replaceState({...history.state,usr:{generateDraft:true}},'')</script>` : ''
    return html.replace('<body>', `<body><aside style="padding:8px 20px;background:#173e50;color:white;font:16px sans-serif;display:flex;gap:20px;flex-wrap:wrap"><strong>개발 검수용 예시 자료</strong><span>실제 AI 생성이나 자료 저장이 아닙니다.</span><a href="/dev/screens" style="color:white">화면 목록으로</a></aside>${auto}`)
  },
  configureServer(server) {
    server.middlewares.use(async (req, res, next) => {
      const url = new URL(req.url, 'http://127.0.0.1:5190')
      if (url.pathname === '/__review/open') {
        const screen = url.searchParams.get('screen'), state = url.searchParams.get('state')
        if (!Object.hasOwn(routes, screen) || !states.has(state)) return error(res, 'INVALID_REQUEST', 400)
        if (sessions.size > 200) sessions.clear()
        const id = randomUUID(); sessions.set(id, fixture(screen, state))
        res.writeHead(303, { Location: routes[screen], 'Set-Cookie': [`rc_review=${id}; Path=/; HttpOnly; SameSite=Strict`, 'rc_csrf=review-token; Path=/; SameSite=Strict'], 'Cache-Control': 'no-store' }); res.end(); return
      }
      if (!url.pathname.startsWith('/api/')) return next()
      const cookie = /(?:^|;\s*)rc_review=([a-f0-9-]+)/.exec(req.headers.cookie ?? '')?.[1]
      const s = sessions.get(cookie) ?? fixture()
      const p = url.pathname.replace(/^\/api\/v1/, ''), method = req.method
      const targeted = p !== '/me' || ['member', 'settings', 'auth', 'save'].includes(s.screen)
      if (targeted && s.state === 'loading') { const timer = setTimeout(() => error(res, 'AI_TIMEOUT', 503), 60000); res.on('close', () => clearTimeout(timer)); return }
      if (targeted && s.state === 'failure') return error(res, 'SERVICE_UNAVAILABLE', 503)
      if (targeted && s.state === 'expired') return error(res, 'SESSION_EXPIRED', 401)
      try {
        const data = ['POST', 'PATCH', 'PUT'].includes(method) ? await body(req) : {}
        if (p === '/me' && method === 'GET') return json(res, me(s))
        if (p === '/consents/notices') return json(res, { ai_processing: notice('review-ai', 'AI 이용 안내'), storage: notice('review-storage', '회원 저장 안내'), login_available: false })
        if (p === '/consents') { s.consent = method !== 'DELETE'; return json(res, {}) }
        if (p === '/auth/logout' || p === '/me' && method === 'DELETE') { s.authenticated = false; res.writeHead(204); res.end(); return }
        if (p.startsWith('/auth/kakao')) return error(res, 'LOGIN_UNAVAILABLE', 503)
        if (p === '/regions') return json(res, { version: 'review-v1', provinces: [{ id: 'seoul', name: '서울', districts: [{ id: 'mapo', name: '마포구' }] }, { id: 'gyeonggi', name: '경기', districts: [] }, { id: 'incheon', name: '인천', districts: [] }] })
        if (p === '/journeys' && method === 'POST') return json(res, { journey_id: J, revision: 1, confirmed: data.source ? profile(s).confirmed : null, expires_at: future(), idle_expires_at: future() }, 201)
        if (/\/profile\/confirm$/.test(p)) { s.profileChanged = false; return json(res, profile(s)) }
        if (/\/profile$/.test(p)) { if (method === 'PATCH') { s.content = data.draft; s.revision++; s.profileChanged = true } return json(res, profile(s)) }
        if (/\/role-exclusions$/.test(p)) return json(res, { role_ids: [], revision: s.revision })
        if (/\/roles$/.test(p)) return json(res, { revision: s.revision, profile_version: 1, items: [{ role_id: 'library_assistant', name: '자료 정리 도우미', description: '자료 정리 경험을 살릴 수 있어요.', excluded: false, evidence: [{ experience_id: E, skill_tags: ['자료 정리'] }] }] })
        if (p === '/recommendations') return json(res, { profile: data.profile, generated_at: now(), based_on_previous_confirmed: false,
          items: ['empty', 'closed', 'changed'].includes(s.state) ? [] : [0, 1, 2].map((i) => ({ rank: i + 1, opportunity: opportunity(s, i), matched: { experience_ids: [E], skill_tags: ['자료 정리'], keywords: ['도서관'], role_ids: ['library_assistant'] }, eligibility: { overall: 'satisfied', no_requirements: true, needs_review_count: 0 } })) })
        if (/\/eligibility$/.test(p)) return json(res, { profile: data.profile, opportunity: { id: O, version: 1 }, evaluated_at: now(), overall: 'satisfied', no_requirements: true, conditions: [], groups: [] })
        const official = 'https://www.1365.go.kr/vols/P9210/partcptn/timeCptn.do?type=show&progrmRegistNo=123456'
        const selected = { ...opportunity(s), id: p.split('/')[2] }
        if (/^\/opportunities\/[^/]+\/preparation$/.test(p)) return json(res, { opportunity: { id: selected.id, version: 1 }, ...selected, application_method: 'online', application_instructions: '공식 사이트에서 신청 방법을 확인해 주세요.', application_url: official, source_url: official, required_documents: ['지원서'], deadline_date: null, deadline_at: null })
        if (p === '/opportunities') { const items = s.state === 'empty' || s.state === 'closed' ? [] : [0, 1, 2].map(i => opportunity(s, i)); return json(res, { items, page: Number(url.searchParams.get('page') ?? 1), page_size: 20, total: items.length }) }
        if (/^\/opportunities\/[^/]+$/.test(p)) return json(res, { ...selected, role_tags: [], skill_tags: ['자료 정리'], location_text: '서울 지역 도서관', schedule_text: '주 2회, 오전', hours_per_week: 4, compensation_text: null, description_text: '도서관 자료를 정리하고 방문객의 이용을 안내하는 활동입니다.', description_truncated: false, requirements: [], required_documents: ['지원서'], application_method: 'online', application_instructions: '공식 안내에서 신청 방법을 확인해 주세요.', source_url: official, application_url: official, source_checked_at: now(), reviewed_at: now() })
        if (/\/journeys\/[^/]+\/drafts/.test(p)) {
          if (['closed', 'changed'].includes(s.state)) return error(res, 'OPPORTUNITY_NOT_AVAILABLE', 409)
          if (method === 'POST' && p.endsWith('/drafts')) s.draft = { ...s.draft, mode: data.mode ?? 'generate', opportunity: data.opportunity ?? s.draft.opportunity }
          if (method === 'PATCH') s.draft = { ...s.draft, self_introduction: data.self_introduction, motivation: data.motivation, revision: s.draft.revision + 1, approved_at: null }
          if (p.endsWith('/approve')) s.draft = { ...s.draft, approved_at: now(), revision: s.draft.revision + 1 }
          return json(res, s.draft)
        }
        if (p === '/profiles/me/versions') { s.saved = true; return json(res, { version: 1, created: true, saved_at: now(), replaced_version: null }) }
        if (p === '/profiles/me') { if (method === 'DELETE') { s.saved = false; s.documents = false; res.writeHead(204); res.end(); return } return json(res, { saved: s.saved ? { profile_id: U, version: 1, saved_at: now(), confirmed_at: now(), content: s.content } : null }) }
        if (p === '/drafts' && method === 'GET') return json(res, { page: 1, total: s.documents ? 1 : 0, items: s.documents ? [{ document_id: D, opportunity_title: '도서관 자료 정리 봉사', version: 1 }] : [] })
        if (p === '/drafts' && method === 'POST') { s.documents = true; return json(res, { document_id: D, profile_version: 1, version: 1, saved_at: now() }) }
        if (/^\/drafts\/[^/]+$/.test(p)) { if (method === 'DELETE') { s.documents = false; res.writeHead(204); res.end(); return } return json(res, { ...s.draft, document_id: D, version: 1, opportunity_title: '도서관 자료 정리 봉사' }) }
        if (p.startsWith('/auth/save-intents')) { s.pending = method !== 'DELETE'; if (method === 'DELETE') { res.writeHead(204); res.end(); return } return json(res, { save_intent_id: I, expires_at: future(), targets: { profile: true, draft: true }, existing_saved_profile_version: 1 }) }
        return error(res, 'REVIEW_ENDPOINT_NOT_AVAILABLE', 503)
      } catch { return error(res, 'INVALID_REQUEST', 400) }
    })
  },
}
const server = await createServer({ plugins: [plugin], server: { host: '127.0.0.1', port: 5190, strictPort: true, proxy: {} } })
await server.listen()
console.log('개발 화면 확인: http://127.0.0.1:5190/dev/screens')
