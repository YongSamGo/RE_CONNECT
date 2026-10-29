import { useMemoryScope } from '../../state/useMemoryScope'
import type { JourneyDraft } from '../preparation/drafts'
import { ReadAloud } from './ReadAloud'

type Field = 'self_introduction' | 'motivation'
const labels: Record<Field, string> = { self_introduction: '자기소개', motivation: '지원동기' }
export function DraftReadAloud({ journeyId, draft }: { journeyId: string; draft: JourneyDraft }) {
  const selected = useMemoryScope<Field>(() => 'self_introduction')
  const available = (Object.keys(labels) as Field[]).filter(field => !!draft[field].trim())
  const field = available.includes(selected.value) ? selected.value : available[0]
  if (!field) return null
  return <section aria-label="초안 읽어주기">
    <label htmlFor="speech-draft-field">읽을 초안 항목</label>
    <select id="speech-draft-field" value={field} onChange={event => selected.setValue(event.target.value as Field)}>
      {available.map(value => <option key={value} value={value}>{labels[value]}</option>)}
    </select>
    <ReadAloud key={`${draft.draft_id}:${draft.revision}:${field}`} target={{ kind: 'journey_draft', journey_id: journeyId, draft_id: draft.draft_id, revision: draft.revision, field }} label={`${labels[field]} 읽어주기`} />
  </section>
}
