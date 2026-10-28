import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'

async function open() {
  const user = userEvent.setup()
  render(<MemoryRouter initialEntries={['/consent']}><App /></MemoryRouter>)
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: /미리보기 시작하기/ }))
  await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
  await user.click(screen.getByRole('link', { name: '지원 내용 직접 작성해 보기' }))
  return user
}
async function fill(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByRole('textbox', { name: '자기소개' }), '도서관에서 책 정리를 도왔어요.')
  await user.type(screen.getByRole('textbox', { name: '지원동기' }), '이웃과 함께 활동하고 싶어요.')
  await user.click(screen.getByRole('checkbox'))
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('manual preparation preview', () => {
  it('requires nonblank fields, focuses errors, copies exact reviewed text, and invalidates review on edit', async () => {
    const user = await open()
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
    await user.click(screen.getByRole('checkbox'))
    expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
    expect(screen.queryByRole('button', { name: '확인한 내용 복사하기' })).not.toBeInTheDocument()
    await fill(user)
    await user.click(screen.getByRole('button', { name: '확인한 내용 복사하기' }))
    expect(write).toHaveBeenCalledExactlyOnceWith('자기소개\n도서관에서 책 정리를 도왔어요.\n\n지원동기\n이웃과 함께 활동하고 싶어요.')
    expect(screen.getByText(/작성한 내용을 복사했습니다/)).toBeVisible()
    await user.type(screen.getByRole('textbox', { name: '자기소개' }), ' 수정')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(screen.queryByRole('textbox', { name: '복사할 내용' })).not.toBeInTheDocument()
    expect(screen.queryByText(/작성한 내용을 복사했습니다/)).not.toBeInTheDocument()
  })
  it('keeps input on copy failure, offers manual selection, and never exposes exception contents', async () => {
    const user = await open()
    vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('private clipboard details'))
    await fill(user)
    await user.click(screen.getByRole('button', { name: '확인한 내용 복사하기' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('자동 복사를 완료하지 못했어요')
    expect(document.body).not.toHaveTextContent('private clipboard details')
    await user.click(screen.getByRole('button', { name: '복사할 내용 전체 선택' }))
    const output = screen.getByRole('textbox', { name: '복사할 내용' }) as HTMLTextAreaElement
    expect(output).toHaveFocus()
    expect(output.selectionEnd - output.selectionStart).toBe(output.value.length)
  })
  it('preserves draft across routes without storage or API writes and clears it on end', async () => {
    const user = await open()
    const store = vi.spyOn(Storage.prototype, 'setItem')
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    await fill(user)
    await user.click(screen.getByRole('link', { name: '내 경험 다시 보기' }))
    await user.click(screen.getByRole('link', { name: '지원 내용 직접 작성해 보기' }))
    expect(screen.getByRole('textbox', { name: '자기소개' })).toHaveValue('도서관에서 책 정리를 도왔어요.')
    expect(store).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
    await user.click(screen.getByRole('link', { name: /내 경험 이야기하기/ }))
    await user.click(screen.getByRole('link', { name: '가상 경험으로 화면 미리보기' }))
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /미리보기 시작하기/ }))
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    await user.click(screen.getByRole('link', { name: '지원 내용 직접 작성해 보기' }))
    expect(screen.getByRole('textbox', { name: '자기소개' })).toHaveValue('')
    expect(screen.getByRole('checkbox')).not.toBeChecked()
    expect(store).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('discards late copy results after clearing and treats HTML as literal text', async () => {
    const user = await open()
    let resolve!: () => void
    const write = vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(() => new Promise<void>((done) => { resolve = done }))
    await fill(user)
    await user.clear(screen.getByRole('textbox', { name: '자기소개' }))
    await user.click(screen.getByRole('textbox', { name: '자기소개' }))
    await user.paste('<script>alert(1)</script>')
    await user.click(screen.getByRole('checkbox'))
    expect(document.querySelector('script')).toBeNull()
    await user.click(screen.getByRole('button', { name: '확인한 내용 복사하기' }))
    expect(screen.getByRole('button', { name: '복사하고 있어요…' })).toBeDisabled()
    expect(write).toHaveBeenCalledTimes(1)
    await user.click(screen.getByRole('button', { name: '작성 내용 지우기' }))
    await act(async () => resolve())
    expect(screen.queryByText(/작성한 내용을 복사했습니다/)).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: '자기소개' })).toHaveValue('')
  })
})
