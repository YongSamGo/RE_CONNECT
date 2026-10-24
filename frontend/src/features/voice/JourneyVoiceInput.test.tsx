import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'
import { JourneyVoiceInput } from './JourneyVoiceInput'
import { parseTranscription } from './transcription'

vi.mock('./VoicePreview', () => ({ VoicePreview: ({ transcription }: { transcription: { onRequest: (blob: Blob) => void; onReset: () => void } }) => <><button onClick={() => transcription.onRequest(new Blob(['fixture-audio'], { type: 'audio/webm' }))}>시험 녹음 전사</button><button onClick={transcription.onReset}>시험 녹음 취소</button></> }))
const id = '12345678-1234-1234-1234-123456789012'
const result = { transcription_id: id, text: '가상 원래 전사', duration_seconds: 2.5 }
beforeEach(async () => {
  // Match Node's Request body implementation instead of mixing jsdom File
  // objects with undici serialization, which would erase their byte content.
  const native = await new Response('fixture=1', { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).formData()
  vi.stubGlobal('FormData', native.constructor)
  vi.stubGlobal('Blob', NodeBlob)
  vi.stubGlobal('File', NodeFile)
})
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
function mount(options: { consent?: boolean; loseFirst?: boolean; replace?: boolean } = {}) {
  let posts = 0
  const fetch = vi.fn(async (request: Request) => {
    if (request.method === 'GET') return json({ authenticated: false, user: null, pending_save_intent: null, consents: options.consent === false ? [] : [{ purpose: 'ai_processing', notice_version: 'fixture-ai', granted_at: '2026-10-18T00:00:00Z' }] })
    posts++
    if (options.loseFirst && posts === 1) throw new TypeError('fixture lost response')
    return json(result)
  })
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const onUseText = vi.fn()
  render(<JourneyVoiceInput journeyId={id} replaceRequired={options.replace ?? false} onUseText={onUseText} />)
  return { user: userEvent.setup(), fetch, onUseText }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('uploads multipart audio only explicitly and requires corrected text plus replacement confirmation', async () => {
  const { user, fetch, onUseText } = mount({ replace: true })
  expect(fetch).not.toHaveBeenCalled()
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' }))
  const text = await screen.findByLabelText('확인·수정할 전사 문장')
  expect(onUseText).not.toHaveBeenCalled()
  await user.clear(text); await user.type(text, '직접 수정한 전사')
  const use = screen.getByRole('button', { name: '확인한 전사 문장을 입력란으로 가져오기' })
  expect(use).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: '현재 경험 입력을 확인한 전사 문장으로 바꿀게요.' }))
  await user.click(use)
  expect(onUseText).toHaveBeenCalledExactlyOnceWith('직접 수정한 전사', id)
  expect(screen.queryByLabelText('확인·수정할 전사 문장')).not.toBeInTheDocument()
  const request = fetch.mock.calls.find(([request]) => request.method === 'POST')![0]
  expect(request.url).toContain(`/journeys/${id}/transcriptions`)
  expect(request.headers.get('Content-Type')).toContain('multipart/form-data; boundary=')
  const body = await request.clone().text()
  expect(body).toContain('Content-Type: audio/webm'); expect(body).toContain('fixture-audio')
})

it('does not upload recording when processing consent is absent', async () => {
  const { user, fetch } = mount({ consent: false })
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' }))
  await screen.findByText('처리 안내와 동의 상태를 확인해 주세요.')
  expect(fetch.mock.calls.some(([request]) => request.method === 'POST')).toBe(false)
})

it('retries a lost response using the same key and original audio', async () => {
  const { user, fetch } = mount({ loseFirst: true })
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' }))
  await screen.findByText('연결하지 못했습니다. 연결 상태를 확인해 주세요.')
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' }))
  await screen.findByLabelText('확인·수정할 전사 문장')
  const posts = fetch.mock.calls.map(([request]) => request).filter(request => request.method === 'POST')
  expect(posts).toHaveLength(2)
  expect(posts[1].headers.get('Idempotency-Key')).toBe(posts[0].headers.get('Idempotency-Key'))
  for (const request of posts) expect(await request.clone().text()).toContain('fixture-audio')
})

it('clears transcription text on cancellation and pagehide without importing it', async () => {
  const { user, onUseText } = mount()
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' })); await screen.findByLabelText('확인·수정할 전사 문장')
  await user.click(screen.getByRole('button', { name: '시험 녹음 취소' }))
  expect(screen.queryByLabelText('확인·수정할 전사 문장')).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' })); await screen.findByLabelText('확인·수정할 전사 문장')
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByLabelText('확인·수정할 전사 문장')).not.toBeInTheDocument()
  expect(onUseText).not.toHaveBeenCalled()
})

it('rejects malformed transcription IDs, long text and invalid duration', () => {
  expect(parseTranscription(result)).toEqual(result)
  for (const changed of [{ transcription_id: '../other' }, { duration_seconds: 91 }, { duration_seconds: 0 }, { duration_seconds: Infinity }, { text: '가'.repeat(2001) }]) {
    expect(() => parseTranscription({ ...result, ...changed })).toThrow()
  }
})

it('discards late parsed transcription after the user cancels waiting', async () => {
  const { user, onUseText } = mount()
  const original = Response.prototype.text
  let release!: () => void, arrived!: () => void
  const waiting = new Promise<void>(resolve => { release = resolve })
  const parsing = new Promise<void>(resolve => { arrived = resolve })
  vi.spyOn(Response.prototype, 'text').mockImplementation(async function (this: Response) {
    const body = await original.call(this)
    if (body.includes('"transcription_id"')) { arrived(); await waiting }
    return body
  })
  await user.click(screen.getByRole('button', { name: '시험 녹음 전사' })); await parsing
  await user.click(screen.getByRole('button', { name: '전사 응답 기다리기 중지' }))
  await act(async () => { release(); await waiting })
  expect(screen.queryByLabelText('확인·수정할 전사 문장')).not.toBeInTheDocument()
  expect(onUseText).not.toHaveBeenCalled()
})
