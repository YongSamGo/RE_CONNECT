import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import type { ApplicationDraft } from './application'
import type { Profile } from './journey'
import { activityLabels, exampleOpportunities } from './opportunities'

function DeleteApplicationDialog({ title, cancel, confirm, opener }: { title: string; cancel: () => void; confirm: () => void; opener: HTMLButtonElement | null }) {
  const dialog = useRef<HTMLDialogElement>(null)
  const cancelButton = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    dialog.current?.showModal()
    cancelButton.current?.focus()
    return () => { queueMicrotask(() => { if (opener?.isConnected) opener.focus() }) }
  }, [opener])
  return <dialog ref={dialog} className="panel native-dialog" aria-labelledby="delete-application-title" aria-describedby="delete-application-description" onCancel={event => { event.preventDefault(); cancel() }} onKeyDown={event => {
    if (event.key !== 'Tab') return
    const buttons = event.currentTarget.querySelectorAll('button')
    if (event.shiftKey && document.activeElement === buttons[0]) { event.preventDefault(); buttons[1].focus() }
    else if (!event.shiftKey && document.activeElement === buttons[1]) { event.preventDefault(); buttons[0].focus() }
  }}>
    <h2 id="delete-application-title">이 지원서를 지울까요?</h2><p id="delete-application-description">‘{title}’에 직접 작성한 문장과 확인 상태를 현재 체험에서 지워요. 복원할 수 없어요. 프로필과 준비 체크는 유지돼요. 직접 복사한 클립보드는 지워지지 않아요.</p>
    <div className="actions"><button ref={cancelButton} className="button secondary" onClick={cancel}>계속 보관하기</button><button className="button" onClick={confirm}>이 지원서 삭제하기</button></div>
  </dialog>
}

export function MyPage({ profile, profileVersion, applications, deleteApplication }: {
  profile: Profile | null
  profileVersion: number
  applications: Record<string, ApplicationDraft>
  deleteApplication: (id: string) => void
}) {
  const [deleting, setDeleting] = useState<{ id: string; opener: HTMLButtonElement } | null>(null)
  const [message, setMessage] = useState('')
  const listHeading = useRef<HTMLHeadingElement>(null)
  const items = exampleOpportunities.filter(item => applications[item.id])
  const selected = items.find(item => item.id === deleting?.id)
  return <section className="narrow my-page"><p className="eyebrow">내가 확인하고 이어가는 이야기</p><h1>내 정보</h1><p className="lead">현재 체험에서 정리한 경험과 직접 작성한 문장을 살펴보세요.</p>
    <aside className="notice"><strong>지금 보이는 자료는 이번 체험에만 있어요.</strong><p>서버에 저장된 회원 자료가 아니에요. 새로고침하거나 ‘종료하고 삭제’를 누르면 사라져요. 카카오 로그인과 별도 저장 동의는 연결 준비 중이에요.</p></aside>
    <section className="panel" aria-labelledby="my-profile-title"><div className="section-heading"><h2 id="my-profile-title">현재 확정한 프로필</h2><span className="badge">{profile ? `체험 확정본 ${profileVersion}` : '아직 확정 전'}</span></div>
      {profile ? <><p className="preserve-lines">{profile.experience}</p><dl className="detail-facts"><div><dt>희망 활동 지역</dt><dd>{profile.region}</dd></div><div><dt>활동 유형</dt><dd>{profile.activities.map(activity => activityLabels[activity]).join(' · ')}</dd></div></dl><p className="field-help">수정 중인 내용은 다시 확정할 때 반영돼요. 프로필을 다시 확정하면 기존 지원서는 재검토가 필요해요.</p><Link className="text-link" to="/profile">프로필 확인·수정하기 →</Link></> : <><p>경험을 적고 프로필을 확정하면 여기에서 확인할 수 있어요. 확정은 영구 저장과 별개예요.</p><Link className="button secondary" to="/profile">프로필 작성·확정하기</Link></>}
    </section>
    <section aria-labelledby="my-applications-title"><div className="section-heading"><h2 id="my-applications-title" ref={listHeading} tabIndex={-1}>현재 체험의 지원서 <span className="application-count">{items.length}개</span></h2></div>
      <p className="field-help">가상 예시 활동에 직접 작성한 문장이에요. 실제 기관에 제출한 지원서가 아니에요.</p>
      <p role="status" className="field-help">{message}</p>
      {items.length === 0 ? <div className="panel empty-state"><h3>아직 작성한 지원서가 없어요</h3><p>예시 공고의 신청 준비 화면에서 자기소개와 지원동기를 써볼 수 있어요.</p><Link className="button secondary" to="/opportunities">공고 탐색으로 이동</Link></div> : <div className="application-list">{items.map(item => {
        const draft = applications[item.id]
        const stale = draft.profileVersion !== profileVersion
        return <article className="panel" key={item.id}><div className="badge-row"><span className="badge">화면 예시</span><span className={stale ? 'review-needed' : ''}>{stale ? '프로필 변경 · 재검토 필요' : draft.approved ? '문장 확인 완료' : '작성 중'}</span></div><h3>{item.title}</h3>
          <p className="preserve-lines">{draft.introduction.trim() ? `${draft.introduction.slice(0, 160)}${draft.introduction.length > 160 ? '…' : ''}` : '자기소개를 아직 작성하지 않았어요.'}</p><p className="field-help">{draft.approved && !stale ? '확인한 문장을 신청 준비 화면에서 복사할 수 있어요.' : '내용을 확인한 뒤 복사할 수 있어요.'} 영구 저장하지 않았어요.</p>
          <div className="actions"><Link className="button secondary" to={`/preparation/${item.id}`} aria-label={`${item.title} 지원서 ${stale ? '재검토하기' : '이어서 보기'}`}>{stale ? '재검토하기' : '이어서 보기'} →</Link><button className="delete-link" aria-label={`${item.title} 지원서 삭제`} onClick={event => setDeleting({ id: item.id, opener: event.currentTarget })}>지원서 삭제</button></div>
        </article>
      })}</div>}
    </section>
    <section className="panel" aria-labelledby="saved-data-title"><h2 id="saved-data-title">회원으로 저장한 자료</h2><p>로그인과 저장 API가 연결되면 별도 동의를 받아 저장한 자료를 조회할 수 있어요.</p><p className="field-help">현재는 회원 저장·철회·탈퇴 기능을 제공하지 않아요. 이번 체험 자료는 위에서 확인해주세요.</p></section>
    {selected && deleting && <DeleteApplicationDialog title={selected.title} opener={deleting.opener} cancel={() => setDeleting(null)} confirm={() => {
      deleteApplication(selected.id); setDeleting(null); setMessage(`${selected.title} 지원서를 현재 체험에서 지웠어요.`)
      queueMicrotask(() => listHeading.current?.focus())
    }} />}
  </section>
}
