import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { createApiClient } from '../../api/client'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { deadlineLabel, parseList, provinces, searchDescription } from './catalog'
import type { Opportunity, OpportunityList, Search } from './catalog'
import { required, useRequest } from '../../state/useRequest'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { parseRegionCatalog } from '../regions/catalog'
import type { RegionCatalog } from '../regions/catalog'
import './catalog.css'

type State = { status: 'idle' }
  | { status: 'loading'; query: Search; page: number }
  | { status: 'loaded'; query: Search; result: OpportunityList }
  | { status: 'error'; query: Search; page: number; error: ApiError }
const initial = (): State => ({ status: 'idle' })
const emptySearch = (): Search => ({ q: '', province: '', district: '', districtName: '', regionVersion: null, activity_type: '' })

function OpportunityCard({ item }: { item: Opportunity }) {
  return <li className="opportunity-card"><article aria-labelledby={`opportunity-${item.id}`}>
    <div className="opportunity-labels"><span>{item.activity_type === 'volunteering' ? '봉사' : item.is_public_job ? '공공일자리' : '취업·일자리'}</span>
      <span>{item.recruitment_status === 'unknown' ? '모집 여부 확인 필요' : '모집 중'}</span>
      {item.change_pending && <span>변경 내용 검수 중</span>}</div>
    <h3 id={`opportunity-${item.id}`}>{item.title}</h3><p className="organization">{item.organization_name}</p>
    <dl><div><dt>활동 지역</dt><dd>{item.activity_region ? provinces[item.activity_region.province] : '지역 확인 필요'}{item.remote_allowed === true && ' · 원격 활동 가능'}{item.activity_region?.district && ' · 시·군·구는 상세에서 확인'}</dd></div>
      <div><dt>보수</dt><dd>{item.paid === null ? '보수 확인 필요' : item.paid ? '보수 있음' : '무보수'}</dd></div>
      <div><dt>마감</dt><dd>{deadlineLabel(item)}</dd></div></dl>
    <Link className="text-link" to={`/opportunities/${item.id}`} aria-label={`${item.title} 공고 상세 화면으로`}>공고 상세 화면으로 →</Link>
    <p className="catalog-note">상세에서 최신 모집 상태와 원문 조건을 확인하세요. 지원 자격과 신청 완료를 뜻하지 않습니다.</p>
  </article></li>
}

