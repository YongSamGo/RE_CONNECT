import type { components } from '../../api/schema'
import { invalid, isOpportunityId, record, text, timestamp } from '../public-opportunities/catalog'

export function parseSession(value: unknown): components['schemas']['Me'] {
  const item = record(value)
  if (typeof item.authenticated !== 'boolean' || !Array.isArray(item.consents)) return invalid()
  const consents = item.consents.map((value): components['schemas']['ConsentState'] => {
    const consent = record(value)
    if (consent.purpose !== 'ai_processing' && consent.purpose !== 'storage') return invalid()
    const granted = timestamp(consent.granted_at)
    if (!granted) return invalid()
    return { purpose: consent.purpose, granted_at: granted, notice_version: text(consent.notice_version, 100) }
  })
  let user: components['schemas']['Me']['user'] = null
  if (item.user !== null) {
    const value = record(item.user)
    const id = text(value.id, 36)
    if (!isOpportunityId(id) || typeof value.mfa_verified !== 'boolean' || !Array.isArray(value.roles)
      || !value.roles.every((role): role is 'user' | 'operator' => role === 'user' || role === 'operator')) return invalid()
    user = { id, roles: value.roles, mfa_verified: value.mfa_verified, reauth_until: timestamp(value.reauth_until) }
  }
  if (item.authenticated !== (user !== null)) return invalid()
  let pending: components['schemas']['PendingSaveIntent'] | null = null
  if (item.pending_save_intent !== null) {
    const intent = record(item.pending_save_intent)
    const targets = record(intent.targets)
    const id = text(intent.save_intent_id, 36)
    const expiry = timestamp(intent.expires_at)
    const existing = intent.existing_saved_profile_version
    if (!isOpportunityId(id) || !expiry || typeof targets.profile !== 'boolean' || typeof targets.draft !== 'boolean'
      || (!targets.profile && !targets.draft) || (targets.draft && !targets.profile)
      || (existing !== null && (typeof existing !== 'number' || !Number.isSafeInteger(existing) || existing < 1))) return invalid()
    pending = { save_intent_id: id, expires_at: expiry, targets: { profile: targets.profile, draft: targets.draft }, existing_saved_profile_version: existing }
  }
  return { authenticated: item.authenticated, user, consents, pending_save_intent: pending }
}
