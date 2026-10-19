import { useEffect, useId, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import type { createApiClient } from '../../api/client'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { provinces } from '../public-opportunities/catalog'
import { JourneyRoute } from '../journeys/JourneyRoute'
import { parseRegionCatalog } from '../regions/catalog'
import type { Region, RegionCatalog } from '../regions/catalog'
import { minimumErrors, parseExclusions, parseProfileView, parseRoles } from './server-model'
import type { DraftInput, ProfileView, Roles } from './server-model'

type Loaded = { view: ProfileView; roles: Roles | null; excludedIds: string[]; roleError: ApiError | null; message: string }
type Editor = { loaded: Loaded; draft: DraftInput; experienceKeys: string[]; dirty: boolean } | null
type Api = ReturnType<typeof createApiClient>

function ListEditor({ label, value, onChange, max = 20, length = 50 }: { label: string; value: string[]; onChange: (value: string[]) => void; max?: number; length?: number }) {
  const [raw, setRaw] = useState(value.join('\n'))
  return <TextAreaField label={label} value={raw} rows={3} maxLength={max * (length + 1)} hint={`한 줄에 하나씩 최대 ${max}개, 항목당 ${length}자. 비워 두면 없음으로 확인합니다.`} onChange={event => {
    setRaw(event.target.value); onChange(event.target.value.split('\n').map(value => value.trim()).filter(Boolean))
  }} />
}

function OptionalList({ label, value, onChange, max, length }: { label: string; value: string[] | null; onChange: (value: string[] | null) => void; max?: number; length: number }) {
  return <div className="panel"><CheckboxField label={`${label} 미확인`} checked={value === null} onChange={event => onChange(event.target.checked ? null : [])} />
    {value !== null && <ListEditor label={label} value={value} onChange={onChange} max={max} length={length} />}</div>
}

function RegionPicker({ label, value, onChange, catalog, max }: { label: string; value: Region[]; onChange: (value: Region[]) => void; catalog: RegionCatalog | null; max: number }) {
  const id = useId()
  const [province, setProvince] = useState<Region['province']>('seoul')
  const [district, setDistrict] = useState('')
  return <div><ul>{value.map((region, index) => <li key={`${region.province}:${region.district}:${index}`}>
    {provinces[region.province]} / {region.district === null ? '전체' : catalog?.provinces.find(p => p.id === region.province)?.districts.find(d => d.id === region.district)?.name ?? region.district}
    <Button variant="compact" onClick={() => onChange(value.filter((_, i) => i !== index))}>{label} {index + 1} 제거</Button></li>)}</ul>
    <label htmlFor={`${id}-province`}>{label} 시·도</label><select id={`${id}-province`} value={province} onChange={event => { setProvince(event.target.value as Region['province']); setDistrict('') }}>
      {Object.entries(provinces).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>
    <label htmlFor={`${id}-district`}>{label} 시·군·구</label><select id={`${id}-district`} value={district} onChange={event => setDistrict(event.target.value)}>
      <option value="">시·도 전체</option>{catalog?.provinces.find(p => p.id === province)?.districts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
    <Button variant="secondary" disabled={max !== 1 && value.length >= max} onClick={() => { const next = { province, district: district || null }; if (!value.some(r => r.province === next.province && r.district === next.district)) onChange(max === 1 ? [next] : [...value, next]) }}>{label} {max === 1 ? '적용' : '추가'}</Button>
    {!catalog && <p>시·군·구는 지역 목록을 불러온 뒤 고를 수 있어요.</p>}</div>
}

export function JourneyProfileRoute() {
  return <JourneyRoute page="profile">{id => <JourneyProfile key={id} journeyId={id} />}</JourneyRoute>
}

export function JourneyProfile({ journeyId }: { journeyId: string }) {
  const scope = useMemoryScope<Editor>(() => null)
  const request = useRequest<Loaded>()
  const regions = useRequest<RegionCatalog>()
  const endRequest = useRequest<boolean>()
  const { value: ending, setValue: setEnding } = useMemoryScope(() => false)
  const navigate = useNavigate()
  const [errors, setErrors] = useState<FieldError[]>([])
  const [currentYear] = useState(() => new Date().getFullYear())
  const state = scope.value
  const pending = request.state.status === 'pending' || endRequest.state.status === 'pending'
  const catalog = regions.state.status === 'success' ? regions.state.data : null
  const clearEditor = scope.clear
  useEffect(() => {
    if ([request.state, endRequest.state].some(state => state.status === 'error' && ['NOT_FOUND', 'SESSION_EXPIRED', 'UNAUTHENTICATED'].includes(state.error.code))) clearEditor()
  }, [request.state, endRequest.state, clearEditor])
  async function read(api: Api, signal: AbortSignal, message = ''): Promise<Loaded> {
    const view = parseProfileView(required((await api.GET('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, signal })).data))
    let roles: Roles | null = null, roleError: ApiError | null = null, excludedIds: string[] = []
    if (view.confirmed) {
      try {
        excludedIds = parseExclusions(required((await api.GET('/journeys/{journey_id}/role-exclusions', { params: { path: { journey_id: journeyId } }, signal })).data), view)
        roles = parseRoles(required((await api.GET('/journeys/{journey_id}/roles', { params: { path: { journey_id: journeyId } }, signal })).data), view)
        if (roles.items.some(role => role.excluded !== excludedIds.includes(role.role_id))) throw new ApiError('INVALID_RESPONSE')
      }
      catch (error) {
        if (error instanceof ApiError && ['NOT_FOUND', 'SESSION_EXPIRED', 'UNAUTHENTICATED'].includes(error.code)) throw error
        roleError = error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE')
      }
    }
    return { view, roles, excludedIds, roleError, message }
  }
  const apply = (loaded: Loaded) => { setErrors([]); scope.setValue({ loaded, draft: structuredClone(loaded.view.draft), experienceKeys: loaded.view.draft.experiences.map(e => e.id), dirty: false }) }
  const update = (draft: DraftInput, experienceKeys = state?.experienceKeys ?? []) => { if (state && !pending) { setErrors([]); scope.setValue({ ...state, draft, experienceKeys, dirty: true }) } }
  function load() { void request.run(async (api, signal) => { await api.GET('/me', { signal }); return read(api, signal) }, apply) }
  function save() {
    if (!state || pending) return
    if (state.draft.experiences.some(experience => !experience.description.trim())) {
      setErrors([{ fieldId: 'server-experiences', message: '추가한 경험의 내용을 적거나 빈 경험을 삭제해 주세요.' }]); return
    }
    // Empty optional facts remain null or [], rather than being inferred from the text.
    void request.run(async (api, signal) => {
      await api.PATCH('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, body: { draft: state.draft, base_revision: state.loaded.view.revision }, signal })
      return read(api, signal, '초안에 변경 내용을 반영했습니다. 확정은 별도로 진행해 주세요.')
    }, apply)
  }
  function confirm() {
    if (!state || pending || state.dirty) return
    const missing = minimumErrors(state.draft)
    setErrors(missing)
    if (missing.length) return
    void request.run(async (api, signal) => {
      await api.POST('/journeys/{journey_id}/profile/confirm', { params: { path: { journey_id: journeyId } }, body: { base_revision: state.loaded.view.revision }, signal })
      return read(api, signal, '프로필을 확정했습니다. 이전 추천·자격 결과는 새 확정본으로 다시 확인해 주세요.')
    }, apply)
  }
  function exclude(roleId: string, checked: boolean) {
    if (!state?.loaded.roles || pending || state.dirty) return
    const current = state.loaded.excludedIds
    setExclusions(checked ? [...current.filter(id => id !== roleId), roleId] : current.filter(id => id !== roleId))
  }
  function setExclusions(roleIds: string[]) {
    if (!state || pending || state.dirty) return
    void request.run(async (api, signal) => {
      await api.PUT('/journeys/{journey_id}/role-exclusions', { params: { path: { journey_id: journeyId } }, body: {
        role_ids: roleIds, base_revision: state.loaded.view.revision,
      }, signal })
      return read(api, signal, '역할 제외 선택을 반영했습니다. 프로필 내용은 바꾸지 않았습니다.')
    }, apply)
  }
  function endJourney() {
    request.clear(); regions.clear()
    void endRequest.run(async (api, signal) => {
      const response = await api.DELETE('/journeys/{journey_id}', { params: { path: { journey_id: journeyId } }, signal })
      if (response.response.status !== 204) throw new ApiError('INVALID_RESPONSE')
      return true
    }, () => { clearEditor(); setErrors([]); setEnding(false); navigate('/', { replace: true }) })
  }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">05 · 체험 프로필</p><h1>경험을 확인하고 확정해 주세요</h1><p>초안 반영·프로필 확정·회원 저장은 서로 다른 단계입니다. 이 화면은 임시 체험의 프로필을 편집합니다.</p></header>
    <Button pending={pending} onClick={load}>{state ? '서버 최신 내용 다시 불러오기' : '체험 프로필 불러오기'}</Button>
    {state && <Button variant="secondary" onClick={() => { request.clear(); regions.clear(); clearEditor(); setErrors([]) }}>이 화면의 입력 닫기</Button>}
    {state && <Button variant="secondary" disabled={pending} onClick={() => setEnding(true)}>종료하고 삭제</Button>}
    {ending && <section className="panel" aria-label="체험 삭제 확인"><h2>체험을 종료하고 임시 자료를 삭제할까요?</h2><p>이 체험의 초안·확정본·역할 선택과 진행 결과가 삭제됩니다. 아직 반영하지 않은 화면 입력도 사라집니다.</p>
      <Button pending={endRequest.state.status === 'pending'} onClick={endJourney}>체험 임시 자료 삭제 확인</Button><Button variant="secondary" disabled={endRequest.state.status === 'pending'} onClick={() => setEnding(false)}>계속 작성하기</Button></section>}
    {endRequest.state.status === 'error' && <RequestError error={endRequest.state.error} />}
    {state?.dirty && <p>아직 반영하지 않은 편집 내용이 있습니다. 다시 불러오면 이 편집 내용을 버리고 서버 초안을 표시합니다.</p>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    <FormErrorSummary errors={errors} />
    {state && <><p role="status">{state.loaded.message}</p>
      {state.loaded.view.confirmed && <StatusNotice title={`확정 프로필 ${state.loaded.view.confirmed.version}번`}>{state.loaded.view.has_unconfirmed_changes || state.dirty ? '수정 중입니다. 재확정 전 추천·자격 결과는 이전 확정 프로필 기준입니다.' : '사용자가 확인한 확정본입니다.'} 기존 지원서 내용은 자동으로 바뀌지 않습니다.</StatusNotice>}
      <fieldset key={state.loaded.view.revision} disabled={pending}><legend>프로필 초안 편집</legend>
        <section className="panel" id="server-experiences" tabIndex={-1}><h2>경험</h2>{state.draft.experiences.map((e, index) => <div className="panel" key={state.experienceKeys[index]}>
          <TextAreaField label={`경험 ${index + 1} 내용`} value={e.description} maxLength={1000} onChange={event => update({ ...state.draft, experiences: state.draft.experiences.map((item, i) => i === index ? { ...item, description: event.target.value } : item) })} />
          <TextAreaField label={`경험 ${index + 1} 기간 (선택)`} value={e.duration_note ?? ''} maxLength={200} onChange={event => update({ ...state.draft, experiences: state.draft.experiences.map((item, i) => i === index ? { ...item, duration_note: event.target.value || null } : item) })} />
          <ListEditor label={`경험 ${index + 1} 역량`} value={e.skill_tags} onChange={skill_tags => update({ ...state.draft, experiences: state.draft.experiences.map((item, i) => i === index ? { ...item, skill_tags } : item) })} />
          <Button variant="secondary" onClick={() => update({ ...state.draft, experiences: state.draft.experiences.filter((_, i) => i !== index) }, state.experienceKeys.filter((_, i) => i !== index))}>경험 {index + 1} 삭제</Button></div>)}
          <Button disabled={state.draft.experiences.length >= 20} onClick={() => update({ ...state.draft, experiences: [...state.draft.experiences, { id: null, description: '', duration_note: null, skill_tags: [] }] }, [...state.experienceKeys, crypto.randomUUID()])}>경험 추가</Button></section>
        <ListEditor label="전체 역량" value={state.draft.skills} max={30} onChange={skills => update({ ...state.draft, skills })} />
        <section className="panel" id="server-regions" tabIndex={-1}><h2>희망 활동 지역</h2><p>거주 자격을 판정하는 주소와는 다릅니다.</p>
          <Button variant="secondary" pending={regions.state.status === 'pending'} onClick={() => void regions.run(async (api, signal) => parseRegionCatalog(required((await api.GET('/regions', { signal })).data)))}>시·군·구 목록 불러오기</Button>
          {regions.state.status === 'error' && <RequestError error={regions.state.error} />}
          <RegionPicker label="희망 지역" value={state.draft.preferred_regions} max={10} catalog={catalog} onChange={preferred_regions => update({ ...state.draft, preferred_regions })} /></section>
        <fieldset id="server-activities" tabIndex={-1}><legend>희망 활동 유형</legend>{(['employment', 'volunteering'] as const).map(type => <CheckboxField key={type} label={type === 'employment' ? '취업·공공일자리' : '봉사'} checked={state.draft.activity_types.includes(type)} onChange={event => update({ ...state.draft, activity_types: event.target.checked ? [...state.draft.activity_types, type] : state.draft.activity_types.filter(t => t !== type) })} />)}</fieldset>
        <label htmlFor="server-paid">유급 선호</label><select id="server-paid" value={state.draft.paid_preference ?? ''} onChange={event => update({ ...state.draft, paid_preference: (event.target.value || null) as DraftInput['paid_preference'] })}><option value="">미확인</option><option value="any">무관</option><option value="paid">유급</option><option value="unpaid">무급</option></select>
        <fieldset><legend>활동 가능한 요일</legend><CheckboxField label="가능 요일 미확인" checked={state.draft.available_weekdays === null} onChange={event => update({ ...state.draft, available_weekdays: event.target.checked ? null : [] })} />
          {state.draft.available_weekdays !== null && ['월', '화', '수', '목', '금', '토', '일'].map((day, i) => <CheckboxField key={day} label={`${day}요일`} checked={state.draft.available_weekdays!.includes(i + 1)} onChange={event => update({ ...state.draft, available_weekdays: event.target.checked ? [...state.draft.available_weekdays!, i + 1] : state.draft.available_weekdays!.filter(d => d !== i + 1) })} />)}</fieldset>
        <label htmlFor="server-hours">주당 가능 시간 (비우면 미확인)</label><input id="server-hours" type="number" min={0} max={168} step="any" value={state.draft.hours_per_week ?? ''} onChange={event => update({ ...state.draft, hours_per_week: event.target.value === '' ? null : Number(event.target.value) })} />
        <TextAreaField label="이동 관련 메모 (선택)" value={state.draft.mobility_note ?? ''} maxLength={300} onChange={event => update({ ...state.draft, mobility_note: event.target.value || null })} />
        <fieldset><legend>거주 자격 대조용 지역 (선택)</legend><p>{state.draft.residence_region === null ? '거주 지역은 미확인입니다. 직접 선택해 적용한 경우에만 입력됩니다.' : '선택을 제거하면 미확인으로 돌아갑니다.'}</p>
          <RegionPicker label="거주 지역" value={state.draft.residence_region === null ? [] : [state.draft.residence_region]} max={1} catalog={catalog} onChange={values => update({ ...state.draft, residence_region: values[0] ?? null })} /></fieldset>
        <label htmlFor="server-birth">출생 연도 (비우면 미확인)</label><input id="server-birth" type="number" min={1900} max={currentYear} value={state.draft.birth_year ?? ''} onChange={event => update({ ...state.draft, birth_year: event.target.value === '' ? null : Number(event.target.value) })} />
        <OptionalList label="자격증" value={state.draft.certifications} length={100} onChange={certifications => update({ ...state.draft, certifications })} />
        <OptionalList label="수료 교육" value={state.draft.completed_courses} length={100} onChange={completed_courses => update({ ...state.draft, completed_courses })} />
        <OptionalList label="활동 수행 조건" value={state.draft.activity_constraints} max={10} length={200} onChange={activity_constraints => update({ ...state.draft, activity_constraints })} />
      </fieldset>
      <div className="actions"><Button pending={pending} disabled={!state.dirty} onClick={save}>변경 내용을 초안에 반영</Button><Button pending={pending} disabled={state.dirty} onClick={confirm}>{state.loaded.view.confirmed ? '수정한 프로필 재확정' : '이 프로필 확정'}</Button></div>
      <p>초안 반영 후 내용을 확인하고 확정해 주세요. 회원 저장은 로그인·저장 동의 연결 후 제공됩니다.</p>
      {state.loaded.view.confirmed && <section className="panel"><h2>확정 경험에서 찾은 역할</h2><p>확정 프로필 {state.loaded.view.confirmed.version}번의 실제 경험 근거입니다. 역할은 활동 자격이나 선발을 보장하지 않습니다.</p>
        <p>현재 제외한 역할: {state.loaded.excludedIds.length}개. 표시된 후보에 없는 역할도 포함합니다.</p>
        <Button variant="secondary" disabled={pending || state.dirty || state.loaded.excludedIds.length === 0 || !!state.loaded.roleError} onClick={() => setExclusions([])}>역할 제외 모두 복원</Button>
        {state.loaded.roleError && <RequestError error={state.loaded.roleError} />}
        {state.loaded.roles?.items.map(role => <article key={role.role_id}><h3>{role.name}</h3><p className="user-text">{role.description}</p><ul>{role.evidence.map((e, i) => <li key={`${e.experience_id}:${i}`} className="user-text">확정 경험 근거: {e.skill_tags.join(', ')}</li>)}</ul>
          <CheckboxField label={`${role.name} 추천에서 제외`} checked={role.excluded} disabled={pending || state.dirty || !role.excluded && state.loaded.excludedIds.length >= 50} onChange={event => exclude(role.role_id, event.target.checked)} /></article>)}
        {state.loaded.roles?.items.length === 0 && <p>연결할 경험 근거가 있는 역할이 아직 없습니다. <Link to="/opportunities">일반 공개 공고 살펴보기</Link></p>}
      </section>}
    </>}
    {state?.loaded.view.confirmed && <p><Link to={`/journeys/${journeyId}/recommendations`}>확정 경험으로 추천 확인하기</Link></p>}
    <p><Link to={`/journeys/${journeyId}/conversation`}>경험 이야기로 이동</Link></p>
    <p><Link to="/opportunities">공개 공고 살펴보기</Link></p>
  </div>
}
