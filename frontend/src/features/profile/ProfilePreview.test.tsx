import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it } from 'vitest'
import App from '../../App'

describe('manual profile choices', () => {
  it('requires experience, region and activity and invalidates local review after experience edits', async () => {
    render(<MemoryRouter initialEntries={['/consent']}><App /></MemoryRouter>)
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /미리보기 시작하기/ }))
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    expect(screen.getByRole('heading', { name: '입력한 항목을 확인해 주세요' }).parentElement).toHaveFocus()
    expect(screen.getByRole('link', { name: '경험을 한 가지 이상 적어 주세요.' })).toBeVisible()
    await user.click(screen.getByRole('link', { name: '경험을 한 가지 이상 적어 주세요.' }))
    expect(screen.getByRole('link', { name: '경험 수정하기' })).toHaveFocus()
    await user.click(screen.getByRole('link', { name: '경험 수정하기' }))
    await user.type(screen.getByRole('textbox'), '이웃과 도서 정리')
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    await user.click(screen.getByRole('checkbox', { name: '서울' }))
    await user.click(screen.getByRole('checkbox', { name: '봉사' }))
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    expect(screen.getByText(/경험과 희망 조건을 확인했습니다/)).toBeVisible()
    await user.click(screen.getByRole('link', { name: '경험 수정하기' }))
    await user.type(screen.getByRole('textbox'), ' 수정')
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    expect(screen.queryByText(/경험과 희망 조건을 확인했습니다/)).not.toBeInTheDocument()
    expect(screen.getByRole('checkbox', { name: '서울' })).toBeChecked()
    expect(screen.queryByRole('button', { name: /저장|서버 확정/ })).not.toBeInTheDocument()
  })
})
