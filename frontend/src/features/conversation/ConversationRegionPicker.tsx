import { useState } from 'react'
import { required, useRequest } from '../../state/useRequest'
import { useEntryAction } from '../../state/useEntryAction'
import { Button } from '../../ui/Button'
import { RequestError } from '../../ui/StatusNotice'
import { provinces } from '../public-opportunities/catalog'
import { parseRegionCatalog } from '../regions/catalog'
import type { RegionCatalog } from '../regions/catalog'

/** 지역 질문에 말 대신 목록에서 고른 정확한 지명을 답변 칸에 넣는다. 서버가 같은 이름표로 희망 지역을 맞춘다. */
export function ConversationRegionPicker({ disabled, onInsert }: { disabled: boolean; onInsert: (place: string) => void }) {
  const regions = useRequest<RegionCatalog>()
  const [province, setProvince] = useState<keyof typeof provinces>('seoul')
  const [district, setDistrict] = useState('')
  const load = () => void regions.run(async (api, signal) => parseRegionCatalog(required((await api.GET('/regions', { signal })).data)))
  useEntryAction(load, true, 'conversation-regions')
  const catalog = regions.state.status === 'success' ? regions.state.data : null
  const districts = catalog?.provinces.find(item => item.id === province)?.districts ?? []
  const name = districts.find(item => item.id === district)?.name
  return <section className="conversation-region-picker" aria-labelledby="conversation-region-title">
    <h3 id="conversation-region-title">지역 목록에서 고르기</h3>
    <label htmlFor="conversation-region-province">시도</label>
    <select id="conversation-region-province" value={province} disabled={disabled} onChange={event => { setProvince(event.target.value as keyof typeof provinces); setDistrict('') }}>
      {Object.entries(provinces).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
    </select>
    <label htmlFor="conversation-region-district">시군구</label>
    <select id="conversation-region-district" value={district} disabled={disabled || !catalog} onChange={event => setDistrict(event.target.value)}>
      <option value="">{provinces[province]} 전체</option>
      {districts.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
    </select>
    {regions.state.status === 'pending' && <p role="status">시군구 목록을 불러오고 있어요.</p>}
    {regions.state.status === 'error' && <><RequestError error={regions.state.error} /><Button variant="secondary" onClick={load}>시군구 목록 다시 불러오기</Button></>}
    <div className="actions"><Button variant="secondary" disabled={disabled} onClick={() => onInsert(name ? `${provinces[province]} ${name}` : `${provinces[province]} 전체`)}>답변에 넣기</Button></div>
  </section>
}
