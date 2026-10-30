import { UnsavedChangesGuard } from '../../ui/UnsavedChangesGuard'
import { useEntryAction } from '../../state/useEntryAction'
import { useEffect, useId, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { SavedProfileSave } from '../account/SavedProfileSave'
import { BeginSave } from '../account/BeginSave'
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
import { ServicePage } from '../../ui/ServicePage'
import { ProfileSummary } from './ProfileSummary'
import type { ProfileField } from './ProfileSummary'
import './profile-task.css'

function profileCopy(draft: DraftInput, catalog: RegionCatalog | null): string {
  const items = (value: string[] | null) => value === null ? '미확인' : value.join(', ') || '없음'
  const region = (value: Region) => `${provinces[value.province]} ${value.district === null ? '전체' : catalog?.provinces.find(item => item.id === value.province)?.districts.find(item => item.id === value.district)?.name ?? value.district}`
  return [
    '경험', ...draft.experiences.map(item => `${item.description}\n기간: ${item.duration_note ?? '미확인'}\n기술: ${items(item.skill_tags)}`),
    `기술: ${items(draft.skills)}`, `희망 지역: ${draft.preferred_regions.map(region).join(', ')}`,
    `희망 활동: ${draft.activity_types.map(item => item === 'employment' ? '취업 및 공공일자리' : '봉사').join(', ')}`,
    `보수 선호: ${draft.paid_preference === null ? '미확인' : { paid: '유급', unpaid: '무급', any: '무관' }[draft.paid_preference]}`,
    `가능 요일: ${draft.available_weekdays === null ? '미확인' : draft.available_weekdays.map(day => ['월', '화', '수', '목', '금', '토', '일'][day - 1]).join(', ') || '없음'}`,
    `주당 시간: ${draft.hours_per_week ?? '미확인'}`, `이동 메모: ${draft.mobility_note ?? '미확인'}`,
    `거주 지역: ${draft.residence_region === null ? '미확인' : region(draft.residence_region)}`, `출생 연도: ${draft.birth_year ?? '미확인'}`,
    `자격증: ${items(draft.certifications)}`, `수료 교육: ${items(draft.completed_courses)}`, `활동 수행 조건: ${items(draft.activity_constraints)}`,
  ].join('\n\n')
}

type Loaded = { view: ProfileView; roles: Roles | null; excludedIds: string[]; roleError: ApiError | null; message: string }
type Editor = { loaded: Loaded; draft: DraftInput; experienceKeys: string[]; editorKey: number; dirty: boolean } | null
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
  return <div className="region-picker"><ul>{value.map((region, index) => <li key={`${region.province}:${region.district}:${index}`}>
    {provinces[region.province]} / {region.district === null ? '전체' : catalog?.provinces.find(p => p.id === region.province)?.districts.find(d => d.id === region.district)?.name ?? region.district}
    <Button variant="compact" onClick={() => onChange(value.filter((_, i) => i !== index))}>{label} {index + 1} 제거</Button></li>)}</ul>
    <label htmlFor={`${id}-province`}>{label} 시도</label><select id={`${id}-province`} value={province} onChange={event => { setProvince(event.target.value as Region['province']); setDistrict('') }}>
      {Object.entries(provinces).map(([id, name]) => <option key={id} value={id}>{name}</option>)}</select>
    <label htmlFor={`${id}-district`}>{label} 시군구</label><select id={`${id}-district`} value={district} onChange={event => setDistrict(event.target.value)}>
      <option value="">시도 전체</option>{catalog?.provinces.find(p => p.id === province)?.districts.map(d => <option key={d.id} value={d.id}>{d.name}</option>)}</select>
    <Button variant="secondary" disabled={max !== 1 && value.length >= max} onClick={() => { const next = { province, district: district || null }; if (!value.some(r => r.province === next.province && r.district === next.district)) onChange(max === 1 ? [next] : [...value, next]) }}>{label} {max === 1 ? '적용' : '추가'}</Button>
    {!catalog && <p>시군구는 지역 목록을 불러온 뒤 고를 수 있어요.</p>}</div>
}

