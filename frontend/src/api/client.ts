import createClient from 'openapi-fetch'
import type { Client } from 'openapi-fetch'
import type { paths } from './schema'
import { ApiError, responseError } from './errors'

// OAuth uses top-level navigation and state, and health is internal-only.
type BrowserPaths = Omit<paths, '/auth/kakao/start' | '/auth/kakao/callback' | '/health/live' | '/health/ready'>

export function csrfToken(cookie: string, pageUrl: string): string | undefined {
  const url = new URL(pageUrl)
  const local = url.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)
  if (url.protocol !== 'https:' && !local) return undefined
  const name = local ? 'rc_csrf' : '__Host-rc_csrf'
  const values = cookie.split(';').map((part) => part.trim()).filter((part) => part.startsWith(`${name}=`))
  if (values.length !== 1) return undefined
  const value = values[0]!.slice(name.length + 1)
  return /^[A-Za-z0-9._~+/=-]{1,4096}$/.test(value) ? value : undefined
}

type ClientOptions = {
  /** Dependency injection for transport tests, not an API origin override. */
  fetch?: (request: Request) => Promise<Response>
  timeoutMs?: number
}

export function createApiClient(options: ClientOptions = {}): Pick<Client<BrowserPaths>, 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'> {
  const origin = window.location.origin
  const send = options.fetch ?? globalThis.fetch.bind(globalThis)
  const timeoutMs = options.timeoutMs ?? 65000
  if (!Number.isInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 65000) throw new ApiError('INVALID_TARGET')

  const safeFetch = async (request: Request) => {
    const url = new URL(request.url)
    const local = window.location.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(window.location.hostname)
    const endpoint = url.pathname.slice('/api/v1'.length)
    if ((window.location.protocol !== 'https:' && !local) || url.origin !== origin
      || !url.pathname.startsWith('/api/v1/') || endpoint.startsWith('/auth/kakao/') || endpoint.startsWith('/health/')) {
      throw new ApiError('INVALID_TARGET')
    }
    const headers = new Headers(request.headers)
    headers.delete('X-CSRF-Token')
    if (request.method !== 'GET') {
      // Session rotation also rotates the cookie. Do not capture it at startup.
      const token = csrfToken(document.cookie, window.location.href)
      if (!token) throw new ApiError('CSRF_MISSING')
      headers.set('X-CSRF-Token', token)
    }
    const controller = new AbortController()
    let timedOut = false
    const cancel = () => controller.abort()
    request.signal.addEventListener('abort', cancel, { once: true })
    if (request.signal.aborted) cancel()
    const timer = setTimeout(() => { timedOut = true; controller.abort() }, timeoutMs)
    try {
      if (request.signal.aborted) throw new ApiError('CANCELLED')
      const secured = new Request(request, { headers, credentials: 'same-origin', cache: 'no-store', redirect: 'error', mode: 'same-origin', signal: controller.signal })
      const response = await send(secured)
      if (controller.signal.aborted) throw new ApiError(request.signal.aborted ? 'CANCELLED' : 'TIMEOUT')
      if (!response.ok) throw await responseError(response)
      if (response.status !== 204) {
        const contentType = response.headers.get('Content-Type')?.split(';')[0]?.trim().toLowerCase()
        if (endpoint === '/speech') {
          if (contentType !== 'audio/wav') throw new ApiError('INVALID_RESPONSE', response.status)
        } else {
          if (contentType !== 'application/json') throw new ApiError('INVALID_RESPONSE', response.status)
          // Reject invalid success JSON here so a parser exception cannot reveal
          // a server body. This is syntax checking, not runtime schema validation.
          await response.clone().json()
        }
      }
      if (controller.signal.aborted) throw new ApiError(request.signal.aborted ? 'CANCELLED' : 'TIMEOUT')
      return response
    } catch (error) {
      if (request.signal.aborted) throw new ApiError('CANCELLED')
      if (timedOut) throw new ApiError('TIMEOUT')
      if (error instanceof ApiError) throw error
      // JSON syntax errors and transport exceptions may contain sensitive text.
      throw new ApiError(error instanceof SyntaxError ? 'INVALID_RESPONSE' : 'NETWORK_ERROR')
    } finally {
      clearTimeout(timer)
      request.signal.removeEventListener('abort', cancel)
    }
  }
  const client = createClient<BrowserPaths>({ baseUrl: `${origin}/api/v1`, fetch: safeFetch })
  // Preserve endpoint/body inference while closing per-call transport and
  // middleware escape hatches. This facade owns those policies.
  function protect<T extends (...args: never[]) => unknown>(method: T): T {
    return new Proxy(method, {
      apply(target, thisArg, args: unknown[]) {
        const init = args[1]
        if (args[0] === '/speech' && (!init || typeof init !== 'object' || !('parseAs' in init) || init.parseAs !== 'blob')) {
          return Promise.reject(new ApiError('INVALID_TARGET'))
        }
        if (init && typeof init === 'object' && ('fetch' in init || 'Request' in init || 'middleware' in init)) {
          return Promise.reject(new ApiError('INVALID_TARGET'))
        }
        return Reflect.apply(target, thisArg, args)
      },
    })
  }
  return { GET: protect(client.GET), POST: protect(client.POST), PUT: protect(client.PUT), PATCH: protect(client.PATCH), DELETE: protect(client.DELETE) }
}
