/* oxlint-disable react/only-export-components -- Map selection helpers are shared with the filter and its tests. */
import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { regionBoundaries } from './region-boundaries'
import { incheonBoundaries } from './incheon-boundaries'
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
const mapViewBoxes: Record<MapArea, string> = {
  seoul: '0 0 760 640',
  gyeonggi: '0 0 540 640',
  incheon: '580 275 210 230',
  'gyeonggi-north': '95 5 365 365',
  'gyeonggi-south': '50 400 380 240',
  'gyeonggi-east': '220 270 320 300',
  'gyeonggi-west': '105 325 155 150',
}
const areaNames: Record<MapArea, string> = { seoul: '서울', gyeonggi: '경기', incheon: '김포/인천', 'gyeonggi-north': '경기 북부', 'gyeonggi-south': '경기 남부', 'gyeonggi-east': '경기 동부', 'gyeonggi-west': '경기 서부' }

const labelOffsets: Record<string, [number, number]> = {
  gwacheon: [3, -3], uiwang: [4, 4], gunpo: [-5, 3], gwangmyeong: [-3, -4],
  guri: [-3, 5], uijeongbu: [0, -3],
}

function withoutSmallIslands(path: string, regionId?: string) {
  return (path.match(/M[^M]+/g) ?? []).filter((part) => {
    const points = Array.from(part.matchAll(/[ML](-?[\d.]+) (-?[\d.]+)/g), (match) => [Number(match[1]), Number(match[2])])
    if (!points.length) return false
    const xs = points.map(([x]) => x)
    const ys = points.map(([, y]) => y)
    const minX = Math.min(...xs), maxX = Math.max(...xs)
    const minY = Math.min(...ys), maxY = Math.max(...ys)
    const area = (maxX - minX) * (maxY - minY)
    if (regionId === 'ganghwa') return area >= 1000 && maxY > 316
    if (regionId === 'yeongjong') return area >= 1000
    if (regionId === 'ansan' || regionId === 'hwaseong') return area >= 3000
    return area >= 20
  }).join(' ')
}

type Props = {
  province: MapArea
  regions: Region[]
  onChange: (regions: Region[]) => void
  compact?: boolean
}

