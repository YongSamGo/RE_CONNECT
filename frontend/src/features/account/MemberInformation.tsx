import { useState } from 'react'
import { Button } from '../../ui/Button'
import { ServicePage } from '../../ui/ServicePage'

type MemberInformation = { name: string; age: string; phone: string; residence: string }

const initialInformation: MemberInformation = {
  name: '홍길동',
  age: '64세',
  phone: '010-0000-0000',
  residence: '서울특별시 마포구',
}

export function MemberInformationPage() {
  const [information, setInformation] = useState(initialInformation)
  const [draft, setDraft] = useState(initialInformation)
  const [editing, setEditing] = useState(false)
  const [message, setMessage] = useState('')

  function beginEdit() {
    setDraft(information)
    setMessage('')
    setEditing(true)
  }

  function cancelEdit() {
    setDraft(information)
    setMessage('')
    setEditing(false)
  }

  function saveEdit() {
    setInformation(draft)
    setEditing(false)
    setMessage('수정한 정보를 반영했습니다.')
  }

  return <ServicePage member title="나의 정보" className="member-information-page">
    <section className="member-info-panel" aria-labelledby="member-info-title">
      <h2 id="member-info-title">회원 정보</h2>
      {editing ? <form id="member-information-form" className="member-info-form" onSubmit={event => { event.preventDefault(); saveEdit() }}>
        <label>이름<input autoComplete="name" value={draft.name} onChange={event => setDraft({ ...draft, name: event.target.value })} /></label>
        <label>나이<input inputMode="numeric" value={draft.age} onChange={event => setDraft({ ...draft, age: event.target.value })} /></label>
        <label>연락처<input type="tel" autoComplete="tel" value={draft.phone} onChange={event => setDraft({ ...draft, phone: event.target.value })} /></label>
        <label>사는 곳<input autoComplete="address-level1" value={draft.residence} onChange={event => setDraft({ ...draft, residence: event.target.value })} /></label>
      </form> : <>
        <dl className="member-information-list">
          <dt>이름</dt><dd>{information.name}</dd>
          <dt>나이</dt><dd>{information.age}</dd>
          <dt>연락처</dt><dd>{information.phone}</dd>
          <dt>사는 곳</dt><dd>{information.residence}</dd>
        </dl>
      </>}
      <p role="status" className="member-preview-status">{message}</p>
    </section>
    <div className="member-info-edit-action">{editing ? <><Button type="submit" form="member-information-form">저장</Button><Button variant="secondary" onClick={cancelEdit}>편집 취소</Button></> : <Button variant="secondary" onClick={beginEdit}>정보 편집</Button>}</div>
  </ServicePage>
}
