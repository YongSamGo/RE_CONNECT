import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { JourneyTranscription } from './JourneyTranscription'
import { parseTranscription } from './transcription'
import { JourneyConversation } from '../conversation/JourneyConversation'

const journeyId = '12345678-1234-1234-1234-123456789012'
const transcriptionId = '22345678-1234-1234-1234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const transcript = { transcription_id: transcriptionId, text: '자동으로 인식한 가상 문장', duration_seconds: 1.5 }
class Recorder {
  static latest: Recorder
  static supported = true
  static isTypeSupported = () => Recorder.supported
  state = 'inactive'
  onstop: (() => void) | null = null
  ondataavailable: ((event: { data: Blob }) => void) | null = null
  onerror: (() => void) | null = null
  constructor() { Recorder.latest = this }
  start() { this.state = 'recording' }
  stop() { this.state = 'inactive'; this.ondataavailable?.({ data: new Blob(['synthetic-audio'], { type: 'audio/webm;codecs=opus' }) }); this.onstop?.() }
}
async function media() {
  // jsdom media controls + Node's actual Request/FormData serializer.
  const nativeForm = await new Response('', { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).formData()
  vi.stubGlobal('FormData', nativeForm.constructor); vi.stubGlobal('Blob', NodeBlob); vi.stubGlobal('File', NodeFile)
  vi.spyOn(HTMLMediaElement.prototype, 'pause').mockImplementation(() => {})
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  const track = { stop: vi.fn(), onended: null as (() => void) | null }
  const stream = { getTracks: () => [track] }
  const getUserMedia = vi.fn(async () => stream)
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } })
  vi.stubGlobal('MediaRecorder', Recorder)
  const create = vi.fn(() => 'blob:journey-recording'), revoke = vi.fn()
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: create, revokeObjectURL: revoke }))
  return { track, stream, getUserMedia, create, revoke }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); vi.useRealTimers(); Recorder.supported = true;
  delete (navigator as unknown as { mediaDevices?: unknown }).mediaDevices; document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
function mount() {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const useText = vi.fn(), close = vi.fn(), accessLost = vi.fn()
  const view = render(<JourneyTranscription journeyId={journeyId} onUseText={useText} onClose={close} onAccessLost={accessLost} />)
  return { ...view, useText, close, accessLost }
}
async function recordAudio() {
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
  fireEvent.click(screen.getByRole('button', { name: '녹음 마치기' }))
}

it('requests mic only on click, sends exact multipart once, releases raw resources and requires explicit edited-text acceptance', async () => {
  const mocks = await media()
  const fetch = vi.fn(async (_request: Request) => json(transcript, 201)); vi.stubGlobal('fetch', fetch)
  const view = mount()
  expect(mocks.getUserMedia).not.toHaveBeenCalled()
  await recordAudio()
  expect(fetch).not.toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  expect(await screen.findByLabelText('보내기 전에 고칠 전사 문장')).toHaveValue(transcript.text)
  expect(view.useText).not.toHaveBeenCalled()
  const request = fetch.mock.calls[0][0]
  expect(request.url).toBe(`https://reconnect.test/api/v1/journeys/${journeyId}/transcriptions`)
  expect(request.headers.get('content-type')).toMatch(/^multipart\/form-data; boundary=/)
  expect(request.headers.get('X-CSRF-Token')).toBe('token')
  expect(request.headers.get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/)
  const body = await request.clone().formData()
  expect([...body.keys()]).toEqual(['audio'])
  expect(await (body.get('audio') as File).text()).toBe('synthetic-audio')
  expect(mocks.track.stop).toHaveBeenCalled()
  expect(mocks.revoke).toHaveBeenCalledWith('blob:journey-recording')
  expect(screen.queryByLabelText('내 녹음 들어보기')).not.toBeInTheDocument()
  fireEvent.change(screen.getByLabelText('보내기 전에 고칠 전사 문장'), { target: { value: '사용자가 고친 가상 문장' } })
  await userEvent.click(screen.getByRole('button', { name: '이 수정 문장을 입력칸에 사용하기' }))
  expect(view.useText).toHaveBeenCalledExactlyOnceWith('사용자가 고친 가상 문장', transcriptionId)
  expect(screen.getByLabelText('보내기 전에 고칠 전사 문장')).toHaveValue('')
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('preserves manually edited text on STT failure while dropping the original audio', async () => {
  const mocks = await media(); vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'MODEL_UNAVAILABLE' }, 503)))
  const view = mount()
  fireEvent.change(screen.getByLabelText('보내기 전에 고칠 전사 문장'), { target: { value: '직접 적은 문장' } })
  await recordAudio()
  await userEvent.click(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  await screen.findByRole('alert')
  expect(screen.getByLabelText('보내기 전에 고칠 전사 문장')).toHaveValue('직접 적은 문장')
  expect(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' })).toBeDisabled()
  expect(mocks.revoke).toHaveBeenCalled()
  await userEvent.click(screen.getByRole('button', { name: '이 수정 문장을 입력칸에 사용하기' }))
  expect(view.useText).toHaveBeenCalledExactlyOnceWith('직접 적은 문장', null)
})

