import { describe, expect, it } from 'vitest'
import { sampleDetail } from '../public-opportunities/test-fixtures'
import { emptyOpportunity, isHttpsReference, opportunityChanges, parseEditable, parseOpportunityInput } from './editor'

const input = () => parseOpportunityInput(sampleDetail())
describe('admin opportunity input projection', () => {
  it('keeps null, zero and explicitly empty lists distinct while dropping unknown fields', () => {
    const value = parseOpportunityInput({ ...sampleDetail(), hours_per_week: 0, required_documents: [], private_body: 'not-for-serialization' })
    expect(value.hours_per_week).toBe(0)
    expect(value.required_documents).toEqual([])
    expect(input().required_documents).toBeNull()
    expect(value).not.toHaveProperty('private_body')
    expect(value).not.toHaveProperty('description_truncated')
  })
  it('patches only changed fields and preserves precise timestamps, regions, groups and tags', () => {
    const requirement = { id: '12345678-1234-1234-1234-123456789010', field: 'age', operator: 'gte', value: 60, source_evidence: '만 60세 이상', clarity: 'clear', group_id: '12345678-1234-1234-1234-123456789020', group_operator: 'and', reference_date: '2026-10-15' }
    const original = parseOpportunityInput({ ...sampleDetail(), deadline_at: '2026-10-30T03:04:05.678Z', activity_region: { province: 'seoul', district: 'seongdong' }, role_tags: ['community_helper'], requirements: [requirement] })
    expect(opportunityChanges(original, { ...original, title: '바뀐 제목' })).toEqual({ title: '바뀐 제목' })
    expect(original.requirements[0]).toEqual(requirement)
    expect(opportunityChanges(original, original)).toEqual({})
  })
  it.each(['javascript:alert(1)', 'http://example.com', 'https:example.com', 'https://user:password@example.com/path', ' https://example.com', 'https://example.com/with space', 'https://example.com/#part', 'https:\\example.com'])('rejects unsafe source syntax %s', (url) => {
    expect(isHttpsReference(url)).toBe(false)
    expect(() => parseOpportunityInput({ ...sampleDetail(), source_url: url })).toThrow()
  })
  it.each([
    { hours_per_week: -1 }, { hours_per_week: 169 }, { hours_per_week: NaN }, { title: ' ' },
    { paid: 'yes' }, { activity_region: { province: 'elsewhere', district: null } },
    { required_documents: Array.from({ length: 21 }, () => '서류') }, { role_tags: ['invalid role'] },
    { skill_tags: ['duplicate', 'duplicate'] }, { deadline_date: '2026-02-30' },
    { deadline_date: '2026-10-30', deadline_at: '2026-10-30T15:00:00Z' },
  ])('rejects invalid inputs %j', (changes) => {
    expect(() => parseOpportunityInput({ ...sampleDetail(), ...changes })).toThrow()
  })
  it('rejects wrong edit targets and does not invent source facts for a new draft', () => {
    const value = { id: sampleDetail().id, version: 2, review_status: 'pending', content: input() }
    expect(() => parseEditable(value, { id: value.id, version: 1 })).toThrow()
    expect(emptyOpportunity()).toMatchObject({ remote_allowed: null, paid: null, activity_region: null, requirements: [], required_documents: null, recruitment_status: 'unknown' })
  })
})
