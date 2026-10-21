import { describe, expect, it } from 'vitest'
import { officialLink, parseDetail } from './detail'
import { sampleDetail, sourceUrl } from './test-fixtures'

const id = sampleDetail().id
describe('public detail display boundary', () => {
  it('permits closed detail and projects out internal/eligibility fields', () => {
    const item = parseDetail({ ...sampleDetail({ recruitment_status: 'closed' }), source_id: 'private', requirements: [{ source_evidence: '원문 조건', clarity: 'needs_review', operator: 'untrusted' }] }, id)
    expect(item.recruitment_status).toBe('closed')
    expect(item).not.toHaveProperty('source_id')
    expect(item.requirements).toEqual([{ source_evidence: '원문 조건', clarity: 'needs_review' }])
    expect(item).not.toHaveProperty('role_tags')
  })
  it.each([
    { id: '12345678-1234-1234-1234-123456789002' }, { description_text: 'x'.repeat(5001) },
    { description_truncated: 'false' }, { hours_per_week: 169 }, { hours_per_week: -1 }, { hours_per_week: NaN },
    { application_method: 'automatic' }, { required_documents: [''] }, { requirements: [{ clarity: 'clear' }] },
    { requirements: [{ source_evidence: '원문', clarity: 'maybe' }] }, { source_checked_at: null },
    { reviewed_at: '2026-02-30T09:00:00Z' }, { source_url: null }, { application_url: 'x'.repeat(2049) },
  ])('rejects malformed or mismatched detail %j', (changes) => {
    expect(() => parseDetail({ ...sampleDetail(), ...changes }, id)).toThrow('응답을 확인하지 못했습니다')
  })
})
describe('explicit official URL navigation allowlist', () => {
  it('allows only the documented HTTPS detail routes and parameters', () => {
    expect(officialLink(sourceUrl)).toEqual({ href: sourceUrl, host: 'www.1365.go.kr' })
    const work = 'https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=K123&infoTypeCd=VALIDATION&infoTypeGroup=tb_workinfoworknet'
    expect(officialLink(work)?.href).toBe(work)
  })
  it.each([
    'javascript:alert(1)', 'data:text/html,<script>alert(1)</script>', '//www.1365.go.kr/',
    sourceUrl.replace('https:', 'http:'), sourceUrl.replace('www.1365.go.kr', 'www.1365.go.kr.evil.test'),
    sourceUrl.replace('www.1365.go.kr', 'evil.test'), sourceUrl.replace('www.1365.go.kr', 'user:secret@www.1365.go.kr'),
    sourceUrl.replace('www.1365.go.kr', '127.0.0.1'), sourceUrl.replace('www.1365.go.kr', '[::1]'),
    sourceUrl.replace('www.1365.go.kr', 'www.1365.go.kr:8443'), sourceUrl.replace('timeCptn.do', 'redirect.do'),
    `${sourceUrl}&redirect=https://evil.test`, `${sourceUrl}&type=show`, `${sourceUrl}#fragment`,
    sourceUrl.replace('1234567', 'evil'), `${sourceUrl} `, sourceUrl.replace('/vols/', '\\vols/'),
    'https://www.work24.go.kr/wk/a/b/1500/empDetailAuthView.do?wantedAuthNo=K123&infoTypeCd=OTHER&infoTypeGroup=tb_workinfoworknet',
  ])('blocks unapproved destination %s', (value) => expect(officialLink(value)).toBeNull())
})
