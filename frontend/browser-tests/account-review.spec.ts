import { expect, test, type Page } from '@playwright/test'
import { join } from 'node:path'

const owner = '12345678-1234-4234-8234-123456789012'
const stamp = '2026-10-18T00:00:00Z'
const description = '도서관에서 책을 정리하고 방문객을 안내했습니다.'
const saved = { profile_id: owner, version: 1, saved_at: stamp, confirmed_at: stamp, content: {
  schema_version: 1, experiences: [{ id: owner, description, duration_note: null, skill_tags: [] }],
  skills: [], preferred_regions: [{ province: 'seoul', district: null }], activity_types: ['volunteering'],
  paid_preference: 'any', available_weekdays: [1], hours_per_week: 8, mobility_note: null,
  residence_region: null, birth_year: null, certifications: null, completed_courses: null, activity_constraints: null,
} }

// Synthetic API responses exercise production routes and confirmation boundaries.
// They do not establish a live Kakao session or prove actual server deletion.
async function accountApi(page: Page, pendingSave = false) {
  let profile: typeof saved | null = pendingSave ? null : saved
  let pending = pendingSave
  let consents = ['storage', 'ai_processing']
  const writes: { method: string; path: string; body: unknown; csrf: string | undefined }[] = []
  await page.context().addCookies([{ name: 'rc_csrf', value: 'browser-fixture', url: 'http://127.0.0.1:5178' }])
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname, method = request.method()
    if (method !== 'GET') writes.push({ method, path, body: request.postData() ? request.postDataJSON() : null, csrf: request.headers()['x-csrf-token'] })
    let data: unknown, status = 200
    if (path === '/api/v1/me' && method === 'GET') data = {
      authenticated: true, user: { id: owner, roles: ['user'], mfa_verified: false, reauth_until: null },
      consents: consents.map(purpose => ({ purpose, notice_version: 'fixture-' + purpose, granted_at: stamp })),
      pending_save_intent: pending ? { save_intent_id: owner, targets: { profile: true, draft: false }, existing_saved_profile_version: null, expires_at: new Date(Date.now() + 600000).toISOString() } : null,
    }
    else if (path === '/api/v1/profiles/me' && method === 'GET') data = { saved: profile }
    else if (path === '/api/v1/profiles/me' && method === 'DELETE') { profile = null; status = 204 }
    else if (path === '/api/v1/consents/withdraw' && method === 'POST') {
      const { purpose } = request.postDataJSON()
      consents = consents.filter(value => value !== purpose)
      if (purpose === 'storage') profile = null
      data = { purpose, withdrawn_at: stamp, deleted: {} }
    }
    else if (path === '/api/v1/profiles/me/versions' && method === 'POST') {
      pending = false; profile = saved; status = 201
      data = { version: 1, created: true, replaced_version: null, saved_at: stamp }
    }
    else { status = 404; data = { code: 'NOT_FOUND' } }
    await route.fulfill(status === 204 ? { status } : { status, json: data })
  })
  return writes
}

async function inspect(page: Page, name: string) {
  await page.evaluate(() => document.fonts.ready)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1)).toBe(true)
  await page.addScriptTag({ path: 'node_modules/axe-core/axe.min.js' })
  const violations = await page.evaluate(async () => {
    const axe = (window as unknown as { axe: { run: (node: string, options: object) => Promise<{ violations: { id: string; nodes: { html: string; failureSummary?: string }[] }[] }> } }).axe
    return (await axe.run('#root', { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] } })).violations.map(item => ({ id: item.id, nodes: item.nodes.map(node => ({ html: node.html, reason: node.failureSummary })) }))
  })
  expect(violations).toEqual([])
  if (process.env.SCREEN_REVIEW_DIR) await page.screenshot({ path: join(process.env.SCREEN_REVIEW_DIR, name + '.png'), fullPage: true })
}

