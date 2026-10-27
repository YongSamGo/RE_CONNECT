# 운영자 권한과 MFA — W07-01

관련 이슈: #52. KISA 보안약점: 적절한 인증 없는 중요기능 허용 (SEC-01), 부적절한 인가 (SEC-02), 반복된 인증시도 제한 기능 부재 (SEC-16), 암호화되지 않은 중요정보 (SEC-05).

## 역할 부여·회수

운영자 역할은 공개 API나 가입 화면에서 고를 수 없다. 첫 로그인은 항상 `role=user`로 만들어진다([회원 세션](member-sessions.md)). 역할 부여·회수와 MFA 등록·복구는 서버 셸에서 `backend/manage_operators.py`로만 한다. 대상자는 먼저 카카오로 한 번 로그인하고, 내 정보(`/me`)의 `user.id`를 관리자에게 전달한다.

| 명령 | 하는 일 | 세션 |
| --- | --- | --- |
| `grant <user-id>` | `role=admin`. 정지·삭제 진행 중 계정은 거절 | 유지. 관리 API는 MFA 전까지 403 `MFA_REQUIRED` |
| `enroll <user-id>` | 인증 앱 등록. 첫 코드가 맞을 때만 저장 | 유지 |
| `reset-mfa <user-id>` | 기기 분실 복구. 비밀값 삭제 후 다시 `enroll` | 모든 세션 즉시 만료 |
| `revoke <user-id>` | `role=user`, 비밀값 삭제 | 모든 세션 즉시 만료 |

```bash
cd backend
python manage_operators.py grant 00000000-0000-4000-8000-000000000000
python manage_operators.py enroll 00000000-0000-4000-8000-000000000000
```

- 모든 명령은 감사 기록(`role.grant`·`role.revoke`·`mfa.enroll`·`mfa.reset`, `actor_role=system`)을 30일 남긴다.
- 세션 만료는 `users.session_generation`을 올려서 한다. 회원 요청마다 DB 세대를 다시 읽으므로 다음 요청부터 401 `SESSION_EXPIRED`다.
- `enroll`은 대상이 운영자인지, 이미 등록됐는지, 삭제 진행 중인지를 먼저 확인한 뒤에야 등록 주소를 만든다. 인증 앱에 쓸 수 없는 항목이 남지 않게 하기 위해서다.
- `enroll`은 터미널(TTY)에서만 실행된다. 등록 주소(`otpauth://`)에 비밀값이 들어 있으므로 파이프·로그 파일로 내보내지 않는다. 주소는 한 번만 표시하고 저장하지 않는다. 코드는 화면에 보이지 않게 입력받으며 3번 틀리면 아무것도 저장하지 않는다.
- 일회용 복구 코드는 만들지 않는다. 복구는 `reset-mfa` 뒤 다시 `enroll`한다.

## OTP

- TOTP(RFC 6238): HMAC-SHA1, 6자리, 30초. 기기 시계 차이로 앞뒤 한 구간까지 받는다. 표준 라이브러리 `hmac`으로 계산하고 RFC 6238 부록 B 시험값으로 확인한다([totp.py](../../backend/app/modules/operators/totp.py)).
- 비밀값(20바이트)은 `operator_mfa_credentials`에 AES-256-GCM 암호문으로만 저장한다. 키는 [개인 본문 암호화](encryption.md)와 같은 키링이고, AAD·파생 키를 `kind=operator_mfa`·회원 ID·자격 ID에 묶는다. 키가 없으면 MFA 확인과 관리 API가 모두 503으로 닫힌다.
- OTP와 비밀값은 로그·감사 기록·Redis에 남기지 않는다.

## 확인 API와 세션 결합

`POST /api/v1/admin/mfa/verify`는 Origin·CSRF 검사와 IP 호출 한도를 거친다. 이어서 DB의 현재 역할이 `admin`인지 확인한 뒤에만 OTP를 비교한다.

