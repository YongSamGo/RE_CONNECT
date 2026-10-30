// docs/data/role-catalog.json의 역할 표시명. 공개 API에는 역할 이름이 없어 화면에서 이 표로 바꾼다.
// 사전이 바뀌면 같이 고친다(roles.test.ts가 문서와 대조한다).
export const roleNames: Record<string, string> = {
  care_assistant: '돌봄 보조 활동가',
  community_organizer: '주민 모임 진행자',
  digital_guide: '디지털 기기 안내 도우미',
  facility_manager: '시설 관리원',
  finance_educator: '금융 사기 예방 교육 강사',
  learning_mentor: '학습 지도 활동가',
  library_assistant: '도서관 자료 정리 도우미',
  meal_assistant: '급식·조리 보조',
  mobility_supporter: '이동 지원 활동가',
  office_accounting: '사무 보조(회계)',
  reading_companion: '책 읽어주기 활동가',
  reading_mentor: '독서 지도 활동가',
  visitor_guide: '민원·방문 안내 도우미',
}
