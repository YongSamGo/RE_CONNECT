import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { Ajv2020 } from 'ajv/dist/2020'
import { JSON_SCHEMA, load } from 'js-yaml'
import { expect, it } from 'vitest'
import { parseJourneyDraft } from '../src/features/preparation/draft-model'

it('parses actual Redis-backed draft creation, revision, approval and invalidation responses', () => {
  const root = new URL('../', import.meta.url)
  const python = process.env.CONTRACT_PYTHON || fileURLToPath(new URL(process.platform === 'win32' ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python', root))
  const actual = JSON.parse(execFileSync(python, ['-I', fileURLToPath(new URL('contract-tests/export_drafts.py', root))], {
    encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024, windowsHide: true,
  }))
  const contract = load(readFileSync(new URL('../../docs/api/openapi.yaml', import.meta.url), 'utf8'), { schema: JSON_SCHEMA }) as { components: Record<string, unknown> }
  const ajv = new Ajv2020({ strict: true, allErrors: true }).addKeyword('components')
    .addFormat('uuid', /^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i)
    .addFormat('date-time', value => Number.isFinite(Date.parse(value)) && /(?:Z|[+-]\d{2}:\d{2})$/.test(value))
  const validate = ajv.compile({ $ref: '#/components/schemas/JourneyDraft', components: contract.components })
  const drafts = ['created', 'edited', 'approved', 'current', 'changed'].map(key => {
    expect(validate(actual[key]), JSON.stringify(validate.errors)).toBe(true)
    return parseJourneyDraft(actual[key], { id: '00000000-0000-0000-0000-000000000001', version: 1 }, 1)
  })
  expect(drafts.map(draft => draft.revision)).toEqual([1, 2, 3, 3, 4])
  expect(drafts[0].self_introduction).toBe('')
  expect(drafts[1].approved_at).toBeNull()
  expect(drafts[2].approved_at).not.toBeNull()
  expect(drafts[3]).toEqual(drafts[2])
  expect(drafts[4].approved_at).toBeNull()
  expect(actual.stale_patch).toBe(409)
  expect(actual.other_owner).toBe(404)
  expect(actual.ai_without_consent).toBe(403)
  expect(actual.inference_calls).toBe(0)
}, 30000)
