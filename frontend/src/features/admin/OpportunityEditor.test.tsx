import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { OpportunityEditor } from './OpportunityEditor'
import { parseOpportunityInput } from './editor'
import { sampleDetail, sourceUrl } from '../public-opportunities/test-fixtures'

const id = sampleDetail().id
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const existing = () => parseOpportunityInput({ ...sampleDetail(), deadline_at: '2026-10-30T03:04:05.678Z', role_tags: ['community_helper'], activity_region: { province: 'seoul', district: 'seongdong' }, requirements: [{ id: '12345678-1234-1234-1234-123456789010', field: 'age', operator: 'gte', value: 60, group_id: null, group_operator: null, reference_date: '2026-10-15', clarity: 'clear', source_evidence: '만 60세 이상' }] })
const change = (label: string, value: string) => fireEvent.change(screen.getByLabelText(label), { target: { value } })
function fill() {
  change('공고 제목 (필수)', '가상 운영 시험 공고')
  change('기관명 (필수)', '가상 기관')
  change('공식 원문 HTTPS 주소 (필수)', sourceUrl)
  change('공식 접수 안내 HTTPS 주소 (필수)', sourceUrl)
  change('공식 접수 방법 (필수)', '공식 안내를 확인하고 직접 신청하세요.')
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('opportunity create and edit', () => {
  it('validates required input before any request', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    render(<OpportunityEditor onBack={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
    expect(screen.getByLabelText('공고 제목 (필수)')).toHaveAttribute('aria-invalid', 'true')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('creates pending data with unresolved source conditions and stable retry body/key', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const requests: Request[] = []
    const fetch = vi.fn(async (request: Request) => {
      requests.push(request)
      if (requests.length === 1) throw new Error('private create transport')
      return json({ id, version: 1, review_status: 'pending', content: await request.clone().json() }, 201)
    })
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityEditor onBack={vi.fn()} />)
    fill()
    change('추가 필수조건 원문 (한 줄에 하나)', '만 60세 이상\n주 2일 참여')
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private create transport')
    expect(screen.getByLabelText('공고 제목 (필수)')).toHaveValue('가상 운영 시험 공고')
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(await screen.findByText('검수 대기 버전 1을 저장했습니다. 아직 공개되지 않았습니다.')).toBeVisible()
    expect(requests).toHaveLength(2)
    expect(requests[0]!.headers.get('Idempotency-Key')).toBe(requests[1]!.headers.get('Idempotency-Key'))
    const body = await requests[0]!.json()
    expect(body).toEqual(await requests[1]!.json())
    expect(body.requirements).toEqual([
      expect.objectContaining({ field: 'other', operator: null, value: null, clarity: 'needs_review', source_evidence: '만 60세 이상' }),
      expect.objectContaining({ field: 'other', operator: null, value: null, clarity: 'needs_review', source_evidence: '주 2일 참여' }),
    ])
    expect(body).toMatchObject({ paid: null, remote_allowed: null, required_documents: null, recruitment_status: 'unknown' })
    expect(screen.getByRole('button', { name: '검수 대기 버전으로 저장' })).toBeDisabled()
  })
  it('edits only the changed field while preserving structured conditions and timestamp precision', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => request.method === 'GET'
      ? json({ id, version: 2, review_status: 'approved', content: existing() })
      : json({ id, version: 3, review_status: 'pending', content: { ...existing(), ...(await request.clone().json()).changes } }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityEditor target={{ id, version: 2 }} onBack={vi.fn()} />)
    expect(fetch).not.toHaveBeenCalled()
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '편집할 공고 불러오기' }))
    expect(await screen.findByText('만 60세 이상')).toBeVisible()
    change('공고 제목 (필수)', '수정한 제목')
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(await screen.findByText('검수 대기 버전 3을 저장했습니다. 아직 공개되지 않았습니다.')).toBeVisible()
    const patch = fetch.mock.calls[1]![0]
    expect(patch.method).toBe('PATCH')
    expect(await patch.json()).toEqual({ base_version: 2, changes: { title: '수정한 제목' } })
  })
  it('preserves edited input on a conflict and requires a latest version before further save', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => request.method === 'GET'
      ? json({ id, version: 2, review_status: 'approved', content: existing() })
      : json({ code: 'VERSION_CONFLICT', message: 'private concurrency state' }, 409)))
    render(<OpportunityEditor target={{ id, version: 2 }} onBack={vi.fn()} />)
    const user = userEvent.setup()
    await user.click(screen.getByRole('button', { name: '편집할 공고 불러오기' }))
    change('공고 제목 (필수)', '유지할 편집 내용')
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private concurrency state')
    expect(screen.getByLabelText('공고 제목 (필수)')).toHaveValue('유지할 편집 내용')
    expect(screen.getByRole('button', { name: '검수 대기 버전으로 저장' })).toBeDisabled()
  })
  it('preserves multiline document editing and sends confirmed empty documents separately from unknown', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const fetch = vi.fn(async (request: Request) => json({ id, version: 1, review_status: 'pending', content: await request.clone().json() }, 201))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityEditor onBack={vi.fn()} />)
    fill()
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox', { name: '공식 원문에 명시된 필수조건이 없는 것을 확인했어요.' }))
    await user.click(screen.getByRole('checkbox', { name: '공식 원문에서 필요 서류 안내를 확인했어요.' }))
    await user.type(screen.getByLabelText('필요 서류 (한 줄에 하나)'), '첫 서류{Enter}둘째 서류')
    expect(screen.getByLabelText('필요 서류 (한 줄에 하나)')).toHaveValue('첫 서류\n둘째 서류')
    await user.clear(screen.getByLabelText('필요 서류 (한 줄에 하나)'))
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(await screen.findByText(/검수 대기 버전 1을 저장했습니다/)).toBeVisible()
    expect((await fetch.mock.calls[0]![0].json()).required_documents).toEqual([])
  })
  it('clears input and discards late creation responses on pagehide', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    let complete!: (value: Response) => void
    vi.stubGlobal('fetch', vi.fn(() => new Promise<Response>((resolve) => { complete = resolve })))
    render(<OpportunityEditor onBack={vi.fn()} />)
    fill()
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox', { name: '공식 원문에 명시된 필수조건이 없는 것을 확인했어요.' }))
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    act(() => window.dispatchEvent(new Event('pagehide')))
    await act(async () => complete(json({ id, version: 1, review_status: 'pending', content: existing() }, 201)))
    expect(screen.getByLabelText('공고 제목 (필수)')).toHaveValue('')
    expect(screen.queryByText(/검수 대기 버전 1을 저장했습니다/)).not.toBeInTheDocument()
  })
  it('rejects a nonpending creation acknowledgement instead of claiming publication or success', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    vi.stubGlobal('fetch', vi.fn(async (request: Request) => json({ id, version: 1, review_status: 'approved', content: await request.clone().json() }, 201)))
    render(<OpportunityEditor onBack={vi.fn()} />)
    fill()
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox', { name: '공식 원문에 명시된 필수조건이 없는 것을 확인했어요.' }))
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(screen.queryByText(/검수 대기 버전 1을 저장했습니다/)).not.toBeInTheDocument()
  })
  it('renders server source text literally and never follows typed source URLs', async () => {
    const attack = '<img src=x onerror=alert(1)>'
    const value = existing()
    const fetch = vi.fn(async () => json({ id, version: 2, review_status: 'approved', content: { ...value, title: attack, requirements: [{ ...value.requirements[0], source_evidence: attack }] } }))
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityEditor target={{ id, version: 2 }} onBack={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: '편집할 공고 불러오기' }))
    expect(await screen.findByText(attack)).toBeVisible()
    expect(screen.getByLabelText('공고 제목 (필수)')).toHaveValue(attack)
    expect(document.querySelector('img, script')).toBeNull()
    expect(fetch).toHaveBeenCalledTimes(1)
  })
})
