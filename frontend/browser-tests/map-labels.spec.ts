import { expect, test } from '@playwright/test'
import { mockServiceApi } from './service-fixtures'

for (const width of [320, 390, 1280]) test(`${width}px 지도 이름 겹침과 경기 남부 해안 표시`, async ({ page }) => {
  await page.setViewportSize({ width, height: 900 })
  await mockServiceApi(page)
  await page.goto('/opportunities')
  await page.getByRole('button', { name: '경기 남부 지도 보기' }).click()
  const coast = page.getByRole('button', { name: '화성시', exact: true })
  await expect(coast).toBeVisible()
  expect((await coast.getAttribute('d'))?.match(/M/g)).toHaveLength(1)
  await coast.click()
  await expect(page.getByRole('button', { name: '화성시 선택됨' })).toHaveAttribute('aria-pressed', 'true')
  await page.getByRole('button', { name: '김포/인천 지도 보기' }).click()
  await page.evaluate(() => document.fonts.ready)
  for (const large of [false, true]) {
    if (large) await page.getByRole('button', { name: '큰 글씨 보기' }).click()
    const first = await page.locator('svg text').filter({ hasText: /^제물포구$/ }).boundingBox()
    const second = await page.locator('svg text').filter({ hasText: /^미추홀구$/ }).boundingBox()
    expect(first).not.toBeNull()
    expect(second).not.toBeNull()
    const overlapping = first!.x < second!.x + second!.width && first!.x + first!.width > second!.x && first!.y < second!.y + second!.height && first!.y + first!.height > second!.y
    expect(overlapping, '제물포구와 미추홀구 이름이 겹치면 안 됩니다').toBe(false)
    const third = await page.locator('svg text').filter({ hasText: /^남동구$/ }).boundingBox()
    const nextOverlap = second!.x < third!.x + third!.width && second!.x + second!.width > third!.x && second!.y < third!.y + third!.height && second!.y + second!.height > third!.y
    expect(nextOverlap, '미추홀구 이동으로 남동구 이름과 겹치면 안 됩니다').toBe(false)
  }
})
