import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'

export type ProfileView = components['schemas']['ProfileDraftView']
export type DraftInput = components['schemas']['ProfileContentInput']
export type Roles = components['schemas']['RoleCandidates']
type Region = components['schemas']['Region']

function text(value: unknown, max: number): string {
  return typeof value === 'string' && !!value.trim() && [...value].length <= max ? value : invalid()
}
function integer(value: unknown, min = 1, max = 2 ** 31 - 1): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value >= min && value <= max ? value : invalid()
}
function list<T>(value: unknown, max: number, parse: (value: unknown) => T): T[] {
  return Array.isArray(value) && value.length <= max ? value.map(parse) : invalid()
}
function choice<const T extends string>(value: unknown, choices: readonly T[]): T {
  return typeof value === 'string' && choices.includes(value as T) ? value as T : invalid()
}
function region(value: unknown): Region {
  const item = record(value)
  return { province: choice(item.province, ['seoul', 'gyeonggi', 'incheon']), district: item.district === null ? null
    : typeof item.district === 'string' && /^[a-z0-9_]{2,40}$/.test(item.district) ? item.district : invalid() }
}
function uuid(value: unknown): string { return typeof value === 'string' && isOpportunityId(value) ? value : invalid() }
const nullableText = (value: unknown, max: number) => value === null ? null : text(value, max)
const stringList = (value: unknown, max: number, length: number) => list(value, max, value => text(value, length))
const nullableList = (value: unknown, max: number, length: number) => value === null ? null : stringList(value, max, length)

export function parseProfileContent(value: unknown): ProfileView['draft'] {
  const content = record(value)
  if (content.schema_version !== 1) return invalid()
  const draft: ProfileView['draft'] = {
    schema_version: 1,
    experiences: list(content.experiences, 20, value => { const e = record(value); return {
      id: uuid(e.id), description: text(e.description, 1000), duration_note: nullableText(e.duration_note, 200), skill_tags: stringList(e.skill_tags, 20, 50),
    } }),
    skills: stringList(content.skills, 30, 50), preferred_regions: list(content.preferred_regions, 10, region),
    activity_types: list(content.activity_types, 2, value => choice(value, ['employment', 'volunteering'])),
    paid_preference: content.paid_preference === null ? null : choice(content.paid_preference, ['paid', 'unpaid', 'any']),
    available_weekdays: content.available_weekdays === null ? null : list(content.available_weekdays, 7, value => integer(value, 1, 7)),
    hours_per_week: content.hours_per_week === null ? null : typeof content.hours_per_week === 'number' && Number.isFinite(content.hours_per_week) && content.hours_per_week >= 0 && content.hours_per_week <= 168 ? content.hours_per_week : invalid(),
    mobility_note: nullableText(content.mobility_note, 300), residence_region: content.residence_region === null ? null : region(content.residence_region),
    birth_year: content.birth_year === null ? null : integer(content.birth_year, 1900, new Date().getFullYear()),
    certifications: nullableList(content.certifications, 20, 100), completed_courses: nullableList(content.completed_courses, 20, 100),
    activity_constraints: nullableList(content.activity_constraints, 10, 200),
  }
  if (new Set(draft.experiences.map(e => e.id)).size !== draft.experiences.length) return invalid()
  return draft
}

export function parseProfileView(value: unknown): ProfileView {
  const item = record(value), draft = parseProfileContent(item.draft)
  if (typeof item.has_unconfirmed_changes !== 'boolean') return invalid()
  let confirmed: ProfileView['confirmed'] = null
  if (item.confirmed !== null) {
    const c = record(item.confirmed)
    if (!timestamp(c.confirmed_at)) return invalid()
    confirmed = { version: integer(c.version), confirmed_at: c.confirmed_at as string }
  }
  return { revision: integer(item.revision), draft, confirmed, has_unconfirmed_changes: item.has_unconfirmed_changes,
    missing_for_recommendation: list(item.missing_for_recommendation, 3, value => choice(value, ['experiences', 'preferred_regions', 'activity_types'])),
    evidence: list(item.evidence, 100, value => { const e = record(value); return { path: text(e.path, 200), message_ids: list(e.message_ids, 100, uuid) } }),
  }
}

export function parseRoles(value: unknown, view: ProfileView): Roles {
  const item = record(value)
  if (!view.confirmed || item.profile_version !== view.confirmed.version || item.revision !== view.revision) return invalid()
  return { profile_version: integer(item.profile_version), revision: integer(item.revision), items: list(item.items, 20, value => {
    const r = record(value)
    if (typeof r.excluded !== 'boolean') return invalid()
    const roleId = text(r.role_id, 64)
    if (!/^[a-z][a-z0-9_]{1,63}$/.test(roleId)) return invalid()
    const evidence = list(r.evidence, 20, value => { const e = record(value); const tags = stringList(e.skill_tags, 20, 50)
      if (!tags.length) return invalid(); return { experience_id: uuid(e.experience_id), skill_tags: tags } })
    if (!evidence.length) return invalid()
    return { role_id: roleId, name: text(r.name, 50), description: text(r.description, 300), excluded: r.excluded, evidence }
  }) }
}

export function parseExclusions(value: unknown, view: ProfileView): string[] {
  const item = record(value)
  if (item.revision !== view.revision) return invalid()
  const ids = list(item.role_ids, 50, value => typeof value === 'string' && /^[a-z][a-z0-9_]{1,63}$/.test(value) ? value : invalid())
  return new Set(ids).size === ids.length ? ids : invalid()
}

export function minimumErrors(draft: DraftInput) {
  const errors = []
  if (!draft.experiences.length || draft.experiences.some(e => !e.description.trim())) errors.push({ fieldId: 'server-experiences', message: '경험을 한 가지 이상 적어 주세요.' })
  if (!draft.preferred_regions.length) errors.push({ fieldId: 'server-regions', message: '희망 활동 지역을 한 곳 이상 골라 주세요.' })
  if (!draft.activity_types.length) errors.push({ fieldId: 'server-activities', message: '희망 활동 유형을 한 가지 이상 골라 주세요.' })
  return errors
}
