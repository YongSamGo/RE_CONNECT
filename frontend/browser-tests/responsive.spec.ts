import { expect, test, type Page } from '@playwright/test'
import { join } from 'node:path'
import { mockServiceApi } from './service-fixtures'
const widths = [320, 390, 768, 1280]

async function capture(page: Page, name: string) { if (process.env.SCREEN_REVIEW_DIR) await page.screenshot({ path: join(process.env.SCREEN_REVIEW_DIR, name + '.png'), fullPage: true }) }

async function checkLayout(page: Page) {
  const overflow = await page.evaluate(() => ({ width: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }))
  expect(overflow.scroll, 'document must not overflow horizontally').toBeLessThanOrEqual(overflow.width + 1)
  const clipping = await page.locator('main').evaluate(root => [...root.querySelectorAll('button, a, input, textarea, select, h1, h2')].filter(element => {
    const el = element as HTMLElement
    if (!el.getClientRects().length || el.closest('[hidden]') || getComputedStyle(el).visibility === 'hidden') return false
    const rect = el.getBoundingClientRect()
    return rect.left < -1 || rect.right > document.documentElement.clientWidth + 1
  }).map(element => `${element.tagName}: ${element.textContent?.trim().slice(0, 50)}`))
  expect(clipping).toEqual([])
}
async function checkAxe(page: Page) {
  await page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: string, options: object) => Promise<{ violations: { id: string; nodes: unknown[] }[] }> } }).axe
    return (await axe.run('#root', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } })).violations.map(v => ({ id: v.id, nodes: v.nodes.length }))
  })
  expect(violations).toEqual([])
}

for (const width of widths) for (const large of [false, true]) {
  test(`${width}px / ${large ? '큰 글씨' : '기본'}: 현재 이용 흐름`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockServiceApi(page)
    await page.goto('/')
    await page.evaluate(() => document.fonts.ready)
    if (large) await page.getByRole('button', { name: '큰 글씨 보기' }).click()
    await checkLayout(page); await checkAxe(page)
    await capture(page, `${width}-${large ? 'large' : 'normal'}-home`)
    await page.getByRole('link', { name: '시작하기', exact: true }).click()
    await expect(page.getByRole('heading', { name: '시작하기 전에 확인해주세요' })).toBeVisible()
    await checkLayout(page); await checkAxe(page)
    await page.getByRole('button', { name: '시작하기', exact: true }).click()
    const consent = page.getByRole('dialog', { name: 'AI 처리 안내와 동의' })
    await expect(consent).toBeVisible()
    await checkAxe(page)
    await page.getByRole('checkbox', { name: '위 안내문을 읽고 AI 처리에 동의합니다.' }).check()
    await expect(page.getByRole('heading', { name: '경험 이야기하기', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '안내 건너뛰기' }).click()
    await page.getByRole('button', { name: '글로 답하기' }).click()
    await page.getByLabel('내 답변', { exact: true }).fill('도서관에서 책을 정리하고 방문객을 안내했습니다.')
    await checkLayout(page); await checkAxe(page)
    await page.getByRole('button', { name: '완료하기', exact: true }).click()
    await page.getByRole('button', { name: '네, 완료하기' }).click()
    await page.getByRole('link', { name: '정리한 경험 확인하기' }).click()
    await page.getByRole('button', { name: '내가 해온 일 수정하기' }).waitFor()
    await checkLayout(page); await checkAxe(page)
    const headingWrap = await page.locator('.profile-summary-heading h2').evaluateAll(elements => elements.map(element => element.getBoundingClientRect().height / parseFloat(getComputedStyle(element).lineHeight)))
    expect(headingWrap.every(lines => lines <= 2.1), '프로필 제목이 수정 버튼에 밀려 잘게 나뉘지 않아야 합니다').toBe(true)
    await capture(page, `${width}-${large ? 'large' : 'normal'}-profile`)
    await page.getByRole('button', { name: '이 내용으로 확정' }).click()
    await page.getByRole('link', { name: '추천 공고 확인하기' }).click()
    await page.getByRole('link', { name: '가상 도서 정리 봉사 자세히 보기' }).click()
    await page.getByRole('heading', { name: '가상 도서 정리 봉사' }).waitFor()
    await checkLayout(page); await checkAxe(page)
    await page.getByRole('link', { name: '지원하기', exact: true }).click()
    await page.getByLabel('지원 자기소개', { exact: true }).waitFor()
    await expect(page.getByLabel('지원 동기', { exact: true })).not.toHaveValue('')
    await checkLayout(page); await checkAxe(page)
    await capture(page, `${width}-${large ? 'large' : 'normal'}-application`)
    await page.getByRole('button', { name: '지원 내용 검토하기' }).click()
    await expect(page.getByRole('dialog', { name: '지원 내용을 확인해 주세요' })).toBeVisible()
    await checkAxe(page)
    await page.getByRole('checkbox', { name: '두 항목을 읽고 확정 경험과 공고에 맞는 내용임을 확인했어요.' }).check()
    await page.getByRole('button', { name: '확인한 현재 본문 승인' }).click()
    await expect(page.getByText('확인한 내용을 승인했어요. 공식 신청처로 이동해 제출해 주세요.')).toBeVisible()
    await page.goto('/opportunities')
    await page.getByRole('button', { name: '김포/인천 지도 보기' }).click()
    await checkLayout(page)
    await page.getByRole('button', { name: '공고 검색하기' }).click()
    await page.getByRole('link', { name: '가상 도서 정리 봉사 자세히 보기' }).waitFor()
    await checkLayout(page)
    await page.goto('/guide'); await checkLayout(page); await checkAxe(page)
    await page.goto('/me')
    await expect(page.getByText('회원 정보를 보려면 로그인해 주세요.')).toBeVisible()
    await checkLayout(page)
    await expect(page.getByRole('button', { name: '큰 글씨 보기' })).toHaveAttribute('aria-pressed', String(large))
  })
}

