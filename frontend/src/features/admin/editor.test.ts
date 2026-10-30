import { describe, expect, it } from 'vitest'
import { sampleDetail } from '../public-opportunities/test-fixtures'
import { emptyOpportunity, isHttpsReference, opportunityChanges, opportunityReviewWarnings, parseEditable, parseOpportunityInput, parseRequirements, parseRoleCatalog, parseSkillLines } from './editor'

const input = () => parseOpportunityInput(sampleDetail())
const condition = { id: '12345678-1234-1234-1234-123456789010', field: 'age', operator: 'gte', value: 60, source_evidence: '만 60세 이상', clarity: 'clear', group_id: null, group_operator: null, reference_date: null }

describe('operator tag input and prepublication checks', () => {
  it('trims explicit skill lines and rejects duplicates, hidden characters and oversized lists', () => {
    expect(parseSkillLines(' 자료 정리 \r\n\n이용 안내')).toEqual(['자료 정리', '이용 안내'])
    for (const value of ['자료 정리\n자료  정리', '자료\u200b정리', 'a'.repeat(51), Array.from({ length: 21 }, (_, i) => `역량${i}`).join('\n')]) expect(() => parseSkillLines(value)).toThrow()
    expect(parseSkillLines('')).toEqual([])
  })
  it('rejects duplicate role identities and does not invent missing catalog fields', () => {
    const role = { id: 'library_assistant', name: '가상 역할', description: '합성 설명', skill_tags: ['자료 정리'] }
    expect(parseRoleCatalog({ items: [role] })).toEqual([role])
    expect(() => parseRoleCatalog({ items: [role, role] })).toThrow()
    expect(() => parseRoleCatalog({ items: [{ ...role, name: null }] })).toThrow()
  })
  it('distinguishes missing tags, unknown location and unreviewed rules without clearing any rule', () => {
    const value = input()
    expect(opportunityReviewWarnings({ ...value, activity_region: null })).toHaveLength(2)
    const unresolved = parseRequirements([{ ...condition, field: 'other', operator: null, value: null, clarity: 'needs_review' }])
    expect(opportunityReviewWarnings({ ...value, skill_tags: ['자료 정리'], requirements: unresolved })).toHaveLength(1)
    expect(unresolved[0]!.source_evidence).toBe('만 60세 이상')
    expect(opportunityReviewWarnings({ ...value, skill_tags: ['자료 정리'], activity_region: null, remote_allowed: true })).toEqual([])
  })
})
describe('requirement rule semantics', () => {
  it.each([
    { field: 'age', operator: 'gte', value: 60.5 }, { field: 'age', operator: 'between', value: [70, 60] },
    { field: 'age', operator: 'between', value: [60] }, { field: 'age', operator: 'has_all', value: ['60'] },
    { field: 'weekday', operator: 'includes_any', value: [0, 8] }, { field: 'weekday', operator: 'includes_all', value: [1.5] },
    { field: 'certification', operator: 'has_any', value: [1] }, { field: 'completed_course', operator: 'has_all', value: [' '] },
    { field: 'residence_region', operator: 'in', value: ['seoul'] }, { field: 'hours_per_week', operator: 'gte', value: [0] },
    { field: 'other', operator: null, value: null, clarity: 'clear' }, { group_id: condition.id, group_operator: null },
  ])('rejects invalid combination %j', (change) => expect(() => parseRequirements([{ ...condition, ...change }])).toThrow())
  it('accepts explicit zero, decimal hours, weekday sets, regions and unresolved originals', () => {
    for (const change of [
      { value: 0 }, { operator: 'between', value: [60, 70] },
      { field: 'hours_per_week', operator: 'lte', value: 3.5 },
      { field: 'weekday', operator: 'includes_any', value: [1, 7] },
      { field: 'residence_region', operator: 'in', value: [{ province: 'seoul', district: 'seongdong' }] },
      { field: 'certification', operator: 'has_all', value: ['시험 자격'] },
      { field: 'other', operator: null, value: null, clarity: 'needs_review' },
    ]) expect(parseRequirements([{ ...condition, ...change }])[0]).toMatchObject(change)
  })
  it('rejects duplicate identities and conflicting group logic', () => {
    expect(() => parseRequirements([condition, condition])).toThrow()
    const first = { ...condition, group_id: condition.id, group_operator: 'and' }
    const second = { ...first, id: '12345678-1234-1234-1234-123456789011', group_operator: 'or' }
    expect(() => parseRequirements([first, second])).toThrow()
  })
})
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
