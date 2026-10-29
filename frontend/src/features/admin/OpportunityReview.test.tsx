import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OpportunityReview } from './OpportunityReview'
import { sampleDetail } from '../public-opportunities/test-fixtures'

const id = sampleDetail().id
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('operator review version and source boundaries', () => {
  it('requires loaded detail, explicit review and note, and preserves version conflicts as failures', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET'
      ? json({ id, version: 2, review_status: 'pending', content: sampleDetail(), published_content: null, changed_fields: ['title'], important_change: true })
      : json({ code: 'VERSION_CONFLICT', message: 'private server data' }, 409))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReview id={id} version={2} />)
    const user = userEvent.setup()
    expect(screen.queryByRole('button', { name: '검토한 버전 승인' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '선택한 버전 원문, 변경 불러오기' }))
    expect(await screen.findByRole('button', { name: '검토한 버전 승인' })).toBeDisabled()
    await user.type(screen.getByRole('textbox'), '공식 공고와 필수 조건 대조')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '검토한 버전 승인' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('최신 내용을 확인해 주세요.')
    expect(document.body).not.toHaveTextContent('private server data')
    expect(screen.queryByText(/서버가 처리를 완료했습니다/)).not.toBeInTheDocument()
    const post = fetch.mock.calls[1]![0]
    expect(await post.json()).toEqual({ base_version: 2, note: '공식 공고와 필수 조건 대조' })
    expect(post.headers.get('X-CSRF-Token')).toBe('token')
  })
  it('rejects mismatched detail versions before enabling approval', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ id, version: 3 })))
    render(<OpportunityReview id={id} version={2} />)
    await userEvent.click(screen.getByRole('button', { name: '선택한 버전 원문, 변경 불러오기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(screen.queryByRole('button', { name: '검토한 버전 승인' })).not.toBeInTheDocument()
  })
  it('requires a note for other rejection reasons and sends a versioned rejection', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET'
      ? json({ id, version: 2, review_status: 'pending', content: sampleDetail(), published_content: null, changed_fields: [], important_change: false })
      : json({ id, version: 2, review_status: 'rejected', reviewed_at: '2026-10-15T03:00:00Z' }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReview id={id} version={2} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '선택한 버전 원문, 변경 불러오기' }))
    await user.selectOptions(await screen.findByLabelText('반려 사유'), 'other')
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('button', { name: '선택한 버전 반려' })).toBeDisabled()
    await user.type(screen.getByRole('textbox'), '조건 원문을 다시 확인해야 합니다.')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '선택한 버전 반려' }))
    expect(await screen.findByText(/서버가 처리를 완료했습니다/)).toBeVisible()
    const post = fetch.mock.calls[1]![0]
    expect(post.url).toBe(`https://reconnect.test/api/v1/admin/opportunities/${id}/reject`)
    expect(await post.json()).toEqual({ base_version: 2, reason_code: 'other', note: '조건 원문을 다시 확인해야 합니다.' })
    expect(screen.getByRole('button', { name: '확인한 공고 모집 종료' })).toBeDisabled()
  })
  it('does not offer rejection for approved versions and sends only an explicitly selected closing basis', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET'
      ? json({ id, version: 2, review_status: 'approved', content: sampleDetail(), published_content: null, changed_fields: [], important_change: false })
      : json({ id, version: 3, review_status: 'approved', reviewed_at: '2026-10-15T03:00:00Z' }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReview id={id} version={2} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '선택한 버전 원문, 변경 불러오기' }))
    expect(screen.queryByRole('button', { name: '선택한 버전 반려' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '확인한 공고 모집 종료' })).toBeDisabled()
    expect(screen.getByLabelText('모집 종료 근거')).not.toHaveTextContent('수집 실패')
    await user.selectOptions(screen.getByLabelText('모집 종료 근거'), 'source_closed')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '확인한 공고 모집 종료' }))
    expect(await screen.findByText(/서버가 처리를 완료했습니다/)).toBeVisible()
    const post = fetch.mock.calls[1]![0]
    expect(post.url).toBe(`https://reconnect.test/api/v1/admin/opportunities/${id}/close`)
    expect(await post.json()).toEqual({ base_version: 2, basis: 'source_closed', note: null })
  })
  it('rejects mismatched mutation acknowledgements instead of showing success', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET'
      ? json({ id, version: 2, review_status: 'pending', content: sampleDetail(), published_content: null, changed_fields: [], important_change: false })
      : json({ id: '12345678-1234-1234-1234-123456789999', version: 2, review_status: 'rejected', reviewed_at: '2026-10-15T03:00:00Z' }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReview id={id} version={2} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '선택한 버전 원문, 변경 불러오기' }))
    await user.selectOptions(screen.getByLabelText('반려 사유'), 'insufficient_information')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '선택한 버전 반려' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(screen.queryByText(/서버가 처리를 완료했습니다/)).not.toBeInTheDocument()
  })
  it('discards a late closing acknowledgement after pagehide', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    let complete!: (value: Response) => void
    const fetch = vi.fn((request: Request) => request.method === 'GET'
      ? Promise.resolve(json({ id, version: 2, review_status: 'approved', content: sampleDetail(), published_content: null, changed_fields: [], important_change: false }))
      : new Promise<Response>((resolve) => { complete = resolve }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReview id={id} version={2} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '선택한 버전 원문, 변경 불러오기' }))
    await user.selectOptions(screen.getByLabelText('모집 종료 근거'), 'deadline_passed')
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: '확인한 공고 모집 종료' }))
    act(() => window.dispatchEvent(new Event('pagehide')))
    await act(async () => complete(json({ id, version: 3, review_status: 'approved', reviewed_at: '2026-10-15T03:00:00Z' })))
    expect(screen.queryByText(/서버가 처리를 완료했습니다/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '확인한 공고 모집 종료' })).not.toBeInTheDocument()
  })
})
