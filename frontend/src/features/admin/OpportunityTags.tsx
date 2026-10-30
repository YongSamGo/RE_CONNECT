import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { RequestError } from '../../ui/StatusNotice'
import { parseRoleCatalog } from './editor'

export function OpportunityTags({ roles, skills, disabled, error, onRoles, onSkills }: {
  roles: string[]; skills: string; disabled: boolean; error?: string
  onRoles: (roles: string[]) => void; onSkills: (skills: string) => void
}) {
  const catalog = useRequest<ReturnType<typeof parseRoleCatalog>>()
  const entries = catalog.state.status === 'success' ? catalog.state.data : []
  const current = skills.split(/\r?\n/).map((value) => value.trim()).filter(Boolean)
  const suggestions = [...new Set(entries.filter((role) => roles.includes(role.id)).flatMap((role) => role.skill_tags))]
  return <fieldset disabled={disabled}>
    <legend>추천에 연결할 역할과 역량</legend>
    <p>공식 원문에 명시된 업무만 선택하세요. 역할을 골라도 역량이나 필수조건을 자동으로 채우지 않습니다.</p>
    <Button type="button" variant="secondary" pending={catalog.state.status === 'pending'} onClick={() => {
      void catalog.run(async (api, signal) => parseRoleCatalog(required((await api.GET('/admin/role-catalog', { signal })).data)))
    }}>역할 사전 불러오기</Button>
    {catalog.state.status === 'error' && <RequestError error={catalog.state.error} />}
    {catalog.state.status === 'success' && entries.length === 0 && <p>등록된 역할이 없습니다. 기존 선택은 유지됩니다.</p>}
    {entries.map((role) => <CheckboxField key={role.id} label={role.name} hint={role.description} checked={roles.includes(role.id)}
      disabled={!roles.includes(role.id) && roles.length >= 10} onChange={(event) => onRoles(event.target.checked ? [...roles, role.id] : roles.filter((id) => id !== role.id))} />)}
    {roles.filter((id) => !entries.some((role) => role.id === id)).map((id) => <div key={id}><p>기존 선택: {id}</p><Button type="button" variant="secondary" onClick={() => onRoles(roles.filter((value) => value !== id))}>기존 역할 {id} 선택 해제</Button></div>)}
    <TextAreaField id="editor-skills" label="원문에서 확인한 역량 (한 줄에 하나)" value={skills} rows={4} maxLength={1019} error={error}
      hint="한 줄 50자 이내로 최대 20개입니다. 비워 두면 경험에 근거한 추천에서 제외될 수 있습니다." onChange={(event) => onSkills(event.target.value)} />
    {suggestions.length > 0 && <div><p>선택한 역할의 역량 중 원문에 근거가 있는 항목만 추가하세요.</p><div className="actions">{suggestions.map((tag) => <Button key={tag} type="button" variant="secondary" disabled={current.includes(tag) || current.length >= 20}
      onClick={() => onSkills([...current, tag].join('\n'))}>{tag} 추가</Button>)}</div></div>}
  </fieldset>
}
