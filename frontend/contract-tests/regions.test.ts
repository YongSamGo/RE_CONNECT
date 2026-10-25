import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { Ajv2020 } from 'ajv/dist/2020'
import { JSON_SCHEMA, load } from 'js-yaml'
import { beforeAll, describe, expect, it } from 'vitest'
import { parseRegionCatalog, regionsMatchCatalog } from '../src/features/regions/catalog'
import type { Region, RegionCatalog } from '../src/features/regions/catalog'

type Schema = Record<string, unknown>
type Document = { components: { schemas: Record<string, Schema> }; paths: Record<string, { get: { responses: Record<string, { content: Record<string, { schema: Schema }> }> } }> }
type Exported = { status: number; content_type: string; body: RegionCatalog; openapi: Document; selections: Region[] }
const root = new URL('../', import.meta.url)
const python = process.env.CONTRACT_PYTHON || fileURLToPath(new URL(process.platform === 'win32' ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python', root))
const contract = load(readFileSync(new URL('../docs/api/openapi.yaml', root), 'utf8'), { schema: JSON_SCHEMA }) as Document
// components is an OpenAPI container, not a validation keyword. Local $refs still
// resolve through it; other unknown schema keywords remain errors in strict mode.
function validator(document: Document, responseSchema: Schema) {
  return new Ajv2020({ strict: true, allErrors: true }).addKeyword('components')
    .compile({ ...responseSchema, components: document.components })
}
const contractResponse = contract.paths['/regions'].get.responses['200'].content['application/json'].schema
const validateContract = validator(contract, contractResponse)
let actual: Exported
beforeAll(() => {
  actual = JSON.parse(execFileSync(python, ['-I', fileURLToPath(new URL('contract-tests/export_regions.py', root))], {
    encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024, windowsHide: true,
  })) as Exported
}, 25000)

describe('#19 actual public region router → OpenAPI → frontend parser', () => {
  it('returns the contracted status/media type and validates the complete body', () => {
    expect(actual.status).toBe(200)
    expect(actual.content_type.split(';')[0]).toBe('application/json')
    expect(validateContract(actual.body), JSON.stringify(validateContract.errors)).toBe(true)
    const backendSchema = actual.openapi.paths['/api/v1/regions'].get.responses['200'].content['application/json'].schema
    expect(validator(actual.openapi, backendSchema)(actual.body)).toBe(true)
  })
  it('frontend preserves every real identifier, label and version without a copied fixture', () => {
    expect(parseRegionCatalog(actual.body)).toEqual(actual.body)
    expect(actual.body.provinces.map(item => item.id).sort()).toEqual(['gyeonggi', 'incheon', 'seoul'])
    expect(actual.selections.length).toBeGreaterThan(0)
    for (const region of actual.selections) expect(regionsMatchCatalog([region], actual.body)).toBe(true)
  })
  it('rejects an undeclared response property rather than hiding backend contract drift', () => {
    expect(validateContract({ ...actual.body, undeclared: true })).toBe(false)
    expect(validateContract.errors?.some(error => error.keyword === 'additionalProperties')).toBe(true)
  })
  it('detects a stale contract that narrows a real backend value', () => {
    const changed = structuredClone(contract)
    changed.components.schemas.RegionCatalog = {
      ...changed.components.schemas.RegionCatalog,
      properties: { version: { const: '__incompatible_contract_version__' }, provinces: { type: 'array' } },
    }
    expect(validator(changed, contractResponse)(actual.body)).toBe(false)
  })
  it('does not broaden an unknown or wrong-province district to a province-wide selection', () => {
    const catalog = parseRegionCatalog(actual.body)
    expect(regionsMatchCatalog([{ province: 'seoul', district: 'missing_district' }], catalog)).toBe(false)
    const region = actual.selections.find(value => value.province === 'gyeonggi' && !catalog.provinces.find(item => item.id === 'seoul')?.districts.some(item => item.id === value.district))!
    expect(region).toBeDefined()
    expect(regionsMatchCatalog([{ ...region, province: 'seoul' }], catalog)).toBe(false)
  })
})
