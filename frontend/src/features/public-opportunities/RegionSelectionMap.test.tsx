import { useState } from 'react'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { RegionSelectionMap } from './RegionSelectionMap'
import { belongsToMap, clearWholeAreaSelection } from './map-selection'
import { regionBoundaries } from './region-boundaries'
import type { Region } from './catalog'

function IncheonMap() {
  const [regions, setRegions] = useState<Region[]>([])
  return <RegionSelectionMap province="incheon" regions={regions} onChange={setRegions} />
}

describe('region map selection', () => {
  it('assigns each Gyeonggi district to exactly one map', () => {
    const areas = ['incheon', 'gyeonggi-north', 'gyeonggi-south', 'gyeonggi-east', 'gyeonggi-west'] as const
    for (const region of regionBoundaries.filter((entry) => entry.province === 'gyeonggi')) {
      expect(areas.filter((area) => belongsToMap(area, region.province, region.id))).toHaveLength(1)
    }
  })
  it('clears a fully selected area while retaining other districts', () => {
    const regions: Region[] = [{ province: 'seoul', district: null }, { province: 'gyeonggi', district: 'gimpo' }]
    expect(clearWholeAreaSelection('seoul', regions)).toEqual([{ province: 'gyeonggi', district: 'gimpo' }])
    expect(clearWholeAreaSelection('incheon', regions)).toEqual(regions)
  })
  it('selects Gimpo and Incheon together while preserving their province identities', async () => {
    const user = userEvent.setup()
    render(<IncheonMap />)
    await user.click(screen.getByRole('button', { name: '김포/인천 전체 선택/해제' }))
    expect(screen.getByRole('button', { name: '김포시 선택됨' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '옹진군 선택됨' })).toHaveAttribute('aria-pressed', 'true')
    await user.click(screen.getByRole('button', { name: '김포시 선택됨' }))
    expect(screen.getByRole('button', { name: '김포시' })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByRole('button', { name: '옹진군 선택됨' })).toHaveAttribute('aria-pressed', 'true')
  })
  it('allows a district to be selected from the map', async () => {
    const user = userEvent.setup()
    render(<IncheonMap />)
    await user.click(screen.getByRole('button', { name: '제물포구' }))
    expect(screen.getByRole('button', { name: '제물포구 선택됨' })).toHaveAttribute('aria-pressed', 'true')
  })


})
