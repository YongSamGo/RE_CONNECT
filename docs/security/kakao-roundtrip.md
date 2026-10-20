# 카카오 인증 왕복 — W10-01

## 범위와 설정

`GET /api/v1/auth/kakao/start?purpose=login|save|reauth`와 `GET /api/v1/auth/kakao/callback`의 state·코드 교환·신원 확인을 구현한다. User 연결/회원 세션 전환은 #73, 저장 대기 이동과 시작 체험 정리는 #74다. 인증만으로 자료를 저장하거나 운영자 역할을 부여하지 않는다.

KAKAO_REST_API_KEY, KAKAO_CLIENT_SECRET, KAKAO_APP_ID, PUBLIC_ORIGIN을 실행 환경에서 설정한다. 실제 값은 커밋/로그/명령행에 넣지 않는다. REST 키/시크릿은 SecretStr이다. APP_ID는 REST 키와 다른 카카오 앱의 숫자 ID이며 access_token_info.app_id와 대조한다. 설정이 없으면 로그인 시작은503이고 기본 키/가짜 신원을 쓰지 않는다.

callback은 `PUBLIC_ORIGIN + /api/v1/auth/kakao/callback`으로 고정한다. 카카오 콘솔에 정확한 Redirect URI 등록이 필요하다. 요청 Host/Forwarded·return_to·redirect_uri로 바꾸지 않는다. 운영 Origin은 HTTPS이며 localhost HTTP 예외는 기존 development 설정에만 적용된다. 콘솔 변경은 이 구현이 수행하지 않는다.

## state·PKCE·외부 요청

state는32바이트 난수다. Redis에는 원문 대신 SHA-256 인덱스, 목적과 별도의 난수 PKCE verifier만 임시 보관한다. verifier의 SHA-256/S256 challenge를 인가 URL에 보내고 verifier는 토큰 교환 POST 본문으로만 보낸다. 실제 카카오 앱에서 PKCE 적용 여부도 정상 왕복으로 추가 확인해야 한다.

Redis Lua는 세션과 state를 같은 원자 연산에서 검사한다. 세션당 최대3개/각10분, 오래된 흐름부터 제거하며 기존 흐름을 덮어쓰지 않는다. Redis TIME과 세션 idle/absolute 만료를 사용하고 호출로 세션 수명을 연장하지 않는다. 회수·교체한 세션의 state는 남아 있어도 사용할 수 없다. callback에서 외부 토큰 교환 전에 state를 소모하므로 동시 재전송 중 하나만 진입한다. 실패/취소도 되살리지 않는다.

다른 세션/만료/재사용/형식 오류는 외부 교환 없이 실패한다. 중복 쿼리·동시 code/error·허용하지 않은 키·과대 쿼리도 거절한다. 유효 state와 access_denied일 때만 cancelled다. 목적은 state에서 읽고, state와 연계하지 못한 실패의 기본 목적은 login이다.

[카카오 공식 REST 문서](https://developers.kakao.com/docs/ko/kakaologin/rest-api)에 따라 고정 HTTPS 엔드포인트만 호출한다.

1. kauth.kakao.com/oauth/token: code·고정 redirect_uri·REST 키·시크릿·verifier를 form POST한다.
2. kapi.kakao.com/v1/user/access_token_info: Bearer 토큰의 앱 ID·만료·정수 회원번호를 검사한다.
3. kapi.kakao.com/v2/user/me: property_keys 빈 배열로 추가 프로필 항목을 요청하지 않고 회원번호 일치를 확인한다.

기본 TLS 인증서 검증, proxy 환경변수/redirect/retry 없음, 호출별5초/전체15초, JSON64KiB/Content-Type/identity 인코딩 제한을 적용한다. 중복 JSON 키·NaN·잘못된 토큰/신원 타입·다른 앱/회원번호·만료 토큰을 거절한다. 액세스/리프레시/ID 토큰은 DB·Redis·클라이언트로 보관/반환하지 않는다. 처리 중 메모리의 완전한 소거 보장은 아니다. OIDC ID 토큰을 해독해 신원으로 신뢰하지 않는다.

## 회원 연결의 완료 처리기

연결되지 않은 CompletionHandler의 기본 대체 구현은 성공을 만들지 않는다. 현재 main은 #73의 실제 MemberService를 연결한다([회원 세션](member-sessions.md)). login은 실제 User·새 세션을 연결하고 reauth는 같은 계정만 재인증한다. save는 #74 저장 대기 연결 전 expired다. 제공자 대역만 쓰는 단위 시험과 실제 DB/Redis 결합 검증을 구분한다.

CompletionHandler.eligible은 save 대기/회원 reauth 가능 여부를 시작 전에 검사한다. complete는 최소 Identity.subject와 시작 Session/목적을 받는다. 외부 대기 중 회수가 가능하므로 #73/#74에서는 세션/계정 상태를 다시 확인하고 원자적으로 처리해야 한다.

- login/save: User 연결, 새 세션·CSRF, 저장 대기 이동과 시작 체험 정리. 이전 세션 재사용 차단.
- reauth: 같은 계정 대조, 세션 교체 없이5분 재인증. 다른 계정은 실패.

완료 처리기가 없거나 장애면 성공을 만들지 않는다. 이 PR만으로 회원 로그인/MFA/저장이 완료된 것은 아니다. 후속에는 실제 Redis·DB 결합, 회수 중 callback, 세션 쿠키 교체 시험이 필요하다.

결과 주소는 `/auth/result?purpose=...&status=success|failed|cancelled|expired`뿐이다. code/state/외부 오류 설명을 복사하지 않고 no-store/no-referrer를 적용한다. 새 세션을 받는 경우 기존 Secure/HttpOnly/SameSite·CSRF 쿠키 경계를 재사용한다.

## 로그와 검증 한계

서버는 `python -m app`으로 실행한다. 기존 SafeJsonFormatter와 비활성 access log가 URL/쿼리/헤더/본문/예외 문자열을 버린다. 다른 ASGI 실행기·프록시·APM도 callback 쿼리를 기록하면 안 된다. 운영 Nginx/APM 설정 전체를 이 구현에서 검증한 것은 아니다.

가상 코드/토큰의 HTTP 전송 대역, 실제 Redis 원자성/수명, 실제 Redis+ASGI HTTP 경로 결합 시험으로 확인한다. 실제 카카오 앱·사용자 승인·정상 인가 코드는 아직 검증하지 않았고 사용자 로그인 동의를 대신하지 않았다. 등록 도메인/콘솔/동의 화면/회원 연결/운영 배포는 별도 확인한다.

## 일회 저장 전달 연결

#74의 [승인 저장 대기](../data/save-intents.md)가 실제로 연결되어 purpose=save는 해당 state의 살아 있는 대기만 새 회원 세션으로 옮긴다. 로그인은 저장을 대신하지 않으며 취소·만료·교체된 대기는 소비할 수 없다. 영구 저장 API는 #75/#76 후속이다.
