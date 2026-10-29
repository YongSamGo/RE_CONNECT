import type { components } from '../../api/schema'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { provinces } from '../public-opportunities/catalog'
import { parseRequirement, parseRequirements } from './editor'

type Requirement = components['schemas']['Requirement']
type Region = components['schemas']['Region']
type Draft = { item: Requirement; text: string; regions: Region[]; verified: boolean }
type State = { draft: Draft | null; remove: string | null; errors: FieldError[] }
const requirementFields = { age: '만 나이', residence_region: '거주 지역', certification: '자격증', completed_course: '이수 교육', weekday: '참여 요일', hours_per_week: '주당 시간', other: '해석 전 원문' }
const operators = { gte: '이상', lte: '이하', between: '범위 (양 끝 포함)', in: '목록에 포함', has_all: '모두 보유·이수', has_any: '하나 이상 보유·이수', includes_all: '모든 요일 참여', includes_any: '하나 이상 요일 참여' }
const allowed: Record<Requirement['field'], NonNullable<Requirement['operator']>[]> = { age: ['gte', 'lte', 'between'], residence_region: ['in'], certification: ['has_all', 'has_any'], completed_course: ['has_all', 'has_any'], weekday: ['includes_all', 'includes_any'], hours_per_week: ['gte', 'lte'], other: [] }
function draftFor(item: Requirement): Draft {
  return { item, verified: false, regions: item.field === 'residence_region' ? item.value as Region[] : [], text: item.value === null ? '' : Array.isArray(item.value) ? item.value.join('\n') : String(item.value) }
}
function requirementDescription(item: Requirement): string {
  const value = item.field === 'residence_region' ? (item.value as Region[]).map((region) => `${provinces[region.province]}${region.district ? ` / ${region.district}` : ' 전체'}`).join(', ')
    : Array.isArray(item.value) ? item.value.join(', ') : item.value ?? '미해석'
  return `${requirementFields[item.field]} · ${item.operator ? operators[item.operator] : '판정하지 않음'} · ${value} · 기준일 ${item.reference_date ?? '미확인'} · ${item.clarity === 'clear' ? '원문 대조됨' : '확인 필요'}`
}

export function RequirementSummary({ items }: { items: Requirement[] }) {
  const groups = [...new Set(items.flatMap((item) => item.group_id ? [item.group_id] : []))]
  return items.length === 0 ? <p>명시된 필수조건 없음</p> : <ol>{items.map((item) => <li key={item.id}><p className="user-text">{item.source_evidence}</p><p>{requirementDescription(item)}</p><p>{item.group_id ? `묶음 ${groups.indexOf(item.group_id) + 1} · ${item.group_operator === 'and' ? '모두 충족' : '하나 이상 충족'}` : '독립 필수조건'}</p></li>)}</ol>
}

