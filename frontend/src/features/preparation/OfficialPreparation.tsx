import { useEffect, useRef } from 'react'
import { Link, useParams } from 'react-router-dom'
import { required, useRequest } from '../../state/useRequest'
import { useMemoryScope } from '../../state/useMemoryScope'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { isOpportunityId } from '../public-opportunities/catalog'
import { officialLink } from '../public-opportunities/detail'
import { parsePreparation, type Preparation } from './official'

const methods = { online: '온라인', phone: '전화', visit: '방문', email: '이메일', mixed: '여러 방법' }
function Reference({ url, label }: { url: string; label: string }) {
  const link = officialLink(url)
  return link ? <a className="button secondary" href={link.href} target="_blank" rel="noopener noreferrer" referrerPolicy="no-referrer">{label} · {link.host} (새 창)</a> : <p>{label}: 확인된 공식 주소가 없어 링크를 제공하지 않습니다.</p>
}
function Content({ item }: { item: Preparation }) {
  const checks = useMemoryScope<number[]>(() => [])
  const available = item.recruitment_status === 'open' && !item.change_pending
  return <>
    <section className="panel"><h2>공식 서류와 접수 절차</h2><p>공고 버전 {item.opportunity.version} · 접수 방법: {methods[item.application_method]}</p>
      <p>{item.application_instructions || '접수 절차가 명시되지 않았어요. 공식 원문에서 확인해 주세요.'}</p>
      <p>마감 안내: {item.deadline_date ?? '날짜 확인 필요'}{item.deadline_at && ` · ${new Date(item.deadline_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' })} (한국시간)`}</p>
      {!available && <StatusNotice title={item.change_pending ? '공고 변경 내용을 확인하고 있어요' : item.recruitment_status === 'closed' ? '모집이 마감된 공고예요' : '모집 상태를 확인해 주세요'}>현재 신청 가능 여부를 확인할 수 없어 신청 안내 링크와 준비 체크를 제공하지 않습니다. 공식 원문을 확인해 주세요.</StatusNotice>}
      {item.required_documents === null ? <p>공고에 제출 서류가 명시되지 않았어요. 서류가 필요 없다는 뜻은 아니에요. 공식 원문이나 담당 기관에 확인해 주세요.</p>
        : item.required_documents.length === 0 ? <p>서버가 제공한 제출 서류 목록이 비어 있어요. 공식 원문에서 실제 필요 서류를 확인해 주세요.</p>
          : <fieldset><legend>공고에 명시된 준비 서류</legend>{item.required_documents.map((document, index) => <CheckboxField key={index} label={document} checked={checks.value.includes(index)} disabled={!available} onChange={event => checks.setValue(previous => event.target.checked ? [...previous, index] : previous.filter(value => value !== index))} />)}</fieldset>}
      <p role="status">{available && item.required_documents?.length ? `${item.required_documents.length}개 중 ${checks.value.length}개 확인` : ''}</p>
      <p className="quiet">체크는 나의 준비 메모예요. 서류 제출·자격 충족·신청 완료를 뜻하지 않아요. 이 화면을 나가거나 새로 조회·새로고침·종료하면 지워져요.</p>
      <div className="actions"><Reference url={item.source_url} label="공식 원문 확인" />{available && <Reference url={item.application_url} label="공식 신청 안내 확인" />}</div>
      <p className="quiet">새 창으로 이동해도 신청 완료로 기록하지 않으며, 서류·개인정보를 대신 제출하지 않습니다.</p>
    </section>
    <StatusNotice title="공고에 연결된 지원서는 준비 중이에요">확정 프로필에 근거한 생성·직접 작성·서버 승인과 별도 저장은 아직 연결되지 않았습니다. 현재 문장 작성 미리보기는 이 공고의 지원서로 처리하지 않습니다.</StatusNotice>
  </>
}
function Request({ id }: { id: string }) {
  const request = useRequest<Preparation>()
  const result = useRef<HTMLElement>(null)
  const { state } = request
  useEffect(() => { if (state.status === 'success' || state.status === 'error') result.current?.focus() }, [state.status])
  const load = () => request.run(async (api, signal) => parsePreparation(required((await api.GET('/opportunities/{opportunity_id}/preparation', { signal, params: { path: { opportunity_id: id } } })).data), id))
  return <section ref={result} tabIndex={-1} aria-label="공식 준비 안내 조회 결과">
    {state.status === 'idle' && <StatusNotice title="공식 준비 안내를 불러와 주세요" actions={<Button onClick={() => void load()}>공식 준비 안내 불러오기</Button>}>로그인·AI 동의 없이 공개 안내를 조회합니다. 서버 응답이 없으면 오류를 안내하며 서류나 절차를 만들어 채우지 않습니다.</StatusNotice>}
    {state.status === 'pending' && <StatusNotice kind="loading" title="공식 준비 안내를 확인하고 있어요" actions={<Button variant="secondary" onClick={request.clear}>조회 취소하기</Button>}>최신 공고 버전의 서류와 접수 절차를 조회합니다.</StatusNotice>}
    {state.status === 'error' && <RequestError error={state.error} actions={<Button onClick={() => void load()}>준비 안내 다시 조회</Button>} />}
    {state.status === 'success' && <><Content item={state.data} /><Button variant="secondary" onClick={() => void load()}>최신 준비 안내 다시 조회</Button></>}
  </section>
}
export function OfficialPreparation() {
  const { id = '' } = useParams()
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">공고에 명시된 정보로 준비해요</p><h1>신청 준비를 차근차근</h1><p>공식 서류·절차·접수 방법을 확인해 주세요.</p></header>
    {isOpportunityId(id) ? <Request key={id} id={id} /> : <StatusNotice kind="error" title="공고 주소를 확인해 주세요">올바른 공고 주소가 아닙니다. 공개 목록에서 공고를 다시 선택해 주세요.</StatusNotice>}
    <Link className="text-link" to={isOpportunityId(id) ? `/opportunities/${id}` : '/opportunities'}>공고 화면으로 돌아가기 →</Link>
  </div>
}
