# 승인·버전·추천 경계 시험 대응표 (W13-02)

관련 이슈: [#99](https://github.com/YongSamGo/RE_CONNECT/issues/99). [기능 명세](../../Plan/04_Functional_Specification.md)의 F03·F04·F06·F07·F08·F10 시험 항목을 이미 있는 모듈별 시험과 새 연결 시험에 대응시킨다.

## 연결 시험

`backend/tests/test_boundary_journey.py`는 실제 Redis 체험·확정본과 SQLite/PostgreSQL 공개 공고를 한 HTTP 앱에 묶고, 체험 하나로 아래 순서를 이어간다. 모듈별 시험은 경계를 하나씩 보므로 앞 단계의 결과가 뒤 단계 판단에 남아 있는지는 이 시험이 본다.

1. 확정 전 참조로 추천·자격을 요청하면 `PROFILE_NOT_CONFIRMED`
2. 확정 뒤 추천: OR 그룹 하나 충족은 유지, 필수 미충족·마감은 제외, 해석하지 못한 조건은 `unknown`과 확인 필요 1건으로 유지, 모든 근거가 확정본의 실제 경험
3. 자기 확정본으로는 추천·자격을 받는 다른 주체도 남의 확정본·체험으로 보낸 추천·자격·역할 제외 요청은 `404`, 없는 확정 버전·공고 버전은 `VERSION_CONFLICT`
4. 공고의 중요 변경(필수조건)이 수집되면 재검수 전까지 추천에서 빠진다. 공개본은 그대로라 자격 판정은 공개 1판 기준이고 신청 안내는 `change_pending`을 알린다
5. 운영자가 새 판을 승인하면 이전 판 기준 자격 요청은 `VERSION_CONFLICT`, 새 판 기준으로 다시 판정한다
6. 역할 제외는 그 역할이 붙은 공고만 개인 추천에서 빼고, 오래된 리비전 기준 변경은 `409`, 복원하면 다시 나온다
7. 재확정하면 이전 확정본 기준 추천·자격은 `409`, 새 확정본으로 새 공고 판을 다시 판정한다. 이전 확정본 내용은 바뀌지 않는다

재검수 대기 제외(`recommendations/filters.py`)나 자격의 공고 버전 검사(`eligibility/service.py`)를 빼면 이 시험이 실패하는 것을 로컬에서 확인했다.

## 명세 항목별 대응

| 이슈 단계 | 명세 시험 항목 | 모듈별 시험 | 연결 시험 |
| --- | --- | --- | --- |
| 1. 초안·소유권·버전 거절 | F03 확정 전 추천 차단·초안 직접 수정 | `test_profile_confirmation`, `test_recommendations` | 1 |
| | F03 기준 리비전 충돌 | `test_profile_confirmation`(실제 Redis 동시 확정), `test_draft_approval` | 6 |
| | F06·F07 확정 프로필 소유권·타 체험 접근 | `test_eligibility_api`, `test_role_exclusions`, `test_recommendations` | 3 |
| | F07 버전 변경 후 재평가 | `test_eligibility_api`(평가 도중 공고 변경) | 3, 5 |
| 2. 재확정·OR·unknown·마감·재검수 | F03 재확정 후 추천 갱신·지원서 재검토 표시 | `test_reconfirmed_results` | 7 |
| | F07 AND·OR 3상태 조합 | `test_eligibility_evaluator`(48가지 판정), `test_eligibility_api` | 2 |
| | F06 OR 그룹 충족 후보 유지·확인 필요 표시 | `test_recommendation_filters`, `test_recommendations` | 2 |
| | F06 마감·미검수·보류 제외 | `test_opportunity_lifecycle`, `test_recommendation_filters`, `test_public_opportunities` | 2, 4 |
| | F05·F10 중요 변경 재검수 | `test_ingestion_versions`, `test_opportunity_reviews` | 4, 5 |
| 3. 역할 제외·근거·신청 안내 | F04 제외·복원·타 체험 제외 목록 접근 | `test_role_exclusions`, `test_roles` | 3, 6 |
| | F04·F06 무근거 추천 차단 | `test_recommendations`, `test_roles` | 2 |
| | F08 공식 절차 표시·없는 서류 생성 금지 | `test_preparation` | 4, 5 |
| | F08 근거 변경 시 지원서 승인 차단 | `test_draft_approval`, `test_reconfirmed_results` | 해당 없음 |

지원서 초안 생성은 로컬 LLM 호출이 필요해 연결 시험에 넣지 않았다. 근거가 바뀐 뒤 승인 차단은 `test_draft_approval`이 실제 Redis에서 본다.

## 남은 범위

- 화면 쪽 경계(재검토 표시·확인 필요 안내·신청 안내 화면)는 [#98](https://github.com/YongSamGo/RE_CONNECT/issues/98) 첫 전체 여정 이후에 더한다.
- 실제 검수 공고와 운영 EC2/RDS 구조에서 같은 순서를 재현한 증거가 없다. 그 전에는 W13-02를 통과로 옮기지 않는다 ([진행 기록](../progress/w13-02-boundary-tests.md)).