/** Edits are staged explicitly; parent submission stays disabled until applied or cancelled. */
export function RequirementEditor({ items, disabled, onChange, onEditingChange }: { items: Requirement[]; disabled: boolean; onChange: (items: Requirement[]) => void; onEditingChange: (editing: boolean) => void }) {
  const scope = useMemoryScope<State>(() => ({ draft: null, remove: null, errors: [] }))
  const { draft, remove, errors } = scope.value
  const groups = [...new Set(items.flatMap((item) => item.group_id ? [item.group_id] : []))]
  function begin(item: Requirement) {
    if (disabled) return
    scope.setValue({ draft: draftFor(item), remove: null, errors: [] }); onEditingChange(true)
  }
  function close() { scope.clear(); onEditingChange(false) }
  function change(patch: Partial<Draft>) {
    if (!draft || disabled) return
    scope.setValue({ draft: { ...draft, ...patch, verified: false }, remove: null, errors: [] })
  }
  function editItem(patch: Partial<Requirement>) { if (draft) change({ item: { ...draft.item, ...patch } }) }
  function apply() {
    if (!draft || disabled) return
    const item = draft.item
    let value: Requirement['value'] = null
    try {
      if (item.field === 'residence_region') value = draft.regions
      else if (item.field !== 'other' && item.value !== null && draft.text === draftFor(item).text) value = item.value
      else if (item.field !== 'other') {
        const parts = draft.text.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
        if (!parts.length) throw new Error()
        if (item.field === 'certification' || item.field === 'completed_course') value = parts
        else if (item.operator === 'between' || item.field === 'weekday') value = parts.map(Number)
        else { if (parts.length !== 1) throw new Error(); value = Number(parts[0]) }
      }
      const edited = parseRequirement({ ...item, value, clarity: item.field !== 'other' && draft.verified ? 'clear' : 'needs_review' })
      // Changing group logic affects every member, and requires their review again.
      const original = items.find((entry) => entry.id === edited.id)
      const moved = original?.group_id !== edited.group_id
      let next = items.map((entry) => {
        if (entry.id === edited.id) return edited
        const newGroup = entry.group_id !== null && entry.group_id === edited.group_id
        const oldGroup = entry.group_id !== null && entry.group_id === original?.group_id
        if (newGroup && entry.group_operator !== edited.group_operator) return { ...entry, group_operator: edited.group_operator, clarity: 'needs_review' as const }
        return moved && (newGroup || oldGroup) ? { ...entry, clarity: 'needs_review' as const } : entry
      })
      if (!items.some((entry) => entry.id === edited.id)) next = [...next, edited]
      onChange(parseRequirements(next)); close()
    } catch {
      const invalidDistrict = draft.regions.findIndex(region => region.district !== null && !/^[a-z0-9_]{2,40}$/.test(region.district))
      const fieldId = !item.source_evidence.trim() ? 'requirement-source' : item.field === 'residence_region' ? (invalidDistrict >= 0 ? `requirement-district-${invalidDistrict}` : 'requirement-region-add') : item.field === 'other' ? 'requirement-source' : 'requirement-value'
      const message = invalidDistrict >= 0 && fieldId.startsWith('requirement-district-') ? '시·군·구 코드는 영문 소문자, 숫자, 밑줄로 2~40자 입력해 주세요.' : '조건 원문·값·기준일을 확인해 주세요. 나이 범위는 작은 값부터 2개, 요일은 1~7, 목록은 한 줄에 하나씩 입력하세요.'
      scope.setValue((previous) => ({ ...previous, errors: [{ fieldId, message }] }))
    }
  }
  return <section aria-label="필수조건 편집">
    <h3>필수조건</h3><p>독립 조건과 각 묶음은 모두 충족해야 합니다. 같은 묶음 안에서만 모두/하나 이상 관계를 적용합니다. 중첩되거나 해석하기 어려운 조건은 원문으로 남겨 주세요.</p>
    <ol className="requirement-list">{items.map((item, index) => <li key={item.id}>
      <p className="user-text">{item.source_evidence}</p><p>{requirementDescription(item)}</p>
      <p>{item.group_id ? `묶음 ${groups.indexOf(item.group_id) + 1} · ${item.group_operator === 'and' ? '모두 충족' : '하나 이상 충족'}` : '독립 필수조건'}</p>
      <div className="actions"><Button variant="secondary" disabled={disabled || !!draft || !!remove} onClick={() => begin(item)}>조건 {index + 1} 편집</Button>
      <Button variant="secondary" disabled={disabled || !!draft || !!remove} onClick={() => { scope.setValue({ draft: null, remove: item.id, errors: [] }); onEditingChange(true) }}>조건 {index + 1} 삭제 검토</Button></div>
    </li>)}</ol>
    <Button variant="secondary" disabled={disabled || !!draft || !!remove || items.length >= 30} onClick={() => begin({ id: crypto.randomUUID(), field: 'other', operator: null, value: null, group_id: null, group_operator: null, reference_date: null, source_evidence: '', clarity: 'needs_review' })}>조건 하나 추가</Button>
    {remove && <div className="panel"><p className="user-text">삭제할 조건: {items.find((item) => item.id === remove)?.source_evidence}</p><p>삭제하면 이 필수조건이 판정 대상에서 빠집니다. 같은 묶음의 남은 조건은 확인 필요로 바뀝니다. 원문을 대조한 뒤 결정하세요.</p><Button disabled={disabled} onClick={() => { const group = items.find((item) => item.id === remove)?.group_id; onChange(items.filter((item) => item.id !== remove).map((item) => group && item.group_id === group ? { ...item, clarity: 'needs_review' } : item)); close() }}>원문 대조 후 조건 삭제</Button><Button variant="secondary" disabled={disabled} onClick={close}>조건 삭제 취소</Button></div>}
    {draft && <fieldset disabled={disabled}><legend>조건 원문과 판정 규칙 편집</legend>
      <FormErrorSummary errors={errors} />
      <TextAreaField id="requirement-source" label="조건 원문 (필수)" value={draft.item.source_evidence} maxLength={1000} error={errors.find((error) => error.fieldId === 'requirement-source')?.message} onChange={(event) => editItem({ source_evidence: event.target.value })} />
      <label htmlFor="requirement-field">조건 종류</label><select id="requirement-field" value={draft.item.field} onChange={(event) => {
        const field = event.target.value as Requirement['field']
        change({ item: { ...draft.item, field, operator: allowed[field][0] ?? null, value: null }, text: '', regions: [] })
      }}>{Object.entries(requirementFields).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
      {draft.item.field !== 'other' && <><label htmlFor="requirement-operator">조건 비교 방법</label><select id="requirement-operator" value={draft.item.operator ?? ''} onChange={(event) => editItem({ operator: event.target.value as Requirement['operator'] })}>{allowed[draft.item.field].map((operator) => <option key={operator} value={operator}>{operators[operator]}</option>)}</select>
        {draft.item.field === 'residence_region' ? <>
          <p>시·도와 시·군·구 코드를 원문 및 지역 목록과 대조하세요. 시·군·구를 비우면 해당 시·도 전체입니다.</p>
          {draft.regions.map((region, index) => <div key={index}>
            <label htmlFor={`requirement-province-${index}`}>조건 지역 {index + 1} 시·도</label><select id={`requirement-province-${index}`} value={region.province} onChange={(event) => change({ regions: draft.regions.map((entry, i) => i === index ? { province: event.target.value as Region['province'], district: null } : entry) })}>{Object.entries(provinces).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
            <label htmlFor={`requirement-district-${index}`}>조건 지역 {index + 1} 시·군·구 코드</label><input id={`requirement-district-${index}`} value={region.district ?? ''} maxLength={40} aria-invalid={errors.some(error => error.fieldId === `requirement-district-${index}`) || undefined} aria-describedby={errors.some(error => error.fieldId === `requirement-district-${index}`) ? `requirement-district-${index}-error` : undefined} onChange={(event) => change({ regions: draft.regions.map((entry, i) => i === index ? { ...entry, district: event.target.value || null } : entry) })} />
            {errors.some(error => error.fieldId === `requirement-district-${index}`) && <p className="field-error" id={`requirement-district-${index}-error`}>{errors.find(error => error.fieldId === `requirement-district-${index}`)?.message}</p>}
            <Button variant="secondary" onClick={() => change({ regions: draft.regions.filter((_, i) => i !== index) })}>조건 지역 {index + 1} 제거</Button>
          </div>)}
          <Button id="requirement-region-add" variant="secondary" disabled={draft.regions.length >= 30} aria-describedby={errors.some((error) => error.fieldId === 'requirement-region-add') ? 'requirement-region-error' : undefined} onClick={() => change({ regions: [...draft.regions, { province: 'seoul', district: null }] })}>조건 지역 추가</Button>
          {errors.some((error) => error.fieldId === 'requirement-region-add') && <p className="field-error" id="requirement-region-error">{errors.find((error) => error.fieldId === 'requirement-region-add')?.message}</p>}
        </> : <TextAreaField id="requirement-value" label="조건 값 (한 줄에 하나)" value={draft.text} maxLength={2019} hint="나이 범위는 최솟값과 최댓값을 두 줄로, 요일은 월=1부터 일=7로 입력하세요. 숫자 0도 값입니다." error={errors.find((error) => error.fieldId === 'requirement-value')?.message} onChange={(event) => change({ text: event.target.value })} />}
      </>}
      <label htmlFor="requirement-date">조건 판정 기준일 (미확인은 비워두기)</label><input id="requirement-date" type="date" value={draft.item.reference_date ?? ''} onChange={(event) => editItem({ reference_date: event.target.value || null })} />
      <p id="requirement-group-help">묶음에 조건을 넣거나 빼면 영향을 받는 다른 조건도 확인 필요로 바뀝니다.</p><label htmlFor="requirement-group">조건 묶음</label><select id="requirement-group" aria-describedby="requirement-group-help" value={draft.item.group_id ?? ''} onChange={(event) => {
        const value = event.target.value
        editItem({ group_id: value === 'new' ? crypto.randomUUID() : value || null, group_operator: value ? items.find((item) => item.group_id === value)?.group_operator ?? 'and' : null })
      }}><option value="">독립 필수조건</option>{[...new Set([...groups, ...(draft.item.group_id ? [draft.item.group_id] : [])])].map((id, index) => <option key={id} value={id}>묶음 {index + 1}</option>)}<option value="new">새 묶음 만들기</option></select>
      {draft.item.group_id && <><label htmlFor="requirement-group-operator">묶음 충족 방법</label><select id="requirement-group-operator" value={draft.item.group_operator ?? 'and'} onChange={(event) => editItem({ group_operator: event.target.value as 'and' | 'or' })}><option value="and">모두 충족</option><option value="or">하나 이상 충족</option></select><p>묶음 충족 방법을 바꾸면 같은 묶음의 모든 조건에 적용하고 다른 조건의 원문 대조 표시를 해제합니다.</p></>}
      {draft.item.field !== 'other' && <CheckboxField label="이 조건의 원문·규칙·묶음·기준일을 대조했어요." checked={draft.verified} onChange={(event) => scope.setValue((previous) => ({ ...previous, draft: previous.draft ? { ...previous.draft, verified: event.target.checked } : null }))} />}
      <p>대조 표시가 없거나 해석 전 원문이면 확인 필요로 유지합니다. 아래 적용은 작성 중인 화면에만 반영하며 서버 저장은 별도입니다.</p>
      <div className="actions"><Button onClick={apply}>조건 편집 적용</Button><Button variant="secondary" onClick={close}>조건 편집 취소</Button></div>
    </fieldset>}
  </section>
}
