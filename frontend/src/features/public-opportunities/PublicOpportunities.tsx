import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { createApiClient } from '../../api/client'
import { ApiError } from '../../api/errors'
import { Button } from '../../ui/Button'
import { StatusNotice } from '../../ui/StatusNotice'
import { deadlineLabel, parseList, provinces } from './catalog'
import type { Opportunity, Search } from './catalog'
import { PublicCatalogProvider } from './PublicCatalogState'
import { emptySearch, usePublicCatalog } from './public-catalog-state'
import { useEntryAction } from '../../state/useEntryAction'
import { RegionSelectionMap } from './RegionSelectionMap'
import { belongsToMap, clearWholeAreaSelection } from './map-selection'
import type { MapArea } from './map-selection'
import { OpportunityListCard } from '../opportunities/OpportunityListCard'
import './catalog.css'

function OpportunityCard({ item }: { item: Opportunity }) {
  const activity = item.activity_type === 'volunteering' ? '봉사' : item.is_public_job ? '공공일자리' : '일자리'
  const region = item.activity_region ? provinces[item.activity_region.province] : '지역 확인 필요'
  const status = item.recruitment_status === 'unknown' ? '모집 여부 확인 필요' : item.change_pending ? '변경 내용 확인 중' : '모집 중'
  return <OpportunityListCard title={item.title} organization={item.organization_name}
    tags={[activity, region, deadlineLabel(item), ...(item.recruitment_status === 'unknown' || item.change_pending ? [status] : [])]}
    to={`/opportunities/${item.id}`} />
}

export function PublicOpportunities() {
  const memory = usePublicCatalog()
  return memory ? <Catalog /> : <PublicCatalogProvider><Catalog /></PublicCatalogProvider>
}

