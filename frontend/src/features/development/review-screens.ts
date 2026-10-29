export const screens = [
  ['home', '첫 화면', '영상과 버튼 안전 영역'],
  ['start', '시작 안내', '동의 안내와 공고 둘러보기'],
  ['conversation', '경험 이야기', '음성이나 글 입력'],
  ['profile', '내 경험 확인', '요약, 수정, 확정'],
  ['recommendations', '추천 공고', '확정한 경험으로 추천'],
  ['filter', '공고 조건 선택', '지도와 검색 조건'],
  ['catalog', '전체 공고', '검색 결과 목록'],
  ['detail', '공고 상세', '추천 이유와 필수조건 대조'],
  ['application', '지원서 작성', '초안, 편집, 최종 검토'],
  ['save', '자료 저장', '저장 동의와 단계별 결과'],
  ['member', '나의 정보', '프로필, 지원서, 계정 설정'],
  ['login', '로그인', '카카오 로그인 진입'],
  ['guide', '이용 안내', '서비스 이용 방법'],
] as const

const scenarios = new Set(['normal', 'empty', 'loading', 'failure', 'expired', 'closed', 'changed'])
export function reviewScenario() {
  try {
    const value = sessionStorage.getItem('screen-review-scenario')
    return value && scenarios.has(value) ? value : 'normal'
  } catch { return 'normal' }
}
export function reviewHref(screen: string, scenario = reviewScenario()) {
  return `http://127.0.0.1:5190/__review/open?screen=${encodeURIComponent(screen)}&state=${encodeURIComponent(scenario)}`
}
