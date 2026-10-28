import { act, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { Link, MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { PublicOpportunityDetail } from './PublicOpportunityDetail'
import { sampleDetail, sourceUrl } from './test-fixtures'

const id = sampleDetail().id
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount(path = id) {
  return render(<MemoryRouter initialEntries={[`/opportunities/${path}`]}><Link to="/opportunities/12345678-1234-1234-1234-123456789002">다른 공고</Link><Routes><Route path="/opportunities/:id" element={<PublicOpportunityDetail />} /></Routes></MemoryRouter>)
}
async function load() { await userEvent.click(screen.getByRole('button', { name: '공고 정보 불러오기' })) }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('public detail request and state', () => {
  it('makes one explicit public GET without consent/profile and displays nullable facts honestly', async () => {
    const fetch = vi.fn(async (_request: Request) => json(sampleDetail()))
    vi.stubGlobal('fetch', fetch)
    mount()
    expect(fetch).not.toHaveBeenCalled()
    await load()
    expect(await screen.findByRole('heading', { name: '가상 도서 정리 봉사' })).toBeVisible()
    const request = fetch.mock.calls[0]![0]
    expect(request.url).toBe(`https://reconnect.test/api/v1/opportunities/${id}`)
    expect(request.method).toBe('GET')
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
    expect(screen.getByText('필요 서류 확인 필요')).toBeVisible()
    expect(screen.getByText(/제공된 원문 설명이 없습니다/)).toBeVisible()
    expect(screen.getByText(/검수된 공고에 명시된 필수조건이 없습니다/)).toBeVisible()
    expect(screen.getByText(/내 지원 자격을 판정한 결과가 아닙니다/)).toBeVisible()
    expect(screen.getByRole('link', { name: 'AI 처리 안내를 확인하고 새 체험 시작' })).toHaveAttribute('href', '/start')
    expect(screen.getByText(/원문 확인:/)).toHaveTextContent('2026년 10월 15일 08:30')
    expect(screen.getByRole('region', { name: '공고 상세 조회 결과' })).toHaveFocus()
    const link = screen.getByRole('link', { name: /공식 원문 확인 / })
    expect(link).toHaveAttribute('href', sourceUrl)
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
    expect(link).toHaveAttribute('referrerpolicy', 'no-referrer')
  })
  it.each(['preview', 'not-a-uuid'])('rejects invalid route %s before any request', (path) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    mount(path)
    expect(screen.getByText('공고 주소를 확인해 주세요')).toBeVisible()
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each([
    { recruitment_status: 'closed' as const }, { recruitment_status: 'unknown' as const }, { change_pending: true },
  ])('keeps official source but withholds application for %j', async (changes) => {
    vi.stubGlobal('fetch', vi.fn(async () => json(sampleDetail(changes))))
    mount(); await load()
    expect(await screen.findByRole('link', { name: /공식 원문 확인 / })).toBeVisible()
    expect(screen.queryByRole('link', { name: /공식 신청 안내 확인 / })).not.toBeInTheDocument()
  })
  it('renders hostile text literally and withholds unapproved links', async () => {
    const attack = '<img src=x onerror=alert(1)>'
    vi.stubGlobal('fetch', vi.fn(async () => json(sampleDetail({ description_text: attack, description_truncated: true, source_url: 'javascript:alert(1)', application_url: 'https://evil.test' }))))
    const { container } = mount(); await load()
    expect(await screen.findByText(attack)).toBeVisible()
    expect(container.querySelector('img, script')).toBeNull()
    expect(screen.getByText(/원문이 길어 앞부분만 표시/)).toBeVisible()
    expect(screen.queryByRole('link', { name: /공식 원문 확인 / })).not.toBeInTheDocument()
    expect(container.querySelector('a[href="https://evil.test"]')).toBeNull()
  })
  it('shows a missing notice for 404 without leaking server message or offering immediate retry', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'NOT_FOUND', message: 'secret database path' }, 404)))
    mount(); await load()
    expect(await screen.findByText('이 공고를 찾을 수 없어요')).toBeVisible()
    expect(screen.queryByText(/secret database/)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '공고 다시 조회' })).not.toBeInTheDocument()
  })
  it('rejects another opportunity response and allows only manual retry', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(sampleDetail({ id: '12345678-1234-1234-1234-123456789002' }))).mockResolvedValueOnce(json(sampleDetail()))
    vi.stubGlobal('fetch', fetch)
    mount(); await load()
    expect(await screen.findByText(/응답을 확인하지 못했습니다/)).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: '공고 다시 조회' }))
    expect(await screen.findByRole('heading', { name: '가상 도서 정리 봉사' })).toBeVisible()
  })
  it.each(['cancel', 'route', 'pagehide', 'restore', 'unmount'])('discards late responses after %s', async (kind) => {
    let complete!: (value: Response) => void
    const fetch = vi.fn((_request: Request) => new Promise<Response>((resolve) => { complete = resolve }))
    vi.stubGlobal('fetch', fetch)
    const view = mount(); await load()
    const request = fetch.mock.calls[0]![0]
    if (kind === 'cancel') await userEvent.click(screen.getByRole('button', { name: '조회 취소하기' }))
    if (kind === 'route') await userEvent.click(screen.getByRole('link', { name: '다른 공고' }))
    if (kind === 'pagehide') act(() => { window.dispatchEvent(new PageTransitionEvent('pagehide')) })
    if (kind === 'restore') act(() => { window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })) })
    if (kind === 'unmount') view.unmount()
    expect(request.signal.aborted).toBe(true)
    await act(async () => { complete(json(sampleDetail())); await Promise.resolve() })
    expect(screen.queryByRole('heading', { name: '가상 도서 정리 봉사' })).not.toBeInTheDocument()
    if (kind !== 'unmount') await waitFor(() => expect(screen.getByRole('button', { name: '공고 정보 불러오기' })).toBeEnabled())
  })
  it('does not offer immediate retry on daily quota', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ code: 'DAILY_QUOTA_EXCEEDED' }, 429)))
    mount(); await load()
    expect(await screen.findByText(/오늘 이용 한도/)).toBeVisible()
    expect(screen.queryByRole('button', { name: '공고 다시 조회' })).not.toBeInTheDocument()
  })
  it('refreshes the detail version explicitly without retaining old content while loading', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(json(sampleDetail())).mockResolvedValueOnce(json(sampleDetail({ version: 2, recruitment_status: 'closed' })))
    vi.stubGlobal('fetch', fetch)
    mount(); await load()
    expect(await screen.findByText(/공고 버전 1/)).toBeVisible()
    await userEvent.click(screen.getByRole('button', { name: '최신 정보 다시 조회' }))
    expect(await screen.findByText(/공고 버전 2/)).toBeVisible()
    expect(screen.queryByText(/공고 버전 1/)).not.toBeInTheDocument()
    expect(screen.getByText('모집 마감')).toBeVisible()
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('starts a fresh route request even if the previous route completes late', async () => {
    let complete!: (value: Response) => void
    const nextId = '12345678-1234-1234-1234-123456789002'
    const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { complete = resolve })).mockResolvedValueOnce(json(sampleDetail({ id: nextId, title: '다음 공고' })))
    vi.stubGlobal('fetch', fetch)
    mount(); await load()
    await userEvent.click(screen.getByRole('link', { name: '다른 공고' }))
    await load()
    expect(await screen.findByRole('heading', { name: '다음 공고' })).toBeVisible()
    await act(async () => { complete(json(sampleDetail())); await Promise.resolve() })
    expect(screen.queryByRole('heading', { name: '가상 도서 정리 봉사' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '다음 공고' })).toBeVisible()
  })
  it('keeps only one request active during repeated submission and permits loading after cancellation', async () => {
    const fetch = vi.fn((_request: Request) => new Promise<Response>(() => {}))
    vi.stubGlobal('fetch', fetch)
    mount()
    await userEvent.dblClick(screen.getByRole('button', { name: '공고 정보 불러오기' }))
    expect(fetch).toHaveBeenCalledTimes(1)
    await userEvent.click(screen.getByRole('button', { name: '조회 취소하기' }))
    await load()
    expect(fetch).toHaveBeenCalledTimes(2)
  })
  it('shows requirement evidence and uncertainty as text without computing eligibility', async () => {
    const requirement = { id, field: 'other' as const, operator: null, value: null, group_id: null, group_operator: null, reference_date: null, source_evidence: '관련 경험을 기관에 문의하세요.', clarity: 'needs_review' as const }
    vi.stubGlobal('fetch', vi.fn(async () => json(sampleDetail({ requirements: [requirement], required_documents: ['기관 지정 서식'], hours_per_week: 0 }))))
    mount(); await load()
    expect(await screen.findByText(requirement.source_evidence)).toBeVisible()
    expect(screen.getByText(/조건 해석 확인 필요/)).toBeVisible()
    expect(screen.getByText('기관 지정 서식')).toBeVisible()
    expect(screen.getByText(/주 0시간/)).toBeVisible()
    expect(screen.queryByRole('button', { name: /지원/ })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '공고 오류 신고 보내기' })).toBeInTheDocument()
  })
  it('uses fixed service failure text and never retries automatically', async () => {
    const fetch = vi.fn(async () => json({ code: 'SERVICE_UNAVAILABLE', message: 'private upstream address' }, 503))
    vi.stubGlobal('fetch', fetch)
    mount(); await load()
    expect(await screen.findByText(/서비스 연결이 원활하지 않습니다/)).toBeVisible()
    expect(screen.queryByText(/private upstream/)).not.toBeInTheDocument()
    expect(fetch).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: '공고 다시 조회' })).toBeEnabled()
  })
})