- 한 트랜잭션에서 회원·자격 행을 잠그고 잠금 확인 → OTP 비교 → 재사용 검사 → 실패 수·잠금·성공을 기록한다.
- 재사용: 마지막으로 받은 시간 구간 이하의 코드는 받지 않는다. 관리 절차의 등록 확인 코드도 웹에서 다시 쓸 수 없다.
- 실패는 계정 단위로 센다. 연속 5회 실패하면 잠그고 5번째 응답부터 429 `MFA_LOCKED`(`Retry-After`)다. 잠금 중에는 정답도 비교하지 않는다. 로그아웃·재로그인으로 초기화되지 않는다.
- 잠금 시간은 연속 잠금마다 15분 → 1시간 → 24시간으로 늘어난다. 연속 10번 잠기면(연속 실패 50회) `reset-mfa` 뒤 다시 `enroll`할 때까지 막는다. ±1 구간을 받으므로 한 번에 맞힐 확률은 3/10⁶이고, 막히기 전까지 성공 확률은 약 1.5×10⁻⁴ 이하다. 잠금 시간만 두면 15분마다 5번씩 한 달 약 14,400번(약 4%)까지 시도할 수 있어서 상한을 두었다.
- 성공하면 실패 횟수와 연속 잠금 횟수가 0으로 돌아간다.
- 아직 `enroll`하지 않은 운영자의 확인 시도는 비교할 비밀값이 없으므로 `MFA_INVALID`로 응답하고, 감사에는 `mfa.fail`(`result=denied`)을 15분에 한 번만 남긴다.

### 운영 감시

- `mfa.lock` 감사가 생기면 해당 운영자에게 본인 시도였는지 확인한다. 본인이 아니면 운영자 카카오 계정이 탈취된 것으로 보고 `revoke`한 뒤 계정 보안을 점검한다.
- 막힘(연속 10번 잠금)은 본인 확인 뒤 `reset-mfa` → `enroll`로만 푼다.
- 성공하면 권한 상승으로 보고 새 세션·새 임의 주체·새 CSRF를 발급하고 이전 세션을 폐기한다. 로그인 전환과 같은 Lua 교체를 써서 이전 세션의 체험·저장 대기도 정리된다. MFA 확인(`mfa_until_ms`, `mfa_credential`)은 새 세션 해시에만 기록한다.
- 확인은 60분 동안 유효하고, 세션 절대 만료(12시간)를 넘지 않는다.

관리 API(`require_member(operator=True)`)는 요청마다 다음을 모두 확인한다. 화면 숨김에 의존하지 않는다.

1. 세션의 회원·세대가 DB와 같다(역할 회수·복구·정지·탈퇴 뒤 401).
2. DB 역할이 `admin`이다(아니면 403 `FORBIDDEN`).
3. 이 세션의 MFA 확인이 만료되지 않았다.
4. 세션에 기록한 자격 ID가 DB의 현재 자격 ID와 같다(재등록 뒤 이전 확인 무효).

2~4 중 하나라도 어긋나면 403 `MFA_REQUIRED`다(2는 `FORBIDDEN`). `/me`의 `mfa_verified`도 같은 기준으로 계산한다.

## 시험

| 파일 | 내용 |
| --- | --- |
| `tests/test_operator_totp.py` | RFC 6238 시험값, 시계 오차 범위, 형식 공격 입력 |
| `tests/test_operator_mfa.py` | 부여·등록·확인·재사용·잠금 단계 증가와 막힘·회수·복구·삭제 진행 계정·비밀값 변조·등록 전 시도 감사, 관리 스크립트 사전 확인 |
| `tests/test_operator_mfa_http.py` | 실제 Redis·SQL HTTP: 세션 교체, 이전 쿠키 재사용, CSRF·형식 거절, MFA 만료·재등록·회수 즉시 차단, 재로그인 잠금 유지, 일반 회원·익명 거절 |

`test_operator_mfa*.py`의 PostgreSQL·Redis 시험은 CI 통합 잡에서 실행한다. 실제 카카오 로그인과 EC2 배포에서의 확인은 #72·#73 실제 연동 검증과 함께 남아 있다.
