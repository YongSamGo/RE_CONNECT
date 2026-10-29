import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { BeginSaveRoute } from './BeginSave'

const id = '12345678-1234-4234-9234-123456789012'
const draftId = '22345678-1234-4234-9234-123456789012'
const intentId = '32345678-1234-4234-9234-123456789012'
const owner = '42345678-1234-4234-9234-123456789012'
const stamp = '2026-10-20T00:00:00Z'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const view = { revision: 3, confirmed: { version: 1, confirmed_at: stamp }, has_unconfirmed_changes: false, missing_for_recommendation: [], evidence: [], draft: {
  schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [], paid_preference: null,
  available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: [], activity_constraints: null,
} }
const notice = { version: 'fixture-storage', title: '가상 저장 안내', controller: '가상 주체', contact: '시험 문의처', aws_region: '시험 리전', body: '가상 안내', retention: '시험 보관', deletion: '시험 삭제' }
function setup(options: { bundle?: boolean; member?: boolean; available?: boolean; approved?: boolean; confirmed?: boolean } = {}) {
  const writes: Request[] = []
  const fetch = vi.fn(async (request: Request) => {
    const path = new URL(request.url).pathname
    if (request.method === 'GET') {
      if (path.endsWith('/consents/notices')) return json({ ai_processing: null, storage: options.available === false ? null : notice, login_available: options.available !== false })
      if (path === '/api/v1/me') return json({ authenticated: !!options.member, user: options.member ? { id: owner, roles: ['user'], mfa_verified: false, reauth_until: null } : null, consents: options.member ? [{ purpose: 'storage', notice_version: notice.version, granted_at: stamp }] : [], pending_save_intent: null })
      if (path.endsWith('/profiles/me')) return json({ saved: null })
      if (path.endsWith('/profile')) return json(options.confirmed === false ? { ...view, confirmed: null } : view)
      if (path.endsWith('/drafts/' + draftId)) return json({ draft_id: draftId, revision: 3, profile_version: 1, approved_at: options.approved === false ? null : stamp, review_reasons: [] })
    }
    writes.push(request.clone())
    if (path.endsWith('/auth/save-intents')) return json({ save_intent_id: intentId, expires_at: new Date(Date.now() + 600000).toISOString(), targets: { profile: true, draft: !!options.bundle } }, 201)
    if (path.endsWith('/profiles/me/versions')) return json({ version: 1, created: true, replaced_version: null, saved_at: stamp }, 201)
    if (request.method === 'DELETE') return new Response(null, { status: 204 })
    throw new Error('unexpected endpoint')
  })
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter initialEntries={[options.bundle ? `/journeys/${id}/drafts/${draftId}/save` : `/journeys/${id}/save`]}><Routes>
    <Route path="/journeys/:journeyId/save" element={<BeginSaveRoute />} /><Route path="/journeys/:journeyId/drafts/:draftId/save" element={<BeginSaveRoute />} />
  </Routes></MemoryRouter>)
  return { fetch, writes }
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('makes the anonymous profile and approved draft bundle explicit before making its login-bound reference', async () => {
  const { writes } = setup({ bundle: true })
  await userEvent.click(screen.getByRole('button', { name: '서버에서 저장 대상 확인' }))
  const checked = await screen.findByLabelText('프로필도 포함된 묶음 저장 준비를 확인했어요.')
  expect(screen.getByRole('heading', { name: '확인된 저장 대상' })).toBeVisible()
  expect(screen.getByText('확정 프로필 1번 · 승인한 지원서 수정본 3번')).toBeVisible()
  expect(writes).toHaveLength(0)
  expect(screen.getByRole('button', { name: '확인한 자료로 로그인 준비' })).toBeDisabled()
  await userEvent.click(checked)
  await userEvent.click(screen.getByRole('button', { name: '확인한 자료로 로그인 준비' }))
  expect(await screen.findByRole('link', { name: '카카오 로그인 후 저장 선택' })).toHaveAttribute('href', '/api/v1/auth/kakao/start?purpose=save')
  expect(writes).toHaveLength(1)
  expect(await writes[0]!.json()).toEqual({ journey_id: id, profile: { version: 1 }, draft: { draft_id: draftId, revision: 3 } })
  expect(document.body).not.toHaveTextContent(intentId)
  await userEvent.click(screen.getByRole('button', { name: '저장 준비 취소' }))
  expect(await screen.findByText(/선택한 저장 준비를 취소했습니다/)).toBeVisible()
  expect(writes[1]!.method).toBe('DELETE')
  expect(new URL(writes[1]!.url).pathname).toBe('/api/v1/auth/save-intents/' + intentId)
  expect(screen.queryByRole('link', { name: '카카오 로그인 후 저장 선택' })).not.toBeInTheDocument()
})

it('keeps new login and intent creation off while publication or provider is unavailable', async () => {
  const { writes } = setup({ available: false })
  await userEvent.click(screen.getByRole('button', { name: '서버에서 저장 대상 확인' }))
  expect(await screen.findByText('회원 저장 시작 준비 중이에요')).toBeVisible()
  expect(screen.queryByRole('button', { name: '확인한 자료로 로그인 준비' })).not.toBeInTheDocument()
  expect(writes).toHaveLength(0)
})

it('uses direct journey saving for the already bound member, without another login or anonymous intent', async () => {
  const { writes } = setup({ member: true })
  await userEvent.click(screen.getByRole('button', { name: '서버에서 저장 대상 확인' }))
  await userEvent.click(await screen.findByLabelText('확정 프로필 저장을 확인했어요.'))
  await userEvent.click(screen.getByRole('button', { name: '확인한 프로필 저장' }))
  expect(await screen.findByText('프로필 저장을 완료했습니다.')).toBeVisible()
  expect(screen.getByText(/단계별 저장 결과는 아래에서 확인해 주세요/)).toBeVisible()
  expect(screen.queryByText(/저장 버튼을 누르기 전에는 자료를 저장하지 않아요/)).not.toBeInTheDocument()
  expect(writes).toHaveLength(1)
  expect(await writes[0]!.json()).toEqual({ source: { type: 'journey', journey_id: id, version: 1 }, base_saved_version: null })
  expect(new URL(writes[0]!.url).pathname).toBe('/api/v1/profiles/me/versions')
})

it.each([{ bundle: true, approved: false }, { confirmed: false }])('rejects an unapproved or unconfirmed source before preparing login %j', async options => {
  const { writes } = setup(options)
  await userEvent.click(screen.getByRole('button', { name: '서버에서 저장 대상 확인' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(writes).toHaveLength(0)
  expect(screen.queryByRole('button', { name: '확인한 자료로 로그인 준비' })).not.toBeInTheDocument()
})
