import { describe, expect, it } from 'vitest'
import { parseRegionCatalog, regionsMatchCatalog } from './regions'

const district = { id: 'test_district', name: '가상구' }
const province = { id: 'seoul', name: '서울', districts: [district] }
const catalog = { version: 'test-version', provinces: [province] }
describe('region catalog projection', () => {
  it('keeps server identifiers/names/version and drops unknown properties', () => {
    expect(parseRegionCatalog({ ...catalog, internal: 'private', provinces: [{ ...province, private: 'hidden', districts: [{ ...district, body: 'hidden' }] }] })).toEqual(catalog)
  })
  it.each([
    { version: '' }, { version: 'x'.repeat(33) }, { provinces: null },
    { provinces: [{ ...province, id: 'other' }] }, { provinces: [province, province] },
    { provinces: [{ ...province, name: 'x'.repeat(21) }] },
    { provinces: [{ ...province, districts: [district, district] }] },
    { provinces: [{ ...province, districts: [{ id: 'bad/id', name: '가상구' }] }] },
    { provinces: [{ ...province, districts: [{ id: 'a', name: '가상구' }] }] },
    { provinces: [{ ...province, districts: [{ ...district, name: '' }] }] },
    { provinces: [{ ...province, districts: Array.from({ length: 101 }, (_, index) => ({ id: `test_${index}`, name: '가상구' })) }] },
  ])('rejects invalid or excessive catalogs %j', (patch) => expect(() => parseRegionCatalog({ ...catalog, ...patch })).toThrow())
  it('requires a current catalog match for districts without broadening unknown selections', () => {
    const parsed = parseRegionCatalog(catalog)
    const selected = [{ province: 'seoul' as const, district: district.id }]
    expect(regionsMatchCatalog(selected, parsed)).toBe(true)
    expect(regionsMatchCatalog(selected, null)).toBe(false)
    expect(regionsMatchCatalog([{ province: 'seoul', district: 'missing' }], parsed)).toBe(false)
    expect(regionsMatchCatalog([{ province: 'seoul', district: null }], null)).toBe(true)
    expect(regionsMatchCatalog([...selected, ...selected], parsed)).toBe(false)
    expect(regionsMatchCatalog([...selected, { province: 'seoul', district: null }], parsed)).toBe(false)
    expect(regionsMatchCatalog([], parsed)).toBe(false)
  })
})
