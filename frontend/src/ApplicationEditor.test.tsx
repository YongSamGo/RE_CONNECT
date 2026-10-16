import { useState } from 'react'
import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, expect, it, vi } from 'vitest'
import { ApplicationEditor } from './ApplicationEditor'
import { canApproveApplication, emptyApplication, type ApplicationDraft } from './application'
import { App } from './App'

beforeEach(() => { window.scrollTo = vi.fn() })
const profile = { experience: '이웃에게 책을 안내했어요.', region: '서울 성동구', activities: ['volunteering' as const] }
const introduction = '  이웃에게 책을 안내했어요.\n함께 정리했어요.  '
const motivation = '책을 읽는 이웃을 돕고 싶어요.'
function Harness() {
  const [draft, update] = useState<ApplicationDraft>()
  const [version, setVersion] = useState(1)
  return <><button onClick={() => setVersion(previous => previous + 1)}>프로필 재확정</button><ApplicationEditor key={version} draft={draft} update={update} profile={profile} profileVersion={version} /></>
}
function mount() { return render(<MemoryRouter><Harness /></MemoryRouter>) }
function fill() {
  fireEvent.change(screen.getByLabelText('자기소개'), { target: { value: introduction } })
  fireEvent.change(screen.getByLabelText('지원동기'), { target: { value: motivation } })
}
async function approve(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole('checkbox', { name: /직접 쓴 내용이 사실인지/ }))
  await user.click(screen.getByRole('button', { name: '이 문장으로 확인하기' }))
}

it('프로필 미확정 상태에는 지원서 편집기를 제공하지 않는다', () => {
  render(<MemoryRouter><ApplicationEditor draft={undefined} profile={null} profileVersion={0} update={vi.fn()} /></MemoryRouter>)
  expect(screen.queryByRole('textbox')).toBeNull()
  expect(screen.getByRole('link', { name: '프로필 작성·확정하기' })).toHaveAttribute('href', '/profile')
})

it('빈 값·공백·길이 초과는 확인할 수 없고 사실 확인도 필요하다', async () => {
  expect(canApproveApplication(emptyApplication(1))).toBe(false)
  expect(canApproveApplication({ ...emptyApplication(1), introduction: ' ', motivation })).toBe(false)
  expect(canApproveApplication({ ...emptyApplication(1), introduction: '가'.repeat(2001), motivation })).toBe(false)
  const user = userEvent.setup()
  mount(); fill()
  expect(screen.getByRole('button', { name: '이 문장으로 확인하기' })).toBeDisabled()
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeDisabled()
  await approve(user)
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeEnabled()
})

it('확인한 현재 문장을 줄바꿈·공백까지 그대로 복사하고 수정 시 확인을 해제한다', async () => {
  const user = userEvent.setup()
  const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  mount(); fill(); await approve(user)
  await user.click(screen.getByRole('button', { name: '확인한 문장 복사하기' }))
  expect(write).toHaveBeenCalledWith(`자기소개\n${introduction}\n\n지원동기\n${motivation}`)
  expect(screen.getByRole('status')).toHaveTextContent('복사했어요')
  fireEvent.change(screen.getByLabelText('자기소개'), { target: { value: '<img src=x onerror=alert(1)>' } })
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeDisabled()
  expect(document.querySelector('img')).toBeNull()
  expect(screen.getByRole('status')).toBeEmptyDOMElement()
})

it('프로필 재확정 후 본문을 유지하되 재검토 전에는 복사하지 못한다', async () => {
  const user = userEvent.setup()
  mount(); fill(); await approve(user)
  await user.click(screen.getByRole('button', { name: '프로필 재확정' }))
  expect(screen.getByText(/프로필 변경으로 재검토가 필요해요/)).toBeVisible()
  expect(screen.getByLabelText('자기소개')).toHaveValue(introduction)
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeDisabled()
  await approve(user)
  expect(screen.queryByText(/프로필 변경으로 재검토가 필요해요/)).toBeNull()
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeEnabled()
})

