export function SaveProgress({ profileSaved, draftSaved, includesDraft, finished = false }: {
  profileSaved: boolean; draftSaved: boolean; includesDraft: boolean; finished?: boolean
}) {
  return <section className="service-save-progress" aria-label="자료 저장 상태">
    <h2>{finished ? '저장 결과' : '저장 상태'}</h2>
    <dl><div><dt>내 경험</dt><dd className={profileSaved ? 'save-done' : undefined}>{profileSaved ? '저장 완료' : '저장 전'}</dd></div>
      {includesDraft && <div><dt>지원서</dt><dd className={draftSaved ? 'save-done' : undefined}>{draftSaved ? '저장 완료' : '저장 전'}</dd></div>}
    </dl>
  </section>
}
