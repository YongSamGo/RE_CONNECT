import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { JourneyVoiceInput } from './JourneyVoiceInput'
import { anonymousSession } from '../../api/fixtures'

class Recorder {
  static latest: Recorder
  static isTypeSupported = () => true
  state = 'inactive'
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onstop: (() => void) | null = null
  onerror: (() => void) | null = null
  constructor() { Recorder.latest = this }
  start() { this.state = 'recording' }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['audio']) }); this.onstop?.() }
}
afterEach(() => {
  vi.restoreAllMocks(); vi.unstubAllGlobals()
  delete (navigator as unknown as { mediaDevices?: unknown }).mediaDevices
  document.cookie = '__Host-rc_csrf=; Max-Age=0; Path=/; Secure'
})
async function mount() {
  const native = await new Response('', { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).formData()
  vi.stubGlobal('FormData', native.constructor); vi.stubGlobal('Blob', NodeBlob); vi.stubGlobal('File', NodeFile)
  vi.stubGlobal('MediaRecorder', Recorder)
  vi.stubGlobal('AudioContext', undefined)
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: () => 'blob:recording', revokeObjectURL: vi.fn() }))
  const track = { stop: vi.fn(), onended: null }, stream = { getTracks: () => [track] }
  const getUserMedia = vi.fn(async () => stream)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  const onUseText = vi.fn(), onSelectText = vi.fn(), onBusyChange = vi.fn()
  render(<JourneyVoiceInput journeyId="12345678-1234-1234-1234-123456789012" onUseText={onUseText} onSelectText={onSelectText} onBusyChange={onBusyChange} />)
  return { track, stream, getUserMedia, onUseText, onSelectText, onBusyChange }
}

it('cancels an unanswered microphone permission request and stops its late stream', async () => {
  const mocks = await mount()
  let finish!: (stream: typeof mocks.stream) => void
  mocks.getUserMedia.mockImplementation(() => new Promise(resolve => { finish = resolve }))
  fireEvent.click(screen.getByRole('button', { name: '말하기' }))
  expect(screen.getByRole('button', { name: '음성 입력 취소' })).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: '음성 입력 취소' }))
  expect(mocks.onBusyChange).toHaveBeenLastCalledWith(false)
  await act(async () => finish(mocks.stream))
  expect(mocks.track.stop).toHaveBeenCalledOnce()
  expect(mocks.onUseText).not.toHaveBeenCalled()
  expect(screen.getByRole('button', { name: '말하기' })).toBeEnabled()
})

it('stops the active microphone before switching to typed answers without uploading audio', async () => {
  const mocks = await mount(), fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  await userEvent.click(screen.getByRole('button', { name: '말하기' }))
  expect(screen.getByRole('button', { name: '말한 내용 저장하기' })).toBeEnabled()
  await userEvent.click(screen.getByRole('button', { name: '글로 답하기' }))
  expect(mocks.track.stop).toHaveBeenCalled()
  expect(mocks.onSelectText).toHaveBeenCalledOnce()
  expect(mocks.onBusyChange).toHaveBeenLastCalledWith(false)
  expect(fetch).not.toHaveBeenCalled()
})

it('discards a late transcription after switching to typed answers', async () => {
  const mocks = await mount()
  document.cookie = '__Host-rc_csrf=token; Path=/; Secure'
  let finish!: (response: Response) => void
  const fetch = vi.fn(async (request: Request) => request.method === 'GET'
    ? new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } })
    : new Promise<Response>(resolve => { finish = resolve }))
  vi.stubGlobal('fetch', fetch)
  // useRequest captures the transport at construction; remount with the test transport.
  const view = render(<JourneyVoiceInput journeyId="12345678-1234-1234-1234-123456789012" onUseText={mocks.onUseText} />)
  const buttons = screen.getAllByRole('button', { name: '말하기' })
  await userEvent.click(buttons[1])
  await userEvent.click(screen.getByRole('button', { name: '말한 내용 저장하기' }))
  expect(fetch).toHaveBeenCalledTimes(2)
  await userEvent.click(screen.getAllByRole('button', { name: '글로 답하기' })[1])
  await act(async () => finish(new Response(JSON.stringify({ transcription_id: '22345678-1234-1234-1234-123456789012', text: '늦은 전사', duration_seconds: 1 }), { headers: { 'Content-Type': 'application/json' } })))
  expect(mocks.onUseText).not.toHaveBeenCalled()
  expect(fetch.mock.calls[1][0].signal.aborted).toBe(true)
  view.unmount()
})
