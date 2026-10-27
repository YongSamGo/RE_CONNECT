import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { Ajv2020 } from 'ajv/dist/2020'
import { JSON_SCHEMA, load } from 'js-yaml'
import { expect, it } from 'vitest'
import { parseEligibility, parseRecommendations } from '../src/features/recommendations/model'
import type { ProfileRef } from '../src/features/recommendations/model'
import { parseDraft, parseExistingDraft } from '../src/features/preparation/drafts'
import { parseExclusions, parseProfileView, parseRoles } from '../src/features/profile/server-model'

const root = new URL('../', import.meta.url)
const python = process.env.CONTRACT_PYTHON || fileURLToPath(new URL(process.platform === 'win32' ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python', root))
const contract = load(readFileSync(new URL('../../docs/api/openapi.yaml', import.meta.url), 'utf8'), { schema: JSON_SCHEMA }) as { components: Record<string, unknown> }
const ajv = new Ajv2020({ strict: true, allErrors: true }).addKeyword('components')
  .addFormat('uuid', /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i)
  .addFormat('date', value => /^\d{4}-\d{2}-\d{2}$/.test(value) && Number.isFinite(Date.parse(value)))
  .addFormat('date-time', value => Number.isFinite(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value))
const validate = ajv.compile({ $ref: '#/components/schemas/RecommendationList', components: contract.components })

it('validates the actual private recommendation HTTP body against the original OpenAPI contract', () => {
  const actual = JSON.parse(execFileSync(python, ['-I', fileURLToPath(new URL('contract-tests/export_recommendation.py', root))], {
    encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024, windowsHide: true,
  })) as { status: number; body: { items: Record<string, unknown>[]; profile: ProfileRef }; eligibility_status: number; eligibility: unknown; profile: unknown; roles: unknown; exclusions: unknown; draft_statuses: number[]; drafts: unknown[] }
  expect(actual.status).toBe(200)
  expect(actual.body.items).toHaveLength(1)
  expect(validate(actual.body), JSON.stringify(validate.errors)).toBe(true)
  const forged = structuredClone(actual.body)
  forged.items[0].score = 1
  expect(validate(forged)).toBe(false)
  const recommendations = parseRecommendations(actual.body, actual.body.profile)
  expect(recommendations.items[0].matched.experience_ids.length).toBeGreaterThan(0)
  expect(actual.eligibility_status).toBe(200)
  expect(parseEligibility(actual.eligibility, actual.body.profile, { id: '00000000-0000-0000-0000-000000000001', version: 1 }).no_requirements).toBe(true)
  const profile = parseProfileView(actual.profile)
  const roles = parseRoles(actual.roles, profile)
  expect(roles.items[0].evidence[0].experience_id).toBe(profile.draft.experiences[0].id)
  expect(parseExclusions(actual.exclusions, profile)).toEqual([])
  expect(actual.draft_statuses).toEqual([201, 200, 200, 200])
  const created = parseDraft(actual.drafts[0], '00000000-0000-0000-0000-000000000001')
  const edited = parseExistingDraft(actual.drafts[1], created)
  const approved = parseExistingDraft(actual.drafts[2], edited)
  const displayed = parseExistingDraft(actual.drafts[3], approved)
  expect(edited.approved_at).toBeNull()
  expect(displayed.revision).toBe(3)
  expect(displayed.approved_at).not.toBeNull()
  expect(displayed.self_introduction).toBe('직접 쓴 가상 경험')
  const validateDraft = ajv.compile({ $ref: '#/components/schemas/JourneyDraft', components: contract.components })
  for (const draft of actual.drafts) expect(validateDraft(draft), JSON.stringify(validateDraft.errors)).toBe(true)
}, 20000)