it('blocks duplicate uploads, aborts on cancel, and never applies a late transcript', async () => {
  await media(); let finish!: (response: Response) => void
  const fetch = vi.fn(async (_request: Request) => new Promise<Response>(resolve => { finish = resolve })); vi.stubGlobal('fetch', fetch)
  const view = mount(); await recordAudio()
  await userEvent.dblClick(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  expect(fetch).toHaveBeenCalledTimes(1)
  fireEvent.click(screen.getByRole('button', { name: '녹음·입력 취소하고 삭제' }))
  expect(fetch.mock.calls[0][0].signal.aborted).toBe(true)
  await act(async () => finish(json(transcript, 201)))
  expect(screen.getByLabelText('보내기 전에 고칠 전사 문장')).toHaveValue('')
  expect(view.useText).not.toHaveBeenCalled()
})

it('does not stop a new recording when the old cancelled upload finally settles', async () => {
  const mocks = await media(); let finish!: (response: Response) => void
  vi.stubGlobal('fetch', vi.fn(async () => new Promise<Response>(resolve => { finish = resolve })))
  mount(); await recordAudio()
  await userEvent.click(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  fireEvent.click(screen.getByRole('button', { name: '녹음·입력 취소하고 삭제' }))
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
  const stops = mocks.track.stop.mock.calls.length
  await act(async () => finish(json(transcript, 201)))
  expect(Recorder.latest.state).toBe('recording')
  expect(mocks.track.stop).toHaveBeenCalledTimes(stops)
})

it.each(['unmount', 'pagehide'])('discards pending permission/audio/text on %s', async leave => {
  const mocks = await media(); let allow!: (stream: typeof mocks.stream) => void
  mocks.getUserMedia.mockImplementation(() => new Promise(resolve => { allow = resolve }))
  const view = mount()
  fireEvent.change(screen.getByLabelText('보내기 전에 고칠 전사 문장'), { target: { value: '임시 입력' } })
  fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' }))
  if (leave === 'unmount') view.unmount(); else act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => allow(mocks.stream))
  expect(mocks.track.stop).toHaveBeenCalled()
  expect(mocks.create).not.toHaveBeenCalled()
  if (leave === 'pagehide') expect(screen.getByLabelText('보내기 전에 고칠 전사 문장')).toHaveValue('')
})

it('keeps direct input available after permission denial and unsupported recording format', async () => {
  const mocks = await media(); mocks.getUserMedia.mockRejectedValue(new Error('private permission reason'))
  mount()
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
  expect(screen.getByRole('alert')).not.toHaveTextContent('private permission reason')
  Recorder.supported = false
  await act(async () => fireEvent.click(screen.getByRole('button', { name: '녹음 시작하기' })))
  expect(screen.getByRole('alert')).toHaveTextContent('지원하는 녹음 형식')
  expect(screen.getByLabelText('보내기 전에 고칠 전사 문장')).toBeEnabled()
})

it('signals lost session access and does not pass a transcript onward', async () => {
  await media(); vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'SESSION_EXPIRED' }, 401)))
  const view = mount(); await recordAudio()
  await userEvent.click(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  expect(view.accessLost).toHaveBeenCalledOnce()
  expect(view.useText).not.toHaveBeenCalled()
})

it('preserves the original conversation text on voice cancel and only sends accepted edited transcription', async () => {
  await media()
  const profile = { revision: 1, confirmed: null, has_unconfirmed_changes: false, missing_for_recommendation: ['experiences'], evidence: [], draft: {
    schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [], paid_preference: null,
    available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: null, activity_constraints: null,
  } }
  const fetch = vi.fn(async (request: Request) => request.url.endsWith('/transcriptions') ? json(transcript, 201)
    : request.url.endsWith('/messages') ? json({ code: 'MODEL_UNAVAILABLE' }, 503) : json(request.url.endsWith('/me') ? {} : profile))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><JourneyConversation journeyId={journeyId} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '체험 대화 준비하기' }))
  await user.type(await screen.findByLabelText('내가 해온 일'), '기존 직접 입력')
  await user.click(screen.getByRole('button', { name: '말로 입력하고 전사 확인' }))
  await user.click(screen.getByRole('button', { name: '음성 입력 닫고 원래 글로 돌아가기' }))
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('기존 직접 입력')
  await user.click(screen.getByRole('button', { name: '말로 입력하고 전사 확인' }))
  await recordAudio(); await user.click(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  const field = await screen.findByLabelText('보내기 전에 고칠 전사 문장')
  fireEvent.change(field, { target: { value: '전사에서 고친 경험' } })
  expect(fetch.mock.calls.some(([request]) => request.url.endsWith('/messages'))).toBe(false)
  await user.click(screen.getByRole('button', { name: '이 수정 문장을 입력칸에 사용하기' }))
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('전사에서 고친 경험')
  expect(screen.getByLabelText('내가 해온 일')).toHaveFocus()
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByRole('alert')
  const message = fetch.mock.calls.find(([request]) => request.url.endsWith('/messages'))![0]
  expect(await message.clone().json()).toEqual({ text: '전사에서 고친 경험', transcription_id: transcriptionId, base_revision: 1 })
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('전사에서 고친 경험')
})

it('validates the server transcription reference, text and duration', () => {
  expect(parseTranscription(transcript).text).toBe(transcript.text)
  for (const value of [{ ...transcript, transcription_id: 'forged' }, { ...transcript, text: 'x'.repeat(2001) },
    { ...transcript, duration_seconds: true }, { ...transcript, duration_seconds: 91 }, { ...transcript, duration_seconds: 0 }]) expect(() => parseTranscription(value)).toThrow()
})

it('passes structural accessibility with an editable transcription', async () => {
  await media(); vi.stubGlobal('fetch', vi.fn(async () => json(transcript, 201)))
  mount(); await recordAudio(); await userEvent.click(screen.getByRole('button', { name: '이 녹음을 서버에 보내 전사' }))
  await screen.findByDisplayValue(transcript.text)
  const result = await axe.run(document.body, { rules: { 'color-contrast': { enabled: false }, region: { enabled: false } } })
  expect(result.violations).toEqual([])
})
