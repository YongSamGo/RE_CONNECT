import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { activityLabels, exampleOpportunities, filterExamples, type OpportunityFilters } from './opportunities'
import { ApplicationEditor } from './ApplicationEditor'
import type { ApplicationDraft } from './application'
import type { Profile } from './journey'

const emptyFilters = (): OpportunityFilters => ({ keyword: '', region: '', activity: '' })

function ExampleNotice() {
  return <aside className="notice"><strong>화면 체험용 예시 · 실제 모집 공고가 아니에요</strong><p>기관·활동·일정은 화면을 살펴보기 위한 가상 정보예요. 실제 신청, 자격 판단, 공식 접수처 연결은 제공하지 않아요.</p></aside>
}

export function OpportunityList({ examples, showExamples }: { examples: boolean; showExamples: () => void }) {
  const [filters, setFilters] = useState<OpportunityFilters>(emptyFilters)
  const items = filterExamples(filters)
  return <section className="browse-page"><p className="eyebrow">경험에서 이어지는 다음 걸음</p><h1>새로운 기회를 만나는 곳</h1><p className="lead">관심 있는 활동을 살펴보고, 나에게 필요한 준비를 차근차근 확인해요.</p>
    {!examples ? <div className="panel connection-state"><span className="empty-symbol" aria-hidden="true">↗</span><h2>실제 공고를 연결하고 있어요</h2><p>검수한 공고가 연결되면 지역과 활동 유형으로 찾아볼 수 있어요.</p><button className="button" onClick={showExamples}>예시 공고로 화면 체험하기</button><p className="field-help">가상의 예시 3개로 목록·상세·준비 화면을 살펴봐요.</p></div> : <>
      <ExampleNotice />
      <div className="browse-layout"><form className="panel filters" aria-label="예시 공고 필터" onSubmit={event => event.preventDefault()}>
        <h2>어떤 활동을 찾으세요?</h2>
        <div className="field"><label htmlFor="keyword">검색어</label><input id="keyword" type="search" maxLength={100} value={filters.keyword} placeholder="예: 도서관, 식사" onChange={event => setFilters({ ...filters, keyword: event.target.value })} /></div>
        <div className="field"><label htmlFor="filter-region">활동 지역</label><select id="filter-region" value={filters.region} onChange={event => setFilters({ ...filters, region: event.target.value })}><option value="">전체 지역</option>{[...new Set(exampleOpportunities.map(item => item.region))].map(region => <option key={region}>{region}</option>)}</select></div>
        <div className="field"><label htmlFor="filter-activity">활동 유형</label><select id="filter-activity" value={filters.activity} onChange={event => setFilters({ ...filters, activity: event.target.value })}><option value="">전체 활동</option>{Object.entries(activityLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></div>
        <button type="button" className="button secondary" onClick={() => setFilters(emptyFilters())}>필터 초기화</button>
      </form>
      <div><p role="status" className="result-count">화면 예시 <strong>{items.length}개</strong><span>추천 순위가 아닌 예시 목록이에요</span></p>
        {items.length === 0 ? <div className="panel empty-state"><h2>선택한 조건에 맞는 예시가 없어요</h2><p>다른 검색어나 지역·활동 유형을 선택해보세요. 조건은 자동으로 바꾸지 않아요.</p><button className="button secondary" onClick={() => setFilters(emptyFilters())}>모든 예시 보기</button></div> : <div className="opportunity-grid">{items.map(item => <article className="panel opportunity-card" key={item.id}>
          <div className="badge-row"><span className="badge">화면 예시</span><span>{activityLabels[item.activity]}</span></div><p className="organization">{item.organization} · {item.region}</p><h2><Link to={`/opportunities/${item.id}`}>{item.title}</Link></h2><p>{item.summary}</p><p className="schedule">{item.schedule}</p><div className="card-bottom"><span>자격 판단 미제공</span><Link className="text-link" to={`/opportunities/${item.id}`} aria-label={`${item.title} 예시 상세 보기`}>자세히 보기 →</Link></div>
        </article>)}</div>}
      </div></div>
    </>}
  </section>
}

function MissingOpportunity() {
  return <section className="narrow"><p className="eyebrow">공고 확인</p><h1>공고 정보를 확인할 수 없어요</h1><div className="panel"><p>실제 공고는 아직 연결되지 않았어요. 목록에서 화면 체험용 예시를 선택할 수 있어요.</p></div><Link className="button secondary" to="/opportunities">공고 목록으로</Link></section>
}

export function OpportunityDetail({ examples }: { examples: boolean }) {
  const { id } = useParams()
  const item = examples ? exampleOpportunities.find(value => value.id === id) : undefined
  if (!item) return <MissingOpportunity />
  return <section className="narrow"><Link className="text-link" to="/opportunities">← 예시 목록으로</Link><ExampleNotice />
    <p className="eyebrow">{activityLabels[item.activity]} · {item.region}</p><h1>{item.title}</h1><p className="lead">{item.organization}</p>
    <div className="panel"><h2>어떤 활동인가요?</h2><p>{item.summary}</p><dl className="detail-facts"><div><dt>활동 지역</dt><dd>{item.region}</dd></div><div><dt>활동 일정</dt><dd>{item.schedule}</dd></div><div><dt>모집 기간·접수처</dt><dd>실제 공고가 연결된 뒤 제공해요</dd></div></dl></div>
    <div className="panel"><h2>신청 전에 무엇을 확인하나요?</h2><p>아래는 확인 항목의 예시예요. 충족·미충족 여부를 판단한 결과가 아니에요.</p><ul className="readable-list">{item.conditions.map(condition => <li key={condition}>{condition}</li>)}</ul><p className="field-help">나이·자격·급여 등 실제 조건은 공식 원문과 자격 대조 API 연결 후 확인해요.</p></div>
    <div className="notice"><strong>공식 원문과 오류 신고는 연결 준비 중이에요.</strong><p>이 예시에는 실제 출처나 담당 기관이 없어 신청 링크와 신고 접수를 제공하지 않아요.</p></div>
    <div className="actions"><Link className="button" to={`/preparation/${item.id}`}>신청 준비 화면 체험하기 →</Link><Link className="button secondary" to="/opportunities">다른 예시 보기</Link></div>
  </section>
}

export function PreparationPage({ examples, checks, update, applications, updateApplication, profile, profileVersion }: {
  examples: boolean
  checks: Record<string, string[]>
  update: (id: string, checked: string[]) => void
  applications: Record<string, ApplicationDraft>
  updateApplication: (id: string, draft: ApplicationDraft) => void
  profile: Profile | null
  profileVersion: number
}) {
  const { id } = useParams()
  const item = examples ? exampleOpportunities.find(value => value.id === id) : undefined
  if (!item) return <MissingOpportunity />
  const selected = checks[item.id] ?? []
  return <section className="narrow"><Link className="text-link" to={`/opportunities/${item.id}`}>← 예시 상세로</Link><ExampleNotice /><p className="eyebrow">한 가지씩, 내 속도로</p><h1>신청 준비를 차근차근</h1><p className="lead">{item.title} · 준비 과정의 화면 예시예요.</p>
    <div className="panel"><h2>내 준비 체크</h2><p>실제 제출서류 목록이 아닌, 준비 과정을 살펴보는 체크리스트예요.</p><p role="status">{item.preparation.length}개 중 {selected.length}개 확인</p><fieldset><legend className="sr-only">예시 준비 항목</legend>{item.preparation.map(text => <label className="check-row option" key={text}><input type="checkbox" checked={selected.includes(text)} onChange={event => update(item.id, event.target.checked ? [...selected, text] : selected.filter(value => value !== text))} />{text}</label>)}</fieldset><p className="field-help">체크는 현재 화면 메모리에만 남아요. 새로고침하거나 체험을 종료하면 사라져요.</p></div>
    <ApplicationEditor key={`${item.id}:${profileVersion}`} draft={applications[item.id]} profile={profile} profileVersion={profileVersion} update={draft => updateApplication(item.id, draft)} />
    <div className="panel"><h2>공식 신청 안내</h2><p>공식 접수처 연결은 실제 공고 연동 후 제공해요. 준비 항목 체크나 문장 확인·복사는 신청 완료를 의미하지 않아요.</p></div><Link className="button secondary" to="/opportunities">예시 목록으로 돌아가기</Link>
  </section>
}
