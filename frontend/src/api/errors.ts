import type { components } from './schema'

type ServerCode = components['schemas']['ErrorCode']
const messages = {
  UNAUTHENTICATED: [401, '로그인 후 다시 시도해 주세요.'],
  SESSION_EXPIRED: [401, '이용 시간이 만료되었습니다. 새로 시작해 주세요.'],
  FORBIDDEN: [403, '이 작업을 할 권한이 없습니다.'],
  CSRF_FAILED: [403, '요청을 확인하지 못했습니다. 화면을 새로 열어 주세요.'],
  MFA_REQUIRED: [403, '운영자 추가 인증이 필요합니다.'],
  MFA_INVALID: [403, '인증 코드를 확인해 주세요.'],
  MFA_LOCKED: [429, '인증 시도가 잠겼습니다. 잠시 후 다시 시도해 주세요.'],
  CONSENT_REQUIRED: [403, '처리 안내와 동의 상태를 확인해 주세요.'],
  REAUTH_REQUIRED: [403, '계정을 다시 인증한 후 진행해 주세요.'],
  NOT_FOUND: [404, '자료를 찾을 수 없습니다. 만료되었거나 접근할 수 없는 자료일 수 있습니다.'],
  SAVE_INTENT_NOT_FOUND: [404, '저장 대기가 만료되었거나 처리되었습니다. 저장할 내용을 다시 확인해 주세요.'],
  VERSION_CONFLICT: [409, '정보가 변경되었습니다. 최신 내용을 확인해 주세요.'],
  IDEMPOTENCY_KEY_REUSED: [409, '요청 내용이 변경되었습니다. 내용을 확인한 후 새 요청으로 진행해 주세요.'],
  REQUEST_IN_PROGRESS: [409, '이 요청을 처리하고 있습니다. 잠시 기다려 주세요.'],
  REQUEST_ALREADY_COMPLETED: [409, '이미 처리한 요청입니다. 다시 듣기는 새 요청으로 진행해 주세요.'],
  PROFILE_NOT_CONFIRMED: [409, '프로필을 직접 확인하고 확정해 주세요.'],
  PROFILE_NOT_SAVED: [409, '지원서의 근거가 되는 프로필을 먼저 저장해 주세요.'],
  DRAFT_NOT_APPROVED: [409, '지원서 내용을 확인하고 승인해 주세요.'],
  OPPORTUNITY_NOT_AVAILABLE: [409, '공고의 모집, 검수 상태가 변경되었습니다. 최신 공고를 확인해 주세요.'],
  INVALID_STATE_TRANSITION: [409, '현재 상태에서 진행할 수 없습니다. 최신 상태를 확인해 주세요.'],
  ALREADY_SIGNED_IN: [409, '이미 로그인되어 있습니다. 저장할 내용을 확인해 주세요.'],
  PAYLOAD_TOO_LARGE: [413, '입력 크기를 줄여 다시 시도해 주세요.'],
  VALIDATION_FAILED: [422, '입력 형식과 필수 항목을 확인해 주세요.'],
  RATE_LIMITED: [429, '요청이 많습니다. 잠시 후 다시 시도해 주세요.'],
  DAILY_QUOTA_EXCEEDED: [429, '오늘 이용 한도에 도달했습니다. 다음 날 다시 이용해 주세요.'],
  INFERENCE_BUSY: [429, 'AI가 다른 요청을 처리하고 있습니다. 잠시 후 다시 시도해 주세요.'],
  INTERNAL_ERROR: [500, '처리 중 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.'],
  MODEL_UNAVAILABLE: [503, '지금은 AI를 사용할 수 없습니다. 직접 입력하거나 잠시 후 다시 시도해 주세요.'],
  AI_TIMEOUT: [503, 'AI 처리 시간이 초과되었습니다. 입력을 확인하고 다시 시도해 주세요.'],
  SERVICE_UNAVAILABLE: [503, '서비스 연결이 원활하지 않습니다. 잠시 후 다시 시도해 주세요.'],
} as const satisfies Record<ServerCode, readonly [number, string]>

const localMessages = {
  NETWORK_ERROR: '연결하지 못했습니다. 연결 상태를 확인해 주세요.',
  CANCELLED: '요청을 취소했습니다.',
  TIMEOUT: '응답을 기다리는 시간이 초과되었습니다. 처리 상태를 확인해 주세요.',
  CSRF_MISSING: '요청 확인 정보가 없습니다. 화면을 새로 열어 주세요.',
  INVALID_TARGET: '허용되지 않은 요청 경로입니다.',
  INVALID_RESPONSE: '응답을 확인하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  HTTP_ERROR: '요청을 처리하지 못했습니다. 현재 상태를 확인해 주세요.',
} as const

export class ApiError extends Error {
  readonly code: ServerCode | keyof typeof localMessages
  readonly status: number | undefined
  readonly requestId: string | undefined
  readonly retryAfterSeconds: number | undefined
  constructor(code: ServerCode | keyof typeof localMessages, status?: number, requestId?: string, retryAfterSeconds?: number) {
    super(code in messages ? messages[code as ServerCode][1] : localMessages[code as keyof typeof localMessages])
    this.name = 'ApiError'
    this.code = code
    this.status = status
    this.requestId = requestId
    this.retryAfterSeconds = retryAfterSeconds
  }
}

export async function responseError(response: Response): Promise<ApiError> {
  let body: unknown
  try { body = await response.json() } catch { return new ApiError('HTTP_ERROR', response.status) }
  if (!body || typeof body !== 'object' || !('code' in body) || typeof body.code !== 'string'
    || !Object.hasOwn(messages, body.code)) return new ApiError('HTTP_ERROR', response.status)
  const code = body.code as ServerCode
  if (messages[code][0] !== response.status) return new ApiError('HTTP_ERROR', response.status)
  const requestId = 'request_id' in body && typeof body.request_id === 'string'
    && /^req_[A-Za-z0-9_-]{1,80}$/.test(body.request_id) ? body.request_id : undefined
  const header = response.headers.get('Retry-After')
  const seconds = header && /^\d{1,5}$/.test(header) ? Number(header) : undefined
  const retryAfter = (response.status === 429 || response.status === 503 || code === 'REQUEST_IN_PROGRESS')
    && code !== 'DAILY_QUOTA_EXCEEDED' && seconds !== undefined && seconds <= 86400 ? seconds : undefined
  // Neither server message, field paths/input nor the raw error body escapes.
  return new ApiError(code, response.status, requestId, retryAfter)
}
