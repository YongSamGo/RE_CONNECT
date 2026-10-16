import type { components } from '../../api/schema'
import { useMemoryScope } from '../../state/useMemoryScope'
import { ReadAloud } from './ReadAloud'

type Target = components['schemas']['SpeechTargetOpportunity']
type Field = Target['field']
const fields: Record<Field, string> = { title: '공고 제목', description_text: '공식 원문 설명', schedule_text: '활동 일정', location_text: '상세 장소', compensation_text: '보수 상세', application_instructions: '접수 안내' }
export function OpportunityReadAloud({ item }: { item: Pick<components['schemas']['Opportunity'], 'id' | 'version' | Field> }) {
  const selected = useMemoryScope<Field>(() => 'title')
  const field = selected.value
  return <section aria-label="공고 읽어주기">
    <label htmlFor="speech-opportunity-field">읽을 항목</label><select id="speech-opportunity-field" value={field} onChange={(event) => selected.setValue(event.target.value as Field)}>{(Object.keys(fields) as Field[]).filter((key) => !!item[key]?.trim()).map((key) => <option key={key} value={key}>{fields[key]}</option>)}</select>
    <ReadAloud key={`${item.id}:${item.version}:${field}`} target={{ kind: 'opportunity', opportunity_id: item.id, version: item.version, field }} label={`${fields[field]} 읽어주기`} />
  </section>
}