export function RegionSelectionMap({ province, regions, onChange, compact = false }: Props) {
  const [limitReached, setLimitReached] = useState(false)
  const mapRef = useRef<SVGSVGElement>(null)
  const [labelSize, setLabelSize] = useState<number>()
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const updateLabelSize = () => {
      const bounds = map.getBoundingClientRect()
      const [, , width, height] = mapViewBoxes[province].split(' ').map(Number)
      const scale = Math.min(bounds.width / width!, bounds.height / height!)
      if (scale > 0) setLabelSize(Math.min(13, Math.max(8, bounds.height * .04)) / scale)
    }
    updateLabelSize()
    if (typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(updateLabelSize)
    observer.observe(map)
    return () => observer.disconnect()
  }, [province])
  const baseProvince: Province = province.startsWith('gyeonggi') ? 'gyeonggi' : province as Province
  const mapRegions = regionBoundaries.filter((region) => region.province === baseProvince)
  const activeRegions = [...mapRegions.filter((region) => belongsToMap(province, region.province, region.id)), ...(province === 'incheon' ? [{ province: 'gyeonggi' as const, id: 'gimpo', name: '김포시', d: incheonBoundaries.gimpo, labelX: 722, labelY: 366 }] : [])]
  const isSelected = (id: string) => {
    const target = activeRegions.find((region) => region.id === id)
    return !!target && regions.some((region) => region.province === target.province && (region.district === id || region.district === null))
  }
  const wholeProvinceSelected = activeRegions.every((region) => isSelected(region.id))

  function compressProvince(values: Region[]) {
    if (mapRegions.every(({ id }) => values.some((region) => region.province === baseProvince && region.district === id))) {
      return [...values.filter((region) => region.province !== baseProvince), { province: baseProvince, district: null }]
    }
    return values
  }

  function toggleProvince() {
    const expanded = regions.flatMap((region) => region.district === null && activeRegions.some((entry) => entry.province === region.province) ? regionBoundaries.filter((entry) => entry.province === region.province).map(({ id }) => ({ province: region.province, district: id })) : [region])
    const remaining = expanded.filter((region) => !activeRegions.some((entry) => entry.province === region.province && entry.id === region.district))
    const next = wholeProvinceSelected ? remaining : [...remaining, ...activeRegions.map(({ id, province: regionProvince }) => ({ province: regionProvince, district: id }))]
    if (next.length > 67) { setLimitReached(true); return }
    setLimitReached(false)
    onChange(compressProvince(next))
  }

  function toggleDistrict(id: string) {
    const targetProvince = activeRegions.find((region) => region.id === id)?.province
    if (!targetProvince) return
    const exists = isSelected(id)
    const expanded = regions.flatMap((region) => region.province === targetProvince && region.district === null ? regionBoundaries.filter((entry) => entry.province === targetProvince).map(({ id: district }) => ({ province: targetProvince, district })) : [region])
    if (exists) {
      setLimitReached(false)
      onChange(expanded.filter((region) => !(region.province === targetProvince && region.district === id)))
      return
    }
    const next = expanded
    if (next.length >= 67) { setLimitReached(true); return }
    setLimitReached(false)
    onChange(compressProvince([...next, { province: targetProvince, district: id }]))
  }

  function handleMapKeyDown(event: KeyboardEvent<SVGPathElement>, id: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault()
      toggleDistrict(id)
    }
  }

  return <div className={`region-picker${compact ? ' region-picker-compact' : ''}`}>
    <div className="region-map-frame">
      <svg ref={mapRef} className={`region-map region-map--${province}`} viewBox={mapViewBoxes[province]} role="group" aria-label={`${areaNames[province]} 행정구역 지도`}>
        {activeRegions.map(({ id, name, d }) => {
          const selected = isSelected(id)
          return <g key={id} className={`region-map-area${selected ? ' is-selected' : ''}`}>
            <path d={province === 'incheon' ? incheonBoundaries[id] : ((province === 'gyeonggi-west' && id === 'ansan') || (province === 'gyeonggi-south' && id === 'hwaseong')) ? withoutSmallIslands(d, id) : d} fillRule="evenodd" role="button" tabIndex={0} aria-label={`${name}${selected ? ' 선택됨' : ''}`} aria-pressed={selected} onClick={() => toggleDistrict(id)} onKeyDown={(event) => handleMapKeyDown(event, id)} />
          </g>
        })}
        {activeRegions.map(({ id, name, labelX, labelY }) => {
          const [dx, dy] = province === 'incheon' ? ({ jemulpo: [-18, -7], michuhol: [-5, 5], namdong: [25, 1] } as Record<string, [number, number]>)[id] ?? [0, 0] : baseProvince === 'gyeonggi' ? labelOffsets[id] ?? [0, 0] : [0, 0]
          return <text key={id} className={`region-map-label${isSelected(id) ? ' is-selected' : ''}`} style={labelSize ? { fontSize: labelSize } : undefined} x={province === 'incheon' && id === 'ongjin' ? 601 : labelX + dx} y={province === 'incheon' && id === 'ongjin' ? 393 : labelY + dy} aria-hidden="true">{name}</text>
        })}
      </svg>
    </div>
    <div className="region-map-controls">
      <p className="region-map-instruction">지도를 눌러 지역을 선택하세요</p>
      {!compact && <button type="button" className={`region-whole-button${wholeProvinceSelected ? ' is-selected' : ''}`} aria-label={`${areaNames[province]} 전체 선택/해제`} aria-pressed={wholeProvinceSelected} onClick={toggleProvince}>전체 선택/해제</button>}
    </div>
    {limitReached && <p className="region-limit-message" role="status">지역은 최대 67곳까지 선택할 수 있어요.</p>}
  </div>
}
