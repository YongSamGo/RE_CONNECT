import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'

export type OpportunityInput = components['schemas']['OpportunityInput']
type Requirement = components['schemas']['Requirement']
function string(value: unknown, max: number, required = false): string {
  return typeof value === 'string' && value.length <= max && (!required || !!value.trim()) ? value : invalid()
}
const nullableText = (value: unknown, max: number) => value === null ? null : string(value, max)
function enumeration<const T extends string>(value: unknown, values: readonly T[]): T {
  return typeof value === 'string' && values.includes(value as T) ? value as T : invalid()
}
const boolean = (value: unknown): boolean | null => value === null || typeof value === 'boolean' ? value : invalid()
function number(value: unknown, min: number, max: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value >= min && value <= max ? value : invalid()
}
function list<T>(value: unknown, max: number, parse: (item: unknown) => T): T[] {
  if (!Array.isArray(value) || value.length > max) return invalid()
  return value.map(parse)
}
function date(value: unknown): string | null {
  if (value === null) return null
  const result = string(value, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(result) || !timestamp(`${result}T00:00:00Z`)) return invalid()
  return result
}
function region(value: unknown): components['schemas']['Region'] {
  const item = record(value)
  if (item.district !== null && (typeof item.district !== 'string' || !/^[a-z0-9_]{2,40}$/.test(item.district))) return invalid()
  return { province: enumeration(item.province, ['seoul', 'gyeonggi', 'incheon']), district: item.district as string | null }
}
function requirement(value: unknown): Requirement {
  const item = record(value)
  const id = string(item.id, 36)
  if (!isOpportunityId(id) || (item.group_id !== null && (typeof item.group_id !== 'string' || !isOpportunityId(item.group_id)))) return invalid()
  const group = item.group_operator === null ? null : enumeration(item.group_operator, ['and', 'or'])
  if ((item.group_id === null) !== (group === null)) return invalid()
  let parsedValue: Requirement['value']
  if (item.value === null) parsedValue = null
  else if (typeof item.value === 'number') parsedValue = Number.isFinite(item.value) ? item.value : invalid()
  else {
    if (!Array.isArray(item.value) || !item.value.length) return invalid()
    parsedValue = typeof item.value[0] === 'number' ? list(item.value, 7, (value) => typeof value === 'number' && Number.isFinite(value) ? value : invalid())
      : typeof item.value[0] === 'string' ? list(item.value, 20, (value) => string(value, 100)) : list(item.value, 30, region)
  }
  return {
    id, field: enumeration(item.field, ['age', 'residence_region', 'certification', 'completed_course', 'weekday', 'hours_per_week', 'other']),
    operator: item.operator === null ? null : enumeration(item.operator, ['gte', 'lte', 'between', 'in', 'has_all', 'has_any', 'includes_all', 'includes_any']),
    value: parsedValue, group_id: item.group_id as string | null, group_operator: group,
    reference_date: date(item.reference_date), source_evidence: string(item.source_evidence, 1000, true), clarity: enumeration(item.clarity, ['clear', 'needs_review']),
  }
}
export function isHttpsReference(value: string): boolean {
  try {
    if (value.length > 2000 || !value.startsWith('https://') || /[\s\\]/.test(value)) return false
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password && !url.hash
  } catch { return false }
}
/** A display/write projection. Unknown server properties never return to the API. */
export function parseOpportunityInput(value: unknown): OpportunityInput {
  const item = record(value)
  const source = string(item.source_url, 2000, true), application = string(item.application_url, 2000, true)
  if (!isHttpsReference(source) || !isHttpsReference(application)) return invalid()
  const roles = list(item.role_tags, 10, (value) => { const role = string(value, 64, true); return /^[a-z][a-z0-9_]{1,63}$/.test(role) ? role : invalid() })
  const skills = list(item.skill_tags, 20, (value) => string(value, 50, true))
  if (new Set(roles).size !== roles.length || new Set(skills).size !== skills.length) return invalid()
  const deadline = date(item.deadline_date), deadlineAt = timestamp(item.deadline_at)
  if (deadline && deadlineAt && new Date(Date.parse(deadlineAt) + 9 * 60 * 60 * 1000).toISOString().slice(0, 10) !== deadline) return invalid()
  return {
    title: string(item.title, 200, true), organization_name: string(item.organization_name, 200, true),
    activity_type: enumeration(item.activity_type, ['employment', 'volunteering']), is_public_job: boolean(item.is_public_job),
    role_tags: roles, skill_tags: skills, activity_region: item.activity_region === null ? null : region(item.activity_region),
    location_text: nullableText(item.location_text, 500), remote_allowed: boolean(item.remote_allowed), schedule_text: nullableText(item.schedule_text, 500),
    hours_per_week: item.hours_per_week === null ? null : number(item.hours_per_week, 0, 168), paid: boolean(item.paid), compensation_text: nullableText(item.compensation_text, 500),
    description_text: nullableText(item.description_text, 5000), requirements: list(item.requirements, 30, requirement),
    required_documents: item.required_documents === null ? null : list(item.required_documents, 20, (value) => string(value, 200, true)),
    application_method: enumeration(item.application_method, ['online', 'phone', 'visit', 'email', 'mixed']), application_instructions: string(item.application_instructions, 2000, true),
    source_url: source, application_url: application, deadline_date: deadline, deadline_at: deadlineAt, recruitment_status: enumeration(item.recruitment_status, ['open', 'closed', 'unknown']),
  }
}
export function emptyOpportunity(): OpportunityInput {
  return { title: '', organization_name: '', activity_type: 'employment', is_public_job: null, role_tags: [], skill_tags: [], activity_region: null, location_text: null, remote_allowed: null, schedule_text: null, hours_per_week: null, paid: null, compensation_text: null, description_text: null, requirements: [], required_documents: null, application_method: 'online', application_instructions: '', source_url: '', application_url: '', deadline_date: null, deadline_at: null, recruitment_status: 'unknown' }
}
export function opportunityChanges(original: OpportunityInput, edited: OpportunityInput): components['schemas']['OpportunityPatch']['changes'] {
  const changes: Record<string, unknown> = {}
  for (const field of Object.keys(original) as (keyof OpportunityInput)[]) {
    if (JSON.stringify(original[field]) !== JSON.stringify(edited[field])) changes[field] = edited[field]
  }
  return changes
}
export function parseEditable(value: unknown, expected?: { id: string; version: number }) {
  const item = record(value)
  const id = string(item.id, 36)
  if (!isOpportunityId(id) || typeof item.version !== 'number' || !Number.isSafeInteger(item.version) || item.version < 1
    || (expected && (id !== expected.id || item.version !== expected.version))) return invalid()
  return { id, version: item.version, status: enumeration(item.review_status, ['pending', 'approved', 'rejected', 'hidden']), input: parseOpportunityInput(item.content) }
}
