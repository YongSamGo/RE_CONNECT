import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import App from './App'

afterEach(() => { vi.unstubAllGlobals() })

it.each([
  ['/my', '내 정보와 동의를 관리해요'],
  ['/transcript', '시작하기 전에 확인해주세요'],
  ['/preparation/example-library', '작성 화면이 변경되었어요'],
  ['/recommendations', '추천은 확정 프로필 연동 후 제공해요'],
])('이전 주소 %s 를 기존 화면 또는 명시적 전환 안내로 연결한다', (path, heading) => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(heading)
  expect(fetch).not.toHaveBeenCalled()
  expect(screen.queryByText('작은 도서관 이용 안내')).not.toBeInTheDocument()
})
