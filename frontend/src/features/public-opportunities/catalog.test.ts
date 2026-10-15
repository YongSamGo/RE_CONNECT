import { describe, expect, it } from 'vitest'
import { ApiError } from '../../api/errors'
import { deadlineLabel, parseList } from './catalog'
import { sampleList, sampleOpportunity } from './test-fixtures'

describe('public catalogue response boundary', () => {
  it('preserves unknown values rather than inventing region, pay or recruitment facts', () => {
    const input = sampleList({ items: [sampleOpportunity({ activity_region: null, paid: null, recruitment_status: 'unknown', change_pending: true })] })
    expect(parseList(input, 1)).toEqual(input)
  })
  it.each([
    ['missing required keys', {}],
    ['malformed items', { ...sampleList(), items: 'private server details' }],
    ['oversized page', { ...sampleList(), page_size: 21 }],
    ['wrong requested page', { ...sampleList(), page: 2 }],
    ['negative total', { ...sampleList(), total: -1 }],
    ['impossible total', { ...sampleList(), total: 0 }],
    ['duplicate identities', sampleList({ items: [sampleOpportunity(), sampleOpportunity()], total: 2 })],
    ['unsafe route identity', sampleList({ items: [sampleOpportunity({ id: '../admin' })] })],
    ['closed listing', sampleList({ items: [sampleOpportunity({ recruitment_status: 'closed' })] })],
    ['unrecognized enum', { ...sampleList(), items: [{ ...sampleOpportunity(), activity_type: 'invented' }] }],
    ['missing explicit null', { ...sampleList(), items: [{ ...sampleOpportunity(), paid: undefined }] }],
    ['impossible calendar date', sampleList({ items: [sampleOpportunity({ deadline_date: '2026-02-30' })] })],
    ['timestamp missing timezone', sampleList({ items: [sampleOpportunity({ deadline_at: '2026-10-30T11:00:00' })] })],
    ['conflicting date/time', sampleList({ items: [sampleOpportunity({ deadline_at: '2026-10-30T16:00:00Z' })] })],
  ])('rejects %s without returning original server content', (_name, input) => {
    expect(() => parseList(input, 1)).toThrow(ApiError)
    try { parseList(input, 1) } catch (error) { expect(error).toMatchObject({ code: 'INVALID_RESPONSE' }) }
  })
  it('accepts consistent date/time and formats exact times in Korea regardless of host timezone', () => {
    const item = sampleOpportunity({ deadline_date: '2026-10-31', deadline_at: '2026-10-30T16:00:00Z' })
    expect(parseList(sampleList({ items: [item] }), 1).items).toEqual([item])
    expect(deadlineLabel(item)).toContain('2026년 10월 31일 01:00')
    expect(deadlineLabel(item)).toContain('한국시간')
  })
  it('does not invent midnight for a date-only deadline or a deadline for null', () => {
    expect(deadlineLabel(sampleOpportunity())).toBe('2026-10-30 마감 · 정확한 마감 시각 확인 필요')
    expect(deadlineLabel(sampleOpportunity({ deadline_date: null }))).toBe('마감일 확인 필요')
  })
  it('projects only public-list fields and does not retain unexpected data', () => {
    const input = { ...sampleList(), private_profile: 'not-for-this-view', items: [{ ...sampleOpportunity(), private_profile: 'not-for-this-view' }] }
    expect(JSON.stringify(parseList(input, 1))).not.toContain('private_profile')
  })
})
