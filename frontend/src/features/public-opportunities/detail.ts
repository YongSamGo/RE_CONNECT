import type { components } from '../../api/schema'
import { invalid, publicSummary, record, text, timestamp } from './catalog'

type Detail = components['schemas']['Opportunity']
// Display projection only: no eligibility operators, internal fields or inferred conditions.
export type PublicDetail = ReturnType<typeof publicSummary> & Pick<Detail,
  'description_text' | 'description_truncated' | 'location_text' | 'schedule_text' | 'hours_per_week' |
  'compensation_text' | 'required_documents' | 'application_method' | 'application_instructions' |
  'source_url' | 'application_url' | 'source_checked_at' | 'reviewed_at' | 'skill_tags'> & {
    requirements: Pick<components['schemas']['Requirement'], 'source_evidence' | 'clarity'>[]
  }
const nullableText = (value: unknown, max: number) => value === null ? null : text(value, max)

export function parseDetail(value: unknown, requestedId: string): PublicDetail {
  const item = record(value)
  const summary = publicSummary(item)
  if (summary.id.toLowerCase() !== requestedId.toLowerCase()) return invalid()
  if (typeof item.description_truncated !== 'boolean') return invalid()
  const hours = item.hours_per_week
  if (hours !== null && (typeof hours !== 'number' || !Number.isFinite(hours) || hours < 0 || hours > 168)) return invalid()
  const method = item.application_method
  if (method !== 'online' && method !== 'phone' && method !== 'visit' && method !== 'email' && method !== 'mixed') return invalid()
  if (!Array.isArray(item.requirements)) return invalid()
  const requirements = item.requirements.map((value): PublicDetail['requirements'][number] => {
    const requirement = record(value)
    if (requirement.clarity !== 'clear' && requirement.clarity !== 'needs_review') return invalid()
    return { source_evidence: text(requirement.source_evidence, 1000), clarity: requirement.clarity }
  })
  const documents = item.required_documents
  if (documents !== null && !Array.isArray(documents)) return invalid()
  // 운영자가 원문을 보고 붙인 역량 태그. 추천이 경험과 대조하는 값이라 화면에도 그대로 보여준다.
  const skills = item.skill_tags === undefined ? [] : item.skill_tags
  if (!Array.isArray(skills) || skills.length > 20) return invalid()
  const checked = timestamp(item.source_checked_at)
  const reviewed = timestamp(item.reviewed_at)
  if (!checked || !reviewed) return invalid()
  return {
    ...summary, requirements, required_documents: documents === null ? null : documents.map((value) => text(value, 200)),
    description_text: nullableText(item.description_text, 5000), description_truncated: item.description_truncated,
    location_text: nullableText(item.location_text, 500), schedule_text: nullableText(item.schedule_text, 500),
    hours_per_week: hours, compensation_text: nullableText(item.compensation_text, 500),
    application_method: method, application_instructions: text(item.application_instructions, 2000),
    source_url: text(item.source_url, 2048), application_url: text(item.application_url, 2048),
    source_checked_at: checked, reviewed_at: reviewed, skill_tags: skills.map((value) => text(value, 50)),
  }
}

/** Exact official detail patterns verified in docs/data/sources.md; fail closed for other sources.
 * This browser navigation guard does not replace server URL validation or review. */
export function officialLink(value: string): { href: string; host: string } | null {
  try {
    if (value !== value.trim() || /[\\\s]/.test(value)) return null
    const url = new URL(value)
    if (url.protocol !== 'https:' || url.username || url.password || url.port || url.hash) return null
    const params = url.searchParams
    const keys = [...params.keys()]
    if (new Set(keys).size !== keys.length) return null
    if (url.hostname === 'www.work24.go.kr' && url.pathname === '/wk/a/b/1500/empDetailAuthView.do'
      && keys.length === 3 && /^[A-Za-z0-9]{1,100}$/.test(params.get('wantedAuthNo') ?? '')
      && params.get('infoTypeCd') === 'VALIDATION' && params.get('infoTypeGroup') === 'tb_workinfoworknet') {
      return { href: url.href, host: url.hostname }
    }
    if (url.hostname === 'www.1365.go.kr' && url.pathname === '/vols/P9210/partcptn/timeCptn.do'
      && keys.length === 2 && params.get('type') === 'show' && /^\d{1,20}$/.test(params.get('progrmRegistNo') ?? '')) {
      return { href: url.href, host: url.hostname }
    }
    return null
  } catch { return null }
}

export function checkedTime(value: string): string {
  return new Intl.DateTimeFormat('ko-KR', { timeZone: 'Asia/Seoul', year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value))
}
