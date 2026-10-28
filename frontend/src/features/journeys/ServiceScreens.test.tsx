import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from '../../App'

afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it('opens every destination in the guide as a real page without creating data or inferring a successful operation', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  const view = render(<MemoryRouter initialEntries={['/guide']}><App /></MemoryRouter>)
  const links = [...view.container.querySelectorAll('.service-guide a')].map(link => ({ href: link.getAttribute('href')!, name: link.textContent! }))
  expect(links).toHaveLength(17)
  view.unmount()
  for (const link of links) {
    const page = render(<MemoryRouter initialEntries={[link.href]}><App /></MemoryRouter>)
    expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
    expect(screen.queryByText('페이지를 찾을 수 없어요')).not.toBeInTheDocument()
    expect(screen.queryByText(/가상 경험|화면 미리보기|선택한 자료를 저장했어요/)).not.toBeInTheDocument()
    page.unmount()
  }
  expect(fetch).not.toHaveBeenCalled()
})

it('lets users move from results to recommendations and preparation without inventing profile or opportunity references', async () => {
  const fetch = vi.fn(); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={['/results']}><App /></MemoryRouter>)
  await userEvent.click(screen.getByRole('link', { name: '추천 공고' }))
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('확정한 경험으로 기회를 찾아봐요')
  expect(screen.queryByRole('button', { name: '추천 다시 확인하기' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('link', { name: '신청 준비' }))
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('참여를 준비해요')
  expect(screen.getByRole('link', { name: '공고 선택하기' })).toHaveAttribute('href', '/opportunities')
  expect(fetch).not.toHaveBeenCalled()
})

it('keeps the user-specified start screen free of screen-directory or draft controls', () => {
  render(<MemoryRouter initialEntries={['/start']}><App /></MemoryRouter>)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('시작하기 전에 확인해주세요')
  expect(screen.getAllByRole('button', { name: /자세히 보기/ })).toHaveLength(3)
  expect(screen.getByRole('button', { name: '동의하고 대화 시작하기' })).toBeVisible()
  expect(screen.queryByRole('link', { name: '다시잇다 이용 안내' })).not.toBeInTheDocument()
})
