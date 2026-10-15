import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { ReadAloud } from './ReadAloud'

const target = { kind: 'opportunity', opportunity_id: '12345678-1234-1234-1234-123456789012', version: 2, field: 'title' } as const
const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('read aloud consent and resources', () => {
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
    const fetch = vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { headers: { 'Content-Type': 'audio/wav' } }))
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
