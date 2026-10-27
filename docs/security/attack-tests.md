# 웹·AI 공격 시험 대응표 (W13-04 · #101)

W13-04 공격 시나리오를 어떤 시험이 재현하는지 한곳에 모은다. 완료 조건은 "결과·권한·검수 상태 조작 차단"이고, 자동 도구(gitleaks·Bandit·pip-audit·CodeQL) 통과만으로 완료하지 않는다. 그래서 시나리오마다 공격 입력을 직접 보내고, 응답 코드만 보지 않고 저장된 상태가 그대로인지 다시 읽는 시험을 적는다.

**현재 범위:** 백엔드 HTTP·저장소·모델 경계다. 화면을 거치는 공격(운영자 화면의 신고 설명·편집기 출력, 로그인·저장 화면)은 #87·#98 이후 같은 표에 더한다. 실제 EC2·배포 환경 증거가 없으므로 이 문서만으로 이슈를 "통과"로 옮기지 않는다.

## 운영자 경로 행렬

`backend/tests/test_admin_security_matrix.py`가 실제 Redis 세션·SQL 계정·MFA 저장소로 모든 `/admin/*` 경로를 시도한다. 모듈별 시험은 운영자 판정을 대역으로 바꿔 저장소 경계만 보므로, 이 행렬이 실제 로그인·역할·MFA 판정과 저장소를 함께 묶는다. SQLite와 PostgreSQL에서 모두 돈다.

| 주체 | 공고 목록·등록·상세·수정 | 승인·반려·비공개·모집 종료 | 신고 목록·처리 |
| --- | --- | --- | --- |
| 비회원 세션 | 401 `UNAUTHENTICATED` | 401 | 401 |
| 일반 회원 | 403 `FORBIDDEN` | 403 | 403 |
| MFA를 확인하지 않은 운영자 | 403 `MFA_REQUIRED` | 403 | 403 |
| MFA 확인이 만료된 운영자 | 403 `MFA_REQUIRED` | 403 | 403 |
| 역할을 회수당한 운영자 | 401 `SESSION_EXPIRED` → 이후 비회원 | 401 | 401 |
| MFA를 확인한 운영자 | 정상 처리 | 정상 처리 | 정상 처리 |

- 모든 시도에 `X-Role`·`X-User-Role`·`X-MFA-Verified`·`X-User-ID`·`X-Account-ID`·`X-Forwarded-For` 위조 헤더를 함께 보낸다. 주체마다 시도가 끝나면 공고 버전·공개 포인터·검수 근거·등록 응답 기록·신고·감사 기록을 다시 읽어 하나도 바뀌지 않았는지 본다.
- 확인된 운영자도 본문에 `review_status`·`actor_id`·`reviewed_at`·`version`·`published_version`을 넣으면 422이고 상태는 그대로다. 정상 승인의 감사 기록 작성자는 위조 헤더가 가리킨 다른 운영자가 아니라 세션 주체다. 같은 결정을 다시 보내면 409이고 감사 기록은 한 번만 남는다.
- 운영자 쿠키만 훔쳐 다른 Origin·CSRF 없이·위조 CSRF로 보내면 403 `CSRF_FAILED`다. 로그아웃한 세션 쿠키로는 결정할 수 없다.
- 운영자 경로가 새로 생기면 `test_matrix_covers_every_admin_route`가 실패한다. 행렬에 경로를 더하고 위 표를 고친다. MFA 확인(`POST /admin/mfa/verify`)은 정상 시도도 실패 횟수·감사 기록을 남기므로 이 행렬에서 빼고 `test_operator_mfa_http.py`에서 본다.

## 1. SQL 삽입·XSS·CSRF·권한/ID 우회

