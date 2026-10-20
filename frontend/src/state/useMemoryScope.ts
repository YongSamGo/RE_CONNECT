import { useCallback, useEffect, useRef, useState } from 'react'
import type { SetStateAction } from 'react'

export type ScopedResult = { status: 'completed' } | { status: 'discarded' }

/** One component-owned, memory-only lifetime. No module singleton or persistence. */
export function useMemoryScope<T>(initialize: () => T) {
  const initializer = useRef(initialize)
  const [value, setValue] = useState(initialize)
  const generation = useRef(0)
  const mounted = useRef(true)
  const controllers = useRef(new Set<AbortController>())
  const invalidating = useRef(false)

  const invalidate = useCallback(() => {
    if (invalidating.current) return
    invalidating.current = true
    generation.current += 1
    const pending = [...controllers.current]
    controllers.current.clear()
    try { for (const controller of pending) controller.abort() }
    finally { invalidating.current = false }
  }, [])
  const clear = useCallback(() => {
    invalidate()
    if (mounted.current) setValue(initializer.current())
  }, [invalidate])
  const update = useCallback((next: SetStateAction<T>) => { if (mounted.current) setValue(next) }, [])

  const run = useCallback(async <R,>(action: (signal: AbortSignal) => Promise<R>, apply: (result: R) => void): Promise<ScopedResult> => {
    if (!mounted.current || invalidating.current) return { status: 'discarded' }
    const current = generation.current
    const controller = new AbortController()
    controllers.current.add(controller)
    const valid = () => mounted.current && current === generation.current && !controller.signal.aborted
    try {
      const result = await action(controller.signal)
      if (!valid()) return { status: 'discarded' }
      // Apply within the validity check's synchronous turn; do not return raw
      // data to be applied after another await and a possible session reset.
      apply(result)
      return { status: 'completed' }
    } catch (error) {
      // Late failures must not reintroduce a previous session's error or input.
      if (!valid()) return { status: 'discarded' }
      throw error
    } finally {
      controllers.current.delete(controller)
    }
  }, [])

  useEffect(() => {
    mounted.current = true
    const restore = (event: PageTransitionEvent) => { if (event.persisted) clear() }
    window.addEventListener('pagehide', clear)
    window.addEventListener('pageshow', restore)
    return () => {
      mounted.current = false
      invalidate()
      window.removeEventListener('pagehide', clear)
      window.removeEventListener('pageshow', restore)
    }
  }, [clear, invalidate])

  return { value, setValue: update, clear, run }
}
