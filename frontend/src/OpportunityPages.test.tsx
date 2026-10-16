import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { App } from './App'
import { filterExamples } from './opportunities'

beforeEach(() => { window.scrollTo = vi.fn() })
function mount(path = '/opportunities') { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
async function enableExamples() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '예시 공고로 화면 체험하기' }))
  return user
}

it('사용자가 예시를 선택하기 전에는 가상 공고를 표시하지 않는다', () => {
  mount()
  expect(screen.getByText('실제 공고를 연결하고 있어요')).toBeVisible()
  expect(screen.queryByRole('article')).toBeNull()
})

it('지역·유형·검색어를 함께 적용하고 빈 결과에서 조건을 유지한다', async () => {
  mount()
  const user = await enableExamples()
  expect(screen.getAllByRole('article')).toHaveLength(3)
  await user.selectOptions(screen.getByLabelText('활동 지역'), '서울 성동구')
  await user.selectOptions(screen.getByLabelText('활동 유형'), 'volunteering')
  expect(screen.getAllByRole('article')).toHaveLength(1)
  await user.type(screen.getByLabelText('검색어'), '정원')
  expect(screen.getByRole('status')).toHaveTextContent('0개')
  expect(screen.getByLabelText('활동 지역')).toHaveValue('서울 성동구')
  expect(screen.getByLabelText('활동 유형')).toHaveValue('volunteering')
  await user.click(screen.getByRole('button', { name: '모든 예시 보기' }))
  expect(screen.getAllByRole('article')).toHaveLength(3)
})

it('필터 검색어를 정규식이나 HTML로 실행하지 않는다', () => {
  expect(filterExamples({ keyword: ' 도서관 ', region: '', activity: '' })).toHaveLength(1)
  expect(filterExamples({ keyword: '.*', region: '', activity: '' })).toHaveLength(0)
  mount()
  fireEvent.click(screen.getByRole('button', { name: '예시 공고로 화면 체험하기' }))
  fireEvent.change(screen.getByLabelText('검색어'), { target: { value: '<img src=x onerror=alert(1)>' } })
  expect(document.querySelector('img')).toBeNull()
  expect(screen.getByRole('status')).toHaveTextContent('0개')
})

it('공고별 체크를 메모리에 유지하고 종료하면 예시 모드와 함께 지운다', async () => {
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  const view = mount()
  const user = await enableExamples()
  await user.click(screen.getByRole('link', { name: '작은 도서관 이용 안내 예시 상세 보기' }))
  expect(screen.getByText(/실제 모집 공고가 아니에요/)).toBeVisible()
  expect(screen.queryByRole('link', { name: '신청하기' })).toBeNull()
  await user.click(screen.getByRole('link', { name: /신청 준비 화면 체험하기/ }))
  const checkboxName = '내가 가능한 요일과 시간을 정리했어요'
  await user.click(screen.getByRole('checkbox', { name: checkboxName }))
  expect(screen.getByRole('status')).toHaveTextContent('1개 확인')
  await user.click(screen.getByRole('link', { name: '예시 목록으로 돌아가기' }))
  await user.click(screen.getByRole('link', { name: '이웃 식사 준비 보조 예시 상세 보기' }))
  await user.click(screen.getByRole('link', { name: /신청 준비 화면 체험하기/ }))
  expect(screen.getByRole('status')).toHaveTextContent('0개 확인')
  await user.click(screen.getByRole('link', { name: '예시 목록으로 돌아가기' }))
  await user.click(screen.getByRole('link', { name: '작은 도서관 이용 안내 예시 상세 보기' }))
  await user.click(screen.getByRole('link', { name: /신청 준비 화면 체험하기/ }))
  expect(screen.getByRole('checkbox', { name: checkboxName })).toBeChecked()
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  const buttons = screen.getAllByRole('button', { name: '종료하고 삭제' })
  await user.click(buttons[buttons.length - 1])
  await user.click(screen.getByRole('link', { name: /공개 공고 먼저 둘러보기/ }))
  await enableExamples()
  await user.click(screen.getByRole('link', { name: '작은 도서관 이용 안내 예시 상세 보기' }))
  await user.click(screen.getByRole('link', { name: /신청 준비 화면 체험하기/ }))
  expect(screen.getByRole('checkbox', { name: checkboxName })).not.toBeChecked()
  expect(storage).not.toHaveBeenCalled()
  storage.mockRestore()
  view.unmount()
  mount('/preparation/example-library')
  expect(screen.queryByRole('checkbox')).toBeNull()
})

it.each(['/opportunities/example-library', '/opportunities/not-found', '/preparation/example-library'])('예시 선택 전 직접 주소 %s 에서는 예시를 표시하지 않는다', path => {
  mount(path)
  expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('공고 정보를 확인할 수 없어요')
  expect(screen.queryByRole('checkbox')).toBeNull()
})
