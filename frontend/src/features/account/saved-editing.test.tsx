import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import axe from 'axe-core'
import { anonymousSession } from '../../api/fixtures'
import { SavedDraftEditor } from './SavedDraftEditor'
import { SavedProfileSave } from './SavedProfileSave'

const documentId = '12345678-1234-4234-9234-123456789012'
const journeyId = '22345678-1234-4234-9234-123456789012'
const draftId = '32345678-1234-4234-9234-123456789012'
const opportunityId = '42345678-1234-4234-9234-123456789012'
const profileId = '52345678-1234-4234-9234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
const member = { ...anonymousSession, authenticated: true, user: { id: profileId, roles: ['user'], mfa_verified: false, reauth_until: null } }
const draft = { draft_id: draftId, revision: 1, mode: 'from_saved', profile_version: 1,
  opportunity: { id: opportunityId, version: 3 }, self_introduction: '<script>가상 경험</script>', motivation: '가상 동기', approved_at: null,
  review_reasons: [], warnings: ['새 임시 편집본입니다. 다시 승인해 주세요.'] }
function transport() {
  const fetch = vi.fn().mockResolvedValueOnce(json(member)).mockResolvedValueOnce(json({ saved: { profile_id: profileId, version: 2 } }))
    .mockResolvedValueOnce(json({ id: opportunityId, version: 3 })).mockResolvedValueOnce(json({ journey_id: journeyId, confirmed: { version: 1 } }))
    .mockResolvedValueOnce(json(draft))
  vi.stubGlobal('fetch', fetch)
  document.cookie = '__Host-rc_csrf=test; Secure; Path=/'
  return fetch
}
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('keeps edits and the same save key after failure, with copy and an explicit retry', async () => {
  const fetch = transport(), user = userEvent.setup()
  const clipboard = vi.spyOn(navigator.clipboard, 'writeText').mockResolvedValue()
  render(<SavedDraftEditor documentId={documentId} version={1} opportunityId={opportunityId} />)
  await user.click(screen.getByRole('button', { name: '저장본으로 새 임시 편집 시작' }))
  const input = await screen.findByLabelText('재편집 자기소개')
  expect(input).toHaveValue(draft.self_introduction)
  expect(document.querySelector('script')).toBeNull()
  expect(fetch).toHaveBeenCalledTimes(5)
  await user.clear(input); await user.type(input, '새로 쓴 가상 경험')
  expect(fetch).toHaveBeenCalledTimes(5)
  expect(screen.getByRole('button', { name: /지원서 저장/ })).toBeDisabled()
  fetch.mockResolvedValueOnce(json({ ...draft, revision: 2, self_introduction: '새로 쓴 가상 경험' }))
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  fetch.mockResolvedValueOnce(json({ ...draft, revision: 3, self_introduction: '새로 쓴 가상 경험', approved_at: '2026-10-21T00:00:00Z' }))
  await user.click(screen.getByRole('button', { name: '내용을 읽고 현재 근거에 맞게 재승인' }))
  expect(fetch).toHaveBeenCalledTimes(7)
  fetch.mockResolvedValueOnce(json({ code: 'SERVICE_UNAVAILABLE', message: 'private payload' }, 503))
  await user.click(screen.getByRole('button', { name: /지원서 저장/ }))
  expect(await screen.findByRole('alert')).toHaveTextContent('서비스 연결이 원활하지 않습니다')
  expect(input).toHaveValue('새로 쓴 가상 경험')
  expect(document.body).not.toHaveTextContent('private payload')
  await user.click(screen.getByRole('button', { name: '편집 내용 복사' }))
  expect(clipboard).toHaveBeenCalledWith('자기소개\n새로 쓴 가상 경험\n\n지원동기\n가상 동기')
  fetch.mockResolvedValueOnce(json({ document_id: documentId, version: 2 }))
  await user.click(screen.getByRole('button', { name: /지원서 저장/ }))
  expect(await screen.findByText('지원서 2번을 저장했습니다.')).toBeVisible()
  const first = fetch.mock.calls[7]![0] as Request, second = fetch.mock.calls[8]![0] as Request
  expect(first.headers.get('Idempotency-Key')).toBe(second.headers.get('Idempotency-Key'))
  expect(await second.json()).toEqual({ source: { type: 'journey', journey_id: journeyId, draft_id: draftId, revision: 3 }, document_id: documentId, base_document_version: 1 })
  expect(second.headers.get('X-CSRF-Token')).toBe('test')
  expect(screen.getByRole('button', { name: /지원서 저장/ })).toBeDisabled()
})

