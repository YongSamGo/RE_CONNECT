import type { ReactNode } from 'react'
import type { components } from '../../api/schema'
import { Button } from '../../ui/Button'
import { provinces } from '../public-opportunities/catalog'
import type { RegionCatalog } from '../regions/catalog'

type ProfileContent = components['schemas']['ProfileContent']
type Content = Omit<ProfileContent, 'experiences'> & { experiences: Array<Omit<ProfileContent['experiences'][number], 'id'> & { id: string | null }> }
export type ProfileField = 'experiences' | 'preferred_regions' | 'activity_types' | 'additional'
type Props = { content: Content; catalog?: RegionCatalog | null; showAdditional?: boolean; hiddenField?: ProfileField | null; onEdit?: (field: ProfileField) => void; editDisabled?: boolean }
export function ProfileSummary({ content, catalog = null, showAdditional = true, hiddenField = null, onEdit, editDisabled = false }: Props) {
  const list = (value: string[] | null) => value?.join(', ') || '없음'
  const region = (value: Content['preferred_regions'][number]) => {
    const district = catalog?.provinces.find(p => p.id === value.province)?.districts.find(d => d.id === value.district)?.name
    return `${provinces[value.province]}${value.district === null ? ' 전체' : district ? ` ${district}` : ' (시군구 지정)'}`
  }
  // 대화에서 묻지 않는 조건이라 비어 있으면 프로필에서 바로 적을 수 있게 알려준다.
  const missingConditions = [content.available_weekdays === null && '가능 요일', content.hours_per_week === null && '가능 시간', content.paid_preference === null && '보수'].filter((value): value is string => !!value)
  const section = (field: ProfileField, title: string, contentNode: ReactNode) => <section className="profile-summary-section" key={field}>
    <header className="profile-summary-heading"><h2>{title}</h2>{onEdit && <Button id={`profile-edit-${field}`} variant="secondary" disabled={editDisabled} aria-label={`${title} 수정하기`} onClick={() => onEdit(field)}>수정하기</Button>}</header>
    {hiddenField === field ? null : contentNode}
  </section>
  return <>
    {section('experiences', '내가 해온 일', <>
      {content.experiences.length ? <ul className="profile-experience-list">{content.experiences.map(experience => <li key={experience.id}>
        <p>{experience.description}</p>{experience.duration_note && <p className="quiet">{experience.duration_note}</p>}
        {!!experience.skill_tags.length && <ul className="profile-tags" aria-label="경험에서 찾은 역량">{experience.skill_tags.map((skill, i) => <li key={i}>{skill}</li>)}</ul>}
      </li>)}</ul> : <p>아직 정리한 경험이 없어요.</p>}
    </>)}
    {section('preferred_regions', '희망 지역', <p>{content.preferred_regions.map(region).join(', ') || '아직 선택하지 않았어요'}</p>)}
    {section('activity_types', '활동 유형', <p>{content.activity_types.map(type => type === 'employment' ? '취업 및 공공일자리' : '봉사').join(', ') || '아직 선택하지 않았어요'}</p>)}
    {showAdditional && onEdit && section('additional', '추가 정보', <>{missingConditions.length > 0 && <div className="profile-additional-prompt">
      <p>아직 적지 않았어요: {missingConditions.join(', ')}</p>
      <p className="quiet">일할 수 있는 요일·시간과 보수 여부를 적어 두면, 조건이 있는 공고에서 맞는지 바로 확인할 수 있어요.</p>
      <Button variant="secondary" disabled={editDisabled} onClick={() => onEdit('additional')}>요일·시간·보수 적기</Button>
    </div>}<dl className="profile-facts">
      {!!content.skills.length && <><dt>전체 역량</dt><dd>{list(content.skills)}</dd></>}
      {content.paid_preference !== null && <><dt>보수</dt><dd>{{ paid: '유급 활동', unpaid: '무급 활동', any: '상관없어요' }[content.paid_preference]}</dd></>}
      {content.available_weekdays !== null && <><dt>가능 요일</dt><dd>{content.available_weekdays.map(day => ['월', '화', '수', '목', '금', '토', '일'][day - 1] + '요일').join(', ') || '없음'}</dd></>}
      {content.hours_per_week !== null && <><dt>가능 시간</dt><dd>주 {content.hours_per_week}시간</dd></>}
      {content.certifications !== null && <><dt>자격증</dt><dd>{list(content.certifications)}</dd></>}
      {content.completed_courses !== null && <><dt>수료 교육</dt><dd>{list(content.completed_courses)}</dd></>}
      {content.mobility_note !== null && <><dt>이동 관련 메모</dt><dd>{content.mobility_note}</dd></>}
      {content.activity_constraints !== null && <><dt>활동 수행 조건</dt><dd>{list(content.activity_constraints)}</dd></>}
      {content.residence_region !== null && <><dt>거주 지역</dt><dd>{region(content.residence_region)}</dd></>}
      {content.birth_year !== null && <><dt>출생 연도</dt><dd>{content.birth_year}년</dd></>}
      {!content.skills.length && content.paid_preference === null && content.available_weekdays === null && content.hours_per_week === null && content.certifications === null && content.completed_courses === null && content.mobility_note === null && content.activity_constraints === null && content.residence_region === null && content.birth_year === null && <dt>선택한 추가 정보가 없어요</dt>}
    </dl></>)}
    {showAdditional && !onEdit && <details className="disclosure"><summary>추가 정보 보기</summary><dl className="profile-facts">
      {!!content.skills.length && <><dt>전체 역량</dt><dd>{list(content.skills)}</dd></>}
      {content.paid_preference !== null && <><dt>보수</dt><dd>{{ paid: '유급 활동', unpaid: '무급 활동', any: '상관없어요' }[content.paid_preference]}</dd></>}
      {content.available_weekdays !== null && <><dt>가능 요일</dt><dd>{content.available_weekdays.map(day => ['월', '화', '수', '목', '금', '토', '일'][day - 1] + '요일').join(', ') || '없음'}</dd></>}
      {content.hours_per_week !== null && <><dt>가능 시간</dt><dd>주 {content.hours_per_week}시간</dd></>}
      {content.certifications !== null && <><dt>자격증</dt><dd>{list(content.certifications)}</dd></>}
      {content.completed_courses !== null && <><dt>수료 교육</dt><dd>{list(content.completed_courses)}</dd></>}
      {content.mobility_note !== null && <><dt>이동 관련 메모</dt><dd>{content.mobility_note}</dd></>}
      {content.activity_constraints !== null && <><dt>활동 수행 조건</dt><dd>{list(content.activity_constraints)}</dd></>}
      {content.residence_region !== null && <><dt>거주 지역</dt><dd>{region(content.residence_region)}</dd></>}
      {content.birth_year !== null && <><dt>출생 연도</dt><dd>{content.birth_year}년</dd></>}
    </dl></details>}
  </>
}
