import { expect, test, type Page } from '@playwright/test'
import { sampleDetail, sampleList } from '../src/features/public-opportunities/test-fixtures'

const widths = [320, 390, 768, 1280]
const sampleId = sampleDetail().id

async function mockPublicApi(page: Page) {
  await page.route('**/api/v1/opportunities**', async route => {
    const path = new URL(route.request().url()).pathname
    await route.fulfill({ json: path.endsWith(sampleId) ? sampleDetail() : sampleList() })
  })
}
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
  test(`${width}px / ${large ? '큰 글씨' : '기본'}: 주요 화면`, async ({ page }) => {
    await page.setViewportSize({ width, height: 900 })
    await mockPublicApi(page)
    await page.goto('/')
    await page.evaluate(() => document.fonts.ready)
    if (large) await page.getByRole('button', { name: '큰 글씨 보기' }).click()
    await expect(page.getByRole('button', { name: '큰 글씨 보기' })).toHaveAttribute('aria-pressed', String(large))
    await expect(page.getByRole('link', { name: '시작하기', exact: true })).toBeVisible()
    const sizes = await page.locator('.hero-actions .button').evaluateAll(elements => elements.map(element => getComputedStyle(element).fontSize))
    expect(sizes[0]).toBe(sizes[1])
    await checkLayout(page)
    await checkAxe(page)
    if (process.env.VISUAL_REGRESSION === '1') await expect(page).toHaveScreenshot(`home-${width}-${large ? 'large' : 'normal'}.png`, { fullPage: true })
    await page.getByRole('link', { name: '시작하기', exact: true }).click()
    await expect(page.getByRole('heading', { name: '내 정보가 어떻게 쓰이나요?' })).toBeVisible()
    await checkLayout(page)
    await checkAxe(page)
    if (process.env.VISUAL_REGRESSION === '1') await expect(page).toHaveScreenshot(`consent-${width}-${large ? 'large' : 'normal'}.png`, { fullPage: true })
    await page.getByRole('link', { name: '가상 경험으로 화면 미리보기' }).click()
    await expect(page.getByRole('heading', { name: '시작하기 전에 확인해주세요' })).toBeVisible()
    await page.getByLabel('입력과 보관 안내를 확인하고 미리보기에 동의해요.').check()
    await page.getByRole('button', { name: '미리보기 시작하기', exact: true }).click()
    await page.getByLabel('내가 해온 일').fill('도서관에서 책을 정리했어요.')
    await checkLayout(page)
    await page.getByRole('link', { name: '작성한 내용 확인하기' }).click()
    await expect(page.getByRole('heading', { name: '내 경험을 다시 살펴봐요' })).toBeVisible()
    await checkLayout(page)
    await page.getByText('다른 화면 살펴보기').click()
    await page.getByRole('link', { name: '지원 내용 직접 작성해 보기' }).click()
    await expect(page.getByLabel('자기소개')).toBeVisible()
    await checkLayout(page)
    await page.goto('/opportunities')
    await expect(page.getByRole('heading', { name: '조건에 맞는 기회 찾아보기' })).toBeVisible()
    await checkLayout(page)
    await page.getByRole('button', { name: '김포/인천 지도 보기' }).click()
    await checkLayout(page)
    await page.getByRole('button', { name: '공고 검색하기' }).click()
    await expect(page.getByRole('heading', { name: '가상 도서 정리 봉사' })).toBeVisible()
    await checkLayout(page)
    await page.getByRole('link', { name: '가상 도서 정리 봉사 공고 상세 화면으로' }).click()
    await page.getByRole('button', { name: '공고 정보 불러오기' }).click()
    await expect(page.getByRole('heading', { name: '가상 도서 정리 봉사' })).toBeVisible()
    await checkLayout(page)
    await page.goto('/me')
    await expect(page.getByRole('button', { name: '큰 글씨 보기' })).toHaveAttribute('aria-pressed', String(large))
    await checkLayout(page)
    await page.reload()
    await expect(page.getByRole('button', { name: '큰 글씨 보기' })).toHaveAttribute('aria-pressed', String(large))
  })
}

test('키보드로 글씨 크기를 바꾸고 초점을 유지한다', async ({ page }) => {
  await page.goto('/')
  const toggle = page.getByRole('button', { name: '큰 글씨 보기' })
  for (let i = 0; i < 8 && !(await toggle.evaluate(el => el === document.activeElement)); i++) await page.keyboard.press('Tab')
  await expect(toggle).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await expect(toggle).toBeFocused()
})


test('브라우저 저장소가 차단돼도 큰 글씨를 켤 수 있다', async ({ page }) => {
  await page.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked') } }) })
  await page.goto('/')
  const toggle = page.getByRole('button', { name: '큰 글씨 보기' })
  await toggle.click()
  await expect(toggle).toHaveAttribute('aria-pressed', 'true')
  await checkLayout(page)
})


test('큰 글씨는 홈 프레임 크기를 유지하면서 글자를 키운다', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await page.goto('/')
  const frame = page.locator('.home-video')
  const heading = page.getByRole('heading', { name: '여러분의 이야기를 들려주세요' })
  const before = await frame.boundingBox()
  const fontBefore = await heading.evaluate(el => parseFloat(getComputedStyle(el).fontSize))
  await page.getByRole('button', { name: '큰 글씨 보기' }).click()
  const after = await frame.boundingBox()
  const fontAfter = await heading.evaluate(el => parseFloat(getComputedStyle(el).fontSize))
  expect(after?.width).toBeCloseTo(before!.width, 1)
  expect(after?.height).toBeCloseTo(before!.height, 1)
  expect(fontAfter).toBeGreaterThan(fontBefore)
})


test('첫 화면 밖에서 같은 높이의 뒤로가기 버튼으로 시작에 돌아온다', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('link', { name: '뒤로가기', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: '모집 공고 살펴보기' }).click()
  const back = page.getByRole('link', { name: '뒤로가기', exact: true })
  const size = page.getByRole('button', { name: '큰 글씨 보기' })
  const backBox = await back.boundingBox()
  const sizeBox = await size.boundingBox()
  expect(backBox!.height).toBeCloseTo(sizeBox!.height, 1)
  expect(backBox!.x).toBeLessThan(sizeBox!.x)
  await back.click()
  await expect(page).toHaveURL('/')
  await expect(page.getByRole('heading', { name: '여러분의 이야기를 들려주세요' })).toBeVisible()
})
