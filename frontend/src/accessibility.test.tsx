import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import App from './App'

beforeEach(() => {
  // axe feature detection asks for a canvas context; jsdom has no renderer.
  // Report the missing capability without stubbing audit results or rules.
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function mount(path: string) { return render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>) }
async function audit() {
  // jsdom cannot calculate rendered contrast/geometry. Inspect the app subtree
  // rather than asserting that jsdom's host document has production HTML attrs.
  const result = await axe.run(document.getElementById('root-test')!, {
    runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] },
    rules: { 'color-contrast': { enabled: false } },
  })
  expect(result.passes.length).toBeGreaterThan(0)
  expect(result.violations.map(item => ({ id: item.id, targets: item.nodes.map(node => node.target) }))).toEqual([])
}
function app(path: string) {
  const view = mount(path)
  view.container.id = 'root-test'
  return view
}

it.each(['/', '/consent', '/opportunities', '/opportunities/preview', '/me', '/me/saved', '/admin', '/missing'])('%s 화면의 구조·레이블·ARIA를 자동 검사한다', async path => {
  vi.stubGlobal('fetch', vi.fn())
  app(path)
  await audit()
})

it('audits an asynchronous request error while preserving the result focus and retry action', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('test network failure')))
  app('/opportunities')
  await userEvent.click(screen.getByRole('button', { name: '공고 검색하기' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByRole('region', { name: '공고 조회 결과' })).toHaveFocus()
  expect(screen.getByRole('button', { name: '같은 조건으로 다시 조회' })).toBeVisible()
  await audit()
})

it('audits experience input, empty profile errors and manual writing in one preview lifetime', async () => {
  vi.stubGlobal('fetch', vi.fn())
  app('/consent')
  const user = userEvent.setup()
  await user.click(screen.getByRole('checkbox'))
  await user.click(screen.getByRole('button', { name: /미리보기 시작하기/ }))
  await audit()
  await user.click(screen.getByRole('link', { name: /작성한 내용 확인하기/ }))
  await user.click(screen.getByRole('button', { name: '작성 항목 확인하기' }))
  expect(screen.getByRole('region', { name: '입력한 항목을 확인해 주세요' })).toHaveFocus()
  await audit()
  await user.click(screen.getByRole('link', { name: '지원 내용 직접 작성해 보기' }))
  fireEvent.change(screen.getByRole('textbox', { name: '자기소개' }), { target: { value: '가상 경험입니다.' } })
  fireEvent.change(screen.getByRole('textbox', { name: '지원동기' }), { target: { value: '가상의 지원 이유입니다.' } })
  await user.click(screen.getByRole('checkbox', { name: '작성한 두 항목을 읽고, 내 경험과 맞는 내용인지 확인했어요.' }))
  await audit()
})