| 시나리오 | 시험 |
| --- | --- |
| 검색어의 `' OR 1=1 --`·LIKE 메타문자 | `test_public_opportunities::test_literal_bound_search_tags_roles_filters_and_page_order`, `test_admin_opportunities::test_list_filters_literal_search_important_change_and_recent_first`, 운영자 행렬 |
| 경로 ID·열거형 필터·페이지 번호의 SQL 조각과 큰 정수 | 운영자 행렬 (`test_verified_operator_cannot_inject_review_state_actor_or_sql_...`) |
| HTML·스크립트·`javascript:` 입력 | `test_admin_opportunities::test_patch_rejects_unsafe_or_invalid_changes_without_new_version`, `test_source_normalization::test_html_never_retains_active_content_or_attributes`, `test_contracts`, `test_preparation` |
| 오류 응답에 입력 원문이 다시 나옴 | `test_errors::test_validation_error_has_fields_without_input` |
| CSRF 토큰·Origin 누락·위조, Redis 장애 시 우회 | `test_request_security::test_missing_forged_or_non_origin_values_are_rejected`, `test_csrf_cookie_header_and_signature_are_all_required`, `test_no_configured_origin_fails_closed...`, `test_redis_failure_cannot_bypass_csrf_validation`, 모듈별 운영자 시험, 운영자 행렬 |
| 로그인 CSRF(state) | `test_kakao_state` |
| 다른 회원 자료 조회·수정·저장·삭제, 계정 위조 헤더 | `test_member_security_matrix::test_two_members_anonymous_and_operator_cannot_read_edit_save_or_delete_another_owners_data` ([회원 행렬](member-save-matrix.md)) |
| 다른 회원의 적합성 판정 결과 | `test_eligibility_api::test_cross_owner_stale_opportunity_and_late_profile_change_do_not_return_old_results`, `test_request_rejects_raw_profile_and_forged_decisions` |
| 운영자 권한 우회·MFA 우회·역할 회수 | 운영자 행렬, `test_operator_mfa_http` |
| 검수 상태·작성자 위조, 오래된 기준 버전 | 운영자 행렬, `test_opportunity_reviews::test_stale_or_invalid_transitions_change_nothing`, `test_audit_failure_rolls_back_state_and_reason`, `test_reports::test_stale_or_backward_transition_changes_nothing` |

## 2. SSRF·XXE·과대 파일/응답

| 시나리오 | 시험 |
| --- | --- |
| 사설·전환 주소로 풀리는 DNS, 공개·사설 섞인 응답 | `test_ingestion_fetch::test_private_and_transition_dns_answers_never_connect`, `test_mixed_public_private_dns_is_rejected` |
| 리다이렉트 추적·인증키 전달, 요청이 URL을 고름 | `test_ingestion_fetch::test_redirect_never_followed_and_key_never_forwarded`, `test_request_cannot_supply_url_or_unbounded_parameters` |
| DTD·외부 엔티티·XInclude, 깊이·개수 폭주 | `test_ingestion_fetch::test_dtd_entity_and_external_reference_rejected_in_all_encodings`, `test_xinclude_remains_untrusted_element_without_fetch`, `test_xml_depth_count_and_text_limits` |
| 과대 JSON·multipart·chunked·압축 본문 | `test_request_security::test_exact_json_byte_limit_and_oversized_rejection_before_handler`, `test_multipart_upload_has_a_separate_bounded_envelope_allowance`, `test_ambiguous_lengths_and_compressed_inputs_are_rejected`, `test_chunked_request_without_content_length_is_counted_by_actual_bytes` |
| 과대 외부 응답(길이 선언·스트림) | `test_ingestion_fetch::test_announced_oversize_rejected_before_body`, `test_stream_oversize_without_length_rejected` |
| 과대 음성 파일 | `test_transcriptions`, `test_speech_api` |

서버가 밖으로 나가는 대상은 고정 주소(공공 API, 내부 음성 서비스, 로컬 모델)뿐이고 요청 값으로 바꿀 수 없다.

## 3. 프롬프트 인젝션·허위 사실·악성 모델 출력

| 시나리오 | 시험 |
| --- | --- |
| 사용자 발화의 지시문("이전 지시는 무시"), 개인정보 | `test_grounded_generation::test_privacy_and_instruction_screen`, `test_persona_attack_turns_are_not_sent_or_citable` |
| 공고 원문 속 지시문이 확인하지 않은 자격·경력을 쓰게 함 | `test_journey_drafts::test_injected_opportunity_text_cannot_add_unconfirmed_facts` |
| 모델이 원문에 없는 경험·기간·자격을 만들거나 승인 표시를 넣음 | `test_grounded_generation::test_invented_facts_references_and_approval_are_rejected`, `test_application_rejects_foreign_facts_invention_and_authority` |
| 모델 출력의 추가 필드·형식 위반, 다른 Adapter 반환값 | `test_grounded_generation::test_schemas_forbid_extra_fields`, `test_adapter_result_is_revalidated...` |
| 검수·승인 상태를 모델 출력으로 바꿈 | `test_draft_review`, `test_draft_approval` |

모델은 고정 지시문과 비신뢰 데이터 칸을 따로 받고, 결과는 서버가 원문 대조·고정 문구 조립으로 다시 검사한다([생성 근거 검증](../ai/generation.md)).

## 실행

운영자 행렬과 회원 행렬은 실제 Redis·PostgreSQL이 필요하다. `PERSISTENCE_TEST_REDIS_URL`·`PERSISTENCE_TEST_DATABASE_URL`이 없으면 건너뛰고, 건너뛴 시험을 통과로 세지 않는다. CI의 PostgreSQL·Redis 통합 잡이 두 행렬을 실행한다.
