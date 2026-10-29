import { useEffect, useRef } from 'react'
import type { InputHTMLAttributes } from 'react'
import type { components } from '../../api/schema'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { required, useRequest } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { provinces } from '../public-opportunities/catalog'
import { koreaDateTimeInput } from './audit'
import { emptyOpportunity, isHttpsReference, manualSources, opportunityChanges, parseEditable, parseOpportunityInput, quoteFields, quoteLabels } from './editor'
import type { ManualSource, OpportunityInput } from './editor'
import { RequirementEditor } from './RequirementEditor'

type State = { input: OpportunityInput | null; original: OpportunityInput | null; version: number | null; hours: string; at: string; documents: string; additions: components['schemas']['Requirement'][]; extraText: string; checked: boolean; checkedAt: string | null; source: ManualSource; quotes: Record<string, string>; noRequirements: boolean; editing: boolean; errors: FieldError[] }
function initial(input: OpportunityInput | null, version: number | null = null): State {
  return { input, original: version === null ? null : input, version, hours: String(input?.hours_per_week ?? ''), at: input?.deadline_at ? koreaDateTimeInput(Date.parse(input.deadline_at)) : '', documents: input?.required_documents?.join('\n') ?? '', additions: [], extraText: '', checked: false, checkedAt: null, source: 'manual_volunteer', quotes: {}, noRequirements: !!version && input?.requirements.length === 0, editing: false, errors: [] }
}
function InputField({ label, error, id, ...props }: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string; id: string }) {
  return <div className="form-field"><label htmlFor={id}>{label}</label><input {...props} id={id} aria-invalid={error ? true : undefined} aria-describedby={error ? `${id}-error` : undefined} />{error && <p className="field-error" id={`${id}-error`}>{error}</p>}</div>
}
const lines = (value: string) => value.split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
const triValue = (value: boolean | null) => value === null ? '' : value ? 'yes' : 'no'
const tri = (value: string) => value === '' ? null : value === 'yes'

