import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { JourneyConversation } from './JourneyConversation'

vi.mock('../voice/VoicePreview', () => ({ VoicePreview: ({ transcription }: { transcription: { onRequest: (blob: Blob) => void } }) => <button onClick={() => transcription.onRequest(new Blob(['fixture-audio'], { type: 'audio/webm' }))}>시험 음성 전사</button> }))
const id = '12345678-1234-1234-1234-123456789012'
const transcriptId = '22345678-1234-1234-1234-123456789012'
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status, headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals(); document.cookie = '__Host-rc_csrf=; Max-Age=0; Secure; Path=/' })

it('sends only the explicitly imported corrected transcript with its server reference and profile revision', async () => {
  const native = await new Response('fixture=1', { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }).formData()
  vi.stubGlobal('FormData', native.constructor); vi.stubGlobal('Blob', NodeBlob); vi.stubGlobal('File', NodeFile)
  const fetch = vi.fn(async (request: Request) => {
    if (request.url.endsWith('/me')) return json({ authenticated: false, user: null, pending_save_intent: null, consents: [{ purpose: 'ai_processing', notice_version: 'fixture-ai', granted_at: '2026-10-18T00:00:00Z' }] })
    if (request.url.endsWith('/transcriptions')) return json({ transcription_id: transcriptId, text: '가상 자동 전사', duration_seconds: 1.2 }, 201)
    if (request.url.endsWith('/messages')) return json({ code: 'MODEL_UNAVAILABLE' }, 503)
    return json({ revision: 1, confirmed: null, has_unconfirmed_changes: false, evidence: [], missing_for_recommendation: ['experiences'], draft: {
      schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [], paid_preference: null, available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: null, activity_constraints: null,
    } })
  })
  vi.stubGlobal('fetch', fetch); document.cookie = '__Host-rc_csrf=token; Secure; Path=/'
  render(<MemoryRouter><JourneyConversation journeyId={id} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '체험 대화 준비하기' }))
  await user.type(await screen.findByLabelText('내가 해온 일'), '기존 직접 입력')
  await user.click(screen.getByRole('button', { name: '말로 입력하고 전사 확인' }))
  await user.click(screen.getByRole('button', { name: '시험 음성 전사' }))
  const transcript = await screen.findByLabelText('글로 바꾼 내용 확인과 수정')
  await user.clear(transcript); await user.type(transcript, '내가 확인하고 수정한 가상 경험')
  expect(fetch.mock.calls.some(([request]) => request.url.endsWith('/messages'))).toBe(false)
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('기존 직접 입력')
  await user.click(screen.getByRole('checkbox', { name: '현재 경험 입력을 확인한 전사 문장으로 바꿀게요.' }))
  await user.click(screen.getByRole('button', { name: '확인한 전사 문장을 입력란으로 가져오기' }))
  expect(screen.getByLabelText('내가 해온 일')).toHaveValue('내가 확인하고 수정한 가상 경험')
  expect(fetch.mock.calls.some(([request]) => request.url.endsWith('/messages'))).toBe(false)
  await user.click(screen.getByRole('button', { name: '확인한 내용 보내기' }))
  await screen.findByText('지금은 AI를 사용할 수 없습니다. 직접 입력하거나 잠시 후 다시 시도해 주세요.')
  const message = fetch.mock.calls.find(([request]) => request.url.endsWith('/messages'))![0]
  expect(await message.clone().json()).toEqual({ text: '내가 확인하고 수정한 가상 경험', transcription_id: transcriptId, base_revision: 1 })
})

it('does not move focus behind open voice input after refreshing the profile', async () => {
  const fetch = vi.fn(async (request: Request) => request.url.endsWith('/me') ? json({}) : json({
    revision: 1, confirmed: null, has_unconfirmed_changes: false, evidence: [], missing_for_recommendation: ['experiences'], draft: {
      schema_version: 1, experiences: [], skills: [], preferred_regions: [], activity_types: [], paid_preference: null,
      available_weekdays: null, hours_per_week: null, mobility_note: null, residence_region: null, birth_year: null,
      certifications: null, completed_courses: null, activity_constraints: null,
    },
  }))
  vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter><JourneyConversation journeyId={id} /></MemoryRouter>)
  const user = userEvent.setup()
  await user.click(screen.getByRole('button', { name: '체험 대화 준비하기' }))
  await user.click(await screen.findByRole('button', { name: '말로 입력하고 전사 확인' }))
  await user.click(screen.getByRole('button', { name: '최신 프로필 상태 확인' }))
  await waitFor(() => expect(fetch).toHaveBeenCalledTimes(4))
  await waitFor(() => expect(screen.getByRole('button', { name: '최신 프로필 상태 확인' })).toBeEnabled())
  expect(screen.getByRole('heading', { level: 2 })).not.toHaveFocus()
  await user.click(screen.getByRole('button', { name: '음성 입력 닫고 원래 글로 돌아가기' }))
  expect(screen.getByLabelText('내가 해온 일')).toHaveFocus()
})
