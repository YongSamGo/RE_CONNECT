import type { components } from '../../api/schema'
import { invalid, isOpportunityId, publicSummary, record, text, timestamp } from '../public-opportunities/catalog'

export type ProfileRef = components['schemas']['ProfileRef']
export type Recommendations = components['schemas']['RecommendationList']
export type Eligibility = components['schemas']['EligibilityResult']
export const eligibilityLabels = { satisfied: '조건 충족', not_satisfied: '미충족', unknown: '확인 필요' } as const
function status(value: unknown): keyof typeof eligibilityLabels {
  return value === 'satisfied' || value === 'not_satisfied' || value === 'unknown' ? value : invalid()
}
function integer(value: unknown, min = 1): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min ? value : invalid()
}
function uuid(value: unknown): string { return typeof value === 'string' && isOpportunityId(value) ? value : invalid() }
function list<T>(value: unknown, max: number, parse: (value: unknown) => T): T[] {
  return Array.isArray(value) && value.length <= max ? value.map(parse) : invalid()
}
function bool(value: unknown): boolean { return typeof value === 'boolean' ? value : invalid() }
function reference(value: unknown, expected: ProfileRef): ProfileRef {
  const item = record(value)
  return item.kind === expected.kind && item.id === expected.id && item.version === expected.version ? { ...expected } : invalid()
}
const unique = <T,>(items: T[]) => new Set(items).size === items.length ? items : invalid()
const roleId = (value: unknown) => typeof value === 'string' && /^[a-z][a-z0-9_]{1,63}$/.test(value) ? value : invalid()

export function parseRecommendations(value: unknown, expected: ProfileRef): Recommendations {
  const item = record(value)
  const generated = timestamp(item.generated_at)
  if (!generated) return invalid()
  const items = list(item.items, 20, (value): Recommendations['items'][number] => {
    const entry = record(value), matched = record(entry.matched), eligibility = record(entry.eligibility)
    const opportunity = publicSummary(entry.opportunity)
    if (opportunity.recruitment_status !== 'open' || opportunity.change_pending || 'score' in entry) return invalid()
    const overall = status(eligibility.overall)
    if (overall === 'not_satisfied') return invalid()
    const noRequirements = bool(eligibility.no_requirements), reviewCount = integer(eligibility.needs_review_count, 0)
    if (reviewCount > 30 || noRequirements && (overall !== 'satisfied' || reviewCount !== 0) || overall === 'unknown' && reviewCount === 0) return invalid()
    const experienceIds = unique(list(matched.experience_ids, 20, uuid))
    if (!experienceIds.length) return invalid()
    return { rank: integer(entry.rank), opportunity: { ...opportunity, recruitment_status: 'open' },
      matched: { experience_ids: experienceIds, skill_tags: unique(list(matched.skill_tags, 430, value => text(value, 50))),
        keywords: unique(list(matched.keywords, 10000, value => text(value, 50))), role_ids: unique(list(matched.role_ids, 500, roleId)) },
      eligibility: { overall, no_requirements: noRequirements, needs_review_count: reviewCount } }
  })
  unique(items.map(item => item.opportunity.id))
  if (items.some((item, index) => item.rank !== index + 1)) return invalid()
  return { profile: reference(item.profile, expected), generated_at: generated,
    based_on_previous_confirmed: bool(item.based_on_previous_confirmed), items }
}

const fields = ['age', 'residence_region', 'certification', 'completed_course', 'weekday', 'hours_per_week', 'other'] as const
const reasons = ['missing_profile_value', 'unclear_requirement', 'age_boundary', 'reference_date_missing', 'unsupported_group'] as const
export function parseEligibility(value: unknown, expected: ProfileRef, opportunity: { id: string; version: number }): Eligibility {
  const item = record(value), ref = record(item.opportunity)
  const evaluated = timestamp(item.evaluated_at)
  if (ref.id !== opportunity.id || ref.version !== opportunity.version || !evaluated) return invalid()
  const conditions = list(item.conditions, 30, (value): Eligibility['conditions'][number] => {
    const c = record(value)
    if (!fields.includes(c.field as typeof fields[number]) || c.review_reason !== null && !reasons.includes(c.review_reason as typeof reasons[number])) return invalid()
    const result = status(c.result)
    if ((result === 'unknown') !== (c.review_reason !== null)) return invalid()
    let userValue: Eligibility['conditions'][number]['user_value']
    if (c.user_value === null) userValue = null
    else if (typeof c.user_value === 'number' && Number.isFinite(c.user_value)) userValue = c.user_value
    else if (Array.isArray(c.user_value)) {
      userValue = c.user_value.every(value => typeof value === 'number')
        ? list(c.user_value, 7, value => integer(value)) : list(c.user_value, 20, value => text(value, 100))
    } else {
      const region = record(c.user_value)
      if (!['seoul', 'gyeonggi', 'incheon'].includes(region.province as string)
        || region.district !== null && (typeof region.district !== 'string' || !/^[a-z0-9_]{2,40}$/.test(region.district))) return invalid()
      userValue = { province: region.province as 'seoul' | 'gyeonggi' | 'incheon', district: region.district as string | null }
    }
    return { requirement_id: uuid(c.requirement_id), field: c.field as typeof fields[number], result,
      user_value: userValue, source_evidence: text(c.source_evidence, 1000), review_reason: c.review_reason as typeof reasons[number] | null }
  })
  const groups = list(item.groups, 30, (value): Eligibility['groups'][number] => {
    const g = record(value)
    if (g.operator !== 'and' && g.operator !== 'or') return invalid()
    return { group_id: uuid(g.group_id), operator: g.operator, result: status(g.result) }
  })
  unique(conditions.map(c => c.requirement_id)); unique(groups.map(g => g.group_id))
  const noRequirements = bool(item.no_requirements)
  if (noRequirements !== (conditions.length === 0) || noRequirements && (groups.length > 0 || item.overall !== 'satisfied')) return invalid()
  return { profile: reference(item.profile, expected), opportunity: { ...opportunity }, evaluated_at: evaluated,
    overall: status(item.overall), no_requirements: noRequirements, conditions, groups }
}
