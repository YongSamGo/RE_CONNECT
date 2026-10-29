import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Button } from '../../ui/Button'
import { CheckboxField } from '../../ui/Fields'
import { FormErrorSummary } from '../../ui/FormErrorSummary'
import type { FieldError } from '../../ui/FormErrorSummary'
import { RequestError } from '../../ui/StatusNotice'
import { required, useRequest } from '../../state/useRequest'
import { provinces } from '../public-opportunities/catalog'
import type { Province } from '../public-opportunities/catalog'
import type { ProfilePreferences } from './model'
import { parseRegionCatalog, regionsMatchCatalog } from '../regions/catalog'
import type { Region, RegionCatalog } from '../regions/catalog'

export function ProfilePreview({ experience, preferences, onChange }: { experience: string; preferences: ProfilePreferences; onChange: (value: ProfilePreferences) => void }) {
  const [errors, setErrors] = useState<FieldError[]>([])
  const [choosing, setChoosing] = useState(false)
  const heading = useRef<HTMLHeadingElement>(null)
  const previousStep = useRef(choosing)
  useEffect(() => {
    if (previousStep.current === choosing) return
    previousStep.current = choosing
    heading.current?.focus()
  }, [choosing])
  const request = useRequest<RegionCatalog>()
  const catalog = request.state.status === 'success' ? request.state.data : null
  const pending = request.state.status === 'pending'
  function changeRegions(regions: Region[]) {
    if (pending || regions.length > 10) return
    setErrors([]); onChange({ ...preferences, regions, reviewed: false })
  }
  function loadRegions() {
    if (pending) return
    setErrors([]); onChange({ ...preferences, reviewed: false })
    void request.run(async (api, signal) => parseRegionCatalog(required((await api.GET('/regions', { signal })).data)))
  }
  function review() {
    if (pending) return
    const next: FieldError[] = []
    if (!experience.trim()) next.push({ fieldId: 'profile-experience-link', message: '경험을 한 가지 이상 적어 주세요.' })
    if (!preferences.regions.length) next.push({ fieldId: 'profile-region-seoul', message: '희망 활동 지역을 한 곳 이상 골라 주세요.' })
    else if (!regionsMatchCatalog(preferences.regions, catalog)) next.push({ fieldId: 'profile-load-regions', message: '시군구 목록을 불러와 선택한 지역을 확인해 주세요. 목록에 없는 선택은 직접 변경하거나 제거해 주세요.' })
    if (!preferences.activities.length) next.push({ fieldId: 'profile-activity-employment', message: '희망 활동 유형을 한 가지 이상 골라 주세요.' })
    setErrors(next)
    onChange({ ...preferences, reviewed: next.length === 0 })
  }
  return <div className="reading-width"><header className="page-heading"><p className="eyebrow">{choosing ? '활동 조건 선택' : '작성 내용 확인'}</p><h1 ref={heading} tabIndex={-1}>{choosing ? '어디에서 어떤 활동을 하고 싶으세요?' : '내 경험을 다시 살펴봐요'}</h1><p>{choosing ? '활동하고 싶은 지역과 활동 유형을 골라 주세요.' : '입력한 내용이 맞는지 읽어 주세요.'}</p></header>
    {!choosing ? <>
      <section className="panel profile-experience"><h2>내가 적은 경험</h2>{experience.trim() ? <p className="user-text">{experience}</p> : <p>아직 적은 경험이 없어요. 한 가지를 먼저 적어 주세요.</p>}</section>
      <div className="actions"><Button disabled={!experience.trim()} onClick={() => setChoosing(true)}>활동 조건 고르기</Button><Link className="text-link" to="/conversation">경험 수정하기</Link></div>
      <p className="quiet">이 화면에서는 서버에 확정하거나 저장하지 않아요.</p>
    </> : <>
    <FormErrorSummary errors={errors} />
    <section className="panel"><h2>희망 활동 지역</h2><p>합계 10곳까지 고를 수 있어요. 거주 자격을 판정하는 데 쓰지 않아요.</p>
      <Button id="profile-load-regions" variant="secondary" pending={pending} onClick={loadRegions}>{catalog ? '시군구 목록 새로 불러오기' : '시군구 목록 불러오기'}</Button>
      {pending && <Button variant="secondary" onClick={request.clear}>지역 목록 조회 취소</Button>}
      {request.state.status === 'error' && <RequestError error={request.state.error} />}
      <details className="disclosure"><summary>지역 선택 안내</summary><p>시도 전체나 시군구를 고를 수 있어요. 지역 목록은 로그인이나 AI 처리 동의 없이 불러올 수 있어요. 조회에 실패해도 기존 선택을 유지해요. 시도 전체로 임의 변경하지 않아요.</p>{catalog && <p>지역 목록 버전: {catalog.version}</p>}</details>
      <fieldset disabled={pending}><legend>희망 활동 지역 (한 곳 이상)</legend>{(Object.keys(provinces) as Province[]).map((province) => {
        const selected = preferences.regions.filter((region) => region.province === province)
        const entry = catalog?.provinces.find((entry) => entry.id === province)
        return <div key={province}>
          <CheckboxField id={`profile-region-${province}`} label={provinces[province]} checked={selected.length > 0} disabled={selected.length === 0 && preferences.regions.length >= 10} onChange={(event) => changeRegions(event.target.checked ? [...preferences.regions, { province, district: null }] : preferences.regions.filter((value) => value.province !== province))} />
          {selected.length > 0 && <fieldset><legend>{provinces[province]} 활동 범위</legend>
            <CheckboxField label={`${provinces[province]} 전체`} checked={selected.some((region) => region.district === null)} onChange={(event) => changeRegions([...preferences.regions.filter((region) => region.province !== province), ...(event.target.checked ? [{ province, district: null }] : [])])} />
            {entry?.districts.map((district) => <CheckboxField key={district.id} label={`${provinces[province]} ${district.name}`} checked={selected.some((region) => region.district === district.id)} disabled={preferences.regions.length >= 10 && !selected.some((region) => region.district === null || region.district === district.id)} onChange={(event) => changeRegions(event.target.checked ? [...preferences.regions.filter((region) => !(region.province === province && region.district === null)), { province, district: district.id }] : preferences.regions.filter((region) => !(region.province === province && region.district === district.id)))} />)}
            {selected.filter((region) => region.district !== null && !entry?.districts.some((district) => district.id === region.district)).map((region) => <div key={region.district}><p>목록 대조 필요: {provinces[province]} / {region.district}</p><Button variant="secondary" onClick={() => changeRegions(preferences.regions.filter((value) => value !== region))}>{provinces[province]} / {region.district} 선택 제거</Button></div>)}
          </fieldset>}
        </div>
      })}</fieldset>
      <p>{preferences.regions.length} / 10곳 선택</p>
      <fieldset><legend>희망 활동 유형 (한 가지 이상)</legend>{(['employment', 'volunteering'] as const).map((activity) => <CheckboxField key={activity} id={`profile-activity-${activity}`} label={activity === 'employment' ? '취업 및 공공일자리' : '봉사'} checked={preferences.activities.includes(activity)} onChange={(event) => { setErrors([]); onChange({ ...preferences, activities: event.target.checked ? [...preferences.activities, activity] : preferences.activities.filter((value) => value !== activity), reviewed: false }) }} />)}</fieldset>
      <Button disabled={pending} onClick={review}>작성 항목 확인하기</Button><p role="status">{preferences.reviewed ? '경험과 희망 조건을 확인했어요. 이 화면에서만 유지되며 서버에 확정하거나 회원 자료로 저장하지 않았어요.' : ''}</p>
    </section>
    <div className="actions"><Button variant="secondary" onClick={() => { setErrors([]); setChoosing(false) }}>경험 다시 확인하기</Button><Link id="profile-experience-link" className="text-link" to="/conversation">경험 수정하기</Link></div>
    </>}
    <details className="disclosure"><summary>다른 화면 살펴보기</summary><div className="actions"><Link className="button secondary" to="/preparation">지원 내용 직접 작성해 보기</Link><Link className="text-link" to="/opportunities">공개 공고 살펴보기</Link></div><p className="quiet">여기서는 프로필 확정이나 추천을 제공하지 않아요.</p></details>
  </div>
}
