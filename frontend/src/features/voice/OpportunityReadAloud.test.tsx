import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { sampleDetail } from '../public-opportunities/test-fixtures'
import { OpportunityReadAloud } from './OpportunityReadAloud'

const json = (value: unknown) => new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('opportunity speech field selection', () => {
  it('offers only present allowed fields and aborts stale consent checks on selection', async () => {
    let complete!: (value: Response) => void
    const fetch = vi.fn((_request: Request) => new Promise<Response>((resolve) => { complete = resolve }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReadAloud item={sampleDetail({ description_text: '공식 설명', schedule_text: ' ', location_text: null })} />)
    expect(screen.getAllByRole('option').map((option) => option.textContent)).toEqual(['공고 제목', '공식 원문 설명', '접수 안내'])
    expect(fetch).not.toHaveBeenCalled()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '공고 제목 읽어주기' }))
    await user.selectOptions(screen.getByLabelText('읽을 항목'), 'description_text')
    expect(fetch.mock.calls[0]![0].signal.aborted).toBe(true)
    await act(async () => complete(json(anonymousSession)))
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '공식 원문 설명 읽어주기' })).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
  it('sends selected versioned reference only and releases playing audio when changing fields', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET' ? json(anonymousSession) : new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '1' } }))
    vi.stubGlobal('fetch', fetch)
    const pause = vi.fn(), revoke = vi.fn()
    vi.stubGlobal('Audio', class { play = () => Promise.resolve(); pause = pause; load = vi.fn(); removeAttribute = vi.fn(); onended = null; onerror = null })
    const NativeURL = URL
    vi.stubGlobal('URL', Object.assign(class extends NativeURL {}, { createObjectURL: () => 'blob:opportunity-speech', revokeObjectURL: revoke }))
    const item = sampleDetail({ description_text: '공식 설명' })
    render(<OpportunityReadAloud item={item} />)
    const user = userEvent.setup()
    await user.selectOptions(screen.getByLabelText('읽을 항목'), 'application_instructions')
    await user.click(screen.getByRole('button', { name: '접수 안내 읽어주기' }))
    expect(await screen.findByText('읽어주기를 재생하고 있어요.')).toBeVisible()
    const post = fetch.mock.calls.find(([request]) => request.method === 'POST')![0]
    expect(await post.json()).toEqual({ target: { kind: 'opportunity', opportunity_id: item.id, version: item.version, field: 'application_instructions' }, segment: 0 })
    await user.selectOptions(screen.getByLabelText('읽을 항목'), 'description_text')
    expect(pause).toHaveBeenCalled()
    expect(revoke).toHaveBeenCalledWith('blob:opportunity-speech')
    expect(fetch).toHaveBeenCalledTimes(2)
    expect(screen.queryByText(/개 부분 중/)).not.toBeInTheDocument()
  })
})