export function OpportunityEditor({ target, onBack }: { target?: { id: string; version: number }; onBack: () => void }) {
  const headingRef = useRef<HTMLHeadingElement>(null)
  useEffect(() => { headingRef.current?.focus() }, [])
  const form = useMemoryScope<State>(() => initial(target ? null : emptyOpportunity()))
  const load = useRequest<ReturnType<typeof parseEditable>>()
  const save = useRequest<{ id: string; version: number }>()
  const attempt = useRef<{ fingerprint: string; key: string } | null>(null)
  useEffect(() => {
    const clear = () => { attempt.current = null }
    const restore = (event: PageTransitionEvent) => { if (event.persisted) clear() }
    window.addEventListener('pagehide', clear)
    window.addEventListener('pageshow', restore)
    return () => { clear(); window.removeEventListener('pagehide', clear); window.removeEventListener('pageshow', restore) }
  }, [])
  const state = form.value
  const input = state.input
  const pending = load.state.status === 'pending' || save.state.status === 'pending'
  const stale = save.state.status === 'error' && save.state.error.code === 'VERSION_CONFLICT'
  const locked = pending || save.state.status === 'success' || stale
  const error = (id: string) => state.errors.find((item) => item.fieldId === id)?.message
  function update<K extends keyof OpportunityInput>(field: K, value: OpportunityInput[K]) {
    if (locked) return
    save.clear()
    form.setValue((previous) => ({ ...previous, input: previous.input ? { ...previous.input, [field]: value } : null, checked: false, errors: [] }))
  }
  function updateRaw(change: Partial<State>) {
    if (locked) return
    save.clear(); form.setValue((previous) => ({ ...previous, ...change, checked: false, errors: [] }))
  }
  function reload() {
    if (!target || pending) return
    form.clear(); save.clear()
    void load.run(async (api, signal) => parseEditable(required((await api.GET('/admin/opportunities/{opportunity_id}', { signal, params: { path: { opportunity_id: target.id } } })).data), target), (result) => form.setValue(initial(result.input, result.version)))
  }
  async function submit() {
    if (!input || locked || state.editing) return
    const errors: FieldError[] = []
    const add = (fieldId: string, message: string) => errors.push({ fieldId, message })
    if (!input.title.trim() || input.title.length > 200) add('editor-title', '공고 제목을 200자 이내로 적어 주세요.')
    if (!input.organization_name.trim() || input.organization_name.length > 200) add('editor-organization', '기관명을 200자 이내로 적어 주세요.')
    if (!isHttpsReference(input.source_url)) add('editor-source', '공식 원문의 올바른 HTTPS 주소를 적어 주세요.')
    if (!isHttpsReference(input.application_url)) add('editor-application', '공식 접수 안내의 올바른 HTTPS 주소를 적어 주세요.')
    if (!input.application_instructions.trim()) add('editor-instructions', '공식 접수 방법을 적어 주세요.')
    const hours = state.hours === '' ? null : Number(state.hours)
    if (hours !== null && (!Number.isFinite(hours) || hours < 0 || hours > 168)) add('editor-hours', '주당 시간은 0~168 사이로 적거나 비워 주세요.')
    if (input.requirements.length + state.additions.length === 0 && !state.noRequirements) add('editor-no-requirements', '원문 조건을 적거나, 원문에 필수조건이 없는지 확인해 주세요.')
    if (input.requirements.length + state.additions.length > 30 || state.additions.some((value) => value.source_evidence.length > 1000)) add('editor-extra', '추가 조건은 한 줄 1,000자 이내, 기존 조건과 합계 30개 이내로 적어 주세요.')
    const documents = input.required_documents === null ? null : state.documents === input.required_documents.join('\n') ? input.required_documents : lines(state.documents)
    if (documents && (documents.length > 20 || documents.some((value) => value.length > 200))) add('editor-documents', '서류는 한 줄 200자 이내, 최대 20개로 적어 주세요.')
    if (!state.checked) add('editor-checked', '공식 원문과 입력 내용을 확인해 주세요.')
    if (errors.length) { form.setValue((previous) => ({ ...previous, errors })); return }
    const unchangedTime = state.original?.deadline_at && state.at === koreaDateTimeInput(Date.parse(state.original.deadline_at))
    const candidate = { ...input, hours_per_week: hours, required_documents: documents, deadline_at: unchangedTime ? state.original!.deadline_at : state.at ? `${state.at}:00+09:00` : null, requirements: [...input.requirements, ...state.additions] }
    let parsed: OpportunityInput
    try { parsed = parseOpportunityInput(candidate) }
    catch { form.setValue((previous) => ({ ...previous, errors: [{ fieldId: 'editor-deadline', message: '입력 길이·목록·날짜를 확인해 주세요. 마감일과 마감 시각의 한국 날짜가 같아야 합니다.' }] })); return }
    const changes = state.original ? opportunityChanges(state.original, parsed) : null
    if (changes && !Object.keys(changes).length) { form.setValue((previous) => ({ ...previous, errors: [{ fieldId: 'editor-title', message: '변경한 항목이 없습니다.' }] })); return }
    const fields = quoteFields(parsed)
    if (!target) {
      const missing = fields.filter((field) => { const quote = state.quotes[field]?.trim() ?? ''; return !quote || [...quote].length > 300 })
      if (missing.length || !state.checkedAt) { form.setValue((previous) => ({ ...previous, errors: missing.map((field) => ({ fieldId: `editor-quote-${field}`, message: `${quoteLabels[field]}의 원문 인용을 300자 이내로 적어 주세요.` })) })); return }
    }
    // 원문 확인 시각은 확인 선택 시점으로 고정한다. 같은 입력의 재시도는 같은 본문·같은 키가 된다.
    const created = { source: state.source, content: parsed, evidence: { url: parsed.source_url, observed_at: state.checkedAt ?? '', confirmed_official: true as const, quotes: Object.fromEntries(fields.map((field) => [field, (state.quotes[field] ?? '').trim()])) } }
    const fingerprint = JSON.stringify(target ? parsed : created)
    if (!attempt.current || attempt.current.fingerprint !== fingerprint) attempt.current = { fingerprint, key: crypto.randomUUID() }
    const key = attempt.current.key
    await save.run(async (api, signal) => {
      const response = target && changes && state.version !== null
        ? await api.PATCH('/admin/opportunities/{opportunity_id}', { signal, params: { path: { opportunity_id: target.id } }, body: { base_version: state.version, changes } })
        : await api.POST('/admin/opportunities', { signal, params: { header: { 'Idempotency-Key': key } }, body: created })
      const result = parseEditable(required(response.data))
      if (result.status !== 'pending' || (target ? result.id !== target.id || result.version <= (state.version ?? 0) : result.version !== 1)) throw new ApiError('INVALID_RESPONSE')
      return { id: result.id, version: result.version }
    })
  }
  return <>
    <header className="page-heading"><h2 className="review-heading" ref={headingRef} tabIndex={-1}>{target ? '공고 수정하기' : '공고 직접 등록하기'}</h2><p>공식 원문에 있는 사실만 입력하세요. 새로 등록하거나 수정한 내용은 검수 대기 버전으로 저장됩니다. 수정 전 공개본은 승인 전까지 유지됩니다.</p></header>
    {target && <Button disabled={pending} variant="secondary" onClick={reload}>{input ? '편집 내용 버리고 선택한 버전 다시 불러오기' : '편집할 공고 불러오기'}</Button>}
    {load.state.status === 'error' && <RequestError error={load.state.error} />}
    {input && <form className="panel opportunity-editor" noValidate onSubmit={(event) => { event.preventDefault(); void submit() }}>
      <FormErrorSummary errors={state.errors} />
      <fieldset disabled={locked}><legend>기본 정보</legend>
        <InputField id="editor-title" label="공고 제목 (필수)" value={input.title} maxLength={200} error={error('editor-title')} onChange={(event) => update('title', event.target.value)} />
        <InputField id="editor-organization" label="기관명 (필수)" value={input.organization_name} maxLength={200} error={error('editor-organization')} onChange={(event) => update('organization_name', event.target.value)} />
        <label htmlFor="editor-type">활동 유형</label><select id="editor-type" value={input.activity_type} onChange={(event) => update('activity_type', event.target.value as OpportunityInput['activity_type'])}><option value="employment">취업·공공일자리</option><option value="volunteering">봉사</option></select>
        <label htmlFor="editor-status">원문의 모집 상태</label><select id="editor-status" value={input.recruitment_status} onChange={(event) => update('recruitment_status', event.target.value as OpportunityInput['recruitment_status'])}><option value="unknown">확인 필요</option><option value="open">모집 중</option><option value="closed">모집 종료</option></select>
        <label htmlFor="editor-public-job">공공일자리 여부</label><select id="editor-public-job" value={triValue(input.is_public_job)} onChange={(event) => update('is_public_job', tri(event.target.value))}><option value="">확인 필요</option><option value="yes">공공일자리</option><option value="no">공공일자리 아님</option></select>
        <TextAreaField id="editor-description" label="공식 원문 설명" value={input.description_text ?? ''} maxLength={5000} rows={6} onChange={(event) => update('description_text', event.target.value || null)} />
      </fieldset>
      <fieldset disabled={locked}><legend>지역·일정·보수</legend>
        <label htmlFor="editor-region">활동 시·도</label><select id="editor-region" aria-describedby="editor-region-help" value={input.activity_region?.province ?? ''} onChange={(event) => update('activity_region', event.target.value ? { province: event.target.value as components['schemas']['Province'], district: null } : null)}><option value="">확인 필요</option>{Object.entries(provinces).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select><p id="editor-region-help">기존 시·군·구 범위는 지역을 바꾸지 않으면 유지됩니다. 지역을 바꾸면 선택한 시·도 전체로 변경됩니다.</p>
        <InputField id="editor-location" label="상세 장소" value={input.location_text ?? ''} maxLength={500} onChange={(event) => update('location_text', event.target.value || null)} />
        <label htmlFor="editor-remote">원격 활동</label><select id="editor-remote" value={triValue(input.remote_allowed)} onChange={(event) => update('remote_allowed', tri(event.target.value))}><option value="">확인 필요</option><option value="yes">가능</option><option value="no">불가</option></select>
        <InputField id="editor-schedule" label="활동 일정" value={input.schedule_text ?? ''} maxLength={500} onChange={(event) => update('schedule_text', event.target.value || null)} />
        <InputField id="editor-hours" label="주당 시간 (모르면 비워두기)" type="number" min={0} max={168} step="any" value={state.hours} error={error('editor-hours')} onChange={(event) => updateRaw({ hours: event.target.value })} />
        <label htmlFor="editor-paid">보수 여부</label><select id="editor-paid" value={triValue(input.paid)} onChange={(event) => update('paid', tri(event.target.value))}><option value="">확인 필요</option><option value="yes">보수 있음</option><option value="no">무보수</option></select>
        <InputField id="editor-compensation" label="보수 상세" value={input.compensation_text ?? ''} maxLength={500} onChange={(event) => update('compensation_text', event.target.value || null)} />
        <InputField id="editor-deadline" label="마감일 (한국시간, 모르면 비워두기)" type="date" value={input.deadline_date ?? ''} onChange={(event) => update('deadline_date', event.target.value || null)} />
        <InputField id="editor-deadline-time" label="마감 시각 (한국시간, 모르면 비워두기)" type="datetime-local" value={state.at} onChange={(event) => updateRaw({ at: event.target.value })} />
      </fieldset>
      <fieldset disabled={locked}><legend>원문 조건·필요 서류</legend>
        <RequirementEditor key={load.state.status === 'success' ? load.state.data.version : 'new'} items={input.requirements} disabled={locked} onEditingChange={(editing) => updateRaw({ editing })} onChange={(requirements) => { update('requirements', requirements); updateRaw({ noRequirements: false }) }} />
        <TextAreaField id="editor-extra" label="추가 필수조건 원문 (한 줄에 하나)" value={state.extraText} maxLength={30029} error={error('editor-extra')} hint="추가 조건은 해석하지 않고 확인 필요로 등록합니다. 검수 전까지 지원 가능으로 판정하지 않습니다." onChange={(event) => updateRaw({ extraText: event.target.value, noRequirements: false, additions: lines(event.target.value).slice(0, 31).map((source_evidence) => ({ id: crypto.randomUUID(), source_evidence, field: 'other', operator: null, value: null, group_id: null, group_operator: null, reference_date: null, clarity: 'needs_review' })) })} />
        {input.requirements.length === 0 && <CheckboxField id="editor-no-requirements" label="공식 원문에 명시된 필수조건이 없는 것을 확인했어요." checked={state.noRequirements} disabled={state.additions.length > 0 || state.editing} error={error('editor-no-requirements')} onChange={(event) => updateRaw({ noRequirements: event.target.checked })} />}
        <CheckboxField label="공식 원문에서 필요 서류 안내를 확인했어요." checked={input.required_documents !== null} onChange={(event) => update('required_documents', event.target.checked ? [] : null)} />
        {input.required_documents !== null && <TextAreaField id="editor-documents" label="필요 서류 (한 줄에 하나)" value={state.documents} maxLength={4019} error={error('editor-documents')} hint="원문에 명시된 서류가 없으면 비워두세요. 미확인은 위 확인 선택을 해제해 구분합니다." onChange={(event) => updateRaw({ documents: event.target.value })} />}
      </fieldset>
      <fieldset disabled={locked}><legend>공식 원문·접수 안내</legend>
        <p>전화·방문·이메일 접수도 공식 접수 안내가 있는 HTTPS 주소를 적어 주세요. 입력한 주소를 자동으로 열거나 조회하지 않습니다.</p>
        <InputField id="editor-source" label="공식 원문 HTTPS 주소 (필수)" type="url" value={input.source_url} maxLength={2000} error={error('editor-source')} onChange={(event) => update('source_url', event.target.value)} />
        <InputField id="editor-application" label="공식 접수 안내 HTTPS 주소 (필수)" type="url" value={input.application_url} maxLength={2000} error={error('editor-application')} onChange={(event) => update('application_url', event.target.value)} />
        <label htmlFor="editor-method">접수 방법</label><select id="editor-method" value={input.application_method} onChange={(event) => update('application_method', event.target.value as OpportunityInput['application_method'])}>{Object.entries({ online: '온라인', phone: '전화', visit: '방문', email: '이메일', mixed: '여러 방법' }).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        <TextAreaField id="editor-instructions" label="공식 접수 방법 (필수)" value={input.application_instructions} maxLength={2000} error={error('editor-instructions')} onChange={(event) => update('application_instructions', event.target.value)} />
        <CheckboxField id="editor-checked" label="공식 원문과 입력 내용을 비교해 확인했습니다." checked={state.checked} error={error('editor-checked')} onChange={(event) => form.setValue((previous) => ({ ...previous, checked: event.target.checked, checkedAt: event.target.checked ? new Date().toISOString() : null, errors: [] }))} />
      </fieldset>
      {!target && <fieldset disabled={locked}><legend>공식 원문 근거</legend>
        <p>1365 자원봉사포털·50+포털·고용24의 공고 상세 주소만 등록할 수 있습니다. 입력한 항목마다 공식 원문의 해당 문장을 그대로 옮겨 주세요. 담당자 이름·전화·이메일은 옮기지 마세요.</p>
        <label htmlFor="editor-manual-source">공식 자료 출처</label><select id="editor-manual-source" value={state.source} onChange={(event) => updateRaw({ source: event.target.value as ManualSource })}>{Object.entries(manualSources).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select>
        {quoteFields({ ...input, hours_per_week: state.hours === '' ? null : 0, deadline_at: state.at || null, required_documents: input.required_documents === null ? null : lines(state.documents) }).map((field) => <TextAreaField key={field} id={`editor-quote-${field}`} label={`원문 인용: ${quoteLabels[field]}`} value={state.quotes[field] ?? ''} maxLength={300} rows={2} error={error(`editor-quote-${field}`)} onChange={(event) => updateRaw({ quotes: { ...state.quotes, [field]: event.target.value } })} />)}
      </fieldset>}
      {state.editing && <p role="status">조건 편집을 적용하거나 취소한 뒤 공고를 저장해 주세요.</p>}
      <Button type="submit" pending={save.state.status === 'pending'} disabled={locked || state.editing}>검수 대기 버전으로 저장</Button>
    </form>}
    {save.state.status === 'error' && <RequestError error={save.state.error} />}
    {stale && <StatusNotice label="최신 목록 필요" title="다른 작업으로 공고가 변경됐어요">입력은 유지했습니다. 목록으로 돌아가 최신 버전을 선택한 뒤 변경 내용을 다시 대조해 주세요.</StatusNotice>}
    <p role="status">{save.state.status === 'success' ? `검수 대기 버전 ${save.state.data.version}을 저장했습니다. 아직 공개되지 않았습니다.` : ''}</p>
    <div className="actions">{!target && save.state.status === 'success' && <Button variant="secondary" onClick={() => { form.clear(); save.clear(); attempt.current = null }}>새 공고 작성하기</Button>}<Button variant="secondary" onClick={onBack}>작성 화면 닫고 운영 목록으로</Button></div>
  </>
}
