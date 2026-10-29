import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import App from './App'
import { anonymousSession } from './api/fixtures'
import { sampleDetail } from './features/public-opportunities/test-fixtures'

// jsdom audits can be slower than a browser under parallel CI load. A timed-out
// audit keeps running and otherwise makes the following audits overlap.
vi.setConfig({ testTimeout: 20000 })
beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(null)
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } })))
})
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })
function app(path: string) {
  const view = render(<MemoryRouter initialEntries={[path]}><App /></MemoryRouter>)
  view.container.id = 'root-test'
  return view
}
async function audit() {
  await act(async () => {})
  const result = await axe.run(document.getElementById('root-test')!, {
    runOnly: { type: 'tag', values: ['wcag2a','wcag2aa','wcag21a','wcag21aa'] },
    rules: { 'color-contrast': { enabled: false } },
  })
  expect(result.passes.length).toBeGreaterThan(0)
  expect(result.violations.map(item => ({id:item.id, targets:item.nodes.map(node=>node.target)}))).toEqual([])
}
it.each(['/', '/start', '/guide', '/opportunities', '/me', '/login', '/recommendations', '/missing', '/journeys/invalid/profile'])('%s의 레이블과 구조를 검사한다', async path => {
  app(path); await screen.findByRole('heading',{level:1}); await audit()
})
it('검색 실패 상태에 초점과 재시도 행동을 제공한다', async () => {
  vi.stubGlobal('fetch',vi.fn().mockRejectedValue(new Error('test network failure')))
  app('/opportunities')
  await userEvent.click(screen.getByRole('button',{name:'공고 검색하기'}))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(screen.getByRole('region',{name:'공고 조회 결과'})).toHaveFocus()
  expect(screen.getByRole('button',{name:'다시 시도하기'})).toBeVisible()
  await audit()
})
it('자동 조회한 공고의 접힌 블록과 펼친 블록을 검사한다', async () => {
  const detail=sampleDetail()
  vi.stubGlobal('fetch',vi.fn(async (request:Request)=>new Response(JSON.stringify(request.url.endsWith('/me')?anonymousSession:detail),{headers:{'Content-Type':'application/json'}})))
  app(`/opportunities/${detail.id}`)
  await screen.findByRole('heading',{name:detail.title})
  await audit()
  for(const element of document.querySelectorAll('details')) element.open=true
  await audit()
})
