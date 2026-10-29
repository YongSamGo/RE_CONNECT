import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, expect, it, vi } from 'vitest'
import { JourneyResult } from './JourneyResult'

const id = '12345678-1234-4234-8234-123456789012'
const content = { schema_version: 1, experiences: [{ id, description: '도서관에서 책을 정리했어요.', duration_note: null, skill_tags: ['자료 정리'] }],
  skills: [], preferred_regions: [], activity_types: [], paid_preference: null, available_weekdays: null, hours_per_week: null,
  mobility_note: null, residence_region: null, birth_year: null, certifications: null, completed_courses: null, activity_constraints: null }
const json = (confirmed: boolean) => new Response(JSON.stringify({ revision: 1, draft: content, evidence: [],
  confirmed: confirmed ? { version: 1, confirmed_at: '2026-10-28T00:00:00Z' } : null,
  has_unconfirmed_changes: !confirmed, missing_for_recommendation: ['preferred_regions', 'activity_types'],
}), { headers: { 'Content-Type': 'application/json' } })
afterEach(() => { vi.restoreAllMocks(); vi.unstubAllGlobals() })

it.each([false, true])('offers save only for a server-confirmed unchanged profile: %s', async confirmed => {
  const fetch = vi.fn(async () => json(confirmed)); vi.stubGlobal('fetch', fetch)
  render(<MemoryRouter><JourneyResult journeyId={id} /></MemoryRouter>)
  expect(screen.queryByRole('link', { name: '이 프로필 저장하기' })).not.toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: '정리한 경험 불러오기' }))
  expect(await screen.findByText(content.experiences[0].description)).toBeVisible()
  if (confirmed) expect(screen.getByRole('link', { name: '이 프로필 저장하기' })).toHaveAttribute('href', `/journeys/${id}/save`)
  else expect(screen.queryByRole('link', { name: '이 프로필 저장하기' })).not.toBeInTheDocument()
  expect(fetch).toHaveBeenCalledTimes(1)
  act(() => window.dispatchEvent(new Event('pagehide')))
  expect(screen.queryByText(content.experiences[0].description)).not.toBeInTheDocument()
})
