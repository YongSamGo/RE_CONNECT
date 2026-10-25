import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ReportReview } from './ReportReview'
import { parseReport } from './report'
import type { ReportSnapshot } from './report'
import { AdminPage } from './AdminPage'
import { anonymousSession } from '../../api/fixtures'

const sample = (changes: Partial<ReportSnapshot> = {}): ReportSnapshot => ({ report_id: '12345678-1234-1234-1234-123456789001', version: 1, opportunity: { id: '12345678-1234-1234-1234-123456789002', version: 3 }, opportunity_title: '가상 공고', type: 'wrong_requirements', note: '공식 조건과 다릅니다.', status: 'received', resolution_note: null, created_at: '2026-10-15T03:00:00Z', updated_at: '2026-10-15T03:00:00Z', ...changes })
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount(report = sample()) { render(<MemoryRouter><ReportReview report={report} onRefresh={vi.fn()} /></MemoryRouter>) }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('report state transitions', () => {
  it('connects server role/MFA verification, list selection and processing without exposing extra fields', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => {
      const url = new URL(request.url)
      if (url.pathname === '/api/v1/me') return json({ ...anonymousSession, authenticated: true, user: { id: '12345678-1234-1234-1234-123456789003', roles: ['operator'], mfa_verified: true, reauth_until: null } })
      if (request.method === 'GET') return json({ items: [{ ...sample(), otp: 'must-not-be-displayed' }], page: 1, page_size: 10, total: 1 })
      return json(sample({ status: 'in_progress', version: 2 }))
    })
    vi.stubGlobal('fetch', fetch)
    render(<MemoryRouter><AdminPage /></MemoryRouter>)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '운영자 접근 확인' }))
    await user.click(await screen.findByRole('button', { name: '신고 목록 조회' }))
    await user.click(await screen.findByRole('button', { name: '검토 선택 · 가상 공고' }))
    expect(screen.getByText('지원 조건 오류 · 신고 접수 · 처리 버전 1')).toBeVisible()
    expect(document.body).not.toHaveTextContent('must-not-be-displayed')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '처리 시작' }))
    expect(await screen.findByRole('button', { name: '해결로 종결' })).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(3)
  })
  it('requires processing first and uses the returned version to close a report', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => { const body = await request.clone().json(); return json(sample({ version: body.base_version + 1, status: body.status, resolution_note: body.resolution_note })) })
    vi.stubGlobal('fetch', fetch)
    mount()
    const user = userEvent.setup()
    expect(screen.queryByRole('button', { name: '해결로 종결' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '처리 시작' }))
    expect(await screen.findByRole('button', { name: '해결로 종결' })).toBeVisible()
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await user.type(screen.getByRole('textbox'), '공식 원문을 대조해 공고를 정정했습니다.')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '해결로 종결' }))
    expect(await screen.findByText(/서버가 신고를 해결로 종결 상태로 처리했습니다/)).toBeVisible()
    expect(await fetch.mock.calls[0]![0].json()).toEqual({ base_version: 1, status: 'in_progress', resolution_note: null })
    expect(await fetch.mock.calls[1]![0].json()).toEqual({ base_version: 2, status: 'resolved', resolution_note: '공식 원문을 대조해 공고를 정정했습니다.' })
    expect(fetch.mock.calls.every(([request]) => request.headers.get('X-CSRF-Token') === 'token')).toBe(true)
    expect(screen.queryByRole('button', { name: '조치 없이 종결' })).not.toBeInTheDocument()
  })
  it('requires a resolution note and re-review after editing before dismissal', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async () => json(sample({ version: 3, status: 'dismissed', resolution_note: '원문과 같은 내용으로 확인했습니다.' })))
    vi.stubGlobal('fetch', fetch)
    mount(sample({ status: 'in_progress', version: 2 }))
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '조치 없이 종결' }))
    expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
    expect(fetch).not.toHaveBeenCalled()
    await user.type(screen.getByRole('textbox'), '원문과 같은 내용으로 확인했습니다.')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '조치 없이 종결' }))
    expect(await screen.findByText(/서버가 신고를 조치 없이 종결 상태로 처리했습니다/)).toBeVisible()
  })
  it('preserves notes and locks further writes after a version conflict', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'VERSION_CONFLICT', message: 'private operator details' }, 409)))
    mount(sample({ status: 'in_progress', version: 2 }))
    const user = userEvent.setup()
    await user.type(screen.getByRole('textbox'), '보존할 처리 근거')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '해결로 종결' }))
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private operator details')
    expect(screen.getByRole('textbox')).toHaveValue('보존할 처리 근거')
    expect(screen.getByRole('button', { name: '조치 없이 종결' })).toBeDisabled()
    expect(screen.getByRole('button', { name: '최신 신고 목록 다시 조회' })).toBeEnabled()
  })
  it('does not accept an acknowledgement for a different report', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async () => json(sample({ report_id: '12345678-1234-1234-1234-123456789999', version: 2, status: 'in_progress' }))))
    mount()
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '처리 시작' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(screen.queryByText(/서버가 신고를/)).not.toBeInTheDocument()
  })
  it('discards late transitions after unmount', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    let complete!: (response: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { complete = resolve })))
    const view = render(<MemoryRouter><ReportReview report={sample()} onRefresh={vi.fn()} /></MemoryRouter>)
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '처리 시작' }))
    view.unmount()
    await act(async () => complete(json(sample({ status: 'in_progress', version: 2 }))))
    expect(screen.queryByText(/서버가 신고를/)).not.toBeInTheDocument()
  })
  it('escapes reporter text and rejects oversized or malformed terminal notes', () => {
    const attack = '<img src=x onerror=alert(1)>'
    mount(sample({ note: attack }))
    expect(screen.getByText(attack)).toBeVisible()
    expect(document.querySelector('img, script')).toBeNull()
    expect(() => parseReport(sample({ status: 'resolved' }))).toThrow()
    expect(() => parseReport(sample({ note: 'a'.repeat(501) }))).toThrow()
    expect(() => parseReport({ ...sample(), status: ['received'] })).toThrow()
    expect(parseReport({ ...sample(), otp: 'not-copied' })).not.toHaveProperty('otp')
  })
})
