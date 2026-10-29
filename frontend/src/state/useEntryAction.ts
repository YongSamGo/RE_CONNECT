import { useEffect, useRef } from 'react'

/** Run the current action once on entry, after StrictMode's setup/cleanup cycle.
 * Request hooks still own cancellation, errors and duplicate-request handling.
 */
export function useEntryAction(action: () => unknown, enabled = true, entryKey = '') {
  const latest = useRef(action)
  useEffect(() => { latest.current = action }, [action])
  useEffect(() => {
    let current = true
    queueMicrotask(() => { if (current && enabled) latest.current() })
    return () => { current = false }
  }, [enabled, entryKey])
}
