import { act, render, screen } from '@testing-library/react'
import { useEffect } from 'react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useNavigate } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App, { ErrorBoundary } from './App'

let navigateForTest: (path: string) => void
function NavigationHarness() { const navigate = useNavigate(); useEffect(() => { navigateForTest = navigate }, [navigate]); return null }
function mount(path = '/') {
  return render(<MemoryRouter initialEntries={[path]}><NavigationHarness /><App /></MemoryRouter>)
}
async function start() {
  const user = userEvent.setup()
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: /시작하기/ }))
  return user
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

describe('화면 골격과 입력 경계', () => {
  it.each([
    ['/recommendations', '공고 살펴보기 | 다시잇다'],
    ['/preparation/old', '신청 준비 | 다시잇다'],
    ['/opportunities/invalid/extra', '페이지를 찾을 수 없어요 | 다시잇다'],
    ['/me/unknown', '페이지를 찾을 수 없어요 | 다시잇다'],
  ])('주소 %s에 맞는 브라우저 제목을 표시한다', (path, title) => {
    mount(path)
    expect(document.title).toBe(title)
  })
  it('첫 화면에 새 문구와 비어 있는 영상 영역을 표시한다', () => {
    mount()
    expect(screen.queryByRole('heading', { name: '다시잇다, 이렇게 이용해요' })).not.toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '여러분의 이야기를 들려주세요' })).toBeVisible()
    expect(screen.getByText('여러분의 이야기가 곧 새로운 기회가 됩니다')).toBeVisible()
    expect(document.querySelector('.home-video')).toHaveTextContent('여러분의 이야기를 들려주세요')
    expect(screen.queryByText('화면 미리보기')).not.toBeInTheDocument()
    expect(screen.queryByText('경험 정리 예시 보기')).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /영상.*(보기|재생)/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '내 경험 이야기하기' })).not.toBeInTheDocument()
    expect(screen.queryByRole('link', { name: '공고부터 살펴보기' })).not.toBeInTheDocument()
  })
  it('첫 진입에서는 본문으로 포커스를 강제 이동하지 않는다', async () => {
    mount()
    expect(screen.getByRole('main')).not.toHaveFocus()
    const user = userEvent.setup()
    await user.tab()
    expect(screen.getByRole('link', { name: '본문으로 바로가기' })).toHaveFocus()
  })
  it('종료 뒤 체험 경로를 다시 선택하면 안내 화면으로 이동한다', async () => {
    mount('/consent')
    const user = await start()
    await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
    act(() => navigateForTest('/consent'))
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('시작하기 전에 확인해주세요')
    expect(screen.queryByText('입력한 내용을 삭제했습니다. 새로 시작할 수 있어요.')).not.toBeInTheDocument()
  })
  it('미동의 상태에서 체험 경로 직접 진입을 안내 화면으로 돌린다', () => {
    mount('/profile')
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('시작하기 전에 확인해주세요')
    expect(screen.getByRole('button', { name: /시작하기/ })).toBeDisabled()
  })
  it('공개 탐색은 로그인·동의·네트워크 호출 없이 열린다', () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    mount('/opportunities')
    expect(screen.getByRole('button', { name: '공고 검색하기' })).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('키보드로 안내 확인 후 입력하며 화면 이동 시 본문에 포커스한다', async () => {
    mount('/consent')
    const user = userEvent.setup()
    screen.getByRole('checkbox').focus()
    await user.keyboard(' ')
    await user.tab()
    expect(screen.getByRole('button', { name: /시작하기/ })).toHaveFocus()
    await user.keyboard('{Enter}')
    expect(screen.getByRole('textbox', { name: '내가 해온 일' })).toBeVisible()
    expect(screen.getByRole('main')).toHaveFocus()
    expect(document.title).toBe('경험 이야기 | 다시잇다')
  })
  it('악성 HTML을 실행 가능한 요소로 만들지 않고 입력 문장으로 표시한다', async () => {
    const { container } = mount('/consent')
    const user = await start()
    const attack = '<img src=x onerror="alert(1)"><script>alert(1)</script>'
    await user.click(screen.getByRole('textbox'))
    await user.paste(attack)
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    expect(screen.getByText(attack)).toBeVisible()
    expect(container.querySelector('img, script')).toBeNull()
    expect(screen.queryByRole('button', { name: /확정|저장/ })).not.toBeInTheDocument()
  })
  it('수정 왕복에는 메모리 입력을 유지하고 영구 저장소·네트워크에는 쓰지 않는다', async () => {
    const store = vi.spyOn(Storage.prototype, 'setItem')
    const indexedDB = { open: vi.fn() }
    const fetch = vi.fn()
    vi.stubGlobal('indexedDB', indexedDB)
    vi.stubGlobal('fetch', fetch)
    mount('/consent')
    const user = await start()
    await user.type(screen.getByRole('textbox'), '도서관 책 정리를 도왔어요.')
    await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
    await user.click(screen.getByRole('link', { name: '경험 수정하기' }))
    expect(screen.getByRole('textbox')).toHaveValue('도서관 책 정리를 도왔어요.')
    expect(store).not.toHaveBeenCalled()
    expect(indexedDB.open).not.toHaveBeenCalled()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('종료 후 다시 시작해도 이전 입력을 복원하지 않는다', async () => {
    mount('/consent')
    const user = await start()
    await user.type(screen.getByRole('textbox'), '폐기할 가상 경험')
    await user.click(screen.getByRole('button', { name: '종료하고 삭제' }))
    expect(screen.getByRole('status')).toHaveTextContent('입력한 내용을 삭제했습니다.')
    act(() => navigateForTest('/consent'))
    await start()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
  it('새로고침에 해당하는 재마운트에서는 이전 입력·동의를 복원하지 않는다', async () => {
    const view = mount('/consent')
    const user = await start()
    await user.type(screen.getByRole('textbox'), '이전 화면 입력')
    view.unmount()
    mount('/conversation')
    expect(screen.getByRole('button', { name: /시작하기/ })).toBeDisabled()
    await start()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
  it('전체 페이지를 떠날 때 메모리 입력과 동의를 제거한다', async () => {
    mount('/consent')
    const user = await start()
    await user.type(screen.getByRole('textbox'), '떠나기 전 입력')
    act(() => window.dispatchEvent(new Event('pagehide')))
    expect(screen.getByRole('button', { name: /시작하기/ })).toBeDisabled()
    await start()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
  it.each(['/transcription', '/preparation'])('체험의 대기 화면 %s에서도 종료할 수 있다', async (path) => {
    mount('/consent')
    const user = await start()
    if (path === '/transcription') await user.click(screen.getByRole('link', { name: '음성 입력 안내' }))
    else {
      await user.click(screen.getByRole('link', { name: '작성한 내용 확인하기' }))
      await user.click(screen.getByText('다른 화면 살펴보기'))
      await user.click(screen.getByRole('link', { name: '지원 내용 직접 작성해 보기' }))
    }
    expect(screen.getByRole('button', { name: '종료하고 삭제' })).toBeVisible()
  })
  it('bfcache 복귀에서도 이전 입력과 동의를 복원하지 않는다', async () => {
    mount('/consent')
    const user = await start()
    await user.type(screen.getByRole('textbox'), '복원하면 안 되는 입력')
    act(() => window.dispatchEvent(new PageTransitionEvent('pageshow', { persisted: true })))
    expect(screen.getByRole('button', { name: /시작하기/ })).toBeDisabled()
    await start()
    expect(screen.getByRole('textbox')).toHaveValue('')
  })
  it.each(['/me', '/admin', '/opportunities/preview', '/missing'])('%s를 오류 없이 열고 실패·미연동 상태를 명시한다', async (path) => {
    mount(path)
    expect(await screen.findByRole('heading', { level: 1 })).toBeVisible()
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
  })
  it.each([
    '/journeys/invalid/conversation',
    '/journeys/invalid/profile',
    '/journeys/invalid/opportunities/invalid/preparation',
    '/journeys/invalid/save',
  ])('잘못된 주소 %s에서 공개 공고로 돌아갈 수 있다', async (path) => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    mount(path)
    expect(screen.getByRole('heading', { level: 1, name: /주소를 확인해 주세요/ })).toBeVisible()
    await userEvent.click(screen.getByRole('link', { name: /공고.*살펴보기/ }))
    expect(screen.getByRole('heading', { level: 1, name: '조건에 맞는 기회 찾아보기' })).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })
  it('렌더링 오류의 내부 메시지·입력을 사용자 오류 화면에 노출하지 않는다', () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    function Broken(): never { throw new Error('private-input-and-server-path') }
    render(<ErrorBoundary><Broken /></ErrorBoundary>)
    expect(screen.getByRole('alert')).toHaveTextContent('새로 시작해 주세요.')
    expect(document.body).not.toHaveTextContent('private-input-and-server-path')
  })
})
