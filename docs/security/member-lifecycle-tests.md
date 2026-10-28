# 회원 저장·삭제·복구 시험 대응표 (W13-03, #100)

W13-03의 세 단계를 백엔드 시험에 대응시킨다. 기존 시험이 다루는 경계는 그대로 두고, 빈칸은 `backend/tests/test_member_lifecycle_matrix.py`에 더했다. 모두 실제 PostgreSQL·Redis와 ASGI HTTP 요청을 쓰며, 제공자·안내문·키·본문은 가상 데이터다.

## 1단계 · 로그인 취소·재사용, 저장 대기 만료

| 시나리오 | 확인하는 결과 | 시험 |
| --- | --- | --- |
| 제공자에서 로그인 취소(`access_denied`) | `status=cancelled`, 회원 생성 없음, 저장 대기 폐기, 비회원 세션·체험 유지 | `test_member_lifecycle_matrix` 취소 시험, `test_save_intents` cancel |
| 취소로 소비한 state를 승인 코드로 재사용 | 성공 아님, 회원 생성 없음 | `test_member_lifecycle_matrix` 취소 시험, `test_kakao_state` |
| 취소 뒤 새 저장 대기로 재시도 | 옛 대기 ID는 404, 새 대기는 한 번만 저장(버전·응답 기록 1개), 같은 키는 같은 응답, 다른 키는 409 | `test_member_lifecycle_matrix` 취소 시험 |
| 로그인 전 저장 대기 만료·교체 | `status=expired`, 회원 생성·전달 없음 | `test_save_intents` expire·replace |
| 로그인 뒤 저장 전에 대기 만료 | 404, 저장본·응답 기록 0, 로그인 유지, 대기 표시 없음 | `test_member_lifecycle_matrix` 만료 시험 |
| 동시 콜백·state 1회 사용 | 회원 세션 1개 | `test_member_auth`, `test_kakao_state` |
| 저장 대기 취소 | 소유자 범위, 멱등, 실패 시 대기 보존 | `test_save_intent_cancel` |

## 2단계 · 다른 회원, 동시 저장·철회·탈퇴

| 시나리오 | 확인하는 결과 | 시험 |
| --- | --- | --- |
| 다른 회원·익명·운영자의 조회·수정·저장·삭제 | 404/401, 주인 자료 불변 | `test_member_security_matrix` ([행렬](member-save-matrix.md)) |
| 같은 키·같은 기준 버전 동시 저장 | 버전 1개 증가, 응답 기록 1개, 늦은 요청 409 | `test_member_security_matrix` |
| 기기B 저장 중 기기A 삭제 | 늦은 문서 재생성 없음, 모든 옛 세션 종료 | `test_member_security_matrix`, `test_deletions` |
| 철회 목적별 삭제, 늦은 동의 부여 | 목적 자료만 삭제, 늦은 동의 무효 | `test_deletions` |
| **두 기기에서 동시에 탈퇴** | 먼저 끝난 요청 204, 늦은 요청 401 `SESSION_EXPIRED`, 계정 삭제 이력 1건, 재시도할 일 없음, 흔적 0 | `test_member_lifecycle_matrix` |
| **탈퇴 중 다른 기기에서 저장 동의 철회** | 탈퇴 204, 철회 401 `SESSION_EXPIRED`, 흔적 0 | `test_member_lifecycle_matrix` |
| **탈퇴 뒤 흔적** | 아래 "흔적 검사"가 SQL·Redis 모두 0 | `test_member_lifecycle_matrix` |

## 3단계 · 늦은 결과, 백업 복원 뒤 삭제

| 시나리오 | 확인하는 결과 | 시험 |
| --- | --- | --- |
| 취소·삭제·만료 뒤 늦은 결과 완료(내부 경계) | 완료 거절, 키 재생성 없음 | `test_result_lifecycle`, `test_request_coordination` |
| 체험 종료·로그아웃 뒤 늦은 생성·복사 | 404/401, 키 재생성 없음 | `test_journey_drafts`, `test_journey_end`, `test_saved_material_editing` |
| **AI 지원서 생성 중 탈퇴·저장 철회·AI 철회** | 늦은 결과 404 `NOT_FOUND`, 체험 키 0, 옛 쿠키·같은 키 재전송도 재생성·모델 재호출 없음 | `test_member_lifecycle_matrix` |
| 프로필 삭제 뒤 DB 스냅숏 복원 | 독립 삭제 이력으로 재적용, 새 저장본은 유지 | `test_deletions` |
| **계정 삭제 뒤 DB 스냅숏 복원** | `recover` 1건 재적용 뒤 흔적 0, 같은 카카오 계정은 새 회원으로 로그인하고 옛 저장본을 못 봄, 재실행해도 새 회원 유지 | `test_member_lifecycle_matrix` |
| 삭제 이력 파일의 위조·모호·심볼릭 링크 | 복구 거절 | `test_deletion_journal` |
| 외부 이력 저장 실패 | 로그인·조회 차단, 관리 재시도 뒤 삭제 | `test_deletions`, `test_member_security_matrix` |

## 흔적 검사

탈퇴한 회원의 흔적은 표 이름을 손으로 적지 않고 스키마에서 다시 읽어 찾는다. 새 표나 칸이 생겨도 검사에서 빠지지 않게 하기 위해서다.

- **SQL**: 모든 표의 UUID 칸에서 회원 ID를, 모든 문자열 칸에서 카카오 식별자를 찾는다. 복원 재적용에 필요한 최소 이력 표(`deletion_records`, `audit_events`)만 뺀다. 이 두 표에는 본문과 외부 ID가 없다.
- **Redis**: 시험의 키 접두어 아래 모든 키의 이름과 값에서 회원 ID, 회원 세션 다이제스트, 체험 ID를 찾는다.
- 검사가 실제로 누락을 잡는지 앱 코드를 일부러 바꿔 확인했다. Redis 정리를 빼면 흔적 시험과 늦은 결과 시험이, 탈퇴에서 응답 기록 삭제를 빼면 SQLite(외래키 연쇄 삭제 없음)의 흔적 시험과 복원 시험이 실패했다.

## 이 대응표가 증명하지 않는 것

- 실제 RDS 스냅숏 격리 복원, 운영 외부 삭제 이력의 위치·권한·보관기간: W12-05(#94)·W12-06(#95)에서 확인한다. 여기서는 격리 시험 DB에 삭제 전 행을 다시 넣어 복원을 재현했다.
- 화면 쪽 시험(로그인 취소·저장 실패·탈퇴 안내): W11-08(#87) 머지 뒤 더한다.
- 실제 카카오 승인·EC2·실기기 증거. 이 시험 통과만으로 #100을 통과로 옮기지 않는다.
