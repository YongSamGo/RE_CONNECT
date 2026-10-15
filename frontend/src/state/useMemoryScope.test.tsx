import { StrictMode } from 'react'
import { act, renderHook } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/errors'
import { useMemoryScope } from './useMemoryScope'

const initial = () => ({ text: '' })
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('component-owned memory lifetime', () => {
  it('keeps separate scopes isolated and clears values without persistent writes', () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    const indexedDB = { open: vi.fn() }
    vi.stubGlobal('indexedDB', indexedDB)
    const a = renderHook(() => useMemoryScope(initial))
    const b = renderHook(() => useMemoryScope(initial))
    act(() => a.result.current.setValue({ text: 'A 가상 입력' }))
    expect(a.result.current.value.text).toBe('A 가상 입력')
    expect(b.result.current.value.text).toBe('')
    act(() => a.result.current.clear())
    expect(a.result.current.value.text).toBe('')
    expect(storage).not.toHaveBeenCalled()
    expect(indexedDB.open).not.toHaveBeenCalled()
  })
  it('applies a valid result in its scope and returns no raw data', async () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    await act(async () => {
      const state = await result.current.run(async () => '정리한 가상 경험', (text) => result.current.setValue({ text }))
      expect(state).toEqual({ status: 'completed' })
    })
    expect(result.current.value.text).toBe('정리한 가상 경험')
  })
  it('aborts in-flight work on clear and discards a late result even if transport ignores abort', async () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    const work = deferred<string>()
    let signal!: AbortSignal
    const apply = vi.fn()
    const operation = result.current.run((received) => { signal = received; return work.promise }, apply)
    act(() => result.current.clear())
    expect(signal.aborted).toBe(true)
    work.resolve('늦게 온 가상 경험')
    await expect(operation).resolves.toEqual({ status: 'discarded' })
    expect(apply).not.toHaveBeenCalled()
    expect(result.current.value.text).toBe('')
  })
  it('discards a late failure after clear instead of showing the previous session error', async () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    const work = deferred<string>()
    const apply = vi.fn()
    const operation = result.current.run(() => work.promise, apply)
    act(() => result.current.clear())
    work.reject(new ApiError('SERVICE_UNAVAILABLE', 503))
    await expect(operation).resolves.toEqual({ status: 'discarded' })
    expect(apply).not.toHaveBeenCalled()
  })
  it('keeps input after an active request failure and propagates its safe API error', async () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    act(() => result.current.setValue({ text: '재시도할 가상 경험' }))
    const error = new ApiError('INFERENCE_BUSY', 429)
    await expect(result.current.run(async () => { throw error }, vi.fn())).rejects.toBe(error)
    expect(result.current.value.text).toBe('재시도할 가상 경험')
  })
  it('cannot overwrite a new scope with the previous scope result', async () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    const old = deferred<string>()
    const apply = (text: string) => result.current.setValue({ text })
    const previous = result.current.run(() => old.promise, apply)
    act(() => result.current.clear())
    await act(async () => { await result.current.run(async () => '새 입력 결과', apply) })
    old.resolve('이전 입력 결과')
    await expect(previous).resolves.toEqual({ status: 'discarded' })
    expect(result.current.value.text).toBe('새 입력 결과')
  })
  it('invalidates work on unmount and refuses new work through a stale scope reference', async () => {
    const { result, unmount } = renderHook(() => useMemoryScope(initial))
    const scope = result.current
    const work = deferred<string>()
    let signal!: AbortSignal
    const apply = vi.fn()
    const operation = scope.run((received) => { signal = received; return work.promise }, apply)
    unmount()
    expect(signal.aborted).toBe(true)
    work.resolve('stale')
    await expect(operation).resolves.toEqual({ status: 'discarded' })
    const newWork = vi.fn()
    await expect(scope.run(newWork, apply)).resolves.toEqual({ status: 'discarded' })
    expect(newWork).not.toHaveBeenCalled()
    expect(apply).not.toHaveBeenCalled()
  })
  it.each(['pagehide', 'pageshow'])('invalidates memory and in-flight work at %s', async (event) => {
    const { result } = renderHook(() => useMemoryScope(initial))
    act(() => result.current.setValue({ text: '화면 이탈 전 가상 입력' }))
    const work = deferred<string>()
    const apply = vi.fn()
    let signal!: AbortSignal
    const operation = result.current.run((received) => { signal = received; return work.promise }, apply)
    act(() => window.dispatchEvent(new PageTransitionEvent(event, { persisted: true })))
    expect(result.current.value.text).toBe('')
    expect(signal.aborted).toBe(true)
    work.resolve('late')
    await expect(operation).resolves.toEqual({ status: 'discarded' })
  })
  it('does not clear active input on an ordinary pageshow', () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    act(() => result.current.setValue({ text: '진행 중인 가상 입력' }))
    act(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: false })))
    expect(result.current.value.text).toBe('진행 중인 가상 입력')
  })
  it('remains usable after React StrictMode effect cleanup and reattachment', async () => {
    const { result } = renderHook(() => useMemoryScope(initial), { wrapper: StrictMode })
    await act(async () => { await result.current.run(async () => '현재 입력', (text) => result.current.setValue({ text })) })
    expect(result.current.value.text).toBe('현재 입력')
  })
  it('does not restart work synchronously from a cancellation listener while clearing', async () => {
    const { result } = renderHook(() => useMemoryScope(initial))
    const work = deferred<string>()
    const restart = vi.fn(async () => '재시작한 결과')
    const apply = vi.fn()
    const operation = result.current.run((signal) => {
      signal.addEventListener('abort', () => { void result.current.run(restart, apply) })
      return work.promise
    }, apply)
    act(() => result.current.clear())
    expect(restart).not.toHaveBeenCalled()
    work.resolve('이전 결과')
    await expect(operation).resolves.toEqual({ status: 'discarded' })
    expect(apply).not.toHaveBeenCalled()
  })
})
