import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { OpportunityEditor } from './OpportunityEditor'
import { sampleDetail } from '../public-opportunities/test-fixtures'

const id = sampleDetail().id
const role = { id: 'library_assistant', name: '자료 정리 도우미', description: '합성 역할 설명', skill_tags: ['자료 정리', '이용 안내'] }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('loads the current catalog without auto-selecting tags, then patches only explicitly selected tags', async () => {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const original = sampleDetail({ role_tags: ['legacy_role'], activity_region: { province: 'seoul', district: 'seongdong' }, deadline_at: '2026-10-29T23:59:59.123Z' })
  const requests: Request[] = []
  vi.stubGlobal('fetch', vi.fn(async (request: Request) => {
    requests.push(request)
    if (request.url.endsWith('/admin/role-catalog')) return json({ items: [role] })
    if (request.method === 'GET') return json({ id, version: 2, review_status: 'pending', content: original })
    return json({ id, version: 3, review_status: 'pending', content: { ...original, ...(await request.clone().json()).changes } })
  }))
  render(<OpportunityEditor target={{ id, version: 2 }} onBack={vi.fn()} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '편집할 공고 불러오기' }))
  await user.click(await screen.findByRole('button', { name: '역할 사전 불러오기' }))
  const choice = await screen.findByRole('checkbox', { name: role.name })
  expect(choice).not.toBeChecked()
  expect(screen.getByLabelText('원문에서 확인한 역량 (한 줄에 하나)')).toHaveValue('')
  await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
  await user.click(choice)
  expect(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' })).not.toBeChecked()
  expect(screen.getByLabelText('원문에서 확인한 역량 (한 줄에 하나)')).toHaveValue('')
  await user.click(screen.getByRole('button', { name: '자료 정리 추가' }))
  expect(screen.getByLabelText('원문에서 확인한 역량 (한 줄에 하나)')).toHaveValue('자료 정리')
  expect(screen.getByRole('button', { name: '자료 정리 추가' })).toBeDisabled()
  await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
  await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
  expect(await screen.findByText('검수 대기 버전 3을 저장했습니다. 아직 공개되지 않았습니다.')).toBeVisible()
  const patch = requests.find((request) => request.method === 'PATCH')!
  expect(await patch.json()).toEqual({ base_version: 2, changes: { role_tags: ['legacy_role', 'library_assistant'], skill_tags: ['자료 정리'] } })
  expect(patch.headers.get('X-CSRF-Token')).toBe('token')
})

it('keeps existing tags on catalog failure and blocks duplicate or hidden skill text before sending a patch', async () => {
  const original = sampleDetail({ role_tags: ['legacy_role'], skill_tags: ['자료 정리'] })
  const fetch = vi.fn(async (request: Request) => request.url.endsWith('/admin/role-catalog')
    ? json({ code: 'SERVICE_UNAVAILABLE', message: 'private' }, 503)
    : json({ id, version: 2, review_status: 'pending', content: original }))
  vi.stubGlobal('fetch', fetch)
  render(<OpportunityEditor target={{ id, version: 2 }} onBack={vi.fn()} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '편집할 공고 불러오기' }))
  await user.click(await screen.findByRole('button', { name: '역할 사전 불러오기' }))
  expect(await screen.findByRole('alert')).not.toHaveTextContent('private')
  expect(screen.getByText('기존 선택: legacy_role')).toBeVisible()
  const field = screen.getByLabelText('원문에서 확인한 역량 (한 줄에 하나)')
  expect(field).toHaveValue('자료 정리')
  for (const value of ['자료 정리\n자료 정리', '자료\u202e정리']) {
    fireEvent.change(field, { target: { value } })
    await user.click(screen.getByRole('checkbox', { name: '공식 원문과 입력 내용을 비교해 확인했습니다.' }))
    await user.click(screen.getByRole('button', { name: '검수 대기 버전으로 저장' }))
    expect(field).toHaveAttribute('aria-invalid', 'true')
  }
  expect(fetch.mock.calls.every(([request]) => request.method === 'GET')).toBe(true)
})
