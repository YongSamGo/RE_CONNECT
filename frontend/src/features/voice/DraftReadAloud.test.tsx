import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, expect, it, vi } from 'vitest'
import { anonymousSession } from '../../api/fixtures'
import type { JourneyDraft } from '../preparation/drafts'
import { DraftReadAloud } from './DraftReadAloud'

const draft: JourneyDraft = { draft_id: '00000000-0000-0000-0000-000000000002', revision: 3, mode: 'manual',
  opportunity: { id: '00000000-0000-0000-0000-000000000003', version: 1 }, profile_version: 1,
  self_introduction: '직접 적은 경험', motivation: '직접 적은 지원동기', approved_at: null, review_reasons: [], warnings: [] }
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('reads a single selected versioned draft field and releases audio before switching', async () => {
  document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  const fetch = vi.fn(async (request: Request) => request.method === 'GET'
    ? new Response(JSON.stringify(anonymousSession), { headers: { 'Content-Type': 'application/json' } })
    : new Response(new Blob(['RIFF'], { type: 'audio/wav' }), { headers: { 'Content-Type': 'audio/wav', 'X-Speech-Segment-Count': '1' } }))
  vi.stubGlobal('fetch', fetch)
  const pause = vi.fn(), revoke = vi.fn()
  vi.stubGlobal('Audio', class { play = () => Promise.resolve(); pause = pause; load = vi.fn(); removeAttribute = vi.fn(); onended = null; onerror = null })
  const NativeURL = URL
  vi.stubGlobal('URL', Object.assign(class extends NativeURL {}, { createObjectURL: () => 'blob:draft-speech', revokeObjectURL: revoke }))
  render(<DraftReadAloud journeyId="00000000-0000-0000-0000-000000000001" draft={draft} />)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '자기소개 읽어주기' }))
  expect(await screen.findByText('읽어주기를 재생하고 있어요.')).toBeVisible()
  const post = fetch.mock.calls.find(([request]) => request.method === 'POST')![0]
  expect(await post.json()).toEqual({ target: { kind: 'journey_draft', journey_id: '00000000-0000-0000-0000-000000000001',
    draft_id: draft.draft_id, revision: 3, field: 'self_introduction' }, segment: 0 })
  await user.selectOptions(screen.getByLabelText('읽을 초안 항목'), 'motivation')
  expect(pause).toHaveBeenCalled()
  expect(revoke).toHaveBeenCalledWith('blob:draft-speech')
  expect(screen.queryByRole('button', { name: '자기소개 읽어주기' })).not.toBeInTheDocument()
  expect(screen.getByRole('button', { name: '지원동기 읽어주기' })).toBeEnabled()
  expect(fetch).toHaveBeenCalledTimes(2)
})

it('offers only nonempty fields and does not request audio for an empty draft', () => {
  const fetch = vi.fn()
  vi.stubGlobal('fetch', fetch)
  const view = render(<DraftReadAloud journeyId="j" draft={{ ...draft, self_introduction: '' }} />)
  expect(screen.getAllByRole('option').map(option => option.textContent)).toEqual(['지원동기'])
  view.rerender(<DraftReadAloud journeyId="j" draft={{ ...draft, self_introduction: '', motivation: ' ' }} />)
  expect(screen.queryByRole('button')).not.toBeInTheDocument()
  expect(fetch).not.toHaveBeenCalled()
})
