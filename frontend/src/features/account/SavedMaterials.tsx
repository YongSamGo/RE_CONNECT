import { useState } from 'react'
import { Link } from 'react-router-dom'
import { ApiError } from '../../api/errors'
import { useRequest, required } from '../../state/useRequest'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { RequestError, StatusNotice } from '../../ui/StatusNotice'
import { invalid, isOpportunityId, record, text } from '../public-opportunities/catalog'
import { parseSession } from './session'

type Material = { id: string; title: string; version: number }
type Saved = { experiences: string[] | null; documents: Material[]; page: number; total: number; message?: string; selected?: { id: string; title: string; introduction: string; motivation: string; review: boolean } }
function version(value: unknown): number { return typeof value === 'number' && Number.isSafeInteger(value) && value >= 1 ? value : invalid() }
function parseList(value: unknown): Pick<Saved, 'documents' | 'page' | 'total'> {
  const data = record(value)
  if (!Array.isArray(data.items) || typeof data.total !== 'number' || !Number.isSafeInteger(data.total) || data.total < 0) return invalid()
  return { page: version(data.page), total: data.total, documents: data.items.map((item) => {
    const document = record(item)
    const id = text(document.document_id, 36)
    if (!isOpportunityId(id)) return invalid()
    return { id, title: text(document.opportunity_title, 200), version: version(document.version) }
  }) }
}

export function SavedMaterials() {
  const request = useRequest<Saved>()
  const [confirmed, setConfirmed] = useState(false)
  const [documentConfirmed, setDocumentConfirmed] = useState(false)
  const state = request.state
  const pending = state.status === 'pending'
  const saved = state.status === 'success' ? state.data : null
  const load = (page = 1) => request.run(async (api, signal) => {
    const session = parseSession(required((await api.GET('/me', { signal })).data))
    if (!session.authenticated) throw new ApiError('UNAUTHENTICATED', 401)
    const profile = record(required((await api.GET('/profiles/me', { signal })).data))
    let experiences: string[] | null = null
    if (profile.saved !== null) {
      const content = record(record(profile.saved).content)
      if (!Array.isArray(content.experiences)) return invalid()
      experiences = content.experiences.map((experience) => text(record(experience).description, 2000))
    }
    return { experiences, ...parseList(required((await api.GET('/drafts', { signal, params: { query: { page, page_size: 10 } } })).data)) }
  })
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">내 정보 · 저장 자료</p><h1>내가 저장한 자료를 확인해요</h1><p>조회·삭제는 서버에서 현재 회원의 자료에만 적용합니다.</p></header>
    <Button pending={pending} onClick={() => { setDocumentConfirmed(false); setConfirmed(false); void load() }}>저장 자료 불러오기</Button>
    {state.status === 'error' && <RequestError error={state.error} />}
    {pending && <p role="status">저장 자료를 확인하고 있어요.</p>}
    {saved && <><section className="panel"><h2>저장 프로필의 경험</h2>{saved.experiences === null ? <p>저장한 프로필이 없습니다.</p> : <>
      <ul>{saved.experiences.map((experience, index) => <li className="user-text" key={index}>{experience}</li>)}</ul>
      <p>프로필 삭제는 모든 버전과 연결된 지원서를 함께 삭제합니다.</p><CheckboxField label="저장 프로필과 연결된 지원서를 모두 삭제할게요." checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />
      <Button variant="secondary" disabled={!confirmed} onClick={() => { setConfirmed(false); void request.run(async (api, signal) => { await api.DELETE('/profiles/me', { signal }); return { experiences: null, documents: [], page: 1, total: 0, message: '저장 프로필과 연결된 지원서 삭제 요청이 완료되었습니다.' } }) }}>저장 프로필과 지원서 삭제</Button>
    </>}</section>
    <section className="panel"><h2>저장 지원서</h2>{saved.documents.length === 0 ? <p>이 페이지에 저장 지원서가 없습니다.</p> : <ul>{saved.documents.map((document) => <li key={document.id}><p>{document.title} · 버전 {document.version}</p><div className="actions">
      <Button variant="secondary" onClick={() => { setConfirmed(false); setDocumentConfirmed(false); void request.run(async (api, signal) => {
        const result = record(required((await api.GET('/drafts/{document_id}', { signal, params: { path: { document_id: document.id } } })).data))
        if (result.document_id !== document.id || result.version !== document.version || !Array.isArray(result.review_reasons)) return invalid()
        if (typeof result.self_introduction !== 'string' || result.self_introduction.length > 2000 || typeof result.motivation !== 'string' || result.motivation.length > 2000) return invalid()
        return { ...saved, message: undefined, selected: { id: document.id, title: document.title, introduction: result.self_introduction, motivation: result.motivation, review: result.review_reasons.length > 0 } }
      }) }}>내용 보기 · {document.title}</Button>
    </div></li>)}</ul>}
    <div className="actions"><Button variant="secondary" disabled={saved.page <= 1} onClick={() => void load(saved.page - 1)}>이전 페이지</Button><p>{saved.page}페이지 · 전체 {saved.total}건</p><Button variant="secondary" disabled={saved.page * 10 >= saved.total} onClick={() => void load(saved.page + 1)}>다음 페이지</Button></div></section>
    {saved.selected && <section className="panel"><h2>{saved.selected.title}</h2>{saved.selected.review && <StatusNotice label="재검토 필요" title="근거 정보가 변경되었습니다">프로필 또는 공고가 변경되었습니다. 공식 조건과 내용을 다시 확인해 주세요.</StatusNotice>}<h3>자기소개</h3><p className="user-text">{saved.selected.introduction}</p><h3>지원동기</h3><p className="user-text">{saved.selected.motivation}</p><CheckboxField label="이 지원서의 모든 저장 버전을 삭제할게요." checked={documentConfirmed} onChange={(event) => setDocumentConfirmed(event.target.checked)} /><Button variant="secondary" disabled={!documentConfirmed} onClick={() => { const id = saved.selected!.id; setDocumentConfirmed(false); void request.run(async (api, signal) => { await api.DELETE('/drafts/{document_id}', { signal, params: { path: { document_id: id } } }); return { ...saved, selected: undefined, documents: saved.documents.filter((document) => document.id !== id), total: Math.max(0, saved.total - 1), message: '선택한 지원서의 모든 저장 버전 삭제 요청이 완료되었습니다.' } }) }}>선택한 지원서 삭제</Button></section>}
    </>}
    <p role="status">{saved?.message}</p><Link className="text-link" to="/me">내 정보로 →</Link>
  </div>
}