function Catalog() {
  const location = useLocation()
  const browseOnEntry = new URLSearchParams(location.search).get('browse') === 'all'
  const [api] = useState(() => createApiClient())
  const memory = usePublicCatalog()!
  const { value: browseAll, setValue: setBrowseAll } = memory.resultsOnly
  const { value: draft, setValue: setDraft } = memory.draft
  const scope = memory.result
  const [mapProvince, setMapProvince] = useState<MapArea>('seoul')
  const state = scope.value
  const active = useRef<{ id: number; signal?: AbortSignal } | undefined>(undefined)
  const sequence = useRef(0)
  const resultRef = useRef<HTMLElement>(null)
  const loading = state.status === 'loading'


  useEntryAction(() => {
    if (browseOnEntry) {
      setBrowseAll(true)
      if (state.status === 'idle') void load(emptySearch())
    }
  }, browseOnEntry)

  useEffect(() => {
    if (state.status === 'error' || state.status === 'loaded') resultRef.current?.focus({ preventScroll: true })
  }, [state.status])

  async function load(query: Search, page = 1) {
    if (active.current && !active.current.signal?.aborted) return
    scope.clear()
    const id = ++sequence.current
    active.current = { id }
    scope.setValue({ status: 'loading', query, page })
    try {
      await scope.run(async (signal) => {
        active.current = { id, signal }
        const release = () => { if (active.current?.id === id) active.current = undefined }
        signal.addEventListener('abort', release, { once: true })
        try {
          const { data } = await api.GET('/opportunities', { signal, params: { query: {
            page, page_size: 20, ...(query.q ? { q: query.q } : {}),
            ...(query.regions.length ? { regions: query.regions.map(({ province, district }) => district ? `${province}:${district}` : province) } : {}),
            ...(query.activity_type ? { activity_type: query.activity_type } : {}),
          } } })
          return parseList(data, page)
        } finally { signal.removeEventListener('abort', release) }
      }, (result) => scope.setValue({ status: 'loaded', query, result }))
    } catch (error) {
      if (active.current?.id === id) scope.setValue({ status: 'error', query, page, error: error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE') })
    } finally { if (active.current?.id === id) active.current = undefined }
  }
  const clearOnLeave = scope.clear
  useEffect(() => () => { if (active.current) clearOnLeave() }, [clearOnLeave])
  function cancel() { scope.clear(); active.current = undefined; setBrowseAll(false) }
  function submitSearch() {
    setBrowseAll(true)
    void load({ ...draft, q: draft.q.trim() })
  }

  return <div className={`public-catalog${browseAll ? ' public-catalog-browse-all' : ''}`}>
    {!browseAll && <section className="public-catalog-stage" aria-label="지역별 공고 탐색">
      <header className="public-catalog-heading"><h1 id="public-explore-title">조건에 맞는 기회 찾아보기</h1><button className="catalog-browse-all" type="button" disabled={loading} onClick={() => { setBrowseAll(true); void load(emptySearch()) }}>일단 둘러볼래요</button></header>
      <form className="public-catalog-partition" onSubmit={(event) => { event.preventDefault(); submitSearch() }}>
        <section className="public-map-pane" aria-label="활동 지역 고르기">
          <RegionSelectionMap province={mapProvince} regions={draft.regions} onChange={(regions) => setDraft((previous) => ({ ...previous, regions }))} />
        </section>
        <section className="public-explore-pane" aria-labelledby="public-explore-title">
          <div className="catalog-keyword"><label htmlFor="catalog-query">어떤 기회를 찾으세요?</label>
            <input id="catalog-query" type="search" maxLength={100} autoComplete="off" value={draft.q} onChange={(event) => setDraft((previous) => ({ ...previous, q: event.target.value }))} placeholder="공고 제목, 기관명으로 검색하기" />
          </div>
          <fieldset className="catalog-provinces"><legend>지역</legend><div className="region-province-tabs">
            {([['seoul', '서울'], ['incheon', '김포/인천'], ['gyeonggi-north', '경기 북부'], ['gyeonggi-south', '경기 남부'], ['gyeonggi-east', '경기 동부'], ['gyeonggi-west', '경기 서부']] as const).map(([province, label]) => {
              const selected = draft.regions.some((region) => belongsToMap(province, region.province, region.district))
              return <div className="province-option" key={province}><button type="button" aria-label={`${label} 지도 보기${selected ? ', 선택한 지역 있음' : ''}`} aria-pressed={mapProvince === province} className={`${selected ? 'has-selection' : ''}${mapProvince === province ? ' is-current' : ''}`} onClick={() => { if (mapProvince !== province) { setDraft((previous) => ({ ...previous, regions: clearWholeAreaSelection(mapProvince, previous.regions) })); setMapProvince(province) } }}>{label}</button></div>
            })}
            <div className="province-option"><button type="button" className="region-clear" aria-pressed={draft.regions.length === 0} onClick={() => setDraft((previous) => ({ ...previous, regions: [] }))}>선택 안함</button></div>
          </div></fieldset>
          <div className="catalog-activity"><label htmlFor="catalog-activity">활동 유형</label><select id="catalog-activity" value={draft.activity_type} onChange={(event) => {
            const value = event.target.value
            if (value === '' || value === 'employment' || value === 'volunteering') setDraft((previous) => ({ ...previous, activity_type: value }))
          }}><option value="">활동 유형 전체</option><option value="employment">취업 및 공공일자리</option><option value="volunteering">봉사</option></select></div>
          <div className="public-explore-footer">
            <div className="public-explore-actions"><Button type="submit" pending={loading} pendingLabel="공고를 불러오고 있어요">공고 검색하기</Button>{loading && <Button variant="secondary" onClick={cancel}>조회 취소하기</Button>}</div>
            <Link className="text-link public-experience-link" to="/start">내 경험 이야기하기</Link>
          </div>
        </section>
      </form>
    </section>}
    <div className="public-catalog-results" hidden={!browseAll}>
    <section className="catalog-results" ref={resultRef} tabIndex={-1} aria-label="공고 조회 결과">
      {browseAll && <header className="catalog-browse-heading"><h1>공고 살펴보기</h1><button className="text-link" type="button" onClick={() => { setBrowseAll(false); if (loading) cancel() }}>검색 조건 선택</button></header>}
      {state.status === 'loading' && <StatusNotice kind="loading" title="공고를 확인하고 있어요" actions={<Button variant="secondary" onClick={() => { cancel(); setBrowseAll(false) }}>조회 취소하기</Button>}>잠시 기다려 주세요.</StatusNotice>}
      {state.status === 'error' && <div className="catalog-error" role="alert"><p>{state.error.message}</p>{state.error.code !== 'DAILY_QUOTA_EXCEEDED' && <button type="button" className="catalog-browse-all" onClick={() => void load(state.query, state.page)}>다시 시도하기</button>}</div>}
      {state.status === 'loaded' && <>
        <h2 className="visually-hidden">공개 공고 검색 결과</h2>
        <p role="status">검색 결과 {state.result.total.toLocaleString('ko-KR')}건 / {state.result.page}페이지</p>
        {state.result.items.length ? <ul className="opportunity-list shared-opportunity-list">{state.result.items.map((item) => <OpportunityCard key={item.id} item={item} />)}</ul>
          : state.result.total === 0
            ? <StatusNotice label="검색 결과" title="이 조건의 공고가 없어요">검색어나 지역, 활동 유형을 바꿔 다시 검색해 보세요. 선택한 조건을 자동으로 넓히지는 않아요.</StatusNotice>
            : <StatusNotice label="검색 결과" title="이 페이지에 표시할 공고가 없어요" actions={<Button onClick={() => void load(state.query, 1)}>첫 페이지 다시 조회</Button>}>공고 상태가 변경되었을 수 있어요. 같은 조건으로 첫 페이지를 다시 조회해 보세요.</StatusNotice>}
        {(state.result.page > 1 || state.result.page * state.result.page_size < state.result.total) && <nav className="catalog-pagination" aria-label="공고 페이지 이동">
          <Button variant="secondary" disabled={state.result.page === 1} onClick={() => void load(state.query, state.result.page - 1)}>이전 페이지</Button>
          <span>{state.result.page}페이지</span>
          <Button variant="secondary" disabled={state.result.page * state.result.page_size >= state.result.total} onClick={() => void load(state.query, state.result.page + 1)}>다음 페이지</Button>
        </nav>}
      </>}
    </section>
    </div>
  </div>
}