export function PublicOpportunities() {
  const [api] = useState(() => createApiClient())
  const { value: draft, setValue: setDraft } = useMemoryScope(emptySearch)
  const scope = useMemoryScope(initial)
  const regionRequest = useRequest<RegionCatalog>()
  const errors = useMemoryScope<FieldError[]>(() => [])
  const catalog = regionRequest.state.status === 'success' ? regionRequest.state.data : null
  const regionsPending = regionRequest.state.status === 'pending'
  const districts = catalog?.provinces.find((province) => province.id === draft.province)?.districts ?? []
  const selectedDistrict = districts.find((district) => district.id === draft.district)
  const state = scope.value
  const active = useRef<{ id: number; signal?: AbortSignal } | undefined>(undefined)
  const sequence = useRef(0)
  const resultRef = useRef<HTMLElement>(null)
  const loading = state.status === 'loading'

  useEffect(() => {
    if (state.status === 'loaded' || state.status === 'error') resultRef.current?.focus()
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
            ...(query.province ? { province: query.province } : {}), ...(query.activity_type ? { activity_type: query.activity_type } : {}),
            ...(query.province && query.district ? { district: query.district } : {}),
          } } })
          return parseList(data, page)
        } finally { signal.removeEventListener('abort', release) }
      }, (result) => scope.setValue({ status: 'loaded', query, result }))
    } catch (error) {
      if (active.current?.id === id) scope.setValue({ status: 'error', query, page, error: error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE') })
    } finally { if (active.current?.id === id) active.current = undefined }
  }
  function cancel() { scope.clear(); active.current = undefined }
  function submitSearch() {
    if (regionsPending) return
    if (draft.district && (!draft.province || !selectedDistrict)) {
      errors.setValue([{ fieldId: 'catalog-district', message: '시·군·구 목록을 다시 불러와 선택을 확인하거나, 활동 범위를 직접 변경해 주세요.' }]); return
    }
    errors.clear()
    void load({ ...draft, q: draft.q.trim(), districtName: selectedDistrict?.name ?? '', regionVersion: draft.district ? catalog!.version : null })
  }

  return <div className="reading-width public-catalog">
    <header className="page-heading"><p className="eyebrow">로그인 없이 · 공개 공고 탐색</p><h1>나의 다음 기회를 찾아봐요</h1>
      <p>취업·공공일자리와 봉사 공고를 찾아보세요. 검색에는 AI 처리 동의나 프로필이 필요하지 않습니다.</p></header>
    <form className="panel catalog-form" onSubmit={(event) => { event.preventDefault(); submitSearch() }}>
      <FormErrorSummary errors={errors.value} />
      <div className="catalog-keyword"><label htmlFor="catalog-query">어떤 기회를 찾으세요?</label>
        <input id="catalog-query" type="search" maxLength={100} autoComplete="off" value={draft.q} onChange={(event) => setDraft((previous) => ({ ...previous, q: event.target.value }))} aria-describedby="catalog-query-help" placeholder="공고 제목, 기관명, 역량으로 검색" />
        <p className="field-hint" id="catalog-query-help">검색어는 100자까지 입력할 수 있어요. 비워두면 모든 공고를 살펴봅니다.</p></div>
      <div><label htmlFor="catalog-province">활동 지역</label><select id="catalog-province" value={draft.province} onChange={(event) => {
        const value = event.target.value
        if (value === '' || value === 'seoul' || value === 'gyeonggi' || value === 'incheon') { errors.clear(); setDraft((previous) => ({ ...previous, province: value, district: '', districtName: '', regionVersion: null })) }
      }}><option value="">지역 전체</option>{Object.entries(provinces).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select></div>
      <div><label htmlFor="catalog-district">시·군·구</label><select id="catalog-district" disabled={!draft.province || regionsPending} value={draft.district} aria-invalid={errors.value.length ? true : undefined} aria-describedby="catalog-district-help" onChange={(event) => {
        const value = event.target.value, district = districts.find((district) => district.id === value)
        if (value === '' || district) { errors.clear(); setDraft((previous) => ({ ...previous, district: value, districtName: district?.name ?? '', regionVersion: value ? catalog!.version : null })) }
      }}><option value="">{draft.province ? `${provinces[draft.province]} 전체` : '시·도를 먼저 선택하세요'}</option>{draft.district && !selectedDistrict && <option value={draft.district}>{draft.districtName || draft.district} · 목록 대조 필요</option>}{districts.map((district) => <option key={district.id} value={district.id}>{district.name}</option>)}</select>
        <p id="catalog-district-help">세부 지역은 목록을 불러온 뒤 고르세요. 시·도를 바꾸면 세부 지역 선택이 해제됩니다. 목록 조회가 실패해도 기존 선택은 유지합니다.</p></div>
      <div className="catalog-keyword"><Button variant="secondary" disabled={loading} pending={regionsPending} onClick={() => { errors.clear(); void regionRequest.run(async (api, signal) => parseRegionCatalog(required((await api.GET('/regions', { signal })).data))) }}>{catalog ? '시·군·구 목록 새로 불러오기' : '시·군·구 목록 불러오기'}</Button>
        {regionsPending && <Button variant="secondary" onClick={regionRequest.clear}>지역 목록 조회 취소</Button>}
        {regionRequest.state.status === 'error' && <RequestError error={regionRequest.state.error} />}
        {catalog && <p>지역 목록 버전: {catalog.version}</p>}
      </div>
      <div><label htmlFor="catalog-activity">활동 유형</label><select id="catalog-activity" value={draft.activity_type} onChange={(event) => {
        const value = event.target.value
        if (value === '' || value === 'employment' || value === 'volunteering') setDraft((previous) => ({ ...previous, activity_type: value }))
      }}><option value="">활동 유형 전체</option><option value="employment">취업·공공일자리</option><option value="volunteering">봉사</option></select></div>
      <div className="actions catalog-keyword"><Button type="submit" disabled={regionsPending} pending={loading} pendingLabel="공고를 불러오고 있어요">공고 검색하기</Button>{loading && <Button variant="secondary" onClick={cancel}>조회 취소하기</Button>}</div>
    </form>
    <section className="catalog-results" ref={resultRef} tabIndex={-1} aria-label="공고 조회 결과">
      {state.status === 'idle' && <StatusNotice label="공개 탐색" title="검색 조건을 고르고 공고를 불러오세요">검색 버튼을 누르면 공개 공고 API에서 조회합니다. 현재 서버는 연결 검증 전이며, 응답이 없으면 오류를 안내합니다.</StatusNotice>}
      {state.status === 'loading' && <StatusNotice kind="loading" title="공고를 확인하고 있어요">조회가 끝나기 전에는 결과를 확정하지 않습니다. 원하면 조회를 취소할 수 있어요.</StatusNotice>}
      {state.status === 'error' && <><p className="applied-search">조회한 조건: {searchDescription(state.query)}</p><RequestError error={state.error} actions={state.error.code !== 'DAILY_QUOTA_EXCEEDED' ? <Button onClick={() => void load(state.query, state.page)}>같은 조건으로 다시 조회</Button> : undefined} /></>}
      {state.status === 'loaded' && <>
        <h2>공개 공고 검색 결과</h2><p className="applied-search">적용한 조건: {searchDescription(state.query)}</p>
        {state.query.regionVersion && <p>검색에 적용한 지역 목록 버전: {state.query.regionVersion}</p>}
        <p role="status">검색 결과 {state.result.total.toLocaleString('ko-KR')}건 · {state.result.page}페이지</p>
        <p className="catalog-note">맞춤 추천이나 자격 판정 결과가 아닙니다. 필터를 바꾼 뒤에는 검색 버튼을 눌러 주세요.</p>
        {state.result.items.length ? <ul className="opportunity-list">{state.result.items.map((item) => <OpportunityCard key={item.id} item={item} />)}</ul>
          : state.result.total === 0
            ? <StatusNotice label="검색 결과" title="이 조건의 공고가 없어요">필터를 직접 바꿔 다시 검색해 보세요. 검색 조건을 자동으로 넓히지 않았습니다.</StatusNotice>
            : <StatusNotice label="검색 결과" title="이 페이지에 표시할 공고가 없어요" actions={<Button onClick={() => void load(state.query, 1)}>첫 페이지 다시 조회</Button>}>공고 상태가 변경되었을 수 있어요. 같은 조건으로 첫 페이지를 다시 조회해 보세요.</StatusNotice>}
        {(state.result.page > 1 || state.result.page * state.result.page_size < state.result.total) && <nav className="catalog-pagination" aria-label="공고 페이지 이동">
          <Button variant="secondary" disabled={state.result.page === 1} onClick={() => void load(state.query, state.result.page - 1)}>이전 페이지</Button>
          <span>{state.result.page}페이지</span>
          <Button variant="secondary" disabled={state.result.page * state.result.page_size >= state.result.total} onClick={() => void load(state.query, state.result.page + 1)}>다음 페이지</Button>
        </nav>}
      </>}
    </section>
    <p className="catalog-note">조회·검수 정책의 실제 동작은 백엔드 연결 후 확인해야 합니다.</p>
    <Link className="text-link" to="/consent">가상 경험으로 화면 미리보기 →</Link>
  </div>
}
