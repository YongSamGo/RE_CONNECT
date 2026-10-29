import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
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
