import { useEffect, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { createApiClient } from '../../api/client'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { deadlineLabel, isOpportunityId, provinces } from './catalog'
import { checkedTime, officialLink, parseDetail } from './detail'
import type { PublicDetail } from './detail'
import { OpportunityReport } from './OpportunityReport'
import { OpportunityReadAloud } from '../voice/OpportunityReadAloud'
import './catalog.css'

type State = { status: 'idle' | 'loading' } | { status: 'loaded'; item: PublicDetail } | { status: 'error'; error: ApiError }
const initial = (): State => ({ status: 'idle' })
const methods = { online: '온라인', phone: '전화', visit: '방문', email: '이메일', mixed: '여러 방법' }

function OfficialReference({ value, label }: { value: string; label: string }) {
  const link = officialLink(value)
  return link ? <a className="button secondary" href={link.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{label} · {link.host} (새 창)</a>
    : <p>{label}: 확인된 공식 상세 주소가 없어 링크를 제공하지 않습니다.</p>
}

function DetailContent({ item }: { item: PublicDetail }) {
  return <>
    <article className="panel opportunity-detail">
      <p className="eyebrow">{item.activity_type === 'employment' ? '취업·공공일자리' : '봉사'} · 공고 버전 {item.version}</p>
      <h2>{item.title}</h2><p>{item.organization_name}</p>
      <OpportunityReadAloud key={`${item.id}:${item.version}`} item={item} />
      <p className="badge">{item.recruitment_status === 'closed' ? '모집 마감' : item.recruitment_status === 'open' ? '모집 중' : '모집 여부 확인 필요'}</p>
      {item.change_pending && <StatusNotice label="검수 상태" title="변경 확인 중">중요 변경을 검수하고 있습니다. 확인이 끝나기 전에는 이 공고로 추천·지원서를 만들 수 없습니다.</StatusNotice>}
      {item.recruitment_status === 'closed' && <p>마감된 공고입니다. 내용을 참고할 수 있지만 신청 안내 링크는 제공하지 않습니다.</p>}
      <dl className="detail-facts">
        <div><dt>활동 지역</dt><dd>{item.activity_region ? provinces[item.activity_region.province] : '지역 확인 필요'} · {item.location_text ?? '상세 장소 확인 필요'}</dd></div>
        <div><dt>원격 활동</dt><dd>{item.remote_allowed === null ? '확인 필요' : item.remote_allowed ? '가능' : '불가'}</dd></div>
        <div><dt>일정</dt><dd>{item.schedule_text ?? '일정 확인 필요'}{item.hours_per_week !== null && ` · 주 ${item.hours_per_week}시간`}</dd></div>
        <div><dt>보수</dt><dd>{item.paid === null ? '보수 여부 확인 필요' : item.paid ? '보수 있음' : '무보수'} · {item.compensation_text ?? '보수 상세 확인 필요'}</dd></div>
        <div><dt>마감</dt><dd>{deadlineLabel(item)}</dd></div>
      </dl>
      <h3>공식 원문 설명</h3><p className="user-text">{item.description_text ?? '제공된 원문 설명이 없습니다. 공식 원문에서 확인해 주세요.'}</p>
      {item.description_truncated && <p>원문이 길어 앞부분만 표시합니다. 전체 내용은 공식 원문에서 확인해 주세요.</p>}
      <h3>원문에 명시된 필수조건</h3>
      {item.requirements.length ? <ul>{item.requirements.map((requirement, index) => <li key={index}><span className="user-text">{requirement.source_evidence}</span>{requirement.clarity === 'needs_review' && <strong> · 조건 해석 확인 필요</strong>}</li>)}</ul>
        : <p>검수된 공고에 명시된 필수조건이 없습니다.</p>}
      <p>위 조건은 원문 안내이며, 내 지원 자격을 판정한 결과가 아닙니다. 조건 사이의 조합과 실제 자격은 공식 안내에서 확인해 주세요.</p>
      <h3>필요 서류</h3>{item.required_documents === null ? <p>필요 서류 확인 필요</p> : item.required_documents.length ? <ul>{item.required_documents.map((document, index) => <li key={index}>{document}</li>)}</ul> : <p>명시된 필요 서류가 없습니다. 최종 접수 안내도 확인해 주세요.</p>}
      <h3>신청 방법 · {methods[item.application_method]}</h3><p className="user-text">{item.application_instructions}</p>
      <p>실제 접수는 공식 신청처에서 직접 진행합니다. 링크를 여는 것만으로 신청이 완료되지 않으며, 다시잇다가 개인정보를 대신 제출하지 않습니다.</p>
      <div className="actions"><OfficialReference value={item.source_url} label="공식 원문 확인" />
        {item.recruitment_status === 'open' && !item.change_pending && <OfficialReference value={item.application_url} label="공식 신청 안내 확인" />}</div>
      {item.recruitment_status === 'unknown' && <p>모집 상태를 확인하기 전에는 신청 안내 링크를 제공하지 않습니다.</p>}
      <p className="catalog-note">원문 확인: {checkedTime(item.source_checked_at)} · 검수: {checkedTime(item.reviewed_at)} (한국시간). 현재 상태와 다를 수 있으므로 공식 원문도 확인해 주세요.</p>
    </article>
    <OpportunityReport key={`${item.id}:${item.version}`} id={item.id} version={item.version} />
    <Link className="button secondary" to={`/opportunities/${item.id}/preparation`}>공식 서류·접수 준비 안내 보기</Link>
    <StatusNotice title="개인 자격은 확정 프로필로 대조해 주세요">경험을 정리하고 프로필을 확정하면 추천 화면에서 공고 조건을 대조하고 지원서를 준비할 수 있습니다. <Link className="text-link" to="/start">AI 처리 안내를 확인하고 새 체험 시작</Link></StatusNotice>
  </>
}

function DetailRequest({ id }: { id: string }) {
  const [api] = useState(() => createApiClient())
  const scope = useMemoryScope(initial)
  const state = scope.value
  const active = useRef<AbortSignal | null>(null)
  const result = useRef<HTMLElement>(null)
  useEffect(() => { if (state.status === 'loaded' || state.status === 'error') result.current?.focus() }, [state.status])

  async function load() {
    if (active.current && !active.current.aborted) return
    scope.clear()
    scope.setValue({ status: 'loading' })
    await scope.run(async (signal): Promise<State> => {
      active.current = signal
      try {
        const { data } = await api.GET('/opportunities/{opportunity_id}', { signal, params: { path: { opportunity_id: id } } })
        return { status: 'loaded', item: parseDetail(data, id) }
      } catch (error) {
        return { status: 'error', error: error instanceof ApiError ? error : new ApiError('INVALID_RESPONSE') }
      } finally { if (active.current === signal) active.current = null }
    }, scope.setValue)
  }

  return <>
    <section ref={result} tabIndex={-1} aria-label="공고 상세 조회 결과">
      {state.status === 'idle' && <StatusNotice label="공개 상세" title="공고 정보를 불러와 주세요" actions={<Button onClick={() => void load()}>공고 정보 불러오기</Button>}>로그인이나 AI 처리 동의 없이 공고의 공식 안내와 모집 상태를 확인할 수 있습니다.</StatusNotice>}
      {state.status === 'loading' && <StatusNotice kind="loading" title="공고 정보를 확인하고 있어요" actions={<Button variant="secondary" onClick={scope.clear}>조회 취소하기</Button>}>최신 공고의 모집 상태와 조건을 조회합니다.</StatusNotice>}
      {state.status === 'error' && (state.error.code === 'NOT_FOUND' || state.error.status === 404
        ? <StatusNotice kind="error" title="이 공고를 찾을 수 없어요">삭제되었거나 공개가 종료된 공고일 수 있어요. 공개 검색에서 다른 공고를 찾아보세요.</StatusNotice>
        : <RequestError error={state.error} actions={state.error.code !== 'DAILY_QUOTA_EXCEEDED' ? <Button onClick={() => void load()}>공고 다시 조회</Button> : undefined} />)}
      {state.status === 'loaded' && <DetailContent item={state.item} />}
    </section>
    {state.status === 'loaded' && <Button variant="secondary" onClick={() => void load()}>최신 정보 다시 조회</Button>}
  </>
}

export function PublicOpportunityDetail() {
  const { id = '' } = useParams()
  return <div className="reading-width public-detail">
    <header className="page-heading"><p className="eyebrow">로그인 없이 · 공개 공고 상세</p><h1>공고의 조건을 함께 확인해요</h1><p>모집 상태·원문 조건·신청 방법을 살펴보세요.</p></header>
    {isOpportunityId(id) ? <DetailRequest key={id} id={id} /> : <StatusNotice kind="error" title="공고 주소를 확인해 주세요">올바른 공고 주소가 아닙니다. 공개 검색에서 공고를 다시 선택해 주세요.</StatusNotice>}
    <Link className="text-link" to="/opportunities">공개 공고 검색으로 →</Link>
  </div>
}
