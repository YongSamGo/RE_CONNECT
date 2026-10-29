import { Blob as NodeBlob, File as NodeFile } from 'node:buffer'
import { render, screen } from '@testing-library/react'
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
  const user=userEvent.setup()
  await user.click(screen.getByRole('button',{name:'체험 대화 준비하기'}))
  await user.type(await screen.findByLabelText('내 답변'),'기존 직접 입력')
  await user.click(screen.getByRole('button',{name:'말하기'}))
  await user.click(screen.getByRole('button',{name:'시험 음성 전사'}))
  const text=await screen.findByLabelText('말씀하신 내용 확인')
  await user.clear(text);await user.type(text,'내가 확인하고 수정한 가상 경험')
  expect(fetch.mock.calls.some(([request])=>request.url.endsWith('/messages'))).toBe(false)
  await user.click(screen.getByRole('button',{name:'다음 질문'}))
  expect(screen.getByRole('dialog',{name:'답변 내용을 확인해 주세요'})).toBeVisible()
  await user.click(screen.getByRole('button',{name:'네, 완료하기'}))
  await screen.findByRole('alert')
  const message=fetch.mock.calls.find(([request])=>request.url.endsWith('/messages'))![0]
  expect(await message.clone().json()).toEqual({text:'내가 확인하고 수정한 가상 경험',transcription_id:transcriptId,base_revision:1})
})
