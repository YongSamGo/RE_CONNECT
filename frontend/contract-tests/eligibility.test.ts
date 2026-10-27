import { readFileSync } from 'node:fs'
import { Ajv2020 } from 'ajv/dist/2020'
import { JSON_SCHEMA, load } from 'js-yaml'
import { expect, it } from 'vitest'

const contract = load(readFileSync(new URL('../../docs/api/openapi.yaml', import.meta.url), 'utf8'), { schema: JSON_SCHEMA }) as { components: Record<string, unknown> }
const compile = (name: string) => new Ajv2020({ strict: true, allErrors: true }).addKeyword('components')
  .compile({ $ref: `#/components/schemas/${name}`, components: contract.components })
const userValue = compile('EligibilityUserValue')

it('preserves unknown, confirmed absence and the actual single residence in the API schema', () => {
  for (const value of [null, [], 1958, 6.5, [1, 3], ['사회복지사 1급'], { province: 'seoul', district: 'seongdong' }]) {
    expect(userValue(value), JSON.stringify(userValue.errors)).toBe(true)
  }
})

it('does not allow owner or decision objects, booleans or oversized user values', () => {
  for (const value of [true, { owner_id: 'forged' }, { overall: 'satisfied' }, ['가'.repeat(101)], Array(8).fill(1), Array(21).fill('자격')]) {
    expect(userValue(value)).toBe(false)
  }
})

it('keeps empty comparison operands invalid while allowing confirmed empty profile values', () => {
  expect(compile('RequirementValue')([])).toBe(false)
  expect(userValue([])).toBe(true)
})
