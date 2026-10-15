import { useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { StatusNotice } from '../../ui/StatusNotice'
import { provinces } from '../public-opportunities/catalog'
import type { Province } from '../public-opportunities/catalog'
import type { ProfilePreferences } from './model'

export function ProfilePreview({ experience, preferences, onChange }: { experience: string; preferences: ProfilePreferences; onChange: (value: ProfilePreferences) => void }) {
  const [errors, setErrors] = useState<FieldError[]>([])
  function review() {
    const next: FieldError[] = []
    if (!experience.trim()) next.push({ fieldId: 'profile-experience-link', message: '경험을 한 가지 이상 적어 주세요.' })
    if (!preferences.regions.length) next.push({ fieldId: 'profile-region-seoul', message: '희망 활동 지역을 한 곳 이상 골라 주세요.' })
    if (!preferences.activities.length) next.push({ fieldId: 'profile-activity-employment', message: '희망 활동 유형을 한 가지 이상 골라 주세요.' })
    setErrors(next)
    onChange({ ...preferences, reviewed: next.length === 0 })
  }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">02 · 프로필 확인 미리보기</p><h1>내 경험을 다시 살펴봐요</h1><p>직접 적은 경험과 희망 조건을 확인해 주세요. 아직 서버에서 확정된 프로필은 아닙니다.</p></header>
    <FormErrorSummary errors={errors} />
    <section className="panel"><h2>내가 적은 경험</h2>{experience.trim() ? <p className="user-text">{experience}</p> : <p>아직 적은 경험이 없어요. 떠오르는 경험부터 한 가지 적어보세요.</p>}<Link id="profile-experience-link" className="button secondary" to="/conversation">경험 수정하기</Link></section>
    <section className="panel"><h2>희망 활동 조건</h2><p>거주 자격을 판정하는 주소가 아닌, 활동하고 싶은 지역입니다. 시·군·구 선택은 서버의 지역 목록 연결 후 제공합니다.</p>
      <fieldset><legend>희망 활동 지역 (한 곳 이상)</legend>{(Object.keys(provinces) as Province[]).map((province) => <CheckboxField key={province} id={`profile-region-${province}`} label={provinces[province]} checked={preferences.regions.includes(province)} onChange={(event) => { setErrors([]); onChange({ ...preferences, regions: event.target.checked ? [...preferences.regions, province] : preferences.regions.filter((value) => value !== province), reviewed: false }) }} />)}</fieldset>
      <fieldset><legend>희망 활동 유형 (한 가지 이상)</legend>{(['employment', 'volunteering'] as const).map((activity) => <CheckboxField key={activity} id={`profile-activity-${activity}`} label={activity === 'employment' ? '취업·공공일자리' : '봉사'} checked={preferences.activities.includes(activity)} onChange={(event) => { setErrors([]); onChange({ ...preferences, activities: event.target.checked ? [...preferences.activities, activity] : preferences.activities.filter((value) => value !== activity), reviewed: false }) }} />)}</fieldset>
      <Button onClick={review}>작성 항목 확인하기</Button><p role="status">{preferences.reviewed ? '경험과 희망 조건을 확인했습니다. 화면 미리보기에서만 유지하며 서버 확정·회원 저장은 진행하지 않았습니다.' : ''}</p>
    </section>
    <StatusNotice title="프로필 확정과 역할 후보는 연결 준비 중이에요">서버에서 확정한 경험에 근거해 역할 후보와 추천을 제공할 예정입니다. 이 미리보기 선택만으로 역할·자격·추천 결과를 만들지 않습니다.</StatusNotice>
    <div className="actions"><Link className="button secondary" to="/preparation">지원 내용 직접 작성해 보기</Link><Link className="text-link" to="/opportunities">공개 공고 화면 살펴보기 →</Link></div>
  </div>
}
