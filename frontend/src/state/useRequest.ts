import { useRef, useState } from 'react'
import { createApiClient } from '../api/client'
import { ApiError } from '../api/errors'
import { useMemoryScope } from './useMemoryScope'

type State<T> = { status: 'idle' | 'pending' } | { status: 'success'; data: T } | { status: 'error'; error: ApiError }
export function useRequest<T>() {
  const [api] = useState(() => createApiClient())
  const scope = useMemoryScope<State<T>>(() => ({ status: 'idle' }))
  const active = useRef<AbortSignal | null>(null)
  async function run(action: (api: ReturnType<typeof createApiClient>, signal: AbortSignal) => Promise<T>, onSuccess?: (data: T) => void) {
    if (active.current && !active.current.aborted) return
    scope.clear()
    scope.setValue({ status: 'pending' })
    await scope.run(async (signal): Promise<State<T>> => {
      active.current = signal
      try { return { status: 'success', data: await action(api, signal) } }
      catch (error) { return { status: 'error', error: error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE') } }
      finally { if (active.current === signal) active.current = null }
    }, (result) => { scope.setValue(result); if (result.status === 'success') onSuccess?.(result.data) })
  }
  return { state: scope.value, run, clear: scope.clear }
}

export function required<T>(value: T | undefined): T {
  if (value === undefined) throw new ApiError('INVALID_RESPONSE')
  return value
}
