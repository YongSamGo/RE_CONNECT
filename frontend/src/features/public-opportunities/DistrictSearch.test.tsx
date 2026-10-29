import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { PublicOpportunities } from './PublicOpportunities'
import { sampleList, sampleOpportunity } from './test-fixtures'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount() {
  render(<MemoryRouter><PublicOpportunities /></MemoryRouter>)
  return userEvent.setup()
}
const search = (user: ReturnType<typeof userEvent.setup>) => user.click(screen.getByRole('button', { name: '공고 검색하기' }))

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
it('applies selected districts and reuses that snapshot for pagination',async()=>{
  const fetch=vi.fn(async(request:Request)=>json(sampleList({page:Number(new URL(request.url).searchParams.get('page')),total:21})))
  vi.stubGlobal('fetch',fetch);const user=mount()
  await user.click(screen.getByRole('button',{name:'종로구'}));await user.click(screen.getByRole('button',{name:'중구'}))
  expect(fetch).not.toHaveBeenCalled();await search(user);await screen.findByText('공개 공고 검색 결과')
  expect(screen.queryByRole('button',{name:'종로구 선택됨'})).not.toBeInTheDocument()
  await user.click(screen.getByRole('button',{name:'다음 페이지'}))
  await waitFor(()=>expect(screen.getByRole('status')).toHaveTextContent('2페이지'))
  for(const [request] of fetch.mock.calls) expect(new URL(request.url).searchParams.getAll('regions')).toEqual(['seoul:jongno','seoul:jung'])
})
it('preserves district choices when returning to conditions and applies only the next explicit search',async()=>{
  const fetch=vi.fn(async(_request:Request)=>json(sampleList()));vi.stubGlobal('fetch',fetch);const user=mount()
  await user.click(screen.getByRole('button',{name:'종로구'}));await search(user);await screen.findByText('공개 공고 검색 결과')
  await user.click(screen.getByRole('button',{name:'검색 조건 선택'}))
  expect(screen.getByRole('button',{name:'종로구 선택됨'})).toHaveAttribute('aria-pressed','true')
  await user.click(screen.getByRole('button',{name:'김포/인천 지도 보기'}));await user.click(screen.getByRole('button',{name:'김포시'}))
  expect(fetch).toHaveBeenCalledTimes(1);await search(user)
  await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2))
  expect(new URL(fetch.mock.calls[1][0].url).searchParams.getAll('regions')).toEqual(['seoul:jongno','gyeonggi:gimpo'])
})
it.each([503,400])('retries the same narrowed districts after %s without broadening the request',async status=>{
  const fetch=vi.fn(async(_request:Request)=>json({code:status===503?'SERVICE_UNAVAILABLE':'INVALID_REQUEST',message:'private failure'},status))
  vi.stubGlobal('fetch',fetch);const user=mount();await user.click(screen.getByRole('button',{name:'종로구'}));await search(user)
  await screen.findByRole('alert');expect(document.body).not.toHaveTextContent('private failure')
  await user.click(screen.getByRole('button',{name:'다시 시도하기'}));await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(2))
  expect(fetch.mock.calls[0][0].url).toBe(fetch.mock.calls[1][0].url)
  await user.click(screen.getByRole('button',{name:'검색 조건 선택'}))
  expect(screen.getByRole('button',{name:'종로구 선택됨'})).toHaveAttribute('aria-pressed','true')
})
it.each(['cancel','pagehide'])('aborts district lookup and discards late results on %s',async kind=>{
  let finish!:(response:Response)=>void
  const fetch=vi.fn((_request:Request)=>new Promise<Response>(resolve=>{finish=resolve}))
  vi.stubGlobal('fetch',fetch);const user=mount();await user.click(screen.getByRole('button',{name:'종로구'}));await search(user)
  if(kind==='cancel')await user.click(screen.getByRole('button',{name:'조회 취소하기'}));else act(()=>window.dispatchEvent(new Event('pagehide')))
  expect(fetch.mock.calls[0][0].signal.aborted).toBe(true)
  await act(async()=>finish(json(sampleList({items:[sampleOpportunity({title:'늦은 결과'})]}))))
  expect(screen.queryByRole('heading',{name:'늦은 결과'})).not.toBeInTheDocument()
})
it('rejects hostile district data rather than rendering it as HTML',async()=>{
  const fetch=vi.fn(async(_request:Request)=>json(sampleList({items:[sampleOpportunity({activity_region:{province:'seoul',district:'<img src=x>'}})]})))
  vi.stubGlobal('fetch',fetch);const user=mount();await user.click(screen.getByRole('button',{name:'종로구'}));await search(user)
  expect(await screen.findByRole('alert')).toBeVisible();expect(document.querySelector('img,script')).toBeNull()
  expect(new URL(fetch.mock.calls[0][0].url).searchParams.get('regions')).toBe('seoul:jongno')
})