test('키보드로 글씨 크기를 바꾸고 초점을 유지한다', async ({ page }) => {
  await mockServiceApi(page); await page.goto('/')
  const toggle=page.getByRole('button',{name:'큰 글씨 보기'})
  for(let i=0;i<10 && !(await toggle.evaluate(el=>el===document.activeElement));i++) await page.keyboard.press('Tab')
  await expect(toggle).toBeFocused();await page.keyboard.press('Enter')
  await expect(toggle).toHaveAttribute('aria-pressed','true');await expect(toggle).toBeFocused()
})
test('브라우저 저장소가 차단돼도 큰 글씨를 켤 수 있다', async ({page})=>{
  await mockServiceApi(page)
  await page.addInitScript(()=>{Object.defineProperty(window,'localStorage',{get(){throw new Error('blocked')}})})
  await page.goto('/');await page.getByRole('button',{name:'큰 글씨 보기'}).click();await checkLayout(page)
})
test('큰 글씨는 내용을 자르지 않고 홈 프레임을 확장한다', async ({page})=>{
  await mockServiceApi(page);await page.setViewportSize({width:1280,height:900});await page.goto('/')
  const frame=page.locator('.home-video'),heading=page.getByRole('heading',{name:'여러분의 이야기를 들려주세요'})
  const before=await frame.boundingBox(),fontBefore=await heading.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))
  await page.getByRole('button',{name:'큰 글씨 보기'}).click()
  const after=await frame.boundingBox()
  expect(after!.width).toBeCloseTo(before!.width,1);expect(after!.height).toBeGreaterThanOrEqual(before!.height)
  expect(await heading.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))).toBeGreaterThan(fontBefore)
  const fits=await frame.evaluate(el=>[...el.querySelectorAll('.hero-copy,.hero-actions')].every(child=>child.getBoundingClientRect().bottom<=el.getBoundingClientRect().bottom))
  expect(fits).toBe(true);await checkLayout(page)
})
test('뒤로가기 버튼은 이전 화면으로 이동한다',async({page})=>{
  await mockServiceApi(page);await page.goto('/')
  await expect(page.getByRole('button',{name:'뒤로가기',exact:true})).toHaveCount(0)
  await page.getByRole('link',{name:'모집 공고 살펴보기'}).click()
  const back=page.getByRole('button',{name:'뒤로가기',exact:true}),size=page.getByRole('button',{name:'큰 글씨 보기'})
  expect((await back.boundingBox())!.height).toBeCloseTo((await size.boundingBox())!.height,1)
  await back.click();await expect(page).toHaveURL('/')
})
test('로그인한 회원에게 자료가 없으면 시작 행동을 제공한다',async({page})=>{
  await mockServiceApi(page,true);await page.goto('/me')
  await expect(page.getByText('아직 정보가 없습니다.')).toBeVisible()
  await expect(page.getByRole('link',{name:'나의 경험 이야기하기'})).toHaveAttribute('href','/start')
  await expect(page.getByRole('link',{name:'나의 정보 보기'})).toHaveAttribute('href','/me')
})
