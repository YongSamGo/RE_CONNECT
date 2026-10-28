import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, text, timestamp } from '../public-opportunities/catalog'

export type JourneyDraft = components['schemas']['JourneyDraft']
export function positive(value: unknown): number {
  return typeof value === 'number' && Number.isSafeInteger(value) && value > 0 && value < 2 ** 31 ? value : invalid()
}
export function parseJourneyDraft(value: unknown, opportunity: { id: string; version: number }, profileVersion: number): JourneyDraft {
  const item = record(value), reference = record(item.opportunity)
  if (typeof item.draft_id !== 'string' || !isOpportunityId(item.draft_id) || !['generate', 'manual', 'from_saved'].includes(item.mode as string)
    || reference.id !== opportunity.id || positive(reference.version) !== opportunity.version || positive(item.profile_version) !== profileVersion
    || typeof item.self_introduction !== 'string' || [...item.self_introduction].length > 2000
    || typeof item.motivation !== 'string' || [...item.motivation].length > 2000
    || !Array.isArray(item.review_reasons) || item.review_reasons.length > 3
    || !item.review_reasons.every(reason => ['profile_changed', 'opportunity_changed', 'opportunity_closed'].includes(reason))
    || !Array.isArray(item.warnings) || item.warnings.length > 10) return invalid()
  return { draft_id: item.draft_id, revision: positive(item.revision), mode: item.mode as JourneyDraft['mode'], profile_version: profileVersion,
    opportunity, self_introduction: item.self_introduction, motivation: item.motivation, approved_at: timestamp(item.approved_at),
    review_reasons: item.review_reasons as JourneyDraft['review_reasons'], warnings: item.warnings.map(value => text(value, 300)) }
}
