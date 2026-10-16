import type { components } from '../../api/schema'
import { invalid, record, text } from '../public-opportunities/catalog'

export type RegionCatalog = components['schemas']['RegionCatalog']
export type Region = components['schemas']['Region']
/** Bounded display projection; district identifiers must be unique within each province. */
export function parseRegionCatalog(value: unknown): RegionCatalog {
  const item = record(value)
  if (!Array.isArray(item.provinces) || item.provinces.length > 3) return invalid()
  const provinces = item.provinces.map<RegionCatalog['provinces'][number]>((value) => {
    const province = record(value)
    if (province.id !== 'seoul' && province.id !== 'gyeonggi' && province.id !== 'incheon') return invalid()
    if (!Array.isArray(province.districts) || province.districts.length > 100) return invalid()
    const districts = province.districts.map((value) => {
      const district = record(value)
      const id = text(district.id, 40)
      if (!/^[a-z0-9_]{2,40}$/.test(id)) return invalid()
      return { id, name: text(district.name, 20) }
    })
    if (new Set(districts.map((district) => district.id)).size !== districts.length) return invalid()
    return { id: province.id, name: text(province.name, 20), districts }
  })
  if (new Set(provinces.map((province) => province.id)).size !== provinces.length) return invalid()
  return { version: text(item.version, 32), provinces }
}
export function regionsMatchCatalog(regions: Region[], catalog: RegionCatalog | null): boolean {
  return regions.length > 0 && regions.length <= 10
    && regions.every((region) => region.province === 'seoul' || region.province === 'gyeonggi' || region.province === 'incheon')
    && new Set(regions.map((region) => `${region.province}:${region.district ?? '*'}`)).size === regions.length
    && regions.every((region) => region.district === null || !!catalog?.provinces.find((province) => province.id === region.province)?.districts.some((district) => district.id === region.district)
      && !regions.some((other) => other.province === region.province && other.district === null))
}
