import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { PublicOpportunityDetail } from './PublicOpportunityDetail'
import { sampleDetail, sourceUrl } from './test-fixtures'

const id = sampleDetail().id
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount(path = id) {
  return render(<MemoryRouter initialEntries={[`/opportunities/${path}`]}><Link to="/opportunities/12345678-1234-1234-1234-123456789002">다른 공고</Link><Routes><Route path="/opportunities/:id" element={<PublicOpportunityDetail />} /></Routes></MemoryRouter>)
}
afterEach(()=>{vi.restoreAllMocks();vi.unstubAllGlobals()})
async function loaded(){await screen.findByRole('heading',{name:'가상 도서 정리 봉사'})}
it('automatically reads one public detail and keeps long content in disclosure blocks',async()=>{
  const fetch=vi.fn(async(_request:Request)=>json(sampleDetail()));vi.stubGlobal('fetch',fetch);mount();await loaded()
  expect(fetch).toHaveBeenCalledTimes(1);expect(fetch.mock.calls[0][0].method).toBe('GET')
  const block=document.querySelector('details')!;expect(block.open).toBe(false)
  for(const detail of document.querySelectorAll('details')) detail.open=true
  expect(screen.getByText('필요 서류 확인 필요')).toBeVisible()
  const link=screen.getByRole('link',{name:/공식 원문 확인/})
  expect(link).toHaveAttribute('href',sourceUrl);expect(link).toHaveAttribute('rel','noopener noreferrer')
  expect(link).toHaveAttribute('referrerpolicy','no-referrer');expect(link).not.toHaveTextContent('https://')
  expect(screen.getByRole('link',{name:'다른 공고 둘러보기'})).toHaveAttribute('href','/opportunities?browse=all')
  expect(screen.getByRole('link',{name:'공고 검색하기'})).toHaveAttribute('href','/opportunities')
  expect(screen.queryByText('공고 정보 오류 알리기')).not.toBeInTheDocument()
})
it.each(['preview','not-a-uuid'])('rejects invalid route %s before requesting',path=>{
  const fetch=vi.fn();vi.stubGlobal('fetch',fetch);mount(path)
  expect(screen.getByRole('heading',{name:'공고 주소를 확인해 주세요'})).toBeVisible();expect(fetch).not.toHaveBeenCalled()
})
it.each([{recruitment_status:'closed' as const},{recruitment_status:'unknown' as const},{change_pending:true}])('withholds application links when unavailable %j',async changes=>{
  vi.stubGlobal('fetch',vi.fn(async()=>json(sampleDetail(changes))));mount();await loaded()
  expect(screen.getByRole('link',{name:/공식 원문 확인/})).toBeVisible()
  expect(screen.queryByRole('link',{name:/^지원하기/})).not.toBeInTheDocument()
})
it('renders hostile content literally and withholds unapproved URLs',async()=>{
  const attack='<img src=x onerror=alert(1)>'
  vi.stubGlobal('fetch',vi.fn(async()=>json(sampleDetail({title:attack,description_text:attack,source_url:'javascript:alert(1)',application_url:'https://evil.example/'}))))
  const {container}=mount();await screen.findByRole('heading',{name:attack})
  for(const detail of document.querySelectorAll('details'))detail.open=true
  expect(screen.getAllByText(attack).length).toBeGreaterThan(0);expect(container.querySelector('img,script')).toBeNull()
  expect(screen.queryByRole('link',{name:/공식 원문 확인/})).not.toBeInTheDocument()
})
it.each([404,429,503])('handles %s with fixed text and no automatic repeated request',async status=>{
  const fetch=vi.fn(async(_request:Request)=>json({code:status===404?'NOT_FOUND':status===429?'DAILY_QUOTA_EXCEEDED':'SERVICE_UNAVAILABLE',message:'private failure'},status))
  vi.stubGlobal('fetch',fetch);mount();expect(await screen.findByRole('alert')).toBeVisible()
  expect(document.body).not.toHaveTextContent('private failure');expect(fetch).toHaveBeenCalledTimes(1)
  if(status!==503)expect(screen.queryByRole('button',{name:'공고 다시 조회'})).not.toBeInTheDocument()
})
it.each(['cancel','pagehide','restore','unmount'])('discards late private request state after %s',async kind=>{
  let finish!:(response:Response)=>void
  const fetch=vi.fn((_request:Request)=>new Promise<Response>(resolve=>{finish=resolve}));vi.stubGlobal('fetch',fetch)
  const page=mount();await act(async()=>{})
  if(kind==='cancel')await userEvent.click(screen.getByRole('button',{name:'조회 취소하기'}))
  if(kind==='pagehide')act(()=>window.dispatchEvent(new Event('pagehide')))
  if(kind==='restore')act(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})))
  if(kind==='unmount')page.unmount()
  await act(async()=>finish(json(sampleDetail())))
  expect(screen.queryByRole('heading',{name:'가상 도서 정리 봉사'})).not.toBeInTheDocument()
  expect(fetch.mock.calls[0][0].signal.aborted).toBe(true)
})
it('automatically starts a new route lookup and discards the preceding response',async()=>{
  let finish!:(response:Response)=>void
  const fetch=vi.fn((_request:Request)=>new Promise<Response>(resolve=>{finish=resolve})).mockImplementationOnce(()=>new Promise<Response>(resolve=>{finish=resolve})).mockImplementationOnce(async()=>json(sampleDetail({id:'12345678-1234-1234-1234-123456789002',title:'다음 공고'})))
  vi.stubGlobal('fetch',fetch);mount();await act(async()=>{})
  await userEvent.click(screen.getByRole('link',{name:'다른 공고'}));expect(await screen.findByRole('heading',{name:'다음 공고'})).toBeVisible()
  await act(async()=>finish(json(sampleDetail())))
  expect(screen.queryByRole('heading',{name:'가상 도서 정리 봉사'})).not.toBeInTheDocument()
})
it('rejects another opportunity and permits an explicit retry',async()=>{
  const fetch=vi.fn(async(_request:Request)=>json(sampleDetail())).mockImplementationOnce(async()=>json(sampleDetail({id:'12345678-1234-1234-1234-123456789002'})))
  vi.stubGlobal('fetch',fetch);mount();await screen.findByRole('alert')
  await userEvent.click(screen.getByRole('button',{name:'공고 다시 조회'}));await loaded();expect(fetch).toHaveBeenCalledTimes(2)
})
it('shows the reviewed skill tags that recommendations compare with profile experience',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>json(sampleDetail({skill_tags:['청소','<b>미화</b>']}))));mount();await loaded()
  const section=screen.getByRole('region',{name:'이런 경험과 연결돼요'})
  expect(section).toHaveTextContent('청소');expect(section).toHaveTextContent('<b>미화</b>')
  expect(section.querySelector('b')).toBeNull()
})
it('says skills are being checked when a reviewed opportunity has no skill tags yet',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>json(sampleDetail({skill_tags:[]}))));mount();await loaded()
  expect(screen.getByText('연결할 경험을 확인하고 있어요.')).toBeVisible()
})
