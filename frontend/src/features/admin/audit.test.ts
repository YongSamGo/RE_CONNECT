import { describe, expect, it } from 'vitest'
import { auditRange, koreaDateTimeInput, parseAudit } from './audit'

const range = { from: '2026-10-14T00:00:00+09:00', to: '2026-10-15T00:00:00+09:00' }
const event = { event_id: '12345678-1234-1234-1234-123456789012', at: '2026-10-14T03:00:00Z', action: 'opportunity.reject', actor_role: 'operator', target_type: 'opportunity', result: 'success', request_id: 'req_audit_01' }
const page = (item = event) => ({ items: [item], total: 1, page: 1, page_size: 20 })
describe('audit query and display projection', () => {
  it('uses explicit Korea time and permits exactly 30 days', () => {
    expect(auditRange('2026-09-15T00:00', '2026-10-15T00:00')).toEqual({ from: '2026-09-15T00:00:00+09:00', to: '2026-10-15T00:00:00+09:00' })
    expect(koreaDateTimeInput(Date.parse('2026-10-14T15:00:00Z'))).toBe('2026-10-15T00:00')
  })
  it.each([
    ['2026-09-14T23:59', '2026-10-15T00:00'], ['2026-10-15T00:00', '2026-10-15T00:00'],
    ['2026-10-16T00:00', '2026-10-15T00:00'], ['2026-02-30T00:00', '2026-03-01T00:00'],
    ['', '2026-10-15T00:00'], ['2026-10-14T24:00', '2026-10-15T00:00'],
  ])('rejects invalid, reversed and excessive query range %s to %s', (from, to) => {
    expect(auditRange(from, to)).toBeNull()
  })
  it('drops IDs and every unknown private field from the display state', () => {
    const result = parseAudit(page({ ...event, actor_id: 'not-displayed', target_id: 'not-displayed', profile_body: 'private-content', otp: '123456' } as typeof event), 1, range)
    expect(result.rows[0]).toEqual(event)
    expect(JSON.stringify(result)).not.toMatch(/not-displayed|private-content|123456"/)
  })
  it.each([
    { action: '<script>alert(1)</script>' }, { actor_role: 'administrator' }, { result: 'ok' },
    { target_type: 'profile_body' }, { request_id: 'private path /etc/passwd' },
    { event_id: 'invalid' }, { at: '2026-10-16T00:00:00Z' },
  ])('rejects invalid or uncorrelated events %j', (changes) => {
    expect(() => parseAudit(page({ ...event, ...changes }), 1, range)).toThrow('응답을 확인하지 못했습니다.')
  })
  it('rejects mismatched page metadata and duplicated event IDs', () => {
    expect(() => parseAudit(page(), 2, range)).toThrow()
    expect(() => parseAudit({ ...page(), items: [event, event], total: 2 }, 1, range)).toThrow()
    expect(() => parseAudit({ ...page(), items: [{ ...event, actor_role: ['operator'] }] }, 1, range)).toThrow()
    expect(() => parseAudit({ ...page(), items: [{ ...event, result: ['success'] }] }, 1, range)).toThrow()
  })
})
