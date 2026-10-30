import { useRef, useState } from 'react'
import { createApiClient } from '../api/client'
import { ApiError } from '../api/errors'
import { useMemoryScope } from './useMemoryScope'
import { previewFetch } from '../features/conversation/development-preview'
import { createProfilePreviewFetch } from '../features/profile/development-preview'

type State<T> = { status: 'idle' | 'pending' } | { status: 'success'; data: T } | { status: 'error'; error: ApiError }
export function useRequest<T>() {
  const [api] = useState(() => createApiClient(import.meta.env.DEV && window.location.pathname === '/dev/conversation'
    ? { fetch: previewFetch, developmentPreview: true }
    : import.meta.env.DEV && window.location.pathname === '/dev/profile'
      ? { fetch: createProfilePreviewFetch(), developmentPreview: true } : {}))
  const scope = useMemoryScope<State<T>>(() => ({ status: 'idle' }))
  const active = useRef<AbortSignal | null>(null)
  async function run(action: (api: ReturnType<typeof createApiClient>, signal: AbortSignal) => Promise<T>, onSuccess?: (data: T) => void) {
    if (active.current && !active.current.aborted) return
    scope.clear()
    scope.setValue({ status: 'pending' })
    try { await scope.run(async (signal): Promise<State<T>> => {
      active.current = signal
      try { return { status: 'success', data: await action(api, signal) } }
      catch (error) { return { status: 'error', error: error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE') } }
      finally { if (active.current === signal) active.current = null }
    }, (result) => { scope.setValue(result); if (result.status === 'success') onSuccess?.(result.data) }) }
    catch (error) {
      // Apply callbacks can fail too. useMemoryScope only rethrows while this
      // lifetime is still valid, so discarded callbacks cannot revive an error.
      scope.setValue({ status: 'error', error: error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE') })
    }
  }
  return { state: scope.value, run, clear: scope.clear }
}

export function required<T>(value: T | undefined): T {
  if (value === undefined) throw new ApiError('INVALID_RESPONSE')
  return value
}
