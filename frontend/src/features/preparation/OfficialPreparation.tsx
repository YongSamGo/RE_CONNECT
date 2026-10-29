import { useCallback, useEffect, useRef } from 'react'
import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router-dom'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { isOpportunityId } from '../public-opportunities/catalog'
import { officialLink } from '../public-opportunities/detail'
import { parsePreparation, type Preparation } from './official'
import { ServicePage } from '../../ui/ServicePage'

const methods = { online: '온라인', phone: '전화', visit: '방문', email: '이메일', mixed: '여러 방법' }
function Reference({ url, label }: { url: string; label: string }) {
  const link = officialLink(url)
  return link ? <a className="button secondary" href={link.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer" aria-label={`${label}, 새 창에서 열림`}>{label}</a> : <p>{label}: 확인된 공식 주소가 없어 링크를 제공하지 않습니다.</p>
}
export function OfficialPreparationContent({ item, showDraftNotice = true }: { item: Preparation; showDraftNotice?: boolean }) {
  const checks = useMemoryScope<number[]>(() => [])
  const available = item.recruitment_status === 'open' && !item.change_pending
  return <>
    <section className="panel"><h2>공식 서류와 접수 절차</h2><p>공고 버전 {item.opportunity.version} / 접수 방법: {methods[item.application_method]}</p>
      <p>{item.application_instructions || '접수 절차가 명시되지 않았어요. 공식 원문에서 확인해 주세요.'}</p>
      <p>마감 안내: {item.deadline_date ?? '날짜 확인 필요'}{item.deadline_at && ` / ${new Date(item.deadline_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} (한국시간)`}</p>
      {!available && <StatusNotice title={item.change_pending ? '공고 변경 내용을 확인하고 있어요' : item.recruitment_status === 'closed' ? '모집이 마감된 공고예요' : '모집 상태를 확인해 주세요'}>현재 신청 가능 여부를 확인할 수 없어 신청 안내 링크와 준비 체크를 제공하지 않습니다. 공식 원문을 확인해 주세요.</StatusNotice>}
      {item.required_documents === null ? <p>공고에 제출 서류가 명시되지 않았어요. 서류가 필요 없다는 뜻은 아니에요. 공식 원문이나 담당 기관에 확인해 주세요.</p>
        : item.required_documents.length === 0 ? <p>서버가 제공한 제출 서류 목록이 비어 있어요. 공식 원문에서 실제 필요 서류를 확인해 주세요.</p>
          : <fieldset><legend>공고에 명시된 준비 서류</legend>{item.required_documents.map((document, index) => <CheckboxField key={index} label={document} checked={checks.value.includes(index)} disabled={!available} onChange={event => checks.setValue(previous => event.target.checked ? [...previous, index] : previous.filter(value => value !== index))} />)}</fieldset>}
      <p role="status">{available && item.required_documents?.length ? `${item.required_documents.length}개 중 ${checks.value.length}개 확인` : ''}</p>
      <p className="quiet">체크는 나의 준비 메모예요. 체크해도 서류 제출이나 자격 충족, 신청 완료를 뜻하지는 않아요. 이 화면을 나가거나 새로 조회할 때, 새로고침하거나 종료할 때 지워져요.</p>
      <div className="actions"><Reference url={item.source_url} label="공식 원문 확인" />{available && <Reference url={item.application_url} label="공식 신청 안내 확인" />}</div>
      <p className="quiet">새 창으로 이동해도 신청 완료로 기록하지 않아요. 서류나 개인정보를 대신 제출하지 않아요.</p>
    </section>
    {showDraftNotice && <StatusNotice title="확정 경험에서 공고를 선택하면 지원서를 준비할 수 있어요">체험의 추천 화면에서 이 공고의 신청 준비를 열어 주세요. 공개 안내만 조회할 때는 개인 프로필이나 지원서를 만들지 않습니다.</StatusNotice>}
  </>
}
function Request({ id, withDraft, onApplicationUrl }: { id: string; withDraft: boolean; onApplicationUrl?: (url: string) => void }) {
  const request = useRequest<Preparation>()
  const result = useRef<HTMLElement>(null)
  const { state } = request
  useEffect(() => { if (state.status === 'error') result.current?.focus({ preventScroll: true }) }, [state.status])
  useEffect(() => { onApplicationUrl?.(state.status === 'success' && state.data.recruitment_status === 'open' && !state.data.change_pending ? state.data.application_url : '') }, [state, onApplicationUrl])
  const load = () => request.run(async (api, signal) => parsePreparation(required((await api.GET('/opportunities/{opportunity_id}/preparation', { signal, params: { path: { opportunity_id: id } } })).data), id))
  useEffect(() => {
    if (withDraft) void load()
  // useRequest.run is recreated on each render; the request runs once per selected opportunity.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [withDraft, id])
  return !withDraft || state.status !== 'success' ? <section ref={result} tabIndex={-1} aria-label="공식 준비 안내 조회 결과">
    {state.status === 'idle' && !withDraft && <StatusNotice title="공식 신청 안내를 불러와 주세요" actions={<Button onClick={() => void load()}>공식 신청 안내 확인</Button>}>공개된 신청 정보를 확인합니다.</StatusNotice>}
    {state.status === 'pending' && <StatusNotice kind="loading" title={withDraft ? '공식 신청 방법을 확인하고 있어요' : '공식 신청 안내를 확인하고 있어요'}>최신 공고 정보를 조회합니다.</StatusNotice>}
    {state.status === 'error' && <RequestError error={state.error} actions={<Button onClick={() => void load()}>공식 신청 안내 다시 확인</Button>} />}
    {state.status === 'success' && !withDraft && <OfficialPreparationContent item={state.data} showDraftNotice />}
  </section> : null
}
export function OfficialPreparation({ opportunityId, withDraft = false, children }: { opportunityId?: string; withDraft?: boolean; children?: ReactNode | ((applicationUrl: string) => ReactNode) } = {}) {
  const params = useParams()
  const id = opportunityId ?? params.id ?? ''
  const application = useMemoryScope<{ id: string; url: string } | null>(() => null)
  const updateApplication = application.setValue
  const setApplicationUrl = useCallback((url: string) => updateApplication({ id, url }), [id, updateApplication])
  const applicationUrl = application.value?.id === id ? application.value.url : ''
  const content = typeof children === 'function' ? children(applicationUrl) : children
  const detailHref = isOpportunityId(id) ? `/opportunities/${id}${params.journeyId ? `?journeyId=${params.journeyId}` : ''}` : '/opportunities'
  return <ServicePage title={withDraft ? '다음 내용으로 지원서를 작성할게요' : '공고 신청 안내'} className={withDraft ? 'application-page' : ''}>
    {withDraft && content}
    {isOpportunityId(id) ? <Request key={id} id={id} withDraft={withDraft} onApplicationUrl={withDraft ? setApplicationUrl : undefined} /> : !id ?
      <div className="service-entry"><h2>준비할 공고를 선택해 주세요</h2><p>선택한 공고의 서류와 접수 방법을 확인할 수 있습니다.</p><Link className="button primary" to="/opportunities">공고 선택하기</Link></div>
      : <StatusNotice kind="error" title="공고 주소를 확인해 주세요">올바른 공고 주소가 아닙니다. 공개 목록에서 공고를 다시 선택해 주세요.</StatusNotice>}
    {!withDraft && content}
    <Link className="text-link" to={detailHref}>공고 화면으로 돌아가기</Link>
  </ServicePage>
}
