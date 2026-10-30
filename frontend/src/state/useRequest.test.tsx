import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { useRequest } from './useRequest'

it('turns a success callback exception into a safe error instead of rejecting the event handler', async () => {
  const { result } = renderHook(() => useRequest<string>())
  await act(async () => {
    await expect(result.current.run(async () => 'value', () => { throw new Error('private-callback-path') })).resolves.toBeUndefined()
  })
  expect(result.current.state).toMatchObject({ status: 'error', error: { code: 'INVALID_RESPONSE' } })
  expect(JSON.stringify(result.current.state)).not.toContain('private')
  await act(async () => { await result.current.run(async () => 'retry') })
  expect(result.current.state).toEqual({ status: 'success', data: 'retry' })
})

it('does not revive an error when the callback clears its lifetime before throwing', async () => {
  const { result } = renderHook(() => useRequest<string>())
  await act(async () => { await result.current.run(async () => 'value', () => { result.current.clear(); throw new Error('discarded') }) })
  expect(result.current.state).toEqual({ status: 'idle' })
})

it('does not apply a late result after cancellation and lets a new request finish independently', async () => {
  const { result } = renderHook(() => useRequest<string>())
  let finish!: (value: string) => void
  let old!: Promise<void>
  const applied: string[] = []
  act(() => { old = result.current.run(() => new Promise(resolve => { finish = resolve }), value => { applied.push(value) }) })
  act(() => result.current.clear())
  await act(async () => { await result.current.run(async () => 'new') })
  await act(async () => { finish('old'); await old })
  expect(applied).toEqual([])
  expect(result.current.state).toEqual({ status: 'success', data: 'new' })
})
