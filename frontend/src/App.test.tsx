import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { App } from './App'
import { canConfirm, emptyProfile } from './journey'

beforeEach(() => { window.scrollTo = vi.fn() })
function mount(path = '/') { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
async function start() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('link', { name: /내 경험 이야기하기/ }))
  expect(screen.getByRole('button', { name: /확인하고 시작하기/ })).toBeDisabled()
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: /확인하고 시작하기/ }))
  return user
}

describe('프로필 최소 조건', () => {
  it('공백·누락·과대 입력으로 확정할 수 없다', () => {
    expect(canConfirm(emptyProfile())).toBe(false)
    expect(canConfirm({ experience: ' ', region: '서울', activities: ['employment'] })).toBe(false)
    expect(canConfirm({ experience: '경험', region: ' ', activities: ['employment'] })).toBe(false)
    expect(canConfirm({ experience: '경험', region: '서울', activities: [] })).toBe(false)
    expect(canConfirm({ experience: '가'.repeat(2001), region: '서울', activities: ['employment'] })).toBe(false)
    expect(canConfirm({ experience: '경험', region: '가'.repeat(101), activities: ['employment'] })).toBe(false)
    expect(canConfirm({ experience: '경험', region: '서울 성동구', activities: ['volunteering'] })).toBe(true)
  })
})

describe('체험 흐름', () => {
  it('안내 확인 전에는 직접 주소로 경험 입력에 진입하지 못한다', () => {
    mount('/conversation')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('안심하고 이야기할 수 있도록')
  })
  it('미확정 프로필로 추천에 진입하지 못한다', () => {
    mount('/recommendations')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('안심하고 이야기할 수 있도록')
  })
  it('프로필을 직접 확정하고, 수정 시 이전 확정본을 유지하며 종료하면 지운다', async () => {
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    mount()
    const user = await start()
    expect(screen.getByRole('button', { name: /다음 질문/ })).toBeDisabled()
    const payload = '<img src=x onerror=alert(1)>'
    fireEvent.change(screen.getByLabelText('기억에 남는 경험'), { target: { value: payload } })
    await user.click(screen.getByRole('button', { name: /다음 질문/ }))
    await user.type(screen.getByLabelText('희망 활동 지역'), '서울 성동구')
    await user.click(screen.getByRole('button', { name: /다음 질문/ }))
    await user.click(screen.getByRole('checkbox', { name: '봉사' }))
    await user.click(screen.getByRole('button', { name: /내 프로필 확인하기/ }))
    expect(screen.getByLabelText('기억에 남는 경험')).toHaveValue(payload)
    expect(document.querySelector('img')).toBeNull()
    await user.click(screen.getByRole('button', { name: '이 내용으로 확정하기' }))
    expect(screen.getByRole('status')).toHaveTextContent('영구 저장은 하지 않았어요')
    await user.type(screen.getByLabelText('희망 활동 지역'), ' 수정')
    expect(screen.getByText(/다시 확정하기 전까지 이전 확정 프로필/)).toBeVisible()
    await user.click(screen.getByRole('link', { name: /기회 탐색으로 이동/ }))
    expect(screen.getByText(/이전 확정 프로필 기준/)).toBeVisible()
    await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
    expect(screen.getByRole('alertdialog')).toBeVisible()
    await user.click(screen.getByRole('button', { name: '계속 작성하기' }))
    expect(screen.queryByRole('alertdialog')).toBeNull()
    await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
    const buttons = screen.getAllByRole('button', { name: '종료하고 삭제' })
    await user.click(buttons[buttons.length - 1])
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('살아온 시간만큼')
    await start()
    expect(screen.getByLabelText('기억에 남는 경험')).toHaveValue('')
    expect(storage).not.toHaveBeenCalled()
    storage.mockRestore()
  })
  it('앱 재생성 시 체험 내용을 복원하지 않는다', async () => {
    const view = mount()
    await start()
    fireEvent.change(screen.getByLabelText('기억에 남는 경험'), { target: { value: '저장하지 않을 경험' } })
    view.unmount()
    mount('/profile')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('안심하고 이야기할 수 있도록')
  })
  it.each(['/transcript', '/opportunities', '/opportunities/demo', '/preparation/demo', '/my', '/admin', '/unknown'])('%s 경로에서 화면을 제공한다', path => {
    mount(path)
    expect(screen.getByRole('heading', { level: 1 })).toBeVisible()
  })
})
