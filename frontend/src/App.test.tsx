import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App, { ErrorBoundary } from './App'

function mount(path = '/') { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }

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
  it('공개 탐색은 로그인·동의·네트워크 호출 없이 열린다', () => {
    const fetch = vi.fn()
    vi.stubGlobal('fetch', fetch)
    mount('/opportunities')
    expect(screen.getByRole('button', { name: '공고 검색하기' })).toBeVisible()
    expect(fetch).not.toHaveBeenCalled()
  })
  it.each(['/consent'])('이전 동의 주소 %s는 실제 시작 안내로 이동한다', (path) => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    mount(path);
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('시작하기 전에 확인해주세요');
    expect(screen.getByRole('button', { name: '동의하고 대화 시작하기' })).toBeVisible();
    expect(screen.queryByText(/가상 경험|미리보기/)).not.toBeInTheDocument();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('내 프로필 주소는 회원용 프로필을 열고 임시 프로필을 생성하지 않는다', () => {
    const fetch = vi.fn(); vi.stubGlobal('fetch', fetch);
    mount('/profile');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('내 프로필');
    expect(screen.getByRole('button', { name: '저장한 프로필 불러오기' })).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });
  it('제거한 개발용 미리보기는 서비스 경로로 제공하지 않는다', () => {
    mount('/preview/service');
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent('페이지를 찾을 수 없어요');
  });
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
