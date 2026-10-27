import type { components } from '../../api/schema'
import { invalid, record, text } from '../public-opportunities/catalog'

export function parseNotices(value: unknown): components['schemas']['NoticeCatalog'] {
  const item = record(value)
  const notice = (input: unknown): components['schemas']['PublishedNotice'] | null => {
    if (input === null) return null
    const value = record(input), version = text(value.version, 32)
    if (!/^[a-z0-9._-]{1,32}$/.test(version)) return invalid()
    return { version, title: text(value.title, 200), controller: text(value.controller, 200), contact: text(value.contact, 300),
      aws_region: text(value.aws_region, 100), body: text(value.body, 8000), retention: text(value.retention, 2000), deletion: text(value.deletion, 2000) }
  }
  const storage = notice(item.storage), ai_processing = notice(item.ai_processing)
  if (typeof item.login_available !== 'boolean' || (item.login_available && !storage)) return invalid()
  return { storage, ai_processing, login_available: item.login_available }
}
