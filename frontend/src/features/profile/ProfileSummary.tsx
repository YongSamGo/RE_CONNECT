import type { components } from '../../api/schema'
import { provinces } from '../public-opportunities/catalog'
import type { RegionCatalog } from '../regions/catalog'

type Content = components['schemas']['ProfileContent']
export function ProfileSummary({ content, catalog = null }: { content: Content; catalog?: RegionCatalog | null }) {
  const list = (value: string[] | null) => value === null ? '아직 확인하지 않았어요' : value.join(', ') || '없음'
  const region = (value: Content['preferred_regions'][number]) => {
    const district = catalog?.provinces.find(p => p.id === value.province)?.districts.find(d => d.id === value.district)?.name
    return `${provinces[value.province]}${value.district === null ? ' 전체' : district ? ` ${district}` : ' (시군구 지정)'}`
  }
  return <>
    <section className="profile-summary-section"><h2>내가 해온 일</h2>
      {content.experiences.length ? <ul className="profile-experience-list">{content.experiences.map(experience => <li key={experience.id}>
        <p>{experience.description}</p>{experience.duration_note && <p className="quiet">{experience.duration_note}</p>}
        {!!experience.skill_tags.length && <ul className="profile-tags" aria-label="경험에서 찾은 역량">{experience.skill_tags.map((skill, i) => <li key={i}>{skill}</li>)}</ul>}
      </li>)}</ul> : <p>아직 정리한 경험이 없어요.</p>}
    </section>
    <section className="profile-summary-section"><h2>앞으로 하고 싶은 활동</h2><dl className="profile-facts">
      <dt>희망 지역</dt><dd>{content.preferred_regions.map(region).join(', ') || '아직 선택하지 않았어요'}</dd>
      <dt>활동 유형</dt><dd>{content.activity_types.map(type => type === 'employment' ? '취업 및 공공일자리' : '봉사').join(', ') || '아직 선택하지 않았어요'}</dd>
      <dt>보수</dt><dd>{content.paid_preference === null ? '아직 선택하지 않았어요' : { paid: '유급 활동', unpaid: '무급 활동', any: '상관없어요' }[content.paid_preference]}</dd>
      <dt>가능 요일</dt><dd>{content.available_weekdays === null ? '아직 선택하지 않았어요' : content.available_weekdays.map(day => ['월', '화', '수', '목', '금', '토', '일'][day - 1] + '요일').join(', ') || '없음'}</dd>
      <dt>가능 시간</dt><dd>{content.hours_per_week === null ? '아직 정하지 않았어요' : `주 ${content.hours_per_week}시간`}</dd>
    </dl></section>
    <details className="disclosure"><summary>역량과 추가 정보 보기</summary><dl className="profile-facts">
      <dt>전체 역량</dt><dd>{list(content.skills)}</dd>
      <dt>자격증</dt><dd>{list(content.certifications)}</dd>
      <dt>수료 교육</dt><dd>{list(content.completed_courses)}</dd>
      <dt>이동 관련 메모</dt><dd>{content.mobility_note ?? '아직 확인하지 않았어요'}</dd>
      <dt>활동 수행 조건</dt><dd>{list(content.activity_constraints)}</dd>
    </dl></details>
  </>
}
