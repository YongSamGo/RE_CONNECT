import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import { OpportunityReport } from './OpportunityReport'

const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const id = '12345678-1234-1234-1234-123456789012'
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })
describe('opportunity report submission', () => {
  it('requires explanation for other and never sends a partial report', async () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
    render(<OpportunityReport id={id} version={2} />)
    const user = userEvent.setup()
    await user.click(screen.getByText('공고 정보 오류 알리기'))
    await user.selectOptions(screen.getByLabelText('어떤 정보가 다른가요?'), 'other')
    await user.click(screen.getByRole('button', { name: '공고 오류 신고 보내기' }))
    expect(screen.getByRole('textbox')).toHaveAttribute('aria-invalid', 'true')
    expect(fetch).not.toHaveBeenCalled()
  })
  it('reuses the same idempotency key and body after uncertain network failure', async () => {
    document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
    const writes: Request[] = []
    const fetch = vi.fn(async (request: Request) => {
      if (request.method === 'GET') return json(anonymousSession)
      writes.push(request)
      if (writes.length === 1) throw new Error('private failure')
      return json({ report_id: id, received_at: '2026-10-15T03:00:00Z' }, 201)
    })
    vi.stubGlobal('fetch', fetch)
    render(<OpportunityReport id={id} version={2} />)
    const user = userEvent.setup()
    await user.click(screen.getByText('공고 정보 오류 알리기'))
    await user.click(screen.getByRole('button', { name: '공고 오류 신고 보내기' }))
    expect(await screen.findByRole('alert')).not.toHaveTextContent('private failure')
    await user.click(screen.getByRole('button', { name: '공고 오류 신고 보내기' }))
    expect(await screen.findByText('공고 오류 신고를 접수했습니다. 운영자가 내용을 확인합니다.')).toBeVisible()
    expect(writes).toHaveLength(2)
    expect(writes[0]!.headers.get('Idempotency-Key')).toBe(writes[1]!.headers.get('Idempotency-Key'))
    expect(await writes[0]!.json()).toEqual(await writes[1]!.json())
    expect(screen.getByRole('button', { name: '공고 오류 신고 보내기' })).toBeDisabled()
    expect(writes.every((request) => request.headers.get('X-CSRF-Token') === 'token')).toBe(true)
  })
})
