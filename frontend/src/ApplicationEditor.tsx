import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { applicationText, applicationTextLimit, canApproveApplication, emptyApplication, type ApplicationDraft } from './application'
import type { Profile } from './journey'

export function ApplicationEditor({ draft, profile, profileVersion, update }: {
  draft: ApplicationDraft | undefined
  profile: Profile | null
  profileVersion: number
  update: (draft: ApplicationDraft) => void
}) {
  const [reviewed, setReviewed] = useState(false)
  const [copyState, setCopyState] = useState<'idle' | 'pending' | 'done' | 'failed'>('idle')
  const copyRequest = useRef(0)
  const fallback = useRef<HTMLTextAreaElement>(null)
  useEffect(() => () => { copyRequest.current += 1 }, [])
  useEffect(() => { if (copyState === 'failed') { fallback.current?.focus(); fallback.current?.select() } }, [copyState])
  if (!profile) return <section className="panel" aria-labelledby="application-title"><h2 id="application-title">내 말로 지원서 써보기</h2><p>먼저 경험 프로필을 작성하고 확정해주세요. 확정한 경험을 참고해 자기소개와 지원동기를 직접 쓸 수 있어요.</p><Link className="button secondary" to="/profile">프로필 작성·확정하기</Link></section>
  const current = draft ?? emptyApplication(profileVersion)
  const stale = current.profileVersion !== profileVersion
  const approved = current.approved && !stale
  function edit(field: 'introduction' | 'motivation', value: string) {
    copyRequest.current += 1
    setReviewed(false); setCopyState('idle')
    update({ ...current, [field]: value, approved: false })
  }
  async function copy() {
    const request = ++copyRequest.current
    setCopyState('pending')
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable')
      await navigator.clipboard.writeText(applicationText(current))
      if (request === copyRequest.current) setCopyState('done')
    } catch {
      if (request === copyRequest.current) setCopyState('failed')
    }
  }
  return <section className="panel application-editor" aria-labelledby="application-title"><p className="eyebrow">직접 작성 · 화면 체험</p><h2 id="application-title">내 말로 지원서 써보기</h2>
    <p>예시 활동에 맞춰 직접 써보세요. AI 생성·기관 제출·영구 저장은 하지 않아요. 주민등록번호·연락처·상세 병력은 적지 말아주세요.</p>
    <details className="profile-reference"><summary>현재 확정한 내 경험 참고하기</summary><p className="preserve-lines">{profile.experience}</p><p>{profile.region} · 확정본 {profileVersion}</p><Link className="text-link" to="/profile">프로필 수정하기</Link></details>
    {stale && <p className="notice">프로필 변경으로 재검토가 필요해요. 작성한 문장은 그대로 두었어요. 현재 확정한 경험과 비교한 뒤 다시 확인해주세요.</p>}
    <div className="field"><label htmlFor="introduction">자기소개</label><textarea id="introduction" rows={5} maxLength={applicationTextLimit} autoComplete="off" value={current.introduction} aria-describedby="introduction-help" placeholder="해본 일과 그 과정에서 익힌 점을 내 말로 적어주세요." onChange={event => edit('introduction', event.target.value)} /><p className="field-help" id="introduction-help">실제로 해본 경험만 적어주세요. {current.introduction.length.toLocaleString()} / {applicationTextLimit.toLocaleString()}자</p></div>
    <div className="field"><label htmlFor="motivation">지원동기</label><textarea id="motivation" rows={5} maxLength={applicationTextLimit} autoComplete="off" value={current.motivation} aria-describedby="motivation-help" placeholder="이 활동에 관심을 갖게 된 이유와 함께하고 싶은 일을 적어주세요." onChange={event => edit('motivation', event.target.value)} /><p className="field-help" id="motivation-help">확인하지 않은 경력·자격은 사실처럼 적지 말아주세요. {current.motivation.length.toLocaleString()} / {applicationTextLimit.toLocaleString()}자</p></div>
    <p className="draft-state"><strong>{stale ? '재검토 필요' : approved ? '현재 문장 확인 완료' : '작성 중 · 아직 확인하지 않았어요'}</strong></p>
    <label className="check-row"><input type="checkbox" checked={reviewed} onChange={event => setReviewed(event.target.checked)} />현재 확정 프로필과 비교했고, 직접 쓴 내용이 사실인지 확인했어요.</label>
    <button className="button secondary" disabled={!reviewed || !canApproveApplication(current) || approved} onClick={() => {
      update({ ...current, profileVersion, approved: true }); setReviewed(false); setCopyState('idle')
    }}>이 문장으로 확인하기</button>
    {!canApproveApplication(current) && <p className="field-help">자기소개와 지원동기를 모두 적으면 확인할 수 있어요.</p>}
    <div className="copy-panel"><h3>확인한 문장 복사</h3><p>자기소개·지원동기 제목과 현재 작성한 문장을 함께 복사해요. 수정하거나 프로필을 다시 확정하면 문장을 재확인해야 해요.</p><button className="button" disabled={!approved || copyState === 'pending'} onClick={() => { void copy() }}>{copyState === 'pending' ? '복사 중…' : '확인한 문장 복사하기'}</button>
      <p role="status" className="field-help">{copyState === 'done' ? '복사했어요. 기기의 클립보드에 문장이 남을 수 있어요. 신청하거나 영구 저장한 것은 아니에요.' : copyState === 'failed' ? '자동 복사를 하지 못했어요. 아래 문장을 선택해 기기의 복사 기능을 사용해주세요.' : ''}</p>
      {copyState === 'failed' && <div className="field"><label htmlFor="manual-copy">직접 복사할 문장</label><textarea id="manual-copy" ref={fallback} readOnly rows={8} value={applicationText(current)} /><p className="field-help">PC에서는 Ctrl+C 또는 ⌘C, 휴대전화에서는 길게 눌러 복사할 수 있어요.</p></div>}
    </div><p className="field-help">확인은 영구 저장과 별개예요. 화면을 나갔다 돌아와도 현재 체험 안에서는 작성 내용이 유지되며, 새로고침·종료 시 지워져요. 직접 복사한 클립보드 내용은 체험 종료로 지워지지 않아요.</p>
  </section>
}
