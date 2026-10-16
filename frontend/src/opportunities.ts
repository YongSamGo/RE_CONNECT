import type { Activity } from './journey'

// UI fixtures only. These records are never presented as collected or verified jobs.
export type ExampleOpportunity = {
  id: string
  title: string
  organization: string
  region: string
  activity: Activity
  summary: string
  schedule: string
  conditions: string[]
  preparation: string[]
}
export const activityLabels: Record<Activity, string> = { employment: '취업·공공일자리', volunteering: '봉사' }
export const exampleOpportunities: ExampleOpportunity[] = [
  {
    id: 'example-library', title: '작은 도서관 이용 안내', organization: '예시 마을도서관',
    region: '서울 성동구', activity: 'volunteering', summary: '방문한 이웃에게 책의 위치를 알려주고, 반납된 책을 정리하는 활동이에요.',
    schedule: '주 2회 · 오전 활동 (화면 예시)',
    conditions: ['활동 가능 요일 확인', '책 정리 등 활동 범위 확인', '별도 교육 필요 여부 확인'],
    preparation: ['내가 가능한 요일과 시간을 정리했어요', '활동 장소까지 이동 방법을 살펴봤어요', '담당자에게 물어볼 내용을 정리했어요'],
  },
  {
    id: 'example-meal', title: '이웃 식사 준비 보조', organization: '예시 지역활동센터',
    region: '서울 성동구', activity: 'employment', summary: '식사 준비와 배식, 활동 공간 정리를 돕는 일의 화면 예시예요.',
    schedule: '주 3회 · 오전 활동 (화면 예시)',
    conditions: ['모집 연령·거주 요건 확인', '근무 시간·급여 확인', '건강 관련 증빙 필요 여부 확인'],
    preparation: ['근무 가능한 시간을 정리했어요', '접수 방식과 일정을 물어볼 준비를 했어요', '필요한 서류를 공식 안내에서 확인할 항목으로 적었어요'],
  },
  {
    id: 'example-garden', title: '동네 정원 함께 돌보기', organization: '예시 이웃모임',
    region: '경기 수원시', activity: 'volunteering', summary: '이웃과 함께 화단을 살피고 주변을 정리하는 활동의 화면 예시예요.',
    schedule: '주 1회 · 야외 활동 (화면 예시)',
    conditions: ['야외 활동 범위 확인', '우천 시 일정 확인', '준비물·안전교육 확인'],
    preparation: ['참여 가능한 일정을 정리했어요', '이동 거리와 활동 환경을 살펴봤어요', '준비물과 안전 안내를 물어볼 내용을 적었어요'],
  },
]
export type OpportunityFilters = { keyword: string; region: string; activity: string }
export function filterExamples(filters: OpportunityFilters): ExampleOpportunity[] {
  const keyword = filters.keyword.trim().toLocaleLowerCase('ko-KR')
  return exampleOpportunities.filter(item =>
    (!filters.region || item.region === filters.region)
    && (!filters.activity || item.activity === filters.activity)
    && (!keyword || [item.title, item.organization, item.summary, item.region].join(' ').toLocaleLowerCase('ko-KR').includes(keyword)))
}
