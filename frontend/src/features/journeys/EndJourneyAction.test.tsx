import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, RouterProvider, Routes, createMemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { UnsavedChangesGuard } from '../../ui/UnsavedChangesGuard'
import { EndJourneyAction } from './EndJourneyAction'

const id = '12345678-1234-4234-9234-123456789012'

function mount(responses: Array<() => Response | Promise<Response>>) {
  const calls: Request[] = []
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    calls.push(request)
    const next = responses.shift()
    if (!next) throw new Error('Unexpected request')
    return next()
  }))
  document.cookie = '__Host-rc_csrf=fixture; Secure; Path=/'
  render(<MemoryRouter initialEntries={[`/journeys/${id}/profile`]}><Routes>
    <Route path="/" element={<p>시작 화면</p>} />
    <Route path="/journeys/:journeyId/profile" element={<><label>작성 중 입력<input defaultValue="보내지 않은 입력" /></label><EndJourneyAction journeyId={id} /></>} />
  </Routes></MemoryRouter>)
  return calls
}

afterEach(() => { vi.unstubAllGlobals() })

it('확인한 뒤에만 체험을 삭제하고 204를 받으면 시작 화면으로 이동한다', async () => {
  const user = userEvent.setup()
  const calls = mount([() => new Response(null, { status: 204 })])
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  expect(calls).toHaveLength(0)
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  await screen.findByText('시작 화면')
  expect(calls).toHaveLength(1)
  expect(calls[0].method).toBe('DELETE')
  expect(new URL(calls[0].url).pathname).toBe(`/api/v1/journeys/${id}`)
})

it('취소하면 요청하지 않고 화면을 그대로 둔다', async () => {
  const user = userEvent.setup()
  const calls = mount([])
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  await user.click(screen.getByRole('button', { name: '계속 이용하기' }))
  expect(calls).toHaveLength(0)
  expect(screen.getByRole('button', { name: '종료하고 삭제' })).toBeTruthy()
})

it.each([
  ['서버 오류', () => new Response(JSON.stringify({ code: 'SERVICE_UNAVAILABLE', message: 'private detail' }), { status: 503, headers: { 'Content-Type': 'application/json' } })],
  ['204가 아닌 성공 응답', () => new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } })],
])('%s이면 입력을 보존하고 다시 시도할 수 있다', async (_name, failure) => {
  const user = userEvent.setup()
  const calls = mount([failure, () => new Response(null, { status: 204 })])
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  const retry = await screen.findByRole('button', { name: '삭제 다시 시도' })
  expect(screen.queryByText('시작 화면')).toBeNull()
  expect((screen.getByLabelText('작성 중 입력') as HTMLInputElement).value).toBe('보내지 않은 입력')
  expect(document.body.textContent).not.toContain('private detail')
  await user.click(retry)
  await screen.findByText('시작 화면')
  await waitFor(() => expect(calls).toHaveLength(2))
})

// 실제 앱처럼 data router와 작성 중 입력 보호를 함께 올린다(리뷰 회귀).
Object.defineProperties(HTMLDialogElement.prototype, {
  showModal: { configurable: true, value(this: HTMLDialogElement) { this.setAttribute('open', '') } },
  close: { configurable: true, value(this: HTMLDialogElement) { this.removeAttribute('open'); this.dispatchEvent(new Event('close')) } },
})

function mountGuarded(responses: Array<() => Response>) {
  const calls: Request[] = []
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    calls.push(request)
    const next = responses.shift()
    if (!next) throw new Error('Unexpected request')
    return next()
  }))
  document.cookie = '__Host-rc_csrf=fixture; Secure; Path=/'
  const router = createMemoryRouter([
    { path: '/', element: <p>시작 화면</p> },
    { path: '/other', element: <p>다른 화면</p> },
    { path: '/journeys/:journeyId/conversation', element: <><UnsavedChangesGuard dirty /><label>보낼 글<input defaultValue="아직 보내지 않은 글" /></label>
      <Link to="/other">다른 화면으로</Link><EndJourneyAction journeyId={id} /></> },
  ], { initialEntries: [`/journeys/${id}/conversation`] })
  render(<RouterProvider router={router} />)
  return { calls, router }
}

it('작성 중 입력이 있어도 삭제 204 뒤에는 이탈 확인 없이 시작 화면으로 이동한다', async () => {
  const user = userEvent.setup()
  const { calls, router } = mountGuarded([() => new Response(null, { status: 204 })])
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  await screen.findByText('시작 화면')
  expect(router.state.location.pathname).toBe('/')
  expect(screen.queryByText('작성 중인 내용이 있어요')).toBeNull()
  expect(screen.queryByDisplayValue('아직 보내지 않은 글')).toBeNull()
  expect(calls).toHaveLength(1)
})

it('삭제가 실패하면 입력 보호와 입력을 유지하고, 일반 이동은 계속 확인을 받는다', async () => {
  const user = userEvent.setup()
  const { router } = mountGuarded([() => new Response(JSON.stringify({ code: 'SERVICE_UNAVAILABLE', message: 'private detail' }), { status: 503, headers: { 'Content-Type': 'application/json' } })])
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  await user.click(screen.getByRole('button', { name: '체험 임시 자료 삭제 확인' }))
  await screen.findByRole('button', { name: '삭제 다시 시도' })
  expect(screen.getByDisplayValue('아직 보내지 않은 글')).toBeTruthy()
  await user.click(screen.getByRole('link', { name: '다른 화면으로' }))
  await waitFor(() => expect(router.state.location.pathname).toBe(`/journeys/${id}/conversation`))
  expect(screen.getByText('작성 중인 내용이 있어요')).toBeTruthy()
})
