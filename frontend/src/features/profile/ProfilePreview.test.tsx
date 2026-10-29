import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from '../../App'

afterEach(() => { vi.unstubAllGlobals() })

describe('manual profile choices', () => {
  it('requires experience, region and activity and invalidates local review after experience edits', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ version: 'test-v1', provinces: [{ id: 'seoul', name: '서울', districts: [] }] }), { headers: { 'Content-Type': 'application/json' } })))
    render(<MemoryRouter initialEntries={['/consent']}><App /></MemoryRouter>)
    const user = userEvent.setup()
    await user.click(screen.getByRole('checkbox'))
    await user.click(screen.getByRole('button', { name: /시작하기/ }))
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    expect(screen.getByRole('button', { name: '활동 조건 고르기' })).toBeDisabled()
    expect(screen.queryByRole('checkbox', { name: '서울' })).not.toBeInTheDocument()
    await user.click(screen.getByRole('link', { name: '경험 수정하기' }))
    await user.type(screen.getByRole('textbox'), '이웃과 도서 정리')
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    await user.click(screen.getByRole('button', { name: '활동 조건 고르기' }))
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    expect(screen.getByRole('region', { name: '입력한 항목을 확인해 주세요' })).toHaveFocus()
    await user.click(screen.getByRole('button', { name: '시군구 목록 불러오기' }))
    await user.click(screen.getByText('지역 선택 안내', { exact: true }))
    await screen.findByText('지역 목록 버전: test-v1')
    await user.click(screen.getByRole('checkbox', { name: '서울' }))
    await user.click(screen.getByRole('checkbox', { name: '봉사' }))
    await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
    expect(screen.getByText(/경험과 희망 조건을 확인했어요/)).toBeVisible()
    await user.click(screen.getByRole('link', { name: '경험 수정하기' }))
    await user.type(screen.getByRole('textbox'), ' 수정')
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    expect(screen.queryByText(/경험과 희망 조건을 확인했어요/)).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: '활동 조건 고르기' }))
    expect(screen.getByRole('checkbox', { name: '서울' })).toBeChecked()
    expect(screen.queryByRole('button', { name: /저장|서버 확정/ })).not.toBeInTheDocument()
  })
})
