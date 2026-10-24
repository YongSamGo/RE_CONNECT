import { invalid, isOpportunityId, record } from '../public-opportunities/catalog'

export type Transcript = { id: string; text: string }
export function parseTranscription(value: unknown): Transcript {
  const item = record(value)
  if (typeof item.transcription_id !== 'string' || !isOpportunityId(item.transcription_id)
    || typeof item.text !== 'string' || [...item.text].length > 2000
    || typeof item.duration_seconds !== 'number' || !Number.isFinite(item.duration_seconds)
    || item.duration_seconds <= 0 || item.duration_seconds > 90) return invalid()
  return { id: item.transcription_id, text: item.text }
}
