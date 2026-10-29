import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { PublicOpportunities } from './PublicOpportunities'
import { sampleList } from './test-fixtures'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('browses opportunities without applying the selected filters', async () => {
  const fetch = vi.fn(async (_request: Request) => new Response(JSON.stringify(sampleList({ items: [], total: 0 })), { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const scrollIntoView = vi.fn()
  Object.defineProperty(HTMLElement.prototype, 'scrollIntoView', { configurable: true, value: scrollIntoView })
  const user = userEvent.setup()
  render(<MemoryRouter><PublicOpportunities /></MemoryRouter>)
  await user.click(screen.getByRole('button', { name: '종로구' }))
  await user.type(screen.getByRole('searchbox'), '도서')
  await user.click(screen.getByRole('button', { name: '일단 둘러볼래요' }))
  await screen.findByText('이 조건의 공고가 없어요')
  const params = new URL(fetch.mock.calls[0]![0].url).searchParams
  expect(params.has('regions')).toBe(false)
  expect(params.has('q')).toBe(false)
  expect(scrollIntoView).not.toHaveBeenCalled()
  expect(screen.getByRole('region', { name: '공고 조회 결과' })).toHaveFocus()
})




it('선택 안함은 모든 지역을 해제하되 검색어와 활동 유형은 유지한다', async () => {
  const fetch = vi.fn(async (_request: Request) => new Response(JSON.stringify(sampleList({ items: [], total: 0 })), { headers: { 'Content-Type': 'application/json' } }))
  vi.stubGlobal('fetch', fetch)
  const user = userEvent.setup()
  render(<MemoryRouter><PublicOpportunities /></MemoryRouter>)
  await user.click(screen.getByRole('button', { name: '종로구' }))
  await user.click(screen.getByRole('button', { name: '김포/인천 지도 보기' }))
  await user.click(screen.getByRole('button', { name: '김포시' }))
  await user.type(screen.getByRole('searchbox'), '도서')
  await user.selectOptions(screen.getByRole('combobox', { name: '활동 유형' }), 'volunteering')
  await user.click(screen.getByRole('button', { name: '선택 안함' }))
  expect(screen.getByRole('button', { name: '선택 안함' })).toHaveAttribute('aria-pressed', 'true')
  expect(screen.getByRole('button', { name: '김포시' })).toHaveAttribute('aria-pressed', 'false')
  await user.click(screen.getByRole('button', { name: '서울 지도 보기' }))
  expect(screen.getByRole('button', { name: '종로구' })).toHaveAttribute('aria-pressed', 'false')
  await user.click(screen.getByRole('button', { name: '공고 검색하기' }))
  await screen.findByText('이 조건의 공고가 없어요')
  const params = new URL(fetch.mock.calls[0]![0].url).searchParams
  expect(params.has('regions')).toBe(false)
  expect(params.get('q')).toBe('도서')
  expect(params.get('activity_type')).toBe('volunteering')
})
