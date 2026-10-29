import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { QuestionAudio } from './QuestionAudio'
import { anonymousSession } from '../../api/fixtures'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Path=/; Secure' })

it('reads the fixed opening question slowly with the selected volume', async () => {
  const speak = vi.fn(), cancel = vi.fn()
  vi.stubGlobal('speechSynthesis', { speak, cancel })
  vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; lang = ''; rate = 1; volume = 1; onerror = null; constructor(text: string) { this.text = text } })
  render(<QuestionAudio question="첫 질문입니다." journeyId="12345678-1234-1234-1234-123456789012" messageId={null} />)
  const user = userEvent.setup()
  fireEvent.change(screen.getByLabelText('소리 조절'), { target: { value: '0.5' } })
  await user.click(screen.getByRole('button', { name: '천천히 듣기' }))
  expect(speak).toHaveBeenCalledOnce()
  expect(speak.mock.calls[0][0]).toMatchObject({ text: '첫 질문입니다.', lang: 'ko-KR', rate: 0.75, volume: 0.5 })
})

function synthesis() {
  const speak = vi.fn(), cancel = vi.fn()
  vi.stubGlobal('speechSynthesis', { speak, cancel })
  vi.stubGlobal('SpeechSynthesisUtterance', class { text: string; onerror: ((event: { error: string }) => void) | null = null; constructor(text: string) { this.text = text } })
  return { speak, cancel }
}

it('reports a synchronous speech failure with fixed text and keeps controls usable', async () => {
  const { speak } = synthesis()
  speak.mockImplementation(() => { throw new Error('private-device-path') })
  render(<QuestionAudio question="첫 질문" journeyId="test" messageId={null} />)
  await userEvent.click(screen.getByRole('button', { name: '다시 듣기' }))
  expect(screen.getByRole('alert')).toHaveTextContent('화면의 글을 확인해 주세요.')
  expect(document.body).not.toHaveTextContent('private')
  expect(screen.getByRole('button', { name: '천천히 듣기' })).toBeEnabled()
})

it('stops browser speech on departure and ignores errors from the replaced utterance', async () => {
  const { speak, cancel } = synthesis()
  render(<QuestionAudio question="첫 질문" journeyId="test" messageId={null} />)
  await userEvent.click(screen.getByRole('button', { name: '다시 듣기' }))
  const old = speak.mock.calls[0][0]
  const lateFailure = old.onerror
  await userEvent.click(screen.getByRole('button', { name: '천천히 듣기' }))
  expect(cancel).toHaveBeenCalledTimes(1)
  act(() => lateFailure({ error: 'synthesis-failed' }))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  fireEvent(window, new Event('pagehide'))
  expect(cancel).toHaveBeenCalledTimes(2)
  expect(speak.mock.calls[1][0].onerror).toBeNull()
})

function serverAudio() {
  const players: HTMLAudioElement[] = []
  vi.stubGlobal('Audio', class { constructor() { const player = document.createElement('audio'); players.push(player); return player } })
  vi.spyOn(HTMLMediaElement.prototype, 'load').mockImplementation(() => {})
  const revoke = vi.fn()
  vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: vi.fn(() => 'blob:question'), revokeObjectURL: revoke }))
  document.cookie = '__Host-rc_csrf=token; Path=/; Secure'
  const fetch = vi.fn(async (request: Request) => request.url.endsWith('/me')
    ? new Response(JSON.stringify({ ...anonymousSession, consents: [{ purpose: 'ai_processing', notice_version: 'v1', granted_at: '2026-10-30T00:00:00Z' }] }), { headers: { 'Content-Type': 'application/json' } })
    : new Response('wave', { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '2' } }))
  vi.stubGlobal('fetch', fetch)
  const view = render(<QuestionAudio question="질문" journeyId="12345678-1234-1234-1234-123456789012" messageId="12345678-1234-1234-1234-123456789013" />)
  return { players, revoke, fetch, view }
}

it('announces a playback error after play has already succeeded and releases audio on stop', async () => {
  const { players, revoke } = serverAudio()
  await userEvent.click(screen.getByRole('button', { name: '다시 듣기' }))
  await screen.findByRole('button', { name: '다음 부분 듣기' })
  expect(players).toHaveLength(1)
  fireEvent.error(players[0])
  expect(screen.getByRole('alert')).toHaveTextContent('소리를 재생하지 못했습니다.')
  await userEvent.click(screen.getByRole('button', { name: '듣기 중지' }))
  expect(players[0].onerror).toBeNull()
  expect(revoke).toHaveBeenCalledWith('blob:question')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('releases the previous player before waiting for a replacement and allows cancellation', async () => {
  const { players, revoke, fetch } = serverAudio()
  await userEvent.click(screen.getByRole('button', { name: '다시 듣기' }))
  await screen.findByRole('button', { name: '다음 부분 듣기' })
  const previousError = players[0].onerror
  fetch.mockImplementation(() => new Promise<Response>(() => {}))
  await userEvent.click(screen.getByRole('button', { name: '천천히 듣기' }))
  expect(revoke).toHaveBeenCalledWith('blob:question')
  expect(players[0].getAttribute('src')).toBeNull()
  act(() => previousError?.call(players[0], new Event('error')))
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '듣기 중지' }))
  expect(screen.getByRole('button', { name: '다시 듣기' })).toBeEnabled()
})
