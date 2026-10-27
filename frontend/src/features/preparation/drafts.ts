import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, text, timestamp } from '../public-opportunities/catalog'

export type JourneyDraft = components['schemas']['JourneyDraft']
export type DraftCreate = components['schemas']['DraftCreate']
export const reviewLabels = { profile_changed: '근거 프로필이 재확정되었습니다.', opportunity_changed: '공고 버전 또는 중요 조건이 바뀌었습니다.', opportunity_closed: '공고가 종료되었거나 공개되지 않습니다.' } as const

export function parseDraft(value: unknown, opportunityId: string, expectedId?: string): JourneyDraft {
  const item = record(value), opportunity = record(item.opportunity)
  if (typeof item.draft_id !== 'string' || !isOpportunityId(item.draft_id) || expectedId && item.draft_id !== expectedId
    || opportunity.id !== opportunityId || !Number.isSafeInteger(opportunity.version) || (opportunity.version as number) < 1
    || !Number.isSafeInteger(item.profile_version) || (item.profile_version as number) < 1
    || !Number.isSafeInteger(item.revision) || (item.revision as number) < 1
    || !['generate', 'manual', 'from_saved'].includes(item.mode as string)
    || !Array.isArray(item.review_reasons) || item.review_reasons.some(reason => typeof reason !== 'string' || !Object.hasOwn(reviewLabels, reason))
    || new Set(item.review_reasons).size !== item.review_reasons.length || !Array.isArray(item.warnings) || item.warnings.length > 10) return invalid()
  const body = (value: unknown) => value === '' ? '' : text(value, 2000)
  const approved = timestamp(item.approved_at)
  return { draft_id: item.draft_id, revision: item.revision as number, mode: item.mode as JourneyDraft['mode'],
    opportunity: { id: opportunityId, version: opportunity.version as number }, profile_version: item.profile_version as number,
    self_introduction: body(item.self_introduction), motivation: body(item.motivation), approved_at: approved,
    review_reasons: item.review_reasons as JourneyDraft['review_reasons'], warnings: item.warnings.map(value => text(value, 300)) }
}

export function parseExistingDraft(value: unknown, previous: JourneyDraft): JourneyDraft {
  const next = parseDraft(value, previous.opportunity.id, previous.draft_id)
  if (next.mode !== previous.mode || next.profile_version !== previous.profile_version || next.opportunity.version !== previous.opportunity.version) return invalid()
  return next
}
