import type { components } from './schema'

// Contract examples from draft #117 at bc8cb82e74ad9ba361776f9c8cfe6927ae09a9ee.
// Transport tests only. They are not wired into the application as fake API data.
export const anonymousSession = {
  authenticated: false,
  user: null,
  consents: [{ purpose: 'ai_processing', notice_version: 'ai-2026-10-15', granted_at: '2026-10-15T03:00:00Z' }],
  pending_save_intent: null,
} satisfies components['schemas']['Me']

export const versionConflict = {
  code: 'VERSION_CONFLICT', message: '정보가 변경되었습니다. 최신 내용을 확인해 주세요.', request_id: 'req_01JABCDXYZ',
} satisfies components['schemas']['Error']

export const rateLimited = {
  code: 'RATE_LIMITED', message: '요청이 많습니다. 잠시 후 다시 시도해 주세요.', request_id: 'req_01JABCDXYZ',
} satisfies components['schemas']['Error']
