import { useState } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterAll, beforeAll, expect, it, vi } from 'vitest'
import { MyPage } from './MyPage'
import type { ApplicationDraft } from './application'

const profile = { experience: '<img src=x onerror=alert(1)>', region: '서울 성동구', activities: ['volunteering' as const] }
const drafts: Record<string, ApplicationDraft> = {
  'example-library': { introduction: '책을 안내했어요.', motivation: '이웃과 함께하고 싶어요.', profileVersion: 1, approved: true },
  'example-meal': { introduction: '함께 식사를 준비했어요.', motivation: '', profileVersion: 1, approved: false },
}
beforeAll(() => {
  // jsdom has no top-layer implementation; browser verification covers native modality.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function (this: HTMLDialogElement) { this.setAttribute('open', '') } })
})
afterAll(() => { Reflect.deleteProperty(HTMLDialogElement.prototype, 'showModal') })
function mount(version = 1) {
  function Harness() {
    const [applications, setApplications] = useState(drafts)
    return <MyPage profile={profile} profileVersion={version} applications={applications} deleteApplication={id => setApplications(previous => Object.fromEntries(Object.entries(previous).filter(([key]) => key !== id)))} />
  }
  return render(<MemoryRouter><Harness /></MemoryRouter>)
}

it('체험이 없으면 미확정·미작성과 회원 저장 미연동을 구분해서 안내한다', () => {
  render(<MemoryRouter><MyPage profile={null} profileVersion={0} applications={{}} deleteApplication={vi.fn()} /></MemoryRouter>)
  expect(screen.getByText('아직 확정 전')).toBeVisible()
  expect(screen.getByRole('heading', { name: '아직 작성한 지원서가 없어요' })).toBeVisible()
  expect(screen.getByText(/서버에 저장된 회원 자료가 아니에요/)).toBeVisible()
})

it('확정 경험을 문자열로 표시하고 공고별 상태·이어서 보기 경로를 제공한다', () => {
  mount()
  expect(screen.getByText(profile.experience)).toBeVisible()
  expect(document.querySelector('img')).toBeNull()
  expect(screen.getByText('문장 확인 완료')).toBeVisible()
  expect(screen.getByText('작성 중')).toBeVisible()
  expect(screen.getByRole('link', { name: '작은 도서관 이용 안내 지원서 이어서 보기' })).toHaveAttribute('href', '/preparation/example-library')
})

it('프로필 버전이 달라지면 기존 확인 완료 대신 재검토 상태를 표시한다', () => {
  mount(2)
  expect(screen.queryByText('문장 확인 완료')).toBeNull()
  expect(screen.getAllByText('프로필 변경 · 재검토 필요')).toHaveLength(2)
  expect(screen.getByRole('link', { name: '작은 도서관 이용 안내 지원서 재검토하기' })).toBeVisible()
  expect(screen.getByText('책을 안내했어요.')).toBeVisible()
})

it('삭제 취소·Escape 시 자료를 유지하고 열었던 버튼으로 포커스를 돌린다', async () => {
  const user = userEvent.setup()
  mount()
  const trigger = screen.getByRole('button', { name: '작은 도서관 이용 안내 지원서 삭제' })
  await user.click(trigger)
  expect(within(screen.getByRole('dialog')).getByRole('button', { name: '계속 보관하기' })).toHaveFocus()
  await user.click(screen.getByRole('button', { name: '계속 보관하기' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(trigger).toHaveFocus()
  await user.click(trigger)
  fireEvent(screen.getByRole('dialog'), new Event('cancel', { bubbles: true, cancelable: true }))
  expect(screen.queryByRole('dialog')).toBeNull()
  await waitFor(() => expect(trigger).toHaveFocus())
  expect(screen.getAllByRole('article')).toHaveLength(2)
})

it('확인한 지원서만 삭제하고 다른 지원서·프로필을 유지하며 목록에 포커스를 둔다', async () => {
  const user = userEvent.setup()
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  mount()
  await user.click(screen.getByRole('button', { name: '작은 도서관 이용 안내 지원서 삭제' }))
  await user.click(screen.getByRole('button', { name: '이 지원서 삭제하기' }))
  expect(screen.queryByRole('dialog')).toBeNull()
  expect(screen.getAllByRole('article')).toHaveLength(1)
  expect(screen.getByRole('heading', { name: '이웃 식사 준비 보조' })).toBeVisible()
  expect(screen.getByText(profile.experience)).toBeVisible()
  expect(screen.getByRole('heading', { name: /현재 체험의 지원서 1개/ })).toHaveFocus()
  expect(screen.getByRole('status')).toHaveTextContent('작은 도서관 이용 안내 지원서를 현재 체험에서 지웠어요.')
  expect(storage).not.toHaveBeenCalled()
  storage.mockRestore()
})
