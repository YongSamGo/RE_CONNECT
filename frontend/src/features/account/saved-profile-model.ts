import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, timestamp } from '../public-opportunities/catalog'
import { parseProfileContent } from '../profile/server-model'

export function parseSavedProfile(value: unknown): components['schemas']['SavedProfile'] | null {
  const response = record(value)
  if (response.saved === null) return null
  const saved = record(response.saved)
  if (typeof saved.profile_id !== 'string' || !isOpportunityId(saved.profile_id)
    || typeof saved.version !== 'number' || !Number.isSafeInteger(saved.version) || saved.version < 1
    || !timestamp(saved.saved_at) || !timestamp(saved.confirmed_at)) return invalid()
  return { profile_id: saved.profile_id, version: saved.version, saved_at: saved.saved_at as string,
    confirmed_at: saved.confirmed_at as string, content: parseProfileContent(saved.content) }
}
