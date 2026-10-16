import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { ProfilePreview } from './ProfilePreview'
import { emptyPreferences } from './model'
import type { ProfilePreferences } from './model'

const catalog = { version: 'test-version', provinces: [{ id: 'seoul', name: '서울', districts: [{ id: 'test_first', name: '가상첫구' }, { id: 'test_second', name: '가상둘구' }] }] }
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
function mount() {
  const changed = vi.fn()
  function Harness() {
    const scope = useMemoryScope<ProfilePreferences>(emptyPreferences)
    return <ProfilePreview experience="가상 경험" preferences={scope.value} onChange={(next) => { changed(next); scope.setValue(next) }} />
  }
  render(<MemoryRouter><Harness /></MemoryRouter>)
  return { changed, user: userEvent.setup() }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
describe('profile district selections', () => {
  it('loads public catalog explicitly, replaces whole province with districts and invalidates review', async () => {
    const fetch = vi.fn(async (_request: Request) => json(catalog)); vi.stubGlobal('fetch', fetch)
    const { changed, user } = mount()
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('checkbox', { name: '서울' }))
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    expect(await screen.findByRole('checkbox', { name: '서울 가상첫구' })).toBeVisible()
    const request = fetch.mock.calls[0]![0]
    expect(request.url).toBe('https://reconnect.test/api/v1/regions')
    expect(request.method).toBe('GET')
    expect(request.headers.has('X-CSRF-Token')).toBe(false)
    await user.click(screen.getByRole('checkbox', { name: '서울 가상첫구' }))
    expect(screen.getByRole('checkbox', { name: '서울 전체' })).not.toBeChecked()
    await user.click(screen.getByRole('checkbox', { name: '봉사' }))
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    expect(changed).toHaveBeenLastCalledWith({ regions: [{ province: 'seoul', district: 'test_first' }], activities: ['volunteering'], reviewed: true })
    await user.click(screen.getByRole('checkbox', { name: '서울 가상둘구' }))
    expect(screen.queryByText(/경험과 희망 조건을 확인했습니다/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('checkbox', { name: '서울 전체' }))
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ regions: [{ province: 'seoul', district: null }], reviewed: false }))
    expect(fetch).toHaveBeenCalledTimes(1)
  })
  it.each(['failure', 'removed'])('preserves selected identifiers after catalog %s and requires a manual decision', async (kind) => {
    const fetch = vi.fn().mockResolvedValueOnce(json(catalog)).mockResolvedValueOnce(kind === 'failure' ? json({ code: 'SERVICE_UNAVAILABLE', message: 'private region failure' }, 503) : json({ ...catalog, version: 'new-version', provinces: [] }))
    vi.stubGlobal('fetch', fetch)
    const { changed, user } = mount()
    await user.click(screen.getByRole('checkbox', { name: '서울' }))
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    await user.click(await screen.findByRole('checkbox', { name: '서울 가상첫구' }))
    await user.click(screen.getByRole('checkbox', { name: '봉사' }))
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 새로 불러오기' }))
    expect(await screen.findByText('목록 대조 필요: 서울 / test_first')).toBeVisible()
    expect(changed).toHaveBeenLastCalledWith(expect.objectContaining({ regions: [{ province: 'seoul', district: 'test_first' }], reviewed: false }))
    expect(screen.getByRole('checkbox', { name: '서울 전체' })).not.toBeChecked()
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    expect(screen.queryByText(/경험과 희망 조건을 확인했습니다/)).not.toBeInTheDocument()
    expect(document.body).not.toHaveTextContent('private region failure')
    await user.click(screen.getByRole('button', { name: '서울 / test_first 선택 제거' }))
    expect(screen.getByRole('checkbox', { name: '서울' })).not.toBeChecked()
  })
  it.each(['cancel', 'pagehide'])('discards a late catalog after %s', async (kind) => {
    let complete!: (response: Response) => void
    const fetch = vi.fn((_request: Request) => new Promise<Response>((resolve) => { complete = resolve })); vi.stubGlobal('fetch', fetch)
    const { user } = mount()
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    expect(screen.getByRole('button', { name: '작성 항목 확인하기' })).toBeDisabled()
    if (kind === 'cancel') await user.click(screen.getByRole('button', { name: '지역 목록 조회 취소' }))
    else act(() => window.dispatchEvent(new Event('pagehide')))
    expect(fetch.mock.calls[0]![0].signal.aborted).toBe(true)
    await act(async () => complete(json(catalog)))
    expect(screen.queryByText('지역 목록 버전: test-version')).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: '시·군·구 목록 불러오기' })).toBeEnabled()
  })
  it('enforces the ten-region limit without losing existing choices', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => json({ ...catalog, provinces: [{ ...catalog.provinces[0], districts: Array.from({ length: 11 }, (_, index) => ({ id: `test_${index}`, name: `가상${index}구` })) }] })))
    const { changed, user } = mount()
    await user.click(screen.getByRole('checkbox', { name: '서울' }))
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    await screen.findByText('지역 목록 버전: test-version')
    for (let i = 0; i < 10; i++) await user.click(screen.getByRole('checkbox', { name: `서울 가상${i}구` }))
    expect(screen.getByRole('checkbox', { name: '서울 가상10구' })).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: '경기' })).toBeDisabled()
    expect(changed.mock.lastCall![0].regions).toHaveLength(10)
    await user.click(screen.getByRole('checkbox', { name: '서울 가상0구' }))
    expect(screen.getByRole('checkbox', { name: '서울 가상10구' })).toBeEnabled()
  })
  it('renders server labels as literal text', async () => {
    const name = '<img src=x>'
    vi.stubGlobal('fetch', vi.fn(async () => json({ ...catalog, provinces: [{ ...catalog.provinces[0], districts: [{ id: 'test_safe', name }] }] })))
    const { user } = mount()
    await user.click(screen.getByRole('checkbox', { name: '서울' }))
    await user.click(screen.getByRole('button', { name: '시·군·구 목록 불러오기' }))
    expect(await screen.findByRole('checkbox', { name: `서울 ${name}` })).toBeVisible()
    expect(document.querySelector('img, script')).toBeNull()
  })
})
