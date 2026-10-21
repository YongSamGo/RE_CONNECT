import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PublicOpportunities } from './PublicOpportunities'
import { sampleList } from './test-fixtures'

const catalog = { version: 'test-v1', provinces: [{ id: 'seoul', name: '서울', districts: [{ id: 'test_first', name: '가상첫구' }, { id: 'test_second', name: '가상둘구' }] }] }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount() { render(<MemoryRouter><PublicOpportunities /></MemoryRouter>); return userEvent.setup() }
async function choose(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByLabelText('활동 지역'), 'seoul')
  await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
  await screen.findByRole('option', { name: '가상첫구' })
  await user.selectOptions(screen.getByLabelText('시·군·구'), 'test_first')
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('district search and applied filter snapshots', () => {
  it('sends only allowed public filters and retains applied district/name/version for pagination', async () => {
    let regionCalls = 0
    const fetch = vi.fn(async (request: Request) => {
      const url = new URL(request.url)
      return json(url.pathname.endsWith('/regions') ? ++regionCalls === 1 ? catalog : { ...catalog, version: 'test-v2', provinces: [{ ...catalog.provinces[0], districts: [{ id: 'test_first', name: '이름 변경구' }, catalog.provinces[0]!.districts[1]] }] } : sampleList({ page: Number(url.searchParams.get('page')), total: 21 }))
    }); vi.stubGlobal('fetch', fetch)
    const write = vi.spyOn(Storage.prototype, 'setItem')
    const user = mount()
    expect(fetch).not.toHaveBeenCalled()
    await choose(user)
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(fetch.mock.calls[0]![0].url).toBe('https://reconnect.test/api/v1/regions')
    await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
    expect(await screen.findByText('적용한 조건: 검색어 전체 · 서울 / 가상첫구 · 활동 유형 전체')).toBeVisible()
    expect(screen.getByText('검색에 적용한 지역 목록 버전: test-v1')).toBeVisible()
    expect(Object.fromEntries(new URL(fetch.mock.calls[1]![0].url).searchParams)).toEqual({ page: '1', page_size: '20', province: 'seoul', district: 'test_first' })
    await user.selectOptions(screen.getByLabelText('시·군·구'), 'test_second')
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 새로 불러오기' }))
    await screen.findByRole('option', { name: '이름 변경구' })
    await user.click(screen.getByRole('button', { name: '다음 페이지' }))
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('2페이지'))
    expect(new URL(fetch.mock.calls[3]![0].url).searchParams.get('district')).toBe('test_first')
    expect(screen.getByText(/적용한 조건:/)).toHaveTextContent('서울 / 가상첫구')
    expect(screen.getByText('검색에 적용한 지역 목록 버전: test-v1')).toBeVisible()
    expect(write).not.toHaveBeenCalled()
    expect(window.location.search).toBe('')
    expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
  })
  it('clears district only on an explicit province change and restarts the next search at page one', async () => {
    const fetch = vi.fn(async (request: Request) => json(new URL(request.url).pathname.endsWith('/regions') ? catalog : sampleList()))
    vi.stubGlobal('fetch', fetch)
    const user = mount(); await choose(user)
    await user.selectOptions(screen.getByLabelText('활동 지역'), 'incheon')
    expect(screen.getByLabelText('시·군·구')).toHaveValue('')
    await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
    await screen.findByText('공개 공고 검색 결과')
    expect(Object.fromEntries(new URL(fetch.mock.calls[1]![0].url).searchParams)).toEqual({ page: '1', page_size: '20', province: 'incheon' })
  })
  it.each(['failure', 'removed'])('preserves a district on catalog %s and blocks silently broader searches', async (kind) => {
    let regionCalls = 0
    const fetch = vi.fn(async (request: Request) => {
      if (!new URL(request.url).pathname.endsWith('/regions')) return json(sampleList())
      if (++regionCalls === 1) return json(catalog)
      return kind === 'failure' ? json({ code: 'SERVICE_UNAVAILABLE', message: 'private catalog failure' }, 503) : json({ version: 'test-v2', provinces: [] })
    }); vi.stubGlobal('fetch', fetch)
    const user = mount(); await choose(user)
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 새로 불러오기' }))
    expect(await screen.findByRole('option', { name: '가상첫구 · 목록 대조 필요' })).toBeVisible()
    expect(screen.getByLabelText('시·군·구')).toHaveValue('test_first')
    await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
    expect(fetch).toHaveBeenCalledTimes(2)
    await user.click(screen.getByRole('link', { name: /시·군·구 목록을 다시 불러와/ }))
    expect(screen.getByLabelText('시·군·구')).toHaveFocus()
    expect(document.body).not.toHaveTextContent('private catalog failure')
    await user.selectOptions(screen.getByLabelText('시·군·구'), '')
    await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
    await screen.findByText('공개 공고 검색 결과')
    expect(new URL(fetch.mock.calls[2]![0].url).searchParams.has('district')).toBe(false)
  })
  it('retries the failed applied district rather than newer draft filters', async () => {
    let searches = 0
    const fetch = vi.fn(async (request: Request) => new URL(request.url).pathname.endsWith('/regions') ? json(catalog) : ++searches === 1 ? json({ code: 'SERVICE_UNAVAILABLE' }, 503) : json(sampleList()))
    vi.stubGlobal('fetch', fetch)
    const user = mount(); await choose(user)
    await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
    await screen.findByRole('button', { name: '같은 조건으로 다시 조회' })
    await user.selectOptions(screen.getByLabelText('활동 지역'), 'gyeonggi')
    await user.click(screen.getByRole('button', { name: '같은 조건으로 다시 조회' }))
    await screen.findByText('공개 공고 검색 결과')
    expect(Object.fromEntries(new URL(fetch.mock.calls[2]![0].url).searchParams)).toEqual({ page: '1', page_size: '20', province: 'seoul', district: 'test_first' })
    expect(screen.getByText(/적용한 조건:/)).toHaveTextContent('서울 / 가상첫구')
  })
  it.each(['cancel', 'pagehide'])('discards late region results after %s', async (kind) => {
    let finish!: (value: Response) => void
    const fetch = vi.fn((_request: Request) => new Promise<Response>((resolve) => { finish = resolve })); vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    expect(screen.getByRole('button', { name: '공고 검색하기' })).toBeDisabled()
    if (kind === 'cancel') await user.click(screen.getByRole('button', { name: '지역 목록 조회 취소' }))
    else act(() => window.dispatchEvent(new Event('pagehide')))
    expect(fetch.mock.calls[0]![0].signal.aborted).toBe(true)
    await act(async () => finish(json(catalog)))
    expect(screen.queryByText('지역 목록 버전: test-v1')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '공고 검색하기' })).toBeEnabled()
  })
  it('renders hostile district names literally in options and applied conditions', async () => {
    const name = '<img src=x>'
    const fetch = vi.fn(async (request: Request) => json(new URL(request.url).pathname.endsWith('/regions') ? { ...catalog, provinces: [{ ...catalog.provinces[0], districts: [{ id: 'test_first', name }] }] } : sampleList()))
    vi.stubGlobal('fetch', fetch)
    const user = mount()
    await user.selectOptions(screen.getByLabelText('활동 지역'), 'seoul')
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    await screen.findByRole('option', { name })
    await user.selectOptions(screen.getByLabelText('시·군·구'), 'test_first')
    await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
    expect(await screen.findByText(`적용한 조건: 검색어 전체 · 서울 / ${name} · 활동 유형 전체`)).toBeVisible()
    expect(document.querySelector('img, script')).toBeNull()
  })
})
