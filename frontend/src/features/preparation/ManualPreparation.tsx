import { useEffect, useRef, useState } from 'react'
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
  const [confirmingClear, setConfirmingClear] = useState(false)
  const clearHeading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { if (confirmingClear) clearHeading.current?.focus() }, [confirmingClear])
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
    <header className="page-heading"><p className="eyebrow">지원 내용 작성</p><h1>내 말로 지원 내용을 적어봐요</h1><p>자기소개와 지원동기를 직접 적어 보세요.</p></header>
    <details className="disclosure"><summary>작성 연습과 실제 신청의 차이</summary><p>AI 생성과 자격 판정, 회원 저장은 아직 연결되지 않았어요. 작성한 내용은 특정 공고의 지원서나 서버에서 승인한 자료로 처리하지 않아요.</p><p>실제 신청 전에는 공식 원문에서 모집 상태와 지원 조건, 필요 서류, 접수 방법을 확인해 주세요. 이 연습 화면은 공고별 서류를 안내하거나 준비 완료를 판정하지 않아요.</p><Link className="text-link" to="/opportunities">공개 공고에서 공식 안내 확인하기</Link></details>
    <section className="panel preparation-editor" aria-labelledby="manual-heading"><h2 id="manual-heading">직접 작성하기</h2>
      <p>작성 내용은 화면을 이동해도 유지됩니다. 새로고침하거나 종료하면 삭제됩니다. 개인정보는 입력하지 마세요.</p>
      <FormErrorSummary errors={errors} />
      <TextAreaField id="manual-introduction" label="자기소개" value={draft.introduction} onChange={(event) => edit('introduction', event.target.value)} maxLength={2000} rows={6} hint="직접 해온 일과 경험을 적어 주세요. 연락처나 주민등록번호, 상세 병력은 적지 마세요." error={errors.find((error) => error.fieldId === 'manual-introduction')?.message} />
      <TextAreaField id="manual-motivation" label="지원동기" value={draft.motivation} onChange={(event) => edit('motivation', event.target.value)} maxLength={2000} rows={6} hint="하고 싶은 활동과 그 이유를 적어 주세요. 확인하지 않은 경력이나 자격은 추가하지 마세요." error={errors.find((error) => error.fieldId === 'manual-motivation')?.message} />
      <CheckboxField label="두 항목을 읽고 내 경험과 맞는지 확인했어요." checked={draft.reviewed} onChange={(event) => review(event.target.checked)} hint="내용을 수정하면 다시 확인해야 복사할 수 있어요. 이 선택은 서버 승인이나 저장 동의가 아닙니다." />
    </section>
    {draft.reviewed && complete && <section className="panel" aria-labelledby="copy-heading"><h2 id="copy-heading">내용 확인하고 복사하기</h2>
        <TextAreaField label="복사할 내용" value={body} readOnly rows={10} id="manual-copy" />
        <div className="actions"><Button pending={copy.value === 'pending'} pendingLabel="복사하고 있어요…" onClick={() => void copyText()}>확인한 내용 복사하기</Button></div>
      <p role="status" aria-atomic="true">{copy.value === 'success' ? '작성한 내용을 복사했습니다. 저장이나 신청이 완료된 것은 아닙니다.' : ''}</p>
      {copy.value === 'error' && <StatusNotice kind="error" title="자동 복사를 완료하지 못했어요" actions={<Button variant="secondary" onClick={() => { const field = document.getElementById('manual-copy') as HTMLTextAreaElement | null; field?.focus(); field?.select() }}>복사할 내용 전체 선택</Button>}>브라우저가 복사를 지원하지 않거나 권한이 허용되지 않았습니다. 내용을 선택해 기기의 복사 기능을 사용하거나 다시 시도해 주세요.</StatusNotice>}
      <p className="quiet">복사 버튼은 기기의 클립보드에 내용을 씁니다. 화면을 종료해도 이미 복사한 내용은 클립보드에 남을 수 있어요.</p>
    </section>}
    <div className="actions"><Link className="button secondary" to="/profile">내 경험 다시 보기</Link><Button id="manual-clear" variant="secondary" onClick={() => setConfirmingClear(true)}>작성 내용 지우기</Button></div>
    {confirmingClear && <section className="panel" aria-labelledby="manual-clear-heading"><h2 id="manual-clear-heading" className="result-heading" ref={clearHeading} tabIndex={-1}>작성 내용을 지울까요?</h2><p>자기소개와 지원동기가 지워집니다. 이미 복사한 내용은 클립보드에 남을 수 있어요.</p><div className="actions"><Button onClick={() => { copy.clear(); setErrors([]); onChange(emptyManualDraft()); setConfirmingClear(false); document.getElementById('manual-introduction')?.focus() }}>내용 지우기</Button><Button variant="secondary" onClick={() => { setConfirmingClear(false); document.getElementById('manual-clear')?.focus() }}>계속 작성하기</Button></div></section>}
  </div>
}
