import { afterEach, describe, expect, it, vi } from 'vitest'
import { createApiClient, csrfToken } from './client'
import { ApiError } from './errors'
import { anonymousSession, rateLimited, versionConflict } from './fixtures'

const json = (body: unknown, status = 200, headers?: HeadersInit) => new Response(JSON.stringify(body), {
  status, headers: { 'Content-Type': 'application/json', ...headers },
})
function sessionCookie(value = 'signed-token') { document.cookie = `__Host-rc_csrf=${value}; Path=/; Secure; SameSite=Strict` }
afterEach(() => {
  document.cookie = '__Host-rc_csrf=; Max-Age=0; Path=/; Secure'
  vi.restoreAllMocks()
  vi.useRealTimers()
})

describe('contract transport', () => {
  it('does not start a session or make a network request on construction', () => {
    const fetch = vi.fn()
    createApiClient({ fetch })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('uses the same-origin API prefix, disables cache and redirects, and returns the typed contract example', async () => {
    const fetch = vi.fn(async (_request: Request) => json(anonymousSession))
    const api = createApiClient({ fetch })
    const result = await api.GET('/me', { credentials: 'include', cache: 'force-cache', redirect: 'follow' })
    expect(result.data).toEqual(anonymousSession)
    const request = fetch.mock.calls[0]![0]
    expect(request.url).toBe('https://reconnect.test/api/v1/me')
    expect(request.credentials).toBe('same-origin')
    expect(request.cache).toBe('no-store')
    expect(request.redirect).toBe('error')
    expect(request.mode).toBe('same-origin')
    expect(request.headers.has('X-CSRF-Token')).toBe(false)
  })
  it('reads the CSRF cookie anew for every mutation and replaces any caller header', async () => {
    const requests: Request[] = []
    const fetch = vi.fn(async (request: Request) => { requests.push(request); return new Response(null, { status: 204 }) })
    const api = createApiClient({ fetch })
    sessionCookie('first-signature')
    await api.POST('/auth/logout', { headers: { 'X-CSRF-Token': 'old-header' } })
    sessionCookie('rotated-signature')
    await api.POST('/auth/logout')
    expect(requests.map((request) => request.headers.get('X-CSRF-Token'))).toEqual(['first-signature', 'rotated-signature'])
  })
  it('does not send mutations without a valid CSRF cookie or bootstrap behind the user’s back', async () => {
    const fetch = vi.fn()
    const api = createApiClient({ fetch })
    await expect(api.POST('/auth/logout')).rejects.toMatchObject({ code: 'CSRF_MISSING' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each(['https://external.test/api/v1', 'https://reconnect.test/internal'])('rejects a base URL override %s before sending cookies or input', async (baseUrl) => {
    const fetch = vi.fn()
    await expect(createApiClient({ fetch }).GET('/me', { baseUrl })).rejects.toMatchObject({ code: 'INVALID_TARGET' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('serializes query values rather than allowing them to add new parameters', async () => {
    const fetch = vi.fn(async (_request: Request) => json({ items: [], page: 1, page_size: 20, total: 0 }))
    await createApiClient({ fetch }).GET('/opportunities', { params: { query: { q: '책&role=operator' } } })
    const request = fetch.mock.calls[0]![0]
    const url = new URL(request.url)
    expect(url.searchParams.get('q')).toBe('책&role=operator')
    expect(url.searchParams.has('role')).toBe(false)
  })
  it('returns no data for 204 without trying to parse JSON', async () => {
    sessionCookie()
    const result = await createApiClient({ fetch: async () => new Response(null, { status: 204 }) }).POST('/auth/logout')
    expect(result.data).toBeUndefined()
  })
  it.each(['fetch', 'Request', 'middleware'])('does not allow the %s extension to bypass transport policy', async (extension) => {
    const fetch = vi.fn()
    const override = vi.fn()
    await expect(createApiClient({ fetch }).GET('/me', { [extension]: override })).rejects.toMatchObject({ code: 'INVALID_TARGET' })
    expect(fetch).not.toHaveBeenCalled()
    expect(override).not.toHaveBeenCalled()
  })
  it('accepts WAV only for speech and leaves binary decoding to parseAs blob', async () => {
    sessionCookie()
    const fetch = vi.fn(async () => new Response('test-wave-bytes', { headers: { 'Content-Type': 'audio/wav' } }))
    const speechOptions = {
      params: { header: { 'Idempotency-Key': crypto.randomUUID() } },
      body: { target: { kind: 'opportunity', opportunity_id: crypto.randomUUID(), version: 1, field: 'title' }, segment: 0 },
      parseAs: 'blob' as const,
    } as const
    const response = await createApiClient({ fetch }).POST<'/speech', typeof speechOptions>('/speech', speechOptions)
    expect(response.data?.size).toBe(15)
    expect(response.data?.type).toBe('audio/wav')
  })
  it('refuses speech without explicit binary parsing before sending a request', async () => {
    const fetch = vi.fn()
    await expect(createApiClient({ fetch }).POST('/speech', {
      params: { header: { 'Idempotency-Key': crypto.randomUUID() } },
      body: { target: { kind: 'opportunity', opportunity_id: crypto.randomUUID(), version: 1, field: 'title' }, segment: 0 },
    })).rejects.toMatchObject({ code: 'INVALID_TARGET' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('rejects an unexpected JSON success body for speech', async () => {
    sessionCookie()
    await expect(createApiClient({ fetch: async () => json({ message: 'private' }) }).POST('/speech', {
      params: { header: { 'Idempotency-Key': crypto.randomUUID() } },
      body: { target: { kind: 'opportunity', opportunity_id: crypto.randomUUID(), version: 1, field: 'title' }, segment: 0 },
      parseAs: 'blob',
    })).rejects.toMatchObject({ code: 'INVALID_RESPONSE' })
  })
  it.each([
    [409, versionConflict, 'VERSION_CONFLICT'],
    [429, rateLimited, 'RATE_LIMITED'],
    [422, { code: 'VALIDATION_FAILED', message: 'private', request_id: 'req_test', fields: [{ path: 'private', reason: 'required' }] }, 'VALIDATION_FAILED'],
  ])('maps %s errors to fixed messages, never raw message/input, and never retries automatically', async (status, body, code) => {
    const fetch = vi.fn(async () => json({ ...body, message: 'private-input-server-path' }, status, { 'Retry-After': '30' }))
    const error = await createApiClient({ fetch }).GET('/me').catch((failure: unknown) => failure)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ code, status })
    expect(JSON.stringify(error)).not.toContain('private')
    expect(String(error)).not.toContain('private')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it.each([
    ['RATE_LIMITED', '30', 30], ['DAILY_QUOTA_EXCEEDED', '30', undefined],
    ['INFERENCE_BUSY', 'NaN', undefined], ['MFA_LOCKED', '900', 900],
    ['RATE_LIMITED', '-1', undefined], ['RATE_LIMITED', '99999', undefined],
  ])('handles quota %s with Retry-After %s', async (code, header, expected) => {
    const error = await createApiClient({ fetch: async () => json({ ...rateLimited, code }, 429, { 'Retry-After': header }) }).GET('/me').catch((e: unknown) => e)
    expect(error).toMatchObject({ code, retryAfterSeconds: expected })
  })
  it.each([
    new Response('<html>private-proxy-error</html>', { status: 502 }),
    json({ code: 'UNKNOWN-private', message: 'private' }, 500),
    json({ ...versionConflict, request_id: 'private' }, 429),
  ])('does not expose malformed errors or status/code mismatches', async (response) => {
    const error = await createApiClient({ fetch: async () => response }).GET('/me').catch((e: unknown) => e)
    expect(error).toMatchObject({ code: 'HTTP_ERROR' })
    expect(String(error)).not.toContain('private')
  })
  it.each([
    new Response('private-json', { headers: { 'Content-Type': 'application/json' } }),
    new Response('<html>private</html>', { headers: { 'Content-Type': 'text/html' } }),
  ])('rejects malformed successful JSON and HTML fallback without exposing its content', async (response) => {
    const error = await createApiClient({ fetch: async () => response }).GET('/me').catch((e: unknown) => e)
    expect(error).toMatchObject({ code: 'INVALID_RESPONSE' })
    expect(String(error)).not.toContain('private')
  })
  it('redacts transport errors and sends no data to persistent browser storage', async () => {
    const store = vi.spyOn(Storage.prototype, 'setItem')
    await expect(createApiClient({ fetch: async () => { throw new Error('private-cookie-and-path') } }).GET('/me')).rejects.toMatchObject({ code: 'NETWORK_ERROR' })
    expect(store).not.toHaveBeenCalled()
  })
  it('does not send an already cancelled request', async () => {
    const controller = new AbortController()
    controller.abort()
    const fetch = vi.fn()
    await expect(createApiClient({ fetch }).GET('/me', { signal: controller.signal })).rejects.toMatchObject({ code: 'CANCELLED' })
    expect(fetch).not.toHaveBeenCalled()
  })
  it('discards a late successful response when the caller cancelled the request', async () => {
    const controller = new AbortController()
    const fetch = async () => { controller.abort(); return json(anonymousSession) }
    await expect(createApiClient({ fetch }).GET('/me', { signal: controller.signal })).rejects.toMatchObject({ code: 'CANCELLED' })
  })
  it('times out without retry and discards a late result even if the transport ignores abort', async () => {
    vi.useFakeTimers()
    const fetch = vi.fn(async () => { await new Promise((resolve) => setTimeout(resolve, 20)); return json(anonymousSession) })
    const request = createApiClient({ fetch, timeoutMs: 10 }).GET('/me')
    const assertion = expect(request).rejects.toMatchObject({ code: 'TIMEOUT' })
    await vi.advanceTimersByTimeAsync(20)
    await assertion
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('CSRF cookie selection', () => {
  it.each([
    ['__Host-rc_csrf=signed; rc_csrf=dev', 'https://example.test', 'signed'],
    ['rc_csrf=dev', 'https://example.test', undefined],
    ['rc_csrf=dev', 'http://127.0.0.1:5173', 'dev'],
    ['rc_csrf=dev', 'http://[::1]:5173', 'dev'],
    ['rc_csrf=dev', 'http://public.example', undefined],
    ['__Host-rc_csrf=a; __Host-rc_csrf=b', 'https://example.test', undefined],
    ['__Host-rc_csrf=a%0D%0Asecret', 'https://example.test', undefined],
    ['__Host-rc_csrf=', 'https://example.test', undefined],
  ])('selects the correct cookie and refuses ambiguous or unsafe values (%s, %s)', (cookie, url, expected) => {
    expect(csrfToken(cookie, url)).toBe(expected)
  })
})
