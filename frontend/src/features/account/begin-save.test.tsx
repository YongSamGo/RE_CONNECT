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

it('prepares only a confirmed profile for login after explicit selection', async () => {
  const { writes }=setup()
  await userEvent.click(screen.getByRole('button',{ name:'저장할 자료 확인' }))
  const check=await screen.findByLabelText('확정한 경험을 저장할 준비가 됐어요.')
  expect(writes).toHaveLength(0)
  expect(screen.getByRole('button',{ name:'확인한 자료로 로그인 준비' })).toBeDisabled()
  await userEvent.click(check)
  await userEvent.click(screen.getByRole('button',{ name:'확인한 자료로 로그인 준비' }))
  expect(await screen.findByRole('link',{ name:'카카오 로그인 후 저장 선택' })).toHaveAttribute('href','/api/v1/auth/kakao/start?purpose=save')
  expect(await writes[0].clone().json()).toEqual({ journey_id:id, profile:{version:1}, draft:null })
  expect(writes[0].headers.get('Idempotency-Key')).toMatch(/^[a-f0-9-]{36}$/)
  await userEvent.click(screen.getByRole('button',{ name:'저장 준비 취소' }))
  expect(await screen.findByText(/선택한 저장 준비를 취소했습니다/)).toBeVisible()
  expect(writes.at(-1)?.method).toBe('DELETE')
})
it('cannot prepare an unconfirmed profile or a login connection without published terms', async () => {
  const { writes }=setup({ confirmed:false })
  await userEvent.click(screen.getByRole('button',{ name:'저장할 자료 확인' }))
  expect(await screen.findByRole('alert')).toBeVisible(); expect(writes).toHaveLength(0)
})
it('shows unavailable storage without inventing a successful save', async () => {
  const { writes }=setup({ available:false })
  await userEvent.click(screen.getByRole('button',{ name:'저장할 자료 확인' }))
  expect(await screen.findByText('회원 저장 시작 준비 중이에요')).toBeVisible()
  expect(writes).toHaveLength(0)
})
it('lets a signed-in member save only their confirmed experience', async () => {
  const { writes }=setup({ member:true })
  await userEvent.click(screen.getByRole('button',{ name:'저장할 자료 확인' }))
  await userEvent.click(await screen.findByLabelText('확정한 경험을 저장할게요.'))
  await userEvent.click(screen.getByRole('button',{ name:'이대로 저장하기' }))
  expect(await screen.findByText('경험을 저장했습니다.')).toBeVisible()
  expect(await writes[0].clone().json()).toEqual({source:{type:'journey',journey_id:id,version:1},base_saved_version:null})
  expect(writes.some(request=>new URL(request.url).pathname.endsWith('/drafts'))).toBe(false)
})
