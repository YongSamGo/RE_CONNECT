import { act, fireEvent, render, screen } from '@testing-library/react'
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
async function load() { await userEvent.click(screen.getByRole('button', { name: '공식 준비 안내 불러오기' })) }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('잘못된 공고 ID는 요청하지 않으며 정상 ID도 사용자 동작 전에는 조회하지 않는다', async () => {
  const fetch = vi.fn().mockResolvedValue(response(sample()))
  vi.stubGlobal('fetch', fetch)
  const view = mount('invalid')
  expect(screen.getByRole('heading', { name: '공고 주소를 확인해 주세요' })).toBeVisible()
  expect(fetch).not.toHaveBeenCalled()
  view.unmount(); mount()
  expect(fetch).not.toHaveBeenCalled()
  await load()
  expect((fetch.mock.calls[0][0] as Request).url).toBe(`https://reconnect.test/api/v1/opportunities/${id}/preparation`)
})

it('명시된 서류만 체크하며 조회 갱신·언마운트 시 체크를 초기화한다', async () => {
  const fetch = vi.fn().mockImplementation(async () => response(sample()))
  vi.stubGlobal('fetch', fetch)
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  const view = mount(); await load()
  expect(screen.getByRole('region', { name: '공식 준비 안내 조회 결과' })).toHaveFocus()
  const checkbox = screen.getByRole('checkbox', { name: '공고에 명시된 시험 서류' })
  await userEvent.click(checkbox)
  expect(screen.getByRole('status')).toHaveTextContent('1개 중 1개 확인')
  expect(screen.getByRole('link', { name: /공식 신청 안내 확인/ })).toHaveAttribute('rel', 'noopener noreferrer')
  await userEvent.click(screen.getByRole('button', { name: '최신 준비 안내 다시 조회' }))
  expect(screen.getByRole('checkbox')).not.toBeChecked()
  expect(storage).not.toHaveBeenCalled()
  view.unmount(); mount(); expect(screen.queryByRole('checkbox')).toBeNull()
})

it.each([null, []])('명시되지 않거나 비어 있는 서류 목록 %j 에 임의 서류를 추가하지 않는다', async documents => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(sample({ required_documents: documents }))))
  mount(); await load()
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.getByText(documents === null ? /서류가 필요 없다는 뜻은 아니에요/ : /제출 서류 목록이 비어 있어요/)).toBeVisible()
})

it.each([{ recruitment_status: 'closed' as const }, { recruitment_status: 'unknown' as const }, { change_pending: true }])('마감·상태 미확인·재검수 %j 에서는 신청 링크와 체크를 막는다', async changes => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(sample(changes))))
  mount(); await load()
  expect(screen.queryByRole('link', { name: /공식 신청 안내 확인/ })).toBeNull()
  expect(screen.getByRole('checkbox')).toBeDisabled()
  expect(screen.getByRole('link', { name: /공식 원문 확인/ })).toBeVisible()
})

it('HTML 형태 설명은 문자열로 표시하고 허용되지 않은 공식 URL은 링크로 만들지 않는다', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(sample({ application_instructions: '<img src=x onerror=alert(1)>', application_url: 'javascript:alert(1)', source_url: 'https://evil.example/' }))))
  mount(); await load()
  expect(screen.getByText('<img src=x onerror=alert(1)>')).toBeVisible()
  expect(document.querySelector('img')).toBeNull()
  expect(screen.queryByRole('link', { name: /공식 신청 안내 확인/ })).toBeNull()
  expect(screen.queryByRole('link', { name: /공식 원문 확인/ })).toBeNull()
})

it('실제 API 실패를 오류로 안내하고 같은 공고를 다시 조회할 수 있다', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: 'NOT_FOUND', message: 'internal-input', request_id: 'req_test' }), { status: 404, headers: { 'Content-Type': 'application/json' } })))
  mount(); await load()
  expect(screen.getByRole('alert')).toBeVisible()
  expect(document.body).not.toHaveTextContent('internal-input')
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.getByRole('button', { name: '준비 안내 다시 조회' })).toBeVisible()
})

it('취소 뒤 도착한 응답은 서류·체크·성공 화면을 복원하지 않는다', async () => {
  let resolve: (response: Response) => void = () => {}
  vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>(done => { resolve = done })))
  mount(); await load()
  await userEvent.click(screen.getByRole('button', { name: '조회 취소하기' }))
  await act(async () => { resolve(response(sample())) })
  expect(screen.getByRole('button', { name: '공식 준비 안내 불러오기' })).toBeVisible()
  expect(screen.queryByRole('checkbox')).toBeNull()
})

it('페이지 이탈 이벤트에서도 준비 체크와 조회 자료를 비운다', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(sample())))
  mount(); await load(); await userEvent.click(screen.getByRole('checkbox'))
  fireEvent(window, new PageTransitionEvent('pagehide'))
  expect(screen.queryByRole('checkbox')).toBeNull()
  expect(screen.getByRole('button', { name: '공식 준비 안내 불러오기' })).toBeVisible()
})

it.each([
  { opportunity: { id: '12345678-1234-1234-1234-123456789002', version: 1 } },
  { opportunity: { id, version: 0 } }, { deadline_date: '2026-02-30' },
  { required_documents: ['x'.repeat(201)] }, { required_documents: Array(101).fill('서류') },
  { recruitment_status: 'invalid' }, { change_pending: null }, { application_method: 'invalid' },
])('잘못된 응답 참조·필드 %j 를 거절한다', changes => {
  expect(() => parsePreparation({ ...sample(), ...changes }, id)).toThrow()
})
