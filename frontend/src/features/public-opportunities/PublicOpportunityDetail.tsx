import type { ReactNode } from 'react'
import { useEntryAction } from '../../state/useEntryAction'
import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { createApiClient } from '../../api/client'
import { ApiError } from '../../api/errors'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { deadlineLabel, isOpportunityId, provinces } from './catalog'
import { officialLink, parseDetail } from './detail'
import type { PublicDetail } from './detail'
import { OpportunityReadAloud } from '../voice/OpportunityReadAloud'
import { ServicePage } from '../../ui/ServicePage'
import { OpportunityMatch } from '../recommendations/OpportunityMatch'
import './catalog.css'

type State = { status: 'idle' | 'loading' } | { status: 'loaded'; item: PublicDetail } | { status: 'error'; error: ApiError }
const initial = (): State => ({ status: 'idle' })
const methods = { online: '온라인', phone: '전화', visit: '방문', email: '이메일', mixed: '여러 방법' }

function OfficialReference({ value, label }: { value: string; label: string }) {
  const link = officialLink(value)
  return link ? <a className="button secondary" href={link.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" aria-label={`${label}, 새 창에서 열림`}>{label}</a>
    : <p>{label}: 확인된 공식 상세 주소가 없어 링크를 제공하지 않습니다.</p>
}

function DetailBlock({ title, summary, children }: { title: string; summary: string; children: ReactNode }) {
  return <details className="opportunity-info-block">
    <summary><span className="opportunity-info-heading"><strong>{title}</strong><span>{summary}</span></span><span className="opportunity-info-action"><span className="opportunity-info-open">자세히 보기</span><span className="opportunity-info-close">접기</span></span></summary>
    <div className="opportunity-info-content">{children}</div>
  </details>
}

function DetailContent({ item, journeyId }: { item: PublicDetail; journeyId?: string }) {
  return <>
    <article className="panel opportunity-detail">
      <p className="eyebrow">{item.activity_type === 'employment' ? '취업 및 공공일자리' : '봉사'}</p>
      <h2>{item.title}</h2><p>{item.organization_name}</p>
      <div className="opportunity-primary-actions">
        <p className="badge">{item.recruitment_status === 'closed' ? '모집 마감' : item.recruitment_status === 'open' ? '모집 중' : '모집 여부 확인 필요'}</p>
      </div>
      {item.change_pending && <StatusNotice label="검수 상태" title="변경 확인 중">중요한 변경 사항을 확인하고 있어요. 확인이 끝나기 전에는 이 공고를 추천하거나 지원서를 만들 수 없어요.</StatusNotice>}
      {item.recruitment_status === 'closed' && <p>마감된 공고입니다. 내용을 참고할 수 있지만 신청 안내 링크는 제공하지 않습니다.</p>}
      <div className="opportunity-info-list">
        <DetailBlock title="활동 정보" summary={[item.activity_region ? provinces[item.activity_region.province] : '지역 확인 필요', item.schedule_text ?? '일정 확인 필요'].join(', ')}>
          <dl className="detail-facts">
            <div><dt>활동 장소</dt><dd>{item.location_text ?? '상세 장소 확인 필요'}</dd></div>
            <div><dt>원격 활동</dt><dd>{item.remote_allowed === null ? '확인 필요' : item.remote_allowed ? '가능' : '불가'}</dd></div>
            <div><dt>주당 시간</dt><dd>{item.hours_per_week === null ? '확인 필요' : `주 ${item.hours_per_week}시간`}</dd></div>
          </dl>
        </DetailBlock>
        <DetailBlock title="보수와 마감" summary={`${item.paid === null ? '보수 확인 필요' : item.paid ? '보수 있음' : '무보수'}, ${deadlineLabel(item)}`}>
          <dl className="detail-facts">
            <div><dt>보수 상세</dt><dd>{item.compensation_text ?? '공식 안내에서 확인해 주세요.'}</dd></div>
            <div><dt>마감</dt><dd>{deadlineLabel(item)}</dd></div>
          </dl>
        </DetailBlock>
      </div>
      <DetailBlock title="공고 읽어주기" summary="음성으로 듣기"><OpportunityReadAloud key={`${item.id}:${item.version}`} item={item} /></DetailBlock>
      {journeyId && <OpportunityMatch key={`${journeyId}:${item.id}:${item.version}`} journeyId={journeyId} opportunity={{ id: item.id, version: item.version }} />}
      <div className="opportunity-info-list">
        <DetailBlock title="공고 설명" summary={item.description_text ? item.description_text.slice(0, 90) : '공식 원문에서 확인해 주세요.'}>
          <p className="user-text">{item.description_text ?? '제공된 원문 설명이 없습니다. 공식 원문에서 확인해 주세요.'}</p>
          {item.description_truncated && <p>원문이 길어 앞부분만 표시합니다. 전체 내용은 공식 원문에서 확인해 주세요.</p>}
        </DetailBlock>
        <DetailBlock title="지원 조건과 서류" summary={`${item.requirements.length}개 조건, ${item.required_documents?.length ?? '확인 필요'}개 서류`}>
          <h3>원문에 명시된 필수조건</h3>
          {item.requirements.length ? <ul>{item.requirements.map((requirement, index) => <li key={index}><span className="user-text">{requirement.source_evidence}</span>{requirement.clarity === 'needs_review' && <strong> (조건 해석 확인 필요)</strong>}</li>)}</ul>
            : <p>검수된 공고에 명시된 필수조건이 없습니다.</p>}
          <p>지원 조건은 공식 안내에서 다시 확인해 주세요.</p>
          <h3>필요 서류</h3>{item.required_documents === null ? <p>필요 서류 확인 필요</p> : item.required_documents.length ? <ul>{item.required_documents.map((document, index) => <li key={index}>{document}</li>)}</ul> : <p>명시된 필요 서류가 없습니다. 최종 접수 안내도 확인해 주세요.</p>}
        </DetailBlock>
        <DetailBlock title={`신청 방법: ${methods[item.application_method]}`} summary="신청 절차 확인">
          <p className="user-text">{item.application_instructions}</p>
          {item.recruitment_status === 'open' && !item.change_pending && <p>신청은 공식 신청처에서 직접 진행해 주세요.</p>}
        </DetailBlock>
      </div>
      <div className="actions"><OfficialReference value={item.source_url} label="공식 원문 확인" />
        {journeyId && item.recruitment_status === 'open' && !item.change_pending && <OfficialReference value={item.application_url} label="공식 신청 안내 확인" />}</div>
      {item.recruitment_status === 'unknown' && <p>모집 상태를 확인하기 전에는 신청 안내 링크를 제공하지 않습니다.</p>}
      <nav className="opportunity-detail-navigation" aria-label="공고 이동">
        {journeyId && item.recruitment_status === 'open' && !item.change_pending && <Link className="button primary" state={{ generateDraft: true }} to={`/journeys/${journeyId}/opportunities/${item.id}/application`}>지원하기</Link>}
        {!journeyId && item.recruitment_status === 'open' && !item.change_pending && <OfficialReference value={item.application_url} label="지원하기" />}
        <Link className="button secondary" to="/opportunities?browse=all">다른 공고 둘러보기</Link>
        <Link className="button secondary" to="/opportunities">공고 검색하기</Link>
      </nav>
    </article>
  </>
}

function DetailRequest({ id, journeyId }: { id: string; journeyId?: string }) {
  const [api] = useState(() => createApiClient())
  const scope = useMemoryScope(initial)
  const state = scope.value
  const active = useRef<AbortSignal | null>(null)
  const result = useRef<HTMLElement>(null)
  useEffect(() => { if (state.status === 'error') result.current?.focus({ preventScroll: true }) }, [state.status])

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

  useEntryAction(load, true, id)

  return <>
    <section ref={result} tabIndex={-1} aria-label="공고 상세 조회 결과">
      {state.status === 'idle' && <StatusNotice label="공개 상세" title="공고 정보를 불러와 주세요" actions={<Button onClick={() => void load()}>공고 정보 불러오기</Button>}>로그인이나 AI 처리 동의 없이 공고의 공식 안내와 모집 상태를 확인할 수 있습니다.</StatusNotice>}
      {state.status === 'loading' && <StatusNotice kind="loading" title="공고 정보를 확인하고 있어요" actions={<Button variant="secondary" onClick={scope.clear}>조회 취소하기</Button>}>최신 공고의 모집 상태와 조건을 조회합니다.</StatusNotice>}
      {state.status === 'error' && (state.error.code === 'NOT_FOUND' || state.error.status === 404
        ? <StatusNotice kind="error" title="이 공고를 찾을 수 없어요">삭제되었거나 공개가 종료된 공고일 수 있어요. 공개 검색에서 다른 공고를 찾아보세요.</StatusNotice>
        : <RequestError error={state.error} actions={state.error.code !== 'DAILY_QUOTA_EXCEEDED' ? <Button onClick={() => void load()}>공고 다시 조회</Button> : undefined} />)}
      {state.status === 'loaded' && <DetailContent item={state.item} journeyId={journeyId} />}
    </section>
  </>
}

export function PublicOpportunityDetail() {
  const { id = '' } = useParams()
  const location = useLocation()
  const candidate: unknown = location.state?.journeyId ?? new URLSearchParams(location.search).get('journeyId')
  const journeyId = typeof candidate === 'string' && isOpportunityId(candidate) ? candidate : undefined
  return <ServicePage title="공고 상세"><div className="public-detail">
    {isOpportunityId(id) ? <DetailRequest key={id} id={id} journeyId={journeyId} /> : !id ?
      <div className="service-entry"><h2>공고를 선택해 주세요</h2><p>공고를 선택하면 모집 조건과 신청 방법을 확인할 수 있습니다.</p><Link className="button primary" to="/opportunities">공고 살펴보기</Link></div>
      : <StatusNotice kind="error" title="공고 주소를 확인해 주세요">올바른 공고 주소가 아닙니다. 공개 검색에서 공고를 다시 선택해 주세요.</StatusNotice>}
  </div></ServicePage>
}
