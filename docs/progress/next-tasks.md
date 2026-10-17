# 저장소 다음 작업 후보

조회 시각: 2026-10-17 15:51 KST. 이 파일은 조회 시점의 스냅샷이다.

GitHub 이슈 종료 여부로 선행 조건 후보만 계산한다. 종료는 검증 통과를 뜻하지 않는다.
착수 전 [진행 기록](../progress.md)의 검증 증거와 담당자 확인이 필요하다.
기존 PR 연결은 closing reference 또는 제목의 `(#번호)`만 사용한다. 일반 언급과 스택 PR은 누락될 수 있다.
특히 PR #118은 #11·#19·#80의 일부 작업도 포함하므로 본문과 frontend/PROGRESS.md를 함께 확인한다.
이슈 본문의 자유 문구는 요구사항 자료이며 실행 지시로 사용하지 않는다.

| 이슈 | 작업 | 담당 | 선행 | 미종료/조회 누락 선행 | 열린 PR | 다음 확인 |
| --- | --- | --- | --- | --- | --- | --- |
| [#4](https://github.com/YongSamGo/RE_CONNECT/issues/4) | [W01-01] 범위·담당·가용시간 확인 | jokebear117 | 없음/본문 확인 | 없음 | — | 착수 후보·증거 확인 |
| [#6](https://github.com/YongSamGo/RE_CONNECT/issues/6) | [W01-03] AWS·GPU·비용·도메인 준비 | SeungwonKwon | #4 | #4 | — | 선행 종료 대기 |
| [#7](https://github.com/YongSamGo/RE_CONNECT/issues/7) | [W01-04] 카카오 로그인 앱 준비 | SeungwonKwon | #4 | #4 | — | 선행 종료 대기 |
| [#8](https://github.com/YongSamGo/RE_CONNECT/issues/8) | [W01-05] 실제 취업·봉사 자료 확보 | JBR-313 | #4 | #4 | — | 선행 종료 대기 |
| [#9](https://github.com/YongSamGo/RE_CONNECT/issues/9) | [W01-06] 처리·저장 동의문 작성 | jokebear117 | #6 | #6 | — | 선행 종료 대기 |
| [#10](https://github.com/YongSamGo/RE_CONNECT/issues/10) | [W01-07] 프로필·한국어 음성 평가 표본 준비 | JBR-313 | #4 | #4 | — | 선행 종료 대기 |
| [#11](https://github.com/YongSamGo/RE_CONNECT/issues/11) | [W01-08] 진행 상태와 검증 기록 준비 | jokebear117 | #5 | 없음 | — | 착수 후보·증거 확인 |
| [#13](https://github.com/YongSamGo/RE_CONNECT/issues/13) | [W02-02] 프론트엔드 기본 화면 구성 | jokebear117 | #12 | 없음 | [#118](https://github.com/YongSamGo/RE_CONNECT/pull/118) | 기존 PR 확인 |
| [#16](https://github.com/YongSamGo/RE_CONNECT/issues/16) | [W02-05] 회원·프로필·지원서 DB 모델 정의 | SeungwonKwon | #14, #15 | 없음 | [#145](https://github.com/YongSamGo/RE_CONNECT/pull/145) | 기존 PR 확인 |
| [#17](https://github.com/YongSamGo/RE_CONNECT/issues/17) | [W02-06] 공고·수집·운영 DB 모델 정의 | SeungwonKwon | #15 | 없음 | [#146](https://github.com/YongSamGo/RE_CONNECT/pull/146) | 기존 PR 확인 |
| [#18](https://github.com/YongSamGo/RE_CONNECT/issues/18) | [W02-07] DB 변경과 개발 Compose 구성 | SeungwonKwon | #16, #17 | #16, #17 | [#147](https://github.com/YongSamGo/RE_CONNECT/pull/147) | 기존 PR 확인 |
| [#19](https://github.com/YongSamGo/RE_CONNECT/issues/19) | [W02-08] 프론트엔드 타입·API 클라이언트 연결 | jokebear117 | #5, #13, #15 | #13 | — | 선행 종료 대기 |
| [#20](https://github.com/YongSamGo/RE_CONNECT/issues/20) | [W03-01] 익명 세션과 자료 소유권 검사 | SeungwonKwon | #14, #18 | #18 | [#149](https://github.com/YongSamGo/RE_CONNECT/pull/149) | 기존 PR 확인 |
| [#21](https://github.com/YongSamGo/RE_CONNECT/issues/21) | [W03-02] AI·저장 동의 검사 | SeungwonKwon | #9, #16, #20 | #9, #16, #20 | — | 선행 종료 대기 |
| [#22](https://github.com/YongSamGo/RE_CONNECT/issues/22) | [W03-03] 위조 요청·과대 입력 차단 | SeungwonKwon | #20 | #20 | [#150](https://github.com/YongSamGo/RE_CONNECT/pull/150) | 기존 PR 확인 |
| [#23](https://github.com/YongSamGo/RE_CONNECT/issues/23) | [W03-04] 호출 한도와 공유 추론 슬롯 | SeungwonKwon | #18, #20 | #18, #20 | [#152](https://github.com/YongSamGo/RE_CONNECT/pull/152) | 기존 PR 확인 |
| [#24](https://github.com/YongSamGo/RE_CONNECT/issues/24) | [W03-05] 중복 요청·동시 수정 제어 | SeungwonKwon | #18, #20 | #18, #20 | [#151](https://github.com/YongSamGo/RE_CONNECT/pull/151) | 기존 PR 확인 |
| [#25](https://github.com/YongSamGo/RE_CONNECT/issues/25) | [W03-06] 개인 본문 암호화와 키 관리 | SeungwonKwon | #16 | #16 | [#148](https://github.com/YongSamGo/RE_CONNECT/pull/148) | 기존 PR 확인 |
| [#26](https://github.com/YongSamGo/RE_CONNECT/issues/26) | [W03-07] 안전한 오류 응답과 로그 | SeungwonKwon | #14 | 없음 | [#143](https://github.com/YongSamGo/RE_CONNECT/pull/143) | 기존 PR 확인 |
| [#27](https://github.com/YongSamGo/RE_CONNECT/issues/27) | [W03-08] 삭제·만료 후 결과 저장 차단 | SeungwonKwon | #23, #24 | #23, #24 | — | 선행 종료 대기 |
| [#28](https://github.com/YongSamGo/RE_CONNECT/issues/28) | [W04-01] 모델·가중치·런타임 준비 | JBR-313 | #6, #12 | #6 | — | 선행 종료 대기 |
| [#29](https://github.com/YongSamGo/RE_CONNECT/issues/29) | [W04-02] Ollama 텍스트 통신 모듈 | JBR-313 | #15, #28 | #28 | — | 선행 종료 대기 |
| [#30](https://github.com/YongSamGo/RE_CONNECT/issues/30) | [W04-03] 추출·질문·지원서 근거 검증 | JBR-313 | #10, #29 | #10, #29 | — | 선행 종료 대기 |
| [#31](https://github.com/YongSamGo/RE_CONNECT/issues/31) | [W04-04] 로컬 음성 인식 구현 | JBR-313 | #10, #28 | #10, #28 | — | 선행 종료 대기 |
| [#32](https://github.com/YongSamGo/RE_CONNECT/issues/32) | [W04-05] 로컬 한국어 읽어주기 구현 | JBR-313 | #10, #28 | #10, #28 | — | 선행 종료 대기 |
| [#33](https://github.com/YongSamGo/RE_CONNECT/issues/33) | [W04-06] 내부 음성 서비스 연결 | JBR-313 | #23, #26, #31, #32 | #23, #26, #31, #32 | — | 선행 종료 대기 |
| [#34](https://github.com/YongSamGo/RE_CONNECT/issues/34) | [W04-07] 실제 EC2 성능·품질 검증 | JBR-313 | #29, #30, #33, #92 | #29, #30, #33, #92 | — | 선행 종료 대기 |
| [#35](https://github.com/YongSamGo/RE_CONNECT/issues/35) | [W04-08] 모델 장애·혼잡·재시도 처리 | JBR-313 | #27, #33 | #27, #33 | — | 선행 종료 대기 |
| [#36](https://github.com/YongSamGo/RE_CONNECT/issues/36) | [W05-01] 임시 체험 생성과 만료 | SeungwonKwon | #15, #20, #21, #24 | #20, #21, #24 | — | 선행 종료 대기 |
| [#37](https://github.com/YongSamGo/RE_CONNECT/issues/37) | [W05-02] 한 질문씩 대화·초안 추출 | SeungwonKwon | #23, #27, #30, #36 | #23, #27, #30, #36 | — | 선행 종료 대기 |
| [#38](https://github.com/YongSamGo/RE_CONNECT/issues/38) | [W05-03] 음성 전사 확인·수정 연결 | SeungwonKwon | #27, #33, #36 | #27, #33, #36 | — | 선행 종료 대기 |
| [#39](https://github.com/YongSamGo/RE_CONNECT/issues/39) | [W05-04] 프로필 직접 작성·편집 | SeungwonKwon | #36 | #36 | — | 선행 종료 대기 |
| [#40](https://github.com/YongSamGo/RE_CONNECT/issues/40) | [W05-05] 프로필 확정과 버전 부여 | SeungwonKwon | #39 | #39 | — | 선행 종료 대기 |
| [#41](https://github.com/YongSamGo/RE_CONNECT/issues/41) | [W05-06] 재확정 후 결과 갱신 | SeungwonKwon | #40 | #40 | — | 선행 종료 대기 |
| [#42](https://github.com/YongSamGo/RE_CONNECT/issues/42) | [W05-07] 저장 자료로 새 체험 시작 | SeungwonKwon | #40, #75 | #40, #75 | — | 선행 종료 대기 |
| [#43](https://github.com/YongSamGo/RE_CONNECT/issues/43) | [W05-08] 체험 종료·삭제·재진입 처리 | SeungwonKwon | #27, #36 | #27, #36 | — | 선행 종료 대기 |
| [#44](https://github.com/YongSamGo/RE_CONNECT/issues/44) | [W06-01] 출처 설정과 실제 필드 매핑 | JBR-313 | #8, #17 | #8, #17 | — | 선행 종료 대기 |
| [#45](https://github.com/YongSamGo/RE_CONNECT/issues/45) | [W06-02] 안전한 외부 수집·파싱 | JBR-313 | #26, #44 | #26, #44 | — | 선행 종료 대기 |
| [#46](https://github.com/YongSamGo/RE_CONNECT/issues/46) | [W06-03] 공고와 원문 조건 정규화 | JBR-313 | #15, #45 | #45 | — | 선행 종료 대기 |
| [#47](https://github.com/YongSamGo/RE_CONNECT/issues/47) | [W06-04] 중복 방지·변경 버전 관리 | JBR-313 | #18, #46 | #18, #46 | [#154](https://github.com/YongSamGo/RE_CONNECT/pull/154) | 기존 PR 확인 |
| [#48](https://github.com/YongSamGo/RE_CONNECT/issues/48) | [W06-05] 마감·신선도·수집 실패 처리 | JBR-313 | #47 | #47 | [#144](https://github.com/YongSamGo/RE_CONNECT/pull/144) | 기존 PR 확인 |
| [#49](https://github.com/YongSamGo/RE_CONNECT/issues/49) | [W06-06] 수집 실행·집계·스케줄 연결 | JBR-313 | #48 | #48 | — | 선행 종료 대기 |
| [#50](https://github.com/YongSamGo/RE_CONNECT/issues/50) | [W06-07] 공개 목록·상세·검색 API | SeungwonKwon | #22, #48 | #22, #48 | [#153](https://github.com/YongSamGo/RE_CONNECT/pull/153) | 기존 PR 확인 |
| [#51](https://github.com/YongSamGo/RE_CONNECT/issues/51) | [W06-08] 공식 자료 수동 입력·공고 확보 | JBR-313 | #44, #47 | #44, #47 | — | 선행 종료 대기 |
| [#52](https://github.com/YongSamGo/RE_CONNECT/issues/52) | [W07-01] 운영자 권한과 MFA | SeungwonKwon | #25, #72, #73 | #25, #72, #73 | — | 선행 종료 대기 |
| [#53](https://github.com/YongSamGo/RE_CONNECT/issues/53) | [W07-02] 운영자 공고 등록·수정 API | SeungwonKwon | #47, #51, #52 | #47, #51, #52 | — | 선행 종료 대기 |
| [#54](https://github.com/YongSamGo/RE_CONNECT/issues/54) | [W07-03] 공고 승인·반려·숨김·종료 | SeungwonKwon | #26, #53 | #26, #53 | — | 선행 종료 대기 |
| [#55](https://github.com/YongSamGo/RE_CONNECT/issues/55) | [W07-04] 수집·모델·장애 상태 조회 | SeungwonKwon | #23, #49, #52 | #23, #49, #52 | — | 선행 종료 대기 |
| [#56](https://github.com/YongSamGo/RE_CONNECT/issues/56) | [W07-05] 공고 오류 신고·처리 | SeungwonKwon | #22, #50, #52 | #22, #50, #52 | — | 선행 종료 대기 |
| [#57](https://github.com/YongSamGo/RE_CONNECT/issues/57) | [W07-06] 감사 기록 조회·정리 | SeungwonKwon | #26, #54, #56 | #26, #54, #56 | — | 선행 종료 대기 |
| [#58](https://github.com/YongSamGo/RE_CONNECT/issues/58) | [W08-01] 자격조건별 비교 규칙 | SeungwonKwon | #10, #15 | #10 | [#141](https://github.com/YongSamGo/RE_CONNECT/pull/141) | 기존 PR 확인 |
| [#59](https://github.com/YongSamGo/RE_CONNECT/issues/59) | [W08-02] AND/OR·연령 경계 판정 | SeungwonKwon | #58 | #58 | [#142](https://github.com/YongSamGo/RE_CONNECT/pull/142) | 기존 PR 확인 |
| [#60](https://github.com/YongSamGo/RE_CONNECT/issues/60) | [W08-03] 확정 정보로 자격 대조 API | SeungwonKwon | #40, #50, #59 | #40, #50, #59 | — | 선행 종료 대기 |
| [#61](https://github.com/YongSamGo/RE_CONNECT/issues/61) | [W08-04] 경험 근거가 있는 역할 후보 | JBR-313 | #17, #40 | #17, #40 | — | 선행 종료 대기 |
| [#62](https://github.com/YongSamGo/RE_CONNECT/issues/62) | [W08-05] 역할 제외·복원 | SeungwonKwon | #61 | #61 | — | 선행 종료 대기 |
| [#63](https://github.com/YongSamGo/RE_CONNECT/issues/63) | [W08-06] 추천 후보와 필수조건 필터 | JBR-313 | #48, #60, #62 | #48, #60, #62 | — | 선행 종료 대기 |
| [#64](https://github.com/YongSamGo/RE_CONNECT/issues/64) | [W08-07] 추천 점수·정렬·근거 | JBR-313 | #63 | #63 | — | 선행 종료 대기 |
| [#65](https://github.com/YongSamGo/RE_CONNECT/issues/65) | [W08-08] 실제 공고로 추천 평가 | JBR-313 | #10, #54, #64 | #10, #54, #64 | — | 선행 종료 대기 |
| [#66](https://github.com/YongSamGo/RE_CONNECT/issues/66) | [W09-01] 공식 서류·접수 절차 안내 | SeungwonKwon | #50 | #50 | — | 선행 종료 대기 |
| [#67](https://github.com/YongSamGo/RE_CONNECT/issues/67) | [W09-02] 지원서 생성·직접 작성 | JBR-313 | #27, #30, #40, #60 | #27, #30, #40, #60 | — | 선행 종료 대기 |
| [#68](https://github.com/YongSamGo/RE_CONNECT/issues/68) | [W09-03] 지원서 편집·승인 API | SeungwonKwon | #24, #67 | #24, #67 | — | 선행 종료 대기 |
| [#69](https://github.com/YongSamGo/RE_CONNECT/issues/69) | [W09-04] 근거 변경 시 재검토 표시 | SeungwonKwon | #41, #47, #68 | #41, #47, #68 | — | 선행 종료 대기 |
| [#70](https://github.com/YongSamGo/RE_CONNECT/issues/70) | [W09-05] 생성 실패·수동 작성 연결 | SeungwonKwon | #35, #68 | #35, #68 | — | 선행 종료 대기 |
| [#71](https://github.com/YongSamGo/RE_CONNECT/issues/71) | [W09-06] 편집 문장 복사·공식 안내 이동 | jokebear117 | #66, #68 | #66, #68 | — | 선행 종료 대기 |
| [#72](https://github.com/YongSamGo/RE_CONNECT/issues/72) | [W10-01] 카카오 인증 왕복 검증 | SeungwonKwon | #7, #16, #20, #22 | #7, #16, #20, #22 | — | 선행 종료 대기 |
| [#73](https://github.com/YongSamGo/RE_CONNECT/issues/73) | [W10-02] 내부 계정·로그인 세션 | SeungwonKwon | #72 | #72 | — | 선행 종료 대기 |
| [#74](https://github.com/YongSamGo/RE_CONNECT/issues/74) | [W10-03] 승인 자료의 일회 저장 전달 | SeungwonKwon | #21, #24, #40, #73 | #21, #24, #40, #73 | — | 선행 종료 대기 |
| [#75](https://github.com/YongSamGo/RE_CONNECT/issues/75) | [W10-04] 확정 프로필 암호화 저장 | SeungwonKwon | #25, #74 | #25, #74 | — | 선행 종료 대기 |
| [#76](https://github.com/YongSamGo/RE_CONNECT/issues/76) | [W10-05] 승인 지원서 암호화 저장 | SeungwonKwon | #25, #68, #74 | #25, #68, #74 | — | 선행 종료 대기 |
| [#77](https://github.com/YongSamGo/RE_CONNECT/issues/77) | [W10-06] 저장 자료 조회·재편집 | SeungwonKwon | #42, #75, #76 | #42, #75, #76 | — | 선행 종료 대기 |
| [#78](https://github.com/YongSamGo/RE_CONNECT/issues/78) | [W10-07] 삭제·철회·탈퇴 | SeungwonKwon | #27, #75, #76 | #27, #75, #76 | — | 선행 종료 대기 |
| [#79](https://github.com/YongSamGo/RE_CONNECT/issues/79) | [W10-08] 다른 사용자 접근·저장 경합 검증 | SeungwonKwon | #77, #78 | #77, #78 | — | 선행 종료 대기 |
| [#80](https://github.com/YongSamGo/RE_CONNECT/issues/80) | [W11-01] 공통 UI·메모리 상태·접근성 | jokebear117 | #13, #19 | #13, #19 | — | 선행 종료 대기 |
| [#81](https://github.com/YongSamGo/RE_CONNECT/issues/81) | [W11-02] 시작·동의 화면 | jokebear117 | #9, #36, #50, #80 | #9, #36, #50, #80 | — | 선행 종료 대기 |
| [#82](https://github.com/YongSamGo/RE_CONNECT/issues/82) | [W11-03] 한 질문씩 대화 화면 | jokebear117 | #35, #37, #81 | #35, #37, #81 | — | 선행 종료 대기 |
| [#83](https://github.com/YongSamGo/RE_CONNECT/issues/83) | [W11-04] 녹음·전사 확인 화면 | jokebear117 | #38, #82 | #38, #82 | — | 선행 종료 대기 |
| [#84](https://github.com/YongSamGo/RE_CONNECT/issues/84) | [W11-05] 프로필·역할 확인 화면 | jokebear117 | #40, #41, #61, #62, #80 | #40, #41, #61, #62, #80 | — | 선행 종료 대기 |
| [#85](https://github.com/YongSamGo/RE_CONNECT/issues/85) | [W11-06] 추천·공고 상세·신고 화면 | jokebear117 | #50, #56, #65, #80 | #50, #56, #65, #80 | — | 선행 종료 대기 |
| [#86](https://github.com/YongSamGo/RE_CONNECT/issues/86) | [W11-07] 신청 준비·지원서 화면 | jokebear117 | #69, #70, #71, #80 | #69, #70, #71, #80 | — | 선행 종료 대기 |
| [#87](https://github.com/YongSamGo/RE_CONNECT/issues/87) | [W11-08] 로그인·저장·내 정보 화면 | jokebear117 | #79, #80 | #79, #80 | — | 선행 종료 대기 |
| [#88](https://github.com/YongSamGo/RE_CONNECT/issues/88) | [W11-09] 운영자 관리 화면 | jokebear117 | #55, #57, #80 | #55, #57, #80 | — | 선행 종료 대기 |
| [#89](https://github.com/YongSamGo/RE_CONNECT/issues/89) | [W11-10] 읽어주기·종료·재진입 연결 | jokebear117 | #32, #43, #82, #83, #86 | #32, #43, #82, #83, #86 | — | 선행 종료 대기 |
| [#90](https://github.com/YongSamGo/RE_CONNECT/issues/90) | [W12-01] EC2·RDS·비공개 네트워크 | SeungwonKwon | #6, #18 | #6, #18 | — | 선행 종료 대기 |
| [#91](https://github.com/YongSamGo/RE_CONNECT/issues/91) | [W12-02] HTTPS·Nginx 경로·도메인 | SeungwonKwon | #13, #22, #90 | #13, #22, #90 | — | 선행 종료 대기 |
| [#92](https://github.com/YongSamGo/RE_CONNECT/issues/92) | [W12-03] EC2 GPU·모델 실행 환경 | SeungwonKwon | #18, #28, #90 | #18, #28, #90 | — | 선행 종료 대기 |
| [#93](https://github.com/YongSamGo/RE_CONNECT/issues/93) | [W12-04] CI·릴리스 이미지·배포 | SeungwonKwon | #19, #26, #91, #92 | #19, #26, #91, #92 | — | 선행 종료 대기 |
| [#94](https://github.com/YongSamGo/RE_CONNECT/issues/94) | [W12-05] 백업·최신 삭제 이력 관리 | SeungwonKwon | #25, #78, #90 | #25, #78, #90 | — | 선행 종료 대기 |
| [#95](https://github.com/YongSamGo/RE_CONNECT/issues/95) | [W12-06] 복원 후 삭제 재적용 | SeungwonKwon | #93, #94 | #93, #94 | — | 선행 종료 대기 |
| [#96](https://github.com/YongSamGo/RE_CONNECT/issues/96) | [W12-07] 주기 수집·보관 정리·장애 상태 | SeungwonKwon | #49, #55, #93 | #49, #55, #93 | — | 선행 종료 대기 |
| [#97](https://github.com/YongSamGo/RE_CONNECT/issues/97) | [W12-08] 롤백·운영 절차·인계 | SeungwonKwon | #93, #95, #96 | #93, #95, #96 | — | 선행 종료 대기 |
| [#98](https://github.com/YongSamGo/RE_CONNECT/issues/98) | [W13-01] 첫 비회원 전체 여정 통합 | jokebear117 | #34, #81, #83, #84, #85, #86, #88, #89, #93 | #34, #81, #83, #84, #85, #86, #88, #89, #93 | — | 선행 종료 대기 |
| [#99](https://github.com/YongSamGo/RE_CONNECT/issues/99) | [W13-02] 승인·버전·추천 경계 시험 | SeungwonKwon | #98 | #98 | — | 선행 종료 대기 |
| [#100](https://github.com/YongSamGo/RE_CONNECT/issues/100) | [W13-03] 회원 저장·삭제·복구 시험 | SeungwonKwon | #87, #95 | #87, #95 | — | 선행 종료 대기 |
| [#101](https://github.com/YongSamGo/RE_CONNECT/issues/101) | [W13-04] 웹·AI 공격 시험 | SeungwonKwon | #87, #98 | #87, #98 | — | 선행 종료 대기 |
| [#102](https://github.com/YongSamGo/RE_CONNECT/issues/102) | [W13-05] 음성 수명·한도·공유 자원 시험 | JBR-313 | #35, #98 | #35, #98 | — | 선행 종료 대기 |
| [#103](https://github.com/YongSamGo/RE_CONNECT/issues/103) | [W13-06] 실제 기기·접근성·사용성 시험 | jokebear117 | #87, #98 | #87, #98 | — | 선행 종료 대기 |
| [#104](https://github.com/YongSamGo/RE_CONNECT/issues/104) | [W13-07] 장애·배포·롤백 시험 | SeungwonKwon | #97, #98 | #97, #98 | — | 선행 종료 대기 |
| [#105](https://github.com/YongSamGo/RE_CONNECT/issues/105) | [W13-08] 결함 수정·재시험·릴리스 판정 | jokebear117 | #99, #100, #101, #102, #103, #104 | #99, #100, #101, #102, #103, #104 | — | 선행 종료 대기 |
| [#106](https://github.com/YongSamGo/RE_CONNECT/issues/106) | [W14-01] 대회 양식·채널·제출 목록 확인 | jokebear117 | #4 | #4 | — | 선행 종료 대기 |
| [#107](https://github.com/YongSamGo/RE_CONNECT/issues/107) | [W14-02] 제출 문서·발표·영상 준비 | jokebear117 | #98, #106 | #98, #106 | — | 선행 종료 대기 |
| [#108](https://github.com/YongSamGo/RE_CONNECT/issues/108) | [W14-03] 같은 릴리스로 제출물 확정 | jokebear117 | #97, #105, #107 | #97, #105, #107 | — | 선행 종료 대기 |
| [#109](https://github.com/YongSamGo/RE_CONNECT/issues/109) | [W14-04] 업로드·수신·최종 제출 확인 | jokebear117 | #108 | #108 | — | 선행 종료 대기 |
| [#125](https://github.com/YongSamGo/RE_CONNECT/issues/125) | [CHORE] AI 개발 도구 공용 권한 설정 — Claude·Codex 비밀값 읽기·위험 명령 차단 (AGT-04) | SeungwonKwon | 없음/본문 확인 | 없음 | [#156](https://github.com/YongSamGo/RE_CONNECT/pull/156) | 기존 PR 확인 |
| [#157](https://github.com/YongSamGo/RE_CONNECT/issues/157) | [W01-03] AWS 계정·결제·GPU 할당량 확보 | SeungwonKwon | #6 | #6 | — | 선행 종료 대기 |
