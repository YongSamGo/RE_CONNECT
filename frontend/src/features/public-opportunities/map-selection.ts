import { regionBoundaries } from './region-boundaries'
import type { Province, Region } from './catalog'

export type MapArea = Province | 'gyeonggi-north' | 'gyeonggi-south' | 'gyeonggi-east' | 'gyeonggi-west'
export const northDistricts = new Set(['goyang', 'namyangju', 'uijeongbu', 'paju', 'yangju', 'guri', 'pocheon', 'dongducheon', 'gapyeong', 'yeoncheon'])
const eastDistricts = new Set(['hanam', 'seongnam', 'gwangju', 'icheon', 'yeoju', 'yangpyeong'])
const westDistricts = new Set(['bucheon', 'gwangmyeong', 'anyang', 'siheung', 'ansan', 'gunpo', 'uiwang', 'gwacheon'])
export function belongsToMap(area: MapArea, province: Province, district: string | null) {
  if (area === 'incheon') return province === 'incheon' || (province === 'gyeonggi' && (district === 'gimpo' || district === null))
  if (area.startsWith('gyeonggi-')) {
    if (province !== 'gyeonggi') return false
    if (district === null) return true
    if (district === 'gimpo') return false
    if (area === 'gyeonggi-north') return northDistricts.has(district)
    if (area === 'gyeonggi-east') return eastDistricts.has(district)
    if (area === 'gyeonggi-west') return westDistricts.has(district)
    return !northDistricts.has(district) && !eastDistricts.has(district) && !westDistricts.has(district)
  }
  return area === province
}
export function clearWholeAreaSelection(area: MapArea, regions: Region[]) {
  const targets = regionBoundaries.filter((entry) => belongsToMap(area, entry.province, entry.id))
  const allSelected = targets.length > 0 && targets.every((target) => regions.some((region) => region.province === target.province && (region.district === null || region.district === target.id)))
  if (!allSelected) return regions
  const expanded = regions.flatMap((region) => region.district === null && targets.some((target) => target.province === region.province)
    ? regionBoundaries.filter((entry) => entry.province === region.province).map(({ id }) => ({ province: region.province, district: id })) : [region])
  return expanded.filter((region) => !targets.some((target) => target.province === region.province && target.id === region.district))
}
