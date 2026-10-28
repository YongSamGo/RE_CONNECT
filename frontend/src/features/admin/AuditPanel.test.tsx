import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { AuditPanel } from './AuditPanel'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const event = { event_id: '12345678-1234-1234-1234-123456789012', at: '2026-10-14T03:00:00Z', action: 'opportunity.reject', actor_role: 'operator', target_type: 'opportunity', result: 'success', request_id: 'req_audit_01', private_body: 'private-material-not-for-display', otp: 'secret-otp' }
function mount() {
  render(<AuditPanel onBack={vi.fn()} />)
  fireEvent.change(screen.getByLabelText('조회 시작 (한국시간)'), { target: { value: '2026-10-14T00:00' } })
  fireEvent.change(screen.getByLabelText('조회 종료 (한국시간)'), { target: { value: '2026-10-15T00:00' } })
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('audit screen requests', () => {
  it('queries only on submit, paginates the submitted range and omits private response fields', async () => {
    const fetch = vi.fn(async (request: Request) => {
      const page = Number(new URL(request.url).searchParams.get('page'))
      return json({ items: [{ ...event, event_id: page === 1 ? event.event_id : '12345678-1234-1234-1234-123456789013' }], total: 21, page, page_size: 20 })
    })
    vi.stubGlobal('fetch', fetch)
    mount()
    const user = userEvent.setup()
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '감사 기록 불러오기' }))
    expect(await screen.findByRole('table', { name: '운영 감사 기록' })).toBeVisible()
    expect(screen.getByRole('region', { name: '감사 기록 조회 결과' })).toHaveFocus()
    expect(screen.getByText('공고 반려')).toBeVisible()
    expect(screen.getByText('성공')).toBeVisible()
    expect(document.body).not.toHaveTextContent('private-material-not-for-display')
    expect(document.body).not.toHaveTextContent('secret-otp')
    expect(screen.getByRole('button', { name: '이전 감사 페이지' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: '다음 감사 페이지' }))
    expect(await screen.findByText('2페이지 / 전체 21건')).toBeVisible()
    expect(screen.getByRole('button', { name: '다음 감사 페이지' })).toBeDisabled()
    const requests = fetch.mock.calls.map(([request]) => new URL(request.url))
    expect(requests.every((url) => url.pathname === '/api/v1/admin/audit' && url.searchParams.get('from') === '2026-10-14T00:00:00+09:00' && url.searchParams.get('to') === '2026-10-15T00:00:00+09:00')).toBe(true)
  })
  it('rejects ranges beyond 30 days without making a request', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    mount()
    fireEvent.change(screen.getByLabelText('조회 시작 (한국시간)'), { target: { value: '2026-09-01T00:00' } })
    await userEvent.click(screen.getByRole('button', { name: '감사 기록 불러오기' }))
    expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
    expect(screen.getByLabelText('조회 시작 (한국시간)')).toHaveAccessibleDescription(/종료는 시작 이후/)
    expect(screen.getByLabelText('조회 종료 (한국시간)')).toHaveAccessibleDescription(/최대 30일/)
    expect(fetch).not.toHaveBeenCalled()
  })
  it('keeps focus on the field during an unrelated parent update and refocuses on another invalid submit', async () => {
    const view = render(<AuditPanel onBack={vi.fn()} />)
    fireEvent.change(screen.getByLabelText('조회 시작 (한국시간)'), { target: { value: '2026-09-01T00:00' } })
    fireEvent.change(screen.getByLabelText('조회 종료 (한국시간)'), { target: { value: '2026-10-15T00:00' } })
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '감사 기록 불러오기' }))
    await user.click(screen.getByRole('link', { name: /시작, 종료 시간을 확인/ }))
    expect(screen.getByLabelText('조회 시작 (한국시간)')).toHaveFocus()
    view.rerender(<AuditPanel onBack={vi.fn()} />)
    expect(screen.getByLabelText('조회 시작 (한국시간)')).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '감사 기록 불러오기' }))
    expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
  })
  it('does not show data or raw server messages when MFA is required', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'MFA_REQUIRED', message: 'private-auth-diagnostic' }, 403)))
    mount()
    await userEvent.click(screen.getByRole('button', { name: '감사 기록 불러오기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('운영자 추가 인증이 필요합니다.')
    expect(document.body).not.toHaveTextContent('private-auth-diagnostic')
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
  })
  it('discards late records after explicit cancellation', async () => {
    let complete!: (value: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { complete = resolve })))
    mount()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '감사 기록 불러오기' }))
    await user.click(screen.getByRole('button', { name: '감사 조회 취소' }))
    await act(async () => complete(json({ items: [event], total: 1, page: 1, page_size: 20 })))
    expect(screen.queryByRole('table')).not.toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})
