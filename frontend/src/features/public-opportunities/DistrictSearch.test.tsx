import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PublicOpportunities } from './PublicOpportunities'
import { sampleList, sampleOpportunity } from './test-fixtures'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount() {
  render(<MemoryRouter><PublicOpportunities /></MemoryRouter>)
  return userEvent.setup()
}
const search = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole('button', { name: '공고 검색하기' }))

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('map district search and applied filter snapshots', () => {
  it('sends only selected public filters and preserves applied districts during pagination', async () => {
    const fetch = vi.fn(async (request: Request) => json(sampleList({ page: Number(new URL(request.url).searchParams.get('page')), total: 21 })))
    vi.stubGlobal('fetch', fetch)
    const write = vi.spyOn(Storage.prototype, 'setItem')
    const user = mount()
    await user.click(screen.getByRole('button', { name: '종로구' }))
    await user.click(screen.getByRole('button', { name: '중구' }))
    expect(fetch).not.toHaveBeenCalled()
    await search(user)
    await screen.findByText('공개 공고 검색 결과')
    const request = fetch.mock.calls[0]![0]
    expect(new URL(request.url).pathname).toBe('/api/v1/opportunities')
    expect([...new URL(request.url).searchParams]).toEqual([['page', '1'], ['page_size', '20'], ['regions', 'seoul:jongno'], ['regions', 'seoul:jung']])
    await user.click(screen.getByRole('button', { name: '종로구 선택됨' }))
    await user.click(screen.getByRole('button', { name: '다음 페이지' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('2페이지'))
    expect(new URL(fetch.mock.calls[1]![0].url).searchParams.getAll('regions')).toEqual(['seoul:jongno', 'seoul:jung'])
    expect(write).not.toHaveBeenCalled()
    expect(window.location.search).toBe('')
    expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
  })

  it('retains individual selections across maps and applies changed districts only to a new search', async () => {
    const fetch = vi.fn(async (_request: Request) => json(sampleList()))
    vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.click(screen.getByRole('button', { name: '종로구' }))
    await search(user)
    await screen.findByText('공개 공고 검색 결과')
    await user.click(screen.getByRole('button', { name: '김포/인천 지도 보기' }))
    await user.click(screen.getByRole('button', { name: '김포시' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    await search(user)
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect([...new URL(fetch.mock.calls[1]![0].url).searchParams]).toEqual([['page', '1'], ['page_size', '20'], ['regions', 'seoul:jongno'], ['regions', 'gyeonggi:gimpo']])
  })

  it.each([503, 400])('preserves selected districts after a %s response without broadening the retry', async (status) => {
    const fetch = vi.fn(async (_request: Request) => json({ code: status === 503 ? 'SERVICE_UNAVAILABLE' : 'INVALID_REQUEST', message: 'private district failure' }, status))
    vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.click(screen.getByRole('button', { name: '종로구' }))
    await search(user)
    await screen.findByRole('alert')
    expect(screen.getByRole('button', { name: '종로구 선택됨' })).toHaveAttribute('aria-pressed', 'true')
    expect(document.body).not.toHaveTextContent('private district failure')
    await user.click(screen.getByRole('button', { name: '다시 시도하기' }))
    await waitFor(() => expect(fetch).toHaveBeenCalledTimes(2))
    expect(fetch.mock.calls[1]![0].url).toBe(fetch.mock.calls[0]![0].url)
    expect(new URL(fetch.mock.calls[1]![0].url).searchParams.get('regions')).toBe('seoul:jongno')
  })

  it('retries applied districts rather than newer map selections', async () => {
    const fetch = vi.fn(async (_request: Request) => json({ code: 'SERVICE_UNAVAILABLE' }, 503))
      .mockImplementationOnce(async () => json({ code: 'SERVICE_UNAVAILABLE' }, 503))
      .mockImplementationOnce(async () => json(sampleList()))
    vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.click(screen.getByRole('button', { name: '종로구' }))
    await search(user)
    await screen.findByRole('alert')
    await user.click(screen.getByRole('button', { name: '종로구 선택됨' }))
    await user.click(screen.getByRole('button', { name: '중구' }))
    await user.click(screen.getByRole('button', { name: '다시 시도하기' }))
    await screen.findByText('공개 공고 검색 결과')
    expect(new URL(fetch.mock.calls[1]![0].url).searchParams.get('regions')).toBe('seoul:jongno')
    expect(screen.getByRole('button', { name: '중구 선택됨' })).toHaveAttribute('aria-pressed', 'true')
  })

  it.each(['cancel', 'pagehide'])('aborts district searches and discards late results after %s', async (kind) => {
    let finish!: (value: Response) => void
    const fetch = vi.fn((_request: Request) => new Promise<Response>((resolve) => { finish = resolve }))
    vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.click(screen.getByRole('button', { name: '종로구' }))
    await search(user)
    expect(screen.getByRole('button', { name: '공고를 불러오고 있어요' })).toBeDisabled()
    if (kind === 'cancel') await user.click(screen.getByRole('button', { name: '조회 취소하기' }))
    else act(() => window.dispatchEvent(new Event('pagehide')))
    expect(fetch.mock.calls[0]![0].signal.aborted).toBe(true)
    await act(async () => finish(json(sampleList({ items: [sampleOpportunity({ title: '취소된 지역 검색 결과' })] }))))
    expect(screen.queryByRole('heading', { name: '취소된 지역 검색 결과' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '공고 검색하기' })).toBeEnabled()
  })

  it('rejects hostile district data without rendering HTML or clearing the selected filter', async () => {
    const fetch = vi.fn(async (_request: Request) => json(sampleList({ items: [sampleOpportunity({ activity_region: { province: 'seoul', district: '<img src=x>' } })] })))
    vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.click(screen.getByRole('button', { name: '종로구' }))
    await search(user)
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(document.querySelector('img, script')).toBeNull()
    expect(screen.getByRole('button', { name: '종로구 선택됨' })).toHaveAttribute('aria-pressed', 'true')
    expect(new URL(fetch.mock.calls[0]![0].url).searchParams.get('regions')).toBe('seoul:jongno')
  })
})
