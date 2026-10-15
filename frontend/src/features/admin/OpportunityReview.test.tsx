import { render, screen } from '@testing-library/react'
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
    await user.click(screen.getByRole('button', { name: '선택한 버전 원문·변경 불러오기' }))
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
    await userEvent.click(screen.getByRole('button', { name: '선택한 버전 원문·변경 불러오기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('응답을 확인하지 못했습니다.')
    expect(screen.queryByRole('button', { name: '검토한 버전 승인' })).not.toBeInTheDocument()
  })
})
