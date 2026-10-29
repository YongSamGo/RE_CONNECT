/** Replace this adapter with the opportunity API response when wiring the demo to live data. */
export interface DemoOpportunity {
  id: string
  title: string
  organization: string
  officialApplicationUrl: string | null
  activity: string
  region: string
  schedule: string
  deadline: string
  description: string
  requirements: string[]
  recommendationReason: string
  profileFacts: string[]
  introduction: string
  motivation: string
}

export const demoOpportunities: DemoOpportunity[] = [
  {
    id: 'demo-library', title: '도서관 자료 정리 지원 봉사', organization: '서울나눔도서관', officialApplicationUrl: null, activity: '봉사', region: '서울특별시 마포구', schedule: '주 2회, 회당 3시간', deadline: '2026년 11월 30일까지',
    description: '도서관 자료를 정리하고 방문객이 필요한 공간과 자료를 찾도록 안내합니다.', requirements: ['만 50세 이상', '주 2회 활동 가능', '방문객 안내에 관심 있는 분'],
    recommendationReason: '자료를 정리하고 방문객을 안내해 온 경험이 활동 내용과 맞닿아 있어요.', profileFacts: ['도서관 자료 정리', '방문객 안내'],
    introduction: '도서관에서 자료를 정리하고 방문객의 이용을 도왔습니다.', motivation: '자료 정리와 안내 경험을 살려 지역 주민에게 도움이 되고 싶습니다.',
  },
  {
    id: 'demo-digital', title: '디지털 생활 안내 도우미', organization: '우리동네 복지센터', officialApplicationUrl: null, activity: '공공일자리', region: '서울특별시 은평구', schedule: '주 3회, 회당 2시간', deadline: '2026년 12월 12일까지',
    description: '스마트폰 기본 기능과 공공 서비스를 이용하는 방법을 주민에게 안내합니다.', requirements: ['스마트폰 기본 사용 가능', '주 3회 활동 가능', '초보자에게 차근히 설명할 수 있는 분'],
    recommendationReason: '사람들에게 필요한 정보를 이해하기 쉽게 알려 준 경험을 활용할 수 있어요.', profileFacts: ['방문객에게 정보 설명', '스마트폰 사용 안내'],
    introduction: '방문객이 필요한 정보를 이해하기 쉽게 설명하고 이용을 도왔습니다.', motivation: '설명과 안내 경험을 활용해 지역 주민의 디지털 서비스 이용을 돕고 싶습니다.',
  },
  {
    id: 'demo-culture', title: '지역 문화 행사 운영 지원', organization: '마을문화재단', officialApplicationUrl: null, activity: '봉사', region: '인천광역시 미추홀구', schedule: '행사 일정에 따라 활동', deadline: '2026년 12월 20일까지',
    description: '지역 문화 행사에서 참가자 안내와 현장 운영을 지원합니다.', requirements: ['행사 당일 현장 참여 가능', '팀과 함께 활동할 수 있는 분'],
    recommendationReason: '여러 사람과 협력하고 맡은 일을 꾸준히 해 온 경험이 현장 운영에 도움이 될 수 있어요.', profileFacts: ['행사 준비와 현장 지원', '팀원과 역할 분담'],
    introduction: '여러 사람과 역할을 나눠 행사를 준비하고 현장을 지원했습니다.', motivation: '협력 경험을 살려 지역 문화 행사에 참여하는 주민을 돕고 싶습니다.',
  },
  {
    id: 'demo-office', title: '공공기관 행정 업무 보조', organization: '한결공공서비스', officialApplicationUrl: null, activity: '공공일자리', region: '서울특별시 종로구', schedule: '주 5일, 하루 4시간', deadline: '2027년 1월 8일까지',
    description: '문서 분류와 방문 민원 안내 등 기관의 기본 행정 업무를 지원합니다.', requirements: ['기초 문서 작업 가능', '주중 오전 활동 가능', '정확하고 꼼꼼하게 업무를 처리할 수 있는 분'],
    recommendationReason: '정리와 사람 응대를 함께 해 온 경험을 행정 보조 업무에 연결할 수 있어요.', profileFacts: ['자료 분류와 정리', '방문자 응대'],
    introduction: '자료를 꼼꼼하게 정리하고 방문한 분들에게 필요한 정보를 안내했습니다.', motivation: '정리와 응대 경험을 살려 기관을 찾는 분들이 편하게 업무를 볼 수 있도록 돕고 싶습니다.',
  },
]
