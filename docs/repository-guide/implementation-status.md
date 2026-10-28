# 구현 현황과 검증

> main 병합 코드만을 분석한 자료가 아니다. `54d2daa` 작업 브랜치 스냅샷 기준이다. [브랜치 비교와 분석 범위](README.md)를 확인한다.

기준 `54d2daa3f25e6e39d2abf5585786676d09be7941` · 2026-10-25. [README](README.md)의 증거 수준·시험 한계를 함께 읽는다. 상태는 표시 범위의 판단이며 개발 진행률을 백분율로 계산하지 않는다.

| 기능 | 상태 | 외부 의존 | 남은 작업·완료 조건 |
|---|---|---|---|
| SCOPE 교육·멘토링·지역활동 유형 | 설계만 존재 | 현재 계약은 employment/volunteering만 허용 | 기획서 PDF 13쪽·README의 넓은 참여 유형과 차이가 있음. 범위 축소 승인 여부는 미확인. 완료: MVP 축소를 명시 승인하거나 공통 계약·수집·필터·UI·평가를 함께 확장 |
| F0 실제 체험 시작·안내 | 부분 구현 | 게시 처리 안내·Redis·제어 키 | 운영 주체·문의·보관/삭제 안내 확정과 게시. 완료: 승인된 안내로 실제 브라우저에서 동의→체험 생성·재전송 검증 |
| F1 대화형 경험 추출 | 부분 구현 | Ollama·Redis | 실모델 품질·음성·연속 여정 검증. 완료: 근거 없는 사실 거절과 정상 경험 보존을 실제 모델·브라우저에서 확인 |
| F1b 프로필 편집·확정 | 부분 구현 | Redis·현재 동의 | 이번 환경의 Redis 경합 시험 제외. 완료: 동시 편집·재확정·역할/초안 영향 실제 Redis 시험과 화면 확인 |
| F2 경험 기반 역할 탐색 | 부분 구현 | 검수 역할 사전 | 실제 사전·공고 표본 평가. 완료: 역할 근거·별칭·제외/복원 기능을 실 표본에서 평가 |
| F3a 외부 수집·정규화 | 부분 구현 | 공개 API 키·활성 출처·DB | 실 수집 운영과 검수 가능한 공고 확보. 완료: 허용 출처에서 제한 수집→대기 버전→검수 사유 저장 확인 |
| F3b 운영자 검수·공개·신고 | 부분 구현 | 운영자 MFA·/admin 서버 경로 | 화면/계약과 서버 기능 연결. #52 보류는 기존 문서의 사용자 결정. 완료: MFA 성공 세션만 등록·승인·숨김·신고·감사 API에 접근 가능 |
| F4a 공개 공고 목록·상세 | 구현됐으나 미검증 | DB 공개 포인터 | 이번 분석에서 실제 DB·브라우저 API 연결 미실행. 완료: 승인 공고 검색·상세·마감/신선도 처리를 실제 DB와 화면에서 확인 |
| F4b 추천 순위 계산 코어 | 구현 및 검증 완료 | 정상 확정 프로필·공고·사전 입력 | 실 사용자 품질·검색 재현율 평가. 완료: 코어 회귀 통과. 제품 추천 완료는 실 사전·공고·연속 여정 검증 후 |
| F5 자격 비교 계산 코어 | 구현 및 검증 완료 | 명시 조건·확정 정보 | 실 공고 원문 해석의 정확성·API 연동 검증. 완료: 3상태·AND/OR·연령 경계 코어 검증. 제품 판단은 원문 재확인 필요 |
| F6 지원서 초안·편집·승인 | 부분 구현 | 확정 프로필·공고·모델 | 실모델·Redis·브라우저 연속 검증. 완료: 근거 변경 시 재검토와 재승인, 현재 승인본 복사를 연속 확인 |
| F7 회원 저장·철회·탈퇴·복원 | 부분 구현 | 카카오·게시 저장 안내·키·삭제 이력 | 실 로그인·RDS·IAM/KMS·복원 연습. 완료: 타인 접근 차단·동의 철회·탈퇴·복원 후 삭제 재적용을 운영 구성에서 확인 |
| F8 STT·TTS 음성 | 구현됐으나 미검증 | 모델 가중치·런타임·장치 | 이번 분석에서는 음성 시험·실 GPU 실행 안 함. 완료: 실 한국어·기기·모델 공존/OOM·정상 종료·지연 실측 |
| F9 배포·주기 관리·릴리스 | 구현됐으나 미검증 | 실 EC2/RDS·HTTPS·이미지·계정 승인 | 정확 HEAD CI·실 배포·복구·스케줄 검증. 완료: 같은 소스/이미지의 통합 증거와 G1~G6 게이트 승인 |
| P1 임베딩·pgvector 검색 | 범위 제외 | 초기 구성에는 포함 안 함 | README에는 계획이 남아 있으나 최신 Plan/03에서 초기 범위 제외. 완료: 필요성 평가 뒤 별도 결정. 현재 기능 미완성으로 집계하지 않음 |
| P2 외부기관 자동 제출 | 범위 제외 | MVP 제외 | 구현 목표 아님. 사용자가 공식 신청처에서 직접 신청. 완료: 현재 범위를 유지. 확장하려면 별도 제품·보안 결정 |
| V0 운영 데이터·실기기 품질 | 확인 불가 | 운영 접근·실측 기록 | 실계정·운영 DB·비밀값은 조회하지 않음. 완료: 승인 환경에서 현재 상태·성능·접근성 증거 확보 |

