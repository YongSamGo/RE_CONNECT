import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { VoicePreview } from './VoicePreview'

class Recorder {
  static isTypeSupported = () => true
  static latest: Recorder
  state = 'inactive'
  onstop: (() => void) | null = null
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onerror: (() => void) | null = null
  constructor() { Recorder.latest = this }
  start() { this.state = 'recording' }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['sound']) }); this.onstop?.() }
}
function mount() {
  const useText = vi.fn()
  const view = render(<MemoryRouter><VoicePreview onUseText={useText} /></MemoryRouter>)
  return { ...view, useText }
}
function media() {
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  const track = { stop: vi.fn(), onended: null as (() => void) | null }
  const stream = { getTracks: () => [track] }
  const getUserMedia = vi.fn(async () => stream)
  vi.stubGlobal('MediaRecorder', Recorder)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  const create = vi.fn(() => 'blob:voice-preview')
  const revoke = vi.fn()
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: create, revokeObjectURL: revoke }))
  return { track, stream, getUserMedia, create, revoke }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); delete (navigator as unknown as { mediaDevices?: unknown }).mediaDevices })

describe('voice preview resource lifetime', () => {
  it('offers the recorded blob to transcription only after explicit request and resets on cancellation', async () => {
    const mocks = media(), onRequest = vi.fn(), onReset = vi.fn()
    render(<MemoryRouter><VoicePreview transcription={{ pending: false, onRequest, onReset }} /></MemoryRouter>)
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
    fireEvent.click(screen.getByRole('button', { name: '녹음 마치기' }))
    expect(onRequest).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '녹음 전사 요청 · 같은 요청 재확인' }))
    expect(onRequest).toHaveBeenCalledTimes(1)
    expect(onRequest.mock.calls[0][0]).toBeInstanceOf(Blob)
    expect(onRequest.mock.calls[0][0].size).toBe(5)
    fireEvent.click(screen.getByRole('button', { name: '녹음·입력 취소하고 삭제' }))
    expect(onReset).toHaveBeenCalledTimes(2)
    expect(mocks.revoke).toHaveBeenCalledWith('blob:voice-preview')
    expect(screen.queryByRole('button', { name: '녹음 전사 요청 · 같은 요청 재확인' })).not.toBeInTheDocument()
  })
  it('requests microphone only on click and releases tracks and object URL on unmount', async () => {
    const mocks = media()
    const view = mount()
    expect(mocks.getUserMedia).not.toHaveBeenCalled()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
    expect(mocks.getUserMedia).toHaveBeenCalledExactlyOnceWith({ audio: true })
    fireEvent.click(screen.getByRole('button', { name: '녹음 마치기' }))
    expect(mocks.track.stop).toHaveBeenCalled()
    expect(screen.getByLabelText('내 녹음 들어보기')).toHaveAttribute('src', 'blob:voice-preview')
    view.unmount()
    expect(mocks.revoke).toHaveBeenCalledWith('blob:voice-preview')
    expect(HTMLMediaElement.prototype.pause).toHaveBeenCalled()
  })
  it('stops a late permission result after cancellation without reviving recording', async () => {
    const mocks = media()
    let complete!: (value: typeof mocks.stream) => void
    mocks.getUserMedia.mockImplementation(() => new Promise((resolve) => { complete = resolve }))
    mount()
    fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' }))
    fireEvent.click(screen.getByRole('button', { name: '녹음·입력 취소하고 삭제' }))
    await act(async () => complete(mocks.stream))
    expect(mocks.track.stop).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('button', { name: '녹음 마치기' })).not.toBeInTheDocument()
    expect(mocks.create).not.toHaveBeenCalled()
  })
  it('keeps manually edited text on recording errors and sends only explicit confirmed text', async () => {
    const mocks = media()
    mocks.getUserMedia.mockRejectedValue(new Error('private device details'))
    const view = mount()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: '직접 고친 경험' } })
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
    expect(screen.getByRole('textbox')).toHaveValue('직접 고친 경험')
    expect(screen.getByRole('alert')).not.toHaveTextContent('private device details')
    expect(view.useText).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: '이 문장을 경험 입력에 사용하기' }))
    expect(view.useText).toHaveBeenCalledExactlyOnceWith('직접 고친 경험')
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
  it('discards an oversized recording and stops its microphone', async () => {
    const mocks = media()
    mount()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
    act(() => Recorder.latest.ondataavailable?.({ data: new Blob([new Uint8Array(6 * 1024 * 1024 + 1)]) }))
    expect(screen.getByRole('alert')).toHaveTextContent('6MiB')
    expect(mocks.track.stop).toHaveBeenCalled()
    expect(mocks.create).not.toHaveBeenCalled()
  })
  it('stops recording at the duration limit and clears all preview state on pagehide', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval', 'performance'] })
    const mocks = media()
    mount()
    await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
    act(() => vi.advanceTimersByTime(90000))
    expect(Recorder.latest.state).toBe('inactive')
    expect(mocks.track.stop).toHaveBeenCalled()
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(mocks.revoke).toHaveBeenCalledWith('blob:voice-preview')
    expect(screen.queryByLabelText('내 녹음 들어보기')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
})