for (const width of [320, 390, 768, 1280, 1440, 1920]) for (const large of [false, true]) {
  test(`회원 관리 ${width}px / ${large ? '큰 글씨' : '기본'}: AI 동의 철회와 프로필 삭제`, async ({ page }) => {
    await page.setViewportSize({ width, height: 650 })
    const writes = await accountApi(page)
    await page.goto('/me')
    await expect(page.getByRole('button', { name: '수정하기', exact: true })).toBeVisible()
    if (large) await page.getByRole('button', { name: '큰 글씨 보기' }).click()
    const label = `${width}-${large ? 'large' : 'normal'}`
    await inspect(page, label + '-member')
    await page.getByRole('button', { name: '동의 관리', exact: true }).click()
    await inspect(page, label + '-consents')
    expect(writes).toEqual([])
    await expect(page.getByRole('button', { name: 'AI 처리 동의 철회', exact: true })).toBeDisabled()
    await page.getByLabel('AI 처리 동의 철회와 임시 체험 종료를 확인했어요.').check()
    await page.getByRole('button', { name: 'AI 처리 동의 철회', exact: true }).click()
    await expect.poll(() => writes.length).toBe(1)
    const consentToggle = page.getByRole('button', { name: '동의 관리', exact: true })
    await expect(consentToggle).toBeVisible()
    if (await consentToggle.getAttribute('aria-expanded') === 'false') await consentToggle.click()
    await expect(page.getByText('현재 동의: 회원 저장', { exact: true })).toBeVisible()
    await expect(page.getByRole('heading', { name: '저장한 프로필', exact: true })).toBeVisible()
    await page.getByRole('button', { name: '저장 프로필 삭제', exact: true }).click()
    const remove = page.getByRole('button', { name: '프로필과 연결된 지원서 삭제', exact: true })
    await expect(remove).toBeDisabled()
    await inspect(page, label + '-delete-confirmation')
    await page.getByLabel('저장 프로필과 연결된 지원서를 삭제할게요.').check()
    await remove.click()
    await expect(page.getByText('아직 정보가 없습니다.')).toBeVisible()
    await expect(page.getByRole('heading', { name: '저장한 프로필', exact: true })).toHaveCount(0)
    await expect(page.getByRole('button', { name: '회원 탈퇴', exact: true })).toBeVisible()
    await inspect(page, label + '-after-deletion')
    expect(writes).toEqual([
      { method: 'POST', path: '/api/v1/consents/withdraw', body: { purpose: 'ai_processing' }, csrf: 'browser-fixture' },
      { method: 'DELETE', path: '/api/v1/profiles/me', body: null, csrf: 'browser-fixture' },
    ])
  })
}

test('회원 저장 동의 철회는 저장 프로필을 지우고 계정을 유지한다', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  const writes = await accountApi(page)
  await page.goto('/me')
  await page.getByRole('button', { name: '동의 관리', exact: true }).click()
  await page.getByLabel('회원 저장 동의 철회와 자료 삭제를 확인했어요.').check()
  await page.getByRole('button', { name: '회원 저장 동의 철회', exact: true }).click()
  await expect(page.getByText('아직 정보가 없습니다.')).toBeVisible()
  await expect(page.getByRole('button', { name: '회원 탈퇴', exact: true })).toBeVisible()
  expect(writes).toEqual([{ method: 'POST', path: '/api/v1/consents/withdraw', body: { purpose: 'storage' }, csrf: 'browser-fixture' }])
})

test('저장 목적 로그인 복귀 후 명시적으로 저장하고 나의 정보에서 조회한다', async ({ page }) => {
  const writes = await accountApi(page, true)
  await page.goto('/auth/result?purpose=save&status=success')
  await expect(page).toHaveURL('/me/save')
  const save = page.getByRole('button', { name: '이대로 저장하기', exact: true })
  await expect(save).toBeDisabled()
  expect(writes).toEqual([])
  await page.getByLabel('확정한 경험을 저장할게요.').check()
  await save.click()
  await expect(page.getByText('경험을 저장했습니다.', { exact: true })).toBeVisible()
  await page.getByRole('link', { name: '나의 정보로 이동', exact: true }).click()
  await expect(page.getByRole('heading', { name: '저장한 프로필', exact: true })).toBeVisible()
  expect(writes).toHaveLength(1)
  expect(writes[0]).toEqual({ method: 'POST', path: '/api/v1/profiles/me/versions', body: { source: { type: 'save_intent', save_intent_id: owner }, base_saved_version: null }, csrf: 'browser-fixture' })
})