## 이번 검증 명령

프론트 `frontend/`에서:

```powershell
npm.cmd test -- --reporter=dot
npm.cmd run lint
npm.cmd run build
```

백엔드 `backend/`에서 기존 Python 3.12 가상환경으로:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_architecture.py tests/test_grounded_generation.py tests/test_recommendations.py tests/test_eligibility_rules.py tests/test_eligibility_evaluator.py tests/test_journeys.py tests/test_source_normalization.py tests/test_ingestion_fetch.py tests/test_request_security.py tests/test_encryption.py
.\.venv\Scripts\python.exe -m pytest -q -rs tests/test_journey_messages.py tests/test_profile_confirmation.py tests/test_recommendation_filters.py tests/test_eligibility_api.py tests/test_journey_drafts.py tests/test_draft_approval.py tests/test_saved_profiles.py tests/test_published_notices.py tests/test_anonymous_journey_flow.py
```

첫 실행 413통과·9제외, 둘째 63통과·81제외. 실제 `PERSISTENCE_TEST_DATABASE_URL`·`PERSISTENCE_TEST_REDIS_URL`을 새로 설정하지 않았다. 제외된 시험을 통과로 간주하지 않는다. 특히 `test_anonymous_journey_flow.py`의 정상/guarded·SQLite/PG 연속 경로는 이번에 실행 완료하지 못했다. 프론트 기본 시험은 별도 backend-contract/draft-contract 설정의 실행을 포함하지 않는다.

## 권장 순서와 완료 조건

1. **안내·범위 결정**: 운영 주체·문의·리전·보관/삭제 내용을 승인하고 게시한다. 미리보기/실제 체험 분리를 유지한다.
2. **검수 입력 확보**: 기존 MFA 보류 결정을 확인하고 검수 서버를 연결한다. 승인 공고 20건 목표를 현재 DB에서 다시 집계한다.
3. **한 비회원 여정 연결**: 같은 HEAD·이미지의 브라우저→HTTPS→API→실 PostgreSQL/Redis→실모델 흐름을 동의부터 종료까지 검증한다. 오류·재전송·동시 변경도 확인한다.
4. **회원·음성 별도 게이트**: 실 카카오/저장 동의/키·삭제 복원, 음성 장치/품질/자원 공존을 독립 검증한다.
5. **통합·릴리스 정리**: develop 기준 충돌·변경 분리·정확 HEAD CI·운영 복구·접근성 증거를 맞추고 G1~G6 조건을 승인한다.

이전 게이트 문서의 승인 공고 0/20, #52 보류, 과거 CI 결과는 그 문서 시점의 기록이다. 현재 원격 이슈/PR/공고 DB 상태는 확인하지 않았다.