it('clears the editor on pagehide and refuses to restore a late start response', async () => {
  const fetch = transport(), user = userEvent.setup()
  let resolve!: (value: Response) => void
  fetch.mockReset().mockReturnValueOnce(new Promise<Response>(done => { resolve = done }))
  render(<SavedDraftEditor documentId={documentId} version={1} opportunityId={opportunityId} />)
  await user.click(screen.getByRole('button', { name: '저장본으로 새 임시 편집 시작' }))
  act(() => window.dispatchEvent(new Event('pagehide')))
  await act(async () => resolve(json(member)))
  expect(screen.queryByLabelText('재편집 자기소개')).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('shows the returned draft before approval and rejects an approval with different content', async () => {
  const fetch = transport(), user = userEvent.setup()
  render(<SavedDraftEditor documentId={documentId} version={1} opportunityId={opportunityId} />)
  await user.click(screen.getByRole('button', { name: '저장본으로 새 임시 편집 시작' }))
  const input = await screen.findByLabelText('재편집 자기소개')
  await user.clear(input); await user.type(input, '직접 수정한 내용')
  fetch.mockResolvedValueOnce(json({ ...draft, revision: 2, self_introduction: '서버가 반환한 내용' }))
  await user.click(screen.getByRole('button', { name: '수정 내용을 임시 초안에 반영' }))
  expect(input).toHaveValue('서버가 반환한 내용')
  fetch.mockResolvedValueOnce(json({ ...draft, revision: 3, self_introduction: '다른 승인 내용', approved_at: '2026-10-21T00:00:00Z' }))
  await user.click(screen.getByRole('button', { name: '내용을 읽고 현재 근거에 맞게 재승인' }))
  expect(await screen.findByRole('alert')).toBeVisible()
  expect(input).toHaveValue('서버가 반환한 내용')
  expect(screen.getByRole('button', { name: '재승인한 지원서 저장' })).toBeDisabled()
})

it('offers manual selection when copying edited content fails', async () => {
  transport()
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('private clipboard detail'))
  const user = userEvent.setup()
  const { container } = render(<SavedDraftEditor documentId={documentId} version={1} opportunityId={opportunityId} />)
  await user.click(screen.getByRole('button', { name: '저장본으로 새 임시 편집 시작' }))
  await screen.findByLabelText('재편집 자기소개')
  await user.click(screen.getByRole('button', { name: '편집 내용 복사' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('자동 복사를 완료하지 못했어요')
  await user.click(screen.getByRole('button', { name: '복사 내용 전체 선택' }))
  const field = screen.getByRole('textbox', { name: '복사할 편집 내용' }) as HTMLTextAreaElement
  expect(field).toHaveFocus()
  expect(field.selectionEnd - field.selectionStart).toBe(field.value.length)
  expect(document.body).not.toHaveTextContent('private clipboard detail')
  const result = await axe.run(container, { runOnly: { type: 'tag', values: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] }, rules: { 'color-contrast': { enabled: false } } })
  expect(result.violations.map(item => item.id)).toEqual([])
})

it('does not grant AI consent or start a journey without existing consent', async () => {
  const fetch = vi.fn(async () => json({ ...member, consents: [] })); vi.stubGlobal('fetch', fetch)
  render(<SavedDraftEditor documentId={documentId} version={1} opportunityId={opportunityId} />)
  await userEvent.click(screen.getByRole('button', { name: '저장본으로 새 임시 편집 시작' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('동의')
  expect(fetch).toHaveBeenCalledTimes(1)
})

it('retries profile save with the same key and carries the saved base into the next confirmation', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(json({ code: 'SERVICE_UNAVAILABLE', message: 'private' }, 503))
    .mockResolvedValueOnce(json({ version: 5 })).mockResolvedValueOnce(json({ version: 6 }))
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=test; Secure; Path=/'
  const user = userEvent.setup()
  const component = (version: number) => <SavedProfileSave journeyId={journeyId} version={version} baseVersion={4} disabled={false} copyText="가상 경험" />
  const view = render(component(1))
  await user.click(screen.getByRole('button', { name: /재확정 프로필 저장/ }))
  expect(await screen.findByRole('alert')).toBeVisible()
  await user.click(screen.getByRole('button', { name: /재확정 프로필 저장/ }))
  expect(await screen.findByText('프로필 5번을 저장했습니다.')).toBeVisible()
  expect((fetch.mock.calls[0]![0] as Request).headers.get('Idempotency-Key')).toBe((fetch.mock.calls[1]![0] as Request).headers.get('Idempotency-Key'))
  view.rerender(component(2))
  await user.click(screen.getByRole('button', { name: /재확정 프로필 저장/ }))
  expect(await screen.findByText('프로필 6번을 저장했습니다.')).toBeVisible()
  expect(await (fetch.mock.calls[2]![0] as Request).json()).toEqual({ source: { type: 'journey', journey_id: journeyId, version: 2 }, base_saved_version: 5 })
})

it('offers manual selection if profile copying fails', async () => {
  vi.spyOn(navigator.clipboard, 'writeText').mockRejectedValue(new Error('private clipboard detail'))
  const user = userEvent.setup()
  render(<SavedProfileSave journeyId={journeyId} version={1} baseVersion={4} disabled={false} copyText="가상 경험" />)
  await user.click(screen.getByRole('button', { name: '프로필 내용 복사' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('자동 복사를 완료하지 못했어요')
  await user.click(screen.getByRole('button', { name: '프로필 내용 전체 선택' }))
  const field = screen.getByRole('textbox', { name: '복사할 프로필 내용' }) as HTMLTextAreaElement
  expect(field).toHaveFocus()
  expect(field.selectionEnd - field.selectionStart).toBe(field.value.length)
  expect(document.body).not.toHaveTextContent('private clipboard detail')
})

it('does not report an old copy after the profile content changes', async () => {
  let complete!: () => void
  vi.spyOn(navigator.clipboard, 'writeText').mockImplementation(() => new Promise<void>(resolve => { complete = resolve }))
  const user = userEvent.setup()
  const component = (copyText: string) => <SavedProfileSave journeyId={journeyId} version={1} baseVersion={4} disabled={false} copyText={copyText} />
  const view = render(component('이전 가상 경험'))
  await user.click(screen.getByRole('button', { name: '프로필 내용 복사' }))
  view.rerender(component('수정한 가상 경험'))
  await act(async () => complete())
  expect(screen.queryByText('프로필 내용을 복사했습니다.')).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '프로필 내용 복사' })).toBeEnabled()
})
