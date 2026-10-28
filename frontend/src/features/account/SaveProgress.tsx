export function SaveProgress({ profileSaved, draftSaved, includesDraft, finished = false }: {
  profileSaved: boolean; draftSaved: boolean; includesDraft: boolean; finished?: boolean
}) {
  return <section className="service-save-progress" aria-label="자료 저장 상태">
    <h2>{finished ? '자료별 저장 결과' : '저장할 자료와 진행 상태'}</h2>
    <dl><div><dt>내 프로필</dt><dd className={profileSaved ? 'save-done' : undefined}>{profileSaved ? '저장 완료' : '저장 전'}</dd></div>
      {includesDraft && <div><dt>지원서</dt><dd className={draftSaved ? 'save-done' : undefined}>{draftSaved ? '저장 완료' : '저장 전'}</dd></div>}
    </dl><p>저장한 자료는 내 정보의 ‘저장한 자료’에서 다시 확인할 수 있어요.</p>
  </section>
}
