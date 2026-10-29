import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { OfficialPreparation } from './OfficialPreparation'
import { parsePreparation, type Preparation } from './official'
import { sourceUrl } from '../public-opportunities/test-fixtures'

const id = '12345678-1234-1234-1234-123456789001'
function sample(changes: Partial<Preparation> = {}): Preparation {
  return { opportunity: { id, version: 1 }, application_method: 'online', application_instructions: '공식 원문을 읽고 접수하세요.', application_url: sourceUrl, source_url: sourceUrl, required_documents: ['공고에 명시된 시험 서류'], deadline_date: '2099-10-31', deadline_at: null, recruitment_status: 'open', change_pending: false, ...changes }
}
function response(data: unknown) { return new Response(JSON.stringify(data), { headers: { 'Content-Type': 'application/json' } }) }
function mount(pathId = id) {
  return render(<MemoryRouter initialEntries={[`/opportunities/${pathId}/preparation`]}><Routes><Route path="/opportunities/:id/preparation" element={<OfficialPreparation />} /><Route path="/opportunities/:id" element={<h1>공고 상세</h1>} /></Routes></MemoryRouter>)
}
async function load() { await userEvent.click(screen.getByRole('button', { name: '공식 신청 안내 확인' })) }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('never supplies the previous application link while a different opportunity is loading or fails', async () => {
  const nextId = '12345678-1234-1234-1234-123456789002'
  let fail!: (reason: Error) => void
  const fetch = vi.fn().mockResolvedValueOnce(response(sample())).mockImplementationOnce(() => new Promise<Response>((_, reject) => { fail = reject }))
  vi.stubGlobal('fetch', fetch)
  const page = (opportunityId: string) => <MemoryRouter><OfficialPreparation opportunityId={opportunityId} withDraft>{url => url ? <a href={url}>현재 신청처</a> : <p>신청처 확인 대기</p>}</OfficialPreparation></MemoryRouter>
  const view = render(page(id))
  expect(await screen.findByRole('link', { name: '현재 신청처' })).toHaveAttribute('href', sourceUrl)
  view.rerender(page(nextId))
  expect(screen.queryByRole('link', { name: '현재 신청처' })).not.toBeInTheDocument()
  await act(async () => fail(new Error('private-preparation-failure')))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.queryByRole('link', { name: '현재 신청처' })).not.toBeInTheDocument()
})

it('clears the supplied application link on full-page departure', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => response(sample())))
  render(<MemoryRouter><OfficialPreparation opportunityId={id} withDraft>{url => url ? <a href={url}>현재 신청처</a> : null}</OfficialPreparation></MemoryRouter>)
  await screen.findByRole('link', { name: '현재 신청처' })
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByRole('link', { name: '현재 신청처' })).not.toBeInTheDocument()
})

it('rejects an invalid ID without requesting and loads valid public information only explicitly',async()=>{
  const fetch=vi.fn(async(_request:Request)=>response(sample()));vi.stubGlobal('fetch',fetch)
  const page=mount('invalid');expect(screen.getByRole('heading',{name:'공고 주소를 확인해 주세요'})).toBeVisible();expect(fetch).not.toHaveBeenCalled()
  page.unmount();mount();expect(fetch).not.toHaveBeenCalled();await load()
  expect(fetch.mock.calls[0][0].method).toBe('GET')
})
it('keeps document check marks local and clears them on departure',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response(sample())));mount();await load()
  await userEvent.click(screen.getByRole('checkbox',{name:'공고에 명시된 시험 서류'}))
  expect(screen.getByRole('status')).toHaveTextContent('1개 중 1개 확인')
  act(()=>window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})
it.each([null,[]])('does not invent documents when the server returned %j',async documents=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response(sample({required_documents:documents}))));mount();await load()
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})
it.each([{recruitment_status:'closed' as const},{recruitment_status:'unknown' as const},{change_pending:true}])('withholds application links for unavailable opportunities %j',async changes=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response(sample(changes))));mount();await load()
  expect(screen.queryByRole('link',{name:/공식 신청 안내 확인/})).not.toBeInTheDocument()
  expect(screen.getByRole('checkbox')).toBeDisabled()
  expect(screen.getByRole('link',{name:/공식 원문 확인/})).toBeVisible()
})
it('renders HTML literally and does not link an unapproved application host',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>response(sample({application_instructions:'<img src=x onerror=alert(1)>',application_url:'javascript:alert(1)',source_url:'https://evil.example/'}))));mount();await load()
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible();expect(document.querySelector('img')).toBeNull()
  expect(screen.queryByRole('link',{name:/공식 신청 안내 확인|공식 원문 확인/})).not.toBeInTheDocument()
})
it('discards a delayed reply after pagehide',async()=>{
  let finish!:(response:Response)=>void
  vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(resolve=>{finish=resolve})));mount();await load()
  act(()=>window.dispatchEvent(new Event('pagehide')));await act(async()=>finish(response(sample())))
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
})
it.each([
  { opportunity: { id: '12345678-1234-1234-1234-123456789002', version: 1 } },
  { opportunity: { id, version: 0 } }, { deadline_date: '2026-02-30' },
  { required_documents: ['x'.repeat(201)] }, { required_documents: Array(101).fill('서류') },
  { recruitment_status: 'invalid' }, { change_pending: null }, { application_method: 'invalid' },
])('잘못된 응답 참조·필드 %j 를 거절한다', changes => {
  expect(() => parsePreparation({ ...sample(), ...changes }, id)).toThrow()
})