it('복사가 거부되면 정확한 문장을 선택할 수 있는 대체 화면을 제공한다', async () => {
  const user = userEvent.setup()
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('Denied'))
  mount(); fill(); await approve(user)
  await user.click(screen.getByRole('button', { name: '확인한 문장 복사하기' }))
  expect(screen.getByRole('status')).toHaveTextContent('자동 복사를 하지 못했어요')
  const field = screen.getByRole('textbox', { name: '직접 복사할 문장' })
  expect(field).toHaveValue(`자기소개\n${introduction}\n\n지원동기\n${motivation}`)
  expect(field).toHaveAttribute('readonly')
  expect(field).toHaveFocus()
})

it('복사 처리 중 수정하면 이전 요청의 성공 메시지를 뒤늦게 표시하지 않는다', async () => {
  const user = userEvent.setup()
  let resolveCopy: () => void = () => {}
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(() => new Promise<void>(resolve => { resolveCopy = resolve }))
  mount(); fill(); await approve(user)
  await user.click(screen.getByRole('button', { name: '확인한 문장 복사하기' }))
  expect(screen.getByRole('button', { name: '복사 중…' })).toBeDisabled()
  fireEvent.change(screen.getByLabelText('지원동기'), { target: { value: '다시 작성 중인 문장' } })
  await act(async () => { resolveCopy() })
  expect(screen.getByRole('status')).toBeEmptyDOMElement()
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeDisabled()
})

it('앱에서 공고별 지원서를 분리하고 이동 시 유지하며 종료·재생성 시 지운다', async () => {
  const user = userEvent.setup()
  const storage = vi.spyOn(Storage.prototype, 'setItem')
  const view = render(<MemoryRouter><App /></MemoryRouter>)
  await user.click(screen.getByRole('link', { name: /내 경험 이야기하기/ }))
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: /확인하고 시작하기/ }))
  fireEvent.change(screen.getByLabelText('기억에 남는 경험'), { target: { value: profile.experience } })
  await user.click(screen.getByRole('button', { name: /다음 질문/ }))
  fireEvent.change(screen.getByLabelText('희망 활동 지역'), { target: { value: profile.region } })
  await user.click(screen.getByRole('button', { name: /다음 질문/ }))
  await user.click(screen.getByRole('checkbox', { name: '봉사' }))
  await user.click(screen.getByRole('button', { name: /내 프로필 확인하기/ }))
  await user.click(screen.getByRole('button', { name: '이 내용으로 확정하기' }))
  await user.click(screen.getByRole('link', { name: '기회 둘러보기' }))
  await user.click(screen.getByRole('button', { name: '예시 공고로 화면 체험하기' }))
  async function open(title: string) {
    await user.click(screen.getByRole('link', { name: `${title} 예시 상세 보기` }))
    await user.click(screen.getByRole('link', { name: /신청 준비 화면 체험하기/ }))
  }
  await open('작은 도서관 이용 안내'); fill(); await approve(user)
  await user.click(screen.getByRole('link', { name: '예시 목록으로 돌아가기' }))
  await open('이웃 식사 준비 보조')
  expect(screen.getByLabelText('자기소개')).toHaveValue('')
  await user.click(screen.getByRole('link', { name: '예시 목록으로 돌아가기' }))
  await open('작은 도서관 이용 안내')
  expect(screen.getByLabelText('자기소개')).toHaveValue(introduction)
  expect(screen.getByRole('button', { name: '확인한 문장 복사하기' })).toBeEnabled()
  await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
  await user.click(screen.getByRole('alertdialog').querySelector('button:last-child')!)
  await user.click(screen.getByRole('link', { name: '기회 둘러보기' }))
  await user.click(screen.getByRole('button', { name: '예시 공고로 화면 체험하기' }))
  await open('작은 도서관 이용 안내')
  expect(screen.queryByLabelText('자기소개')).toBeNull()
  expect(storage).not.toHaveBeenCalled()
  storage.mockRestore()
  view.unmount()
  render(<MemoryRouter initialEntries={['/preparation/example-library']}><App /></MemoryRouter>)
  expect(screen.queryByLabelText('자기소개')).toBeNull()
})