export function JourneyProfileRoute() {
  return <JourneyRoute page="profile">{id => <JourneyProfile key={id} journeyId={id} autoLoad />}</JourneyRoute>
}

export function JourneyProfile({ journeyId, autoLoad = false }: { journeyId: string; autoLoad?: boolean }) {
  const location = useLocation()
  const savedBase: unknown = location.state?.savedProfileBaseVersion
  const scope = useMemoryScope<Editor>(() => null)
  const { value: editing, setValue: setEditing } = useMemoryScope(() => false)
  const { value: editingField, setValue: setEditingField } = useMemoryScope<ProfileField | null>(() => null)
  const request = useRequest<Loaded>()
  const regions = useRequest<RegionCatalog>()
  const { value: confirmingReload, setValue: setConfirmingReload } = useMemoryScope(() => false)
  const reloadHeading = useRef<HTMLHeadingElement>(null)
  const editorGeneration = useRef(0)
  const lastEditingField = useRef<ProfileField>('experiences')
  const wasEditing = useRef(false)
  const [errors, setErrors] = useState<FieldError[]>([])
  const [currentYear] = useState(() => new Date().getFullYear())
  const state = scope.value
  const pending = request.state.status === 'pending'
  const catalog = regions.state.status === 'success' ? regions.state.data : null
  const clearEditor = scope.clear
  const saving = useMemoryScope(() => false)
  useEffect(() => {
    if (editing) document.querySelector<HTMLElement>('#profile-editor textarea, #profile-editor input:not([type="checkbox"]), #profile-editor select, #profile-editor button')?.focus()
    else if (wasEditing.current) document.getElementById(`profile-edit-${lastEditingField.current}`)?.focus()
    wasEditing.current = editing
  }, [editing])
  useEffect(() => { if (confirmingReload) reloadHeading.current?.focus() }, [confirmingReload])
  // 지역을 고치는 편집을 열면 시군구 목록을 바로 불러온다. 실패하면 아래 버튼으로 다시 불러온다.
  const loadRegions = () => void regions.run(async (api, signal) => parseRegionCatalog(required((await api.GET('/regions', { signal })).data)))
  useEntryAction(loadRegions, editing && (editingField === 'preferred_regions' || editingField === 'additional') && regions.state.status === 'idle', editingField ?? '')
  useEffect(() => {
    if (request.state.status === 'error' && ['NOT_FOUND', 'SESSION_EXPIRED', 'UNAUTHENTICATED'].includes(request.state.error.code)) clearEditor()
  }, [request.state, clearEditor])
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
  const apply = (loaded: Loaded) => { setEditing(false); setEditingField(null); setErrors([]); setConfirmingReload(false); scope.setValue({ loaded, draft: structuredClone(loaded.view.draft), experienceKeys: loaded.view.draft.experiences.map(e => e.id), editorKey: ++editorGeneration.current, dirty: false }) }
  const editField = (field: ProfileField) => { lastEditingField.current = field; setEditingField(field); setEditing(true) }
  const update = (draft: DraftInput, experienceKeys = state?.experienceKeys ?? []) => { if (state && !pending) { setErrors([]); scope.setValue({ ...state, draft, experienceKeys, dirty: true }) } }
  function load() { void request.run(async (api, signal) => { await api.GET('/me', { signal }); return read(api, signal) }, apply) }
  // The request owns its cancellation scope; repeat safely after StrictMode remount.
  useEntryAction(load, autoLoad, journeyId)
  function save() {
    if (!state || pending) return
    const emptyExperience = state.draft.experiences.findIndex(experience => !experience.description.trim())
    if (emptyExperience !== -1) {
      setErrors([{ fieldId: `server-experience-${emptyExperience}`, message: `경험 ${emptyExperience + 1}의 내용을 적거나 빈 경험을 삭제해 주세요.` }]); return
    }
    // Empty optional facts remain null or [], rather than being inferred from the text.
    void request.run(async (api, signal) => {
      await api.PATCH('/journeys/{journey_id}/profile', { params: { path: { journey_id: journeyId } }, body: { draft: state.draft, base_revision: state.loaded.view.revision }, signal })
      return read(api, signal, '수정한 내용을 확인해 주세요.')
    }, apply)
  }
  function confirm() {
    if (!state || pending || state.dirty) return
    const missing = minimumErrors(state.draft)
    setErrors(missing)
    if (missing.length) { setEditing(true); return }
    void request.run(async (api, signal) => {
      await api.POST('/journeys/{journey_id}/profile/confirm', { params: { path: { journey_id: journeyId } }, body: { base_revision: state.loaded.view.revision }, signal })
      return read(api, signal, '경험을 확인했어요.')
    }, apply)
  }
  return <ServicePage title="말씀하신 내용을 정리해봤어요" className="profile-task"><UnsavedChangesGuard dirty={!!state?.dirty} />
    {!state && <Button id="profile-reload" pending={pending} onClick={load}>정리한 경험 불러오기</Button>}
    {confirmingReload && state && <section className="panel" aria-labelledby="reload-profile-heading"><h2 id="reload-profile-heading" className="result-heading" ref={reloadHeading} tabIndex={-1}>수정을 취소할까요?</h2><p>아직 반영하지 않은 수정 내용이 사라집니다.</p><div className="actions"><Button disabled={pending} onClick={() => { setConfirmingReload(false); load() }}>수정 내용 버리기</Button><Button variant="secondary" onClick={() => { setConfirmingReload(false); document.getElementById('profile-editor')?.focus() }}>계속 수정하기</Button></div></section>}
    {request.state.status === 'error' && <RequestError error={request.state.error} />}
    <FormErrorSummary errors={errors} />
    {state && <><p role="status">{state.loaded.message}</p>
      <div className="profile-review-layout"><div className="profile-review-content" role="region" aria-label="정리한 경험과 활동" tabIndex={0}>
      <ProfileSummary content={state.draft} catalog={catalog} showAdditional onEdit={editField} editDisabled={pending} hiddenField={editing ? editingField : null} />
      </div><aside className="profile-decision" aria-label="경험 확인과 확정">
      <div className="actions">
        {editing ? <><Button pending={pending} disabled={!state.dirty} onClick={save}>변경 내용 반영하기</Button><Button variant="secondary" disabled={pending} onClick={() => { if (state.dirty) setConfirmingReload(true); else { setEditing(false); setEditingField(null) } }}>수정 취소</Button></>
          : <>
            {state.loaded.view.confirmed && !state.dirty && !state.loaded.view.has_unconfirmed_changes && <Button variant="secondary" onClick={() => saving.setValue(previous => !previous)}>이대로 저장하기</Button>}
            {(!state.loaded.view.confirmed || state.loaded.view.has_unconfirmed_changes || state.dirty) && <Button pending={pending} disabled={state.dirty} onClick={confirm}>이 내용으로 확정</Button>}
            {state.loaded.view.confirmed && !state.dirty && !state.loaded.view.has_unconfirmed_changes && <Link className="button primary" to={`/journeys/${journeyId}/recommendations`}>추천 공고 확인하기</Link>}
          </>}
      </div>
      </aside></div>
      {state.loaded.view.confirmed && (state.loaded.view.has_unconfirmed_changes || state.dirty) && <StatusNotice title="수정한 내용을 다시 확인해 주세요">다시 확정하기 전에는 이전 확정본으로 추천합니다. 기존 지원서 내용은 자동으로 바뀌지 않습니다.</StatusNotice>}
      {editing && <fieldset className="profile-editor" id="profile-editor" tabIndex={-1} key={`${state.editorKey}-${editingField}`} disabled={pending}><legend>수정할 내용을 입력해 주세요</legend>
        {editingField === 'experiences' && <section className="panel" id="server-experiences" tabIndex={-1}>{state.draft.experiences.map((e, index) => <div className="panel" key={state.experienceKeys[index]}>
          <TextAreaField id={`server-experience-${index}`} label={`경험 ${index + 1} 내용`} value={e.description} maxLength={1000} error={errors.find(error => error.fieldId === `server-experience-${index}`)?.message} onChange={event => update({ ...state.draft, experiences: state.draft.experiences.map((item, i) => i === index ? { ...item, description: event.target.value } : item) })} />
          <details className="disclosure"><summary>기간과 역량 수정</summary><TextAreaField label={`경험 ${index + 1} 기간 (선택)`} value={e.duration_note ?? ''} maxLength={200} onChange={event => update({ ...state.draft, experiences: state.draft.experiences.map((item, i) => i === index ? { ...item, duration_note: event.target.value || null } : item) })} />
          <ListEditor label={`경험 ${index + 1} 역량`} value={e.skill_tags} onChange={skill_tags => update({ ...state.draft, experiences: state.draft.experiences.map((item, i) => i === index ? { ...item, skill_tags } : item) })} />
          <Button variant="secondary" onClick={() => update({ ...state.draft, experiences: state.draft.experiences.filter((_, i) => i !== index) }, state.experienceKeys.filter((_, i) => i !== index))}>경험 {index + 1} 삭제</Button></details></div>)}
          <Button variant="secondary" disabled={state.draft.experiences.length >= 20} onClick={() => update({ ...state.draft, experiences: [...state.draft.experiences, { id: null, description: '', duration_note: null, skill_tags: [] }] }, [...state.experienceKeys, crypto.randomUUID()])}>경험 추가</Button></section>}
        {editingField === 'preferred_regions' && <section className="panel" id="server-regions" tabIndex={-1}>
          <Button variant="secondary" pending={regions.state.status === 'pending'} onClick={loadRegions}>시군구 목록 불러오기</Button>
          {regions.state.status === 'error' && <RequestError error={regions.state.error} />}
              <RegionPicker label="희망 지역" value={state.draft.preferred_regions} max={10} catalog={catalog} onChange={preferred_regions => update({ ...state.draft, preferred_regions })} /></section>}
        {editingField === 'activity_types' && <fieldset id="server-activities" tabIndex={-1}><legend>활동 유형</legend>{(['employment', 'volunteering'] as const).map(type => <CheckboxField key={type} label={type === 'employment' ? '취업 및 공공일자리' : '봉사'} checked={state.draft.activity_types.includes(type)} onChange={event => update({ ...state.draft, activity_types: event.target.checked ? [...state.draft.activity_types, type] : state.draft.activity_types.filter(t => t !== type) })} />)}</fieldset>}
        {editingField === 'additional' && <div className="profile-optional"><ListEditor label="전체 역량" value={state.draft.skills} max={30} onChange={skills => update({ ...state.draft, skills })} />
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
        </div>}
      </fieldset>}
      {!editing && state.loaded.view.confirmed && !state.dirty && !state.loaded.view.has_unconfirmed_changes && saving.value && <BeginSave key={state.loaded.view.confirmed.version} journeyId={journeyId} embedded />}
      {typeof savedBase === 'number' && Number.isSafeInteger(savedBase) && savedBase >= 1 && state.loaded.view.confirmed && <SavedProfileSave
        journeyId={journeyId} version={state.loaded.view.confirmed.version} baseVersion={savedBase}
        disabled={pending || state.dirty || state.loaded.view.has_unconfirmed_changes}
        copyText={profileCopy(state.draft, catalog)} onUnavailable={clearEditor} />}
    </>}
    {!state && <nav className="context-links" aria-label="관련 화면"><Link to={`/journeys/${journeyId}/conversation`}>경험 이야기로 이동</Link><Link to="/opportunities">공개 공고 살펴보기</Link></nav>}
  </ServicePage>
}
