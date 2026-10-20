import { useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField, TextAreaField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { StatusNotice } from '../../ui/StatusNotice'
import { emptyManualDraft } from './model'
import type { ManualDraft } from './model'
type CopyState = 'idle' | 'pending' | 'success' | 'error'

/** Preview-only writing. Review is local and never represents server approval. */
export function ManualPreparation({ draft, onChange }: { draft: ManualDraft; onChange: (draft: ManualDraft) => void }) {
  const [errors, setErrors] = useState<FieldError[]>([])
  const copy = useMemoryScope<CopyState>(() => 'idle')
  const active = useRef<AbortSignal | null>(null)
  const body = `자기소개\n${draft.introduction}\n\n지원동기\n${draft.motivation}`
  const complete = Boolean(draft.introduction.trim() && draft.motivation.trim())

  function edit(field: 'introduction' | 'motivation', value: string) {
    copy.clear()
    setErrors([])
    onChange({ ...draft, [field]: value, reviewed: false })
  }
  function review(checked: boolean) {
    copy.clear()
    const next: FieldError[] = []
    if (checked && !draft.introduction.trim()) next.push({ fieldId: 'manual-introduction', message: '자기소개를 적어 주세요.' })
    if (checked && !draft.motivation.trim()) next.push({ fieldId: 'manual-motivation', message: '지원동기를 적어 주세요.' })
    setErrors(next)
    onChange({ ...draft, reviewed: checked && next.length === 0 })
  }
  async function copyText() {
    if (!draft.reviewed || !complete || (active.current && !active.current.aborted)) return
    copy.setValue('pending')
    await copy.run(async (signal): Promise<CopyState> => {
      active.current = signal
      try {
        if (!navigator.clipboard?.writeText) return 'error'
        // Call during the click gesture; no clipboard read or background write.
        await navigator.clipboard.writeText(body)
        return 'success'
      } catch { return 'error' }
      finally { if (active.current === signal) active.current = null }
    }, copy.setValue)
  }

  return <div className="reading-width">
    <header className="page-heading"><p className="eyebrow">03 · 신청 준비 미리보기</p><h1>내 말로 지원 내용을 적어봐요</h1><p>가상의 경험으로 자기소개와 지원동기 작성을 연습해 보세요.</p></header>
    <StatusNotice label="직접 작성 미리보기" title="공고·프로필 연결 전의 연습 화면이에요">AI 생성·자격 판정·회원 저장은 연결 준비 중입니다. 실제 개인정보는 적지 마세요. 특정 공고의 지원서나 서버에서 승인한 자료로 처리하지 않습니다.</StatusNotice>
    <section className="panel" aria-labelledby="preparation-guide"><h2 id="preparation-guide">신청 전에 확인해 주세요</h2><p>공고를 선택한 뒤 공식 원문에서 모집 상태·지원 조건·필요 서류·접수 방법을 확인해 주세요. 이 화면에서는 공고별 서류를 안내하거나 준비 완료를 판정하지 않습니다.</p><Link className="text-link" to="/opportunities">공개 공고에서 공식 안내 확인하기 →</Link></section>
    <section className="panel" aria-labelledby="manual-heading"><h2 id="manual-heading">직접 작성하기</h2>
      <p>작성 내용은 화면을 이동해도 이번 미리보기 안에서 유지됩니다. 새로고침하거나 종료하면 삭제됩니다.</p>
      <FormErrorSummary errors={errors} />
      <TextAreaField id="manual-introduction" label="자기소개" value={draft.introduction} onChange={(event) => edit('introduction', event.target.value)} maxLength={2000} rows={6} hint="직접 해온 일과 경험을 적어 주세요. 연락처·주민등록번호·상세 병력은 적지 마세요." error={errors.find((error) => error.fieldId === 'manual-introduction')?.message} />
      <TextAreaField id="manual-motivation" label="지원동기" value={draft.motivation} onChange={(event) => edit('motivation', event.target.value)} maxLength={2000} rows={6} hint="하고 싶은 활동과 그 이유를 적어 주세요. 확인하지 않은 경력·자격은 추가하지 마세요." error={errors.find((error) => error.fieldId === 'manual-motivation')?.message} />
      <CheckboxField label="작성한 두 항목을 읽고, 내 경험과 맞는 내용인지 확인했어요." checked={draft.reviewed} onChange={(event) => review(event.target.checked)} hint="내용을 수정하면 다시 확인해야 복사할 수 있어요. 이 선택은 서버 승인이나 저장 동의가 아닙니다." />
    </section>
    <section className="panel" aria-labelledby="copy-heading"><h2 id="copy-heading">내용 확인하고 복사하기</h2>
      {draft.reviewed && complete ? <>
        <TextAreaField label="복사할 내용" value={body} readOnly rows={10} id="manual-copy" />
        <div className="actions"><Button pending={copy.value === 'pending'} pendingLabel="복사하고 있어요…" onClick={() => void copyText()}>확인한 내용 복사하기</Button></div>
      </> : <p>두 항목을 작성하고 내용 확인을 선택하면 복사할 문장을 보여드려요.</p>}
      <p role="status" aria-atomic="true">{copy.value === 'success' ? '작성한 내용을 복사했습니다. 저장이나 신청이 완료된 것은 아닙니다.' : ''}</p>
      {copy.value === 'error' && <StatusNotice kind="error" title="자동 복사를 완료하지 못했어요" actions={<Button variant="secondary" onClick={() => { const field = document.getElementById('manual-copy') as HTMLTextAreaElement | null; field?.focus(); field?.select() }}>복사할 내용 전체 선택</Button>}>브라우저가 복사를 지원하지 않거나 권한이 허용되지 않았습니다. 내용을 선택해 기기의 복사 기능을 사용하거나 다시 시도해 주세요.</StatusNotice>}
      <p className="quiet">복사 버튼은 기기의 클립보드에 내용을 씁니다. 미리보기를 종료해도 이미 복사한 내용은 클립보드에 남을 수 있어요.</p>
    </section>
    <div className="actions"><Link className="button secondary" to="/profile">내 경험 다시 보기</Link><Button variant="secondary" onClick={() => { copy.clear(); setErrors([]); onChange(emptyManualDraft()) }}>작성 내용 지우기</Button></div>
  </div>
}
