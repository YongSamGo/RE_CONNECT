import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, text, timestamp } from '../public-opportunities/catalog'

export type Preparation = components['schemas']['Preparation']
export function parsePreparation(value: unknown, id: string): Preparation {
  const item = record(value)
  const reference = record(item.opportunity)
  if (typeof reference.id !== 'string' || !isOpportunityId(reference.id) || reference.id.toLowerCase() !== id.toLowerCase()
    || !Number.isSafeInteger(reference.version) || (reference.version as number) < 1) return invalid()
  if (!['online', 'phone', 'visit', 'email', 'mixed'].includes(item.application_method as string)) return invalid()
  if (!['open', 'closed', 'unknown'].includes(item.recruitment_status as string) || typeof item.change_pending !== 'boolean') return invalid()
  if (typeof item.application_instructions !== 'string' || [...item.application_instructions].length > 2000) return invalid()
  const documents = item.required_documents
  if (documents !== null && (!Array.isArray(documents) || documents.length > 100)) return invalid()
  const date = item.deadline_date
  if (date !== null) {
    if (typeof date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(date)) return invalid()
    const parsed = new Date(`${date}T00:00:00Z`)
    if (!Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== date) return invalid()
  }
  return {
    opportunity: { id: reference.id, version: reference.version as number },
    application_method: item.application_method as Preparation['application_method'],
    application_instructions: item.application_instructions,
    application_url: text(item.application_url, 2048), source_url: text(item.source_url, 2048),
    required_documents: documents === null ? null : (documents as unknown[]).map(value => text(value, 200)),
    deadline_date: date as string | null, deadline_at: timestamp(item.deadline_at),
    recruitment_status: item.recruitment_status as Preparation['recruitment_status'], change_pending: item.change_pending,
  }
}
