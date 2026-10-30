import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { ReadAloud } from './ReadAloud'

const target = { kind: 'opportunity', opportunity_id: '12345678-1234-1234-1234-123456789012', version: 2, field: 'title' } as const
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('read aloud consent and resources', () => {
  it('handles synchronous playback failure and releases the URL even when player cleanup throws', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response('RIFF', { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '1' } })))
    const revoke = vi.fn()
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: () => 'blob:failed-player', revokeObjectURL: revoke }))
    vi.stubGlobal('Audio', class {
      onended = null; onerror = null
      play() { throw new Error('private-playback') }
      pause() { throw new Error('private-pause') }
      removeAttribute() {}
      load() { throw new Error('private-load') }
    })
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    await userEvent.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('소리를 재생하지 못했어요')
    await userEvent.click(screen.getByRole('button', { name: '읽어주기 중지' }))
    expect(revoke).toHaveBeenCalledWith('blob:failed-player')
    expect(document.body).not.toHaveTextContent('private')
  })
  it('keeps a failed player stopped if its pending play promise resolves after the error event', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response('RIFF', { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '1' } })))
    vi.stubGlobal('URL', Object.assign(class extends URL {}, { createObjectURL: () => 'blob:late-play', revokeObjectURL: vi.fn() }))
    let finish!: () => void, fail!: () => void
    vi.stubGlobal('Audio', class {
      onended = null
      set onerror(handler: (() => void) | null) { if (handler) fail = handler }
      play() { return new Promise<void>(resolve => { finish = resolve }) }
      pause() {}; removeAttribute() {}; load() {}
    })
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    await userEvent.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    await screen.findByText(/1개 부분 중 1번째 부분/)
    act(() => fail())
    await act(async () => finish())
    expect(screen.getByRole('button', { name: '제목 읽어주기' })).toBeEnabled()
    expect(screen.getByRole('alert')).toHaveTextContent('소리를 재생하지 못했어요')
  })
  it('requires reloading the source after a version conflict', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response(JSON.stringify({ code: 'VERSION_CONFLICT', message: 'private version' }), { status: 409, headers: { 'Content-Type': 'application/json' } }))
    vi.stubGlobal('fetch', fetch)
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    await userEvent.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByText(/자료가 바뀌었어요/)).toBeVisible()
    expect(screen.getByRole('button', { name: '제목 읽어주기' })).toBeDisabled()
    expect(document.body).not.toHaveTextContent('private version')
  })
  it('requests each segment explicitly, preserves the target and uses a fresh key per request', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '2' } }))
    vi.stubGlobal('fetch', fetch)
    const players: { onended: (() => void) | null }[] = []
    vi.stubGlobal('Audio', class { constructor() { players.push(this) }; play = () => Promise.resolve(); pause = vi.fn(); load = vi.fn(); removeAttribute = vi.fn(); onended = null; onerror = null })
    const NativeURL = URL
    vi.stubGlobal('URL', Object.assign(class extends NativeURL {}, { createObjectURL: () => 'blob:speech', revokeObjectURL: vi.fn() }))
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByRole('button', { name: '다음 부분 읽어주기' })).toBeDisabled()
    expect(fetch).toHaveBeenCalledTimes(2)
    act(() => players[0]!.onended!())
    expect(fetch).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('button', { name: '다음 부분 읽어주기' }))
    expect(await screen.findByText(/2개 부분 중 2번째 부분/)).toBeVisible()
    const posts = fetch.mock.calls.map(([request]) => request).filter((request) => request.method === 'POST')
    expect(await posts[0]!.json()).toEqual({ target, segment: 0 })
    expect(await posts[1]!.json()).toEqual({ target, segment: 1 })
    expect(posts[0]!.headers.get('Idempotency-Key')).not.toBe(posts[1]!.headers.get('Idempotency-Key'))
    expect(screen.queryByRole('button', { name: '다음 부분 읽어주기' })).not.toBeInTheDocument()
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(screen.queryByText(/개 부분 중/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByText(/2개 부분 중 1번째 부분/)).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(6)
  })
  it.each([null, '0', '1.5', '9007199254740992', 'private count'])('rejects missing or invalid segment counts %s before playback', async (count) => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { headers: { 'Content-Type': 'audio/wav', ...(count ? { 'X-Speech-Segment-Count': count } : {}) } })))
    const audio = vi.fn(); vi.stubGlobal('Audio', audio)
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    await userEvent.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(audio).not.toHaveBeenCalled()
    expect(document.body).not.toHaveTextContent('private count')
  })
  it('does not request speech without server-confirmed AI consent', async () => {
    const fetch = vi.fn(async () => json({ ...anonymousSession, consents: [] }))
    vi.stubGlobal('fetch', fetch)
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    expect(fetch).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('동의 상태를 확인해 주세요.')
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it('sends only the source reference, handles playback failure, and revokes audio on stop', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '1' } }))
    vi.stubGlobal('fetch', fetch)
    const pause = vi.fn(), load = vi.fn(), removeAttribute = vi.fn()
    vi.stubGlobal('Audio', class { play = () => Promise.reject(new Error('private playback')); pause = pause; load = load; removeAttribute = removeAttribute; onended = null; onerror = null })
    const revoke = vi.fn()
    const NativeURL = URL
    vi.stubGlobal('URL', Object.assign(class extends NativeURL {}, { createObjectURL: () => 'blob:speech', revokeObjectURL: revoke }))
    render(<ReadAloud target={target} label="제목 읽어주기" />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '제목 읽어주기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('소리를 재생하지 못했어요')
    expect(document.body).not.toHaveTextContent('private playback')
    const post = fetch.mock.calls.find(([request]) => request.method === 'POST')![0]
    expect(await post.json()).toEqual({ target, segment: 0 })
    await user.click(screen.getByRole('button', { name: '읽어주기 중지' }))
    expect(pause).toHaveBeenCalled()
    expect(revoke).toHaveBeenCalledWith('blob:speech')
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(screen.queryByRole('button', { name: '읽어주기 중지' })).not.toBeInTheDocument()
  })
})
