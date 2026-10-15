# API 타입·통신 기반 — W02-08.a / #19

아래는 통신 기반 최초 구현의 기록이다. 후속 화면의 API 사용과 현재 연동 상태는 [프론트엔드 진행 기록](../../PROGRESS.md)을 따른다.

이 변경은 #118의 화면 기반 위에서 진행하는 별도 PR이다. #5(API 계약 #116·#117), #13(화면 기반 #118), #15(백엔드 공통 타입)가 아직 완료되지 않아 **준비 구현·초안**이다. 화면에 실제 API를 연결하지 않았으며 #19 전체를 통과로 처리하지 않는다.

## 계약 원본과 변경 감지

`docs/api/openapi.yaml`이 단일 원본이다. 현재 브랜치에는 아직 없으므로 `frontend/api-contract.json`이 #117의 커밋·경로·SHA-256을 고정한다. 생성 도구는 원본이 로컬에 있으면 반드시 그 파일을 사용한다. 없을 때만 고정 커밋의 공개 GitHub 파일을 받아 해시를 확인한다. 네트워크·해시 오류 시 빌드는 실패하며 기존 타입을 조용히 재사용하지 않는다. 원본 YAML을 이 PR에 중복 복사하거나 수정하지 않았다.

`frontend/`에서:

```powershell
npm ci --ignore-scripts
npm run api:generate
npm run api:check
npm run build
```

`schema.d.ts`는 생성 파일이다. `api:check`는 새로 생성한 결과와 커밋된 파일을 비교하며 `build`가 이 검사를 포함한다. 기존 CI에서도 자동 실행된다. 계약이 바뀌면 다시 생성한 diff와 화면·통신 코드를 함께 검토한다. `contract.typecheck.ts`는 실행되지 않지만 타입 검사 대상이다. 없는 경로·잘못된 메서드·금지 enum·필수 본문/멱등 키/명시적 null 누락을 컴파일 단계에서 잡는다.

OpenAPI 3.1의 `contentMediaType=audio/wav`·`application/octet-stream` 및 `format=binary`는 브라우저의 `Blob` 타입으로 생성한다. 계약 원문의 필드·제약을 바꾸지 않는 타입 표현 변환이다.

`fixtures.ts`는 #117의 비회원 `/me`, 409, 429 예제를 옮긴 **테스트용** 자료다. 생성 타입과 일치하는지 검사하며 앱에 주입하지 않는다. 실제 API·FastAPI OpenAPI와의 일치 검증은 백엔드 구현 후 남아 있다. 타입 생성은 실행 중 응답의 JSON Schema 검증을 제공하지 않는다.

`openapi-typescript@7.13.0`은 TypeScript 5.x를 peer로 요구하므로 초기 골격의 6.0.3에서 5.9.3으로 맞췄다. peer 검사 우회 없이 정확한 버전과 lockfile을 갱신했다.

## 화면에서 사용할 방법

```typescript
import { createApiClient } from './client'
import { ApiError } from './errors'

const api = createApiClient() // 생성만으로 통신하지 않음
const controller = new AbortController()
try {
  const { data } = await api.GET('/me', { signal: controller.signal })
  // 서버의 인증·동의 상태 확인. 비회원도 정상 200이다.
  console.assert(data !== undefined)
} catch (error) {
  if (error instanceof ApiError) {
    // error.message는 고정된 안내. 입력은 메모리에 유지한다.
    // code로 만료·버전 충돌·분당/일일 한도·AI 혼잡을 구분한다.
  }
}
// 화면 종료·자료 삭제·세션 전환에서는 controller.abort()로 이전 작업을 취소한다.
```

- HTTPS는 `__Host-rc_csrf`, 로컬 HTTP(loopback 한정)는 `rc_csrf`를 사용한다. 변경 요청마다 쿠키를 다시 읽어 `X-CSRF-Token`을 덮어쓴다. 토큰이 없으면 전송하지 않는다. `/me` 부트스트랩은 화면이 명시적으로 수행해야 한다.
- `Idempotency-Key` 필수 연산에는 `params.header`로 UUID를 제공한다. 같은 논리 요청의 수동 재전송에는 같은 키와 본문을 유지한다. 새 요청은 새 키를 사용한다. 클라이언트는 키를 자동 생성하거나 요청을 자동 재시도하지 않는다.
- 통신은 현재 origin의 `/api/v1/`에만 허용한다. `credentials=same-origin`, `cache=no-store`, `mode=same-origin`, `redirect=error`를 강제한다. 요청별 `fetch`·`Request`·`middleware` 확장점은 거절하며 전역 middleware 등록도 노출하지 않는다. 테스트용 transport 주입은 클라이언트를 생성할 때만 가능하다.
- OAuth 시작·콜백은 fetch 대상 타입에서 제외했다. 카카오 로그인은 서버 state와 최상위 페이지 이동으로 구현해야 한다. health는 내부용이므로 브라우저에서 호출하지 않는다.
- `ApiError`는 서버의 원문 `message`, 입력이 포함될 수 있는 `fields`, 내부 예외를 전달하지 않는다. 알려진 code/HTTP 상태 조합에만 고정 안내를 사용하고 나머지는 일반 오류로 바꾼다. 제한된 형식의 요청 추적 ID와 정수 `Retry-After`만 보조 정보로 제공한다. 일일 한도에는 즉시 재시도 시간을 표시하지 않는다.
- 기본 제한시간은 65초(서버 AI 한도 60초에 전송 여유를 둔 클라이언트 기본값)다. 취소·시간 초과 뒤 늦게 온 결과도 반환하지 않는다. 서버의 작업 취소·삭제 후 재생성 차단은 별도 구현이다. 타임아웃이 서버 처리 실패를 증명하지 않으므로 최신 상태·같은 멱등 키를 확인한 뒤 재시도한다.
- JSON 응답은 content type·문법을 확인한다. `/speech`는 `parseAs: 'blob'`을 지정하지 않으면 거절한다. 서버 표시 자료의 ID·버전 참조를 전달한다. 옵션은 `const speechOptions = { ... , parseAs: 'blob' } as const`로 두고 `api.POST<'/speech', typeof speechOptions>('/speech', speechOptions)`처럼 명시하면 바이너리 결과 타입을 유지한다. 전사는 계약의 multipart 본문과 `bodySerializer`로 FormData를 구성한다. 녹음 형식·크기/시간·자원 해제는 W11-04에서 구현한다.
- 성공 응답의 필드·값 범위는 현재 타입 검사만 제공한다. 서버 런타임 검증은 #15 등 백엔드 작업과 연결해야 한다. UI의 접근 제한은 서버 인가를 대신하지 않는다.

메모리·취소 signal은 호출 화면이 소유한다. 이 모듈은 화면 상태를 갱신하거나 브라우저 저장소·로그에 본문·쿠키를 기록하지 않는다. 개인 체험 미리보기는 서버 요청 없이 작동한다. W11-02.a의 공개 탐색에서만 사용자가 검색할 때 공개 목록 GET을 호출한다.

## 검증·남은 작업

기존 화면 16건과 통신/쿠키 경계 40건(총 56건), 타입 검사, 계약 재생성 일치, 빌드·린트로 검증한다. 성공/204, 409/422/429, CSRF 누락/교체/중복, 외부 대상, 확장점 우회, 쿼리 인코딩, HTML/비정상 JSON/오류 정보 노출, 취소/시간 초과/늦은 응답, WAV 응답을 다룬다. 실제 서버·모바일·로그인 왕복은 미검증이다.

2026-10-15 로컬에서 `npm ci --ignore-scripts` 후 위 검사를 통과했다. 생성 파일에 임의 주석을 넣으면 계약 비교가 실패하고 고정 해시를 바꾸면 계약 다운로드를 거절하는 실패 경계 검증도 수행한 뒤 원래 파일을 복구했다. `npm audit --audit-level=moderate`는 전체 의존성 취약점 0건이며 레지스트리 서명 검사도 통과했다. 원격 CI 결과는 PR에서 별도로 확인한다.

선행 PR 병합 후 원본 계약으로 재생성·비교하고, #15의 모델·지역 목록 및 실제 API 정상/오류 응답과 대조한다. 그 뒤 W11에서 미리보기 입력과 서버 여정을 구분해 연결한다. 이 준비 PR의 통과가 #19 전체 또는 W11 완료를 의미하지 않는다.

## 보안 근거

`AGENTS.md → SW개발보안_obsidian/Security/INDEX.md`에서 선택한 원문이다. 이미 확인한 XSS·오류·세션 원칙은 [초기 기반 기록](../../DEVELOPMENT.md#보안-근거와-검증-범위)을 이어 사용했다.

| 프로젝트 상대경로 | 장·절·PDF 페이지 | 적용과 구분 |
|---|---|---|
| `SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제1절-입력데이터-검증-및-표현/016-11.-크로스사이트-요청-위조(CSRF).md` | 제2장 제1절 11, PDF 54~60쪽(안전한 코딩기법 54쪽) | 토큰 검증 원칙 참고. 쿠키 이름·서명 double-submit·Origin 검사는 #117의 프로젝트 계약이며 공식 예제의 Django/Flask 구현과 구분한다. 이 PR은 브라우저 헤더 전달만 구현한다. |
| `SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제4절-에러처리/043-1.-오류-메시지-정보노출.md` | 제2장 제4절 1, PDF 131~134쪽(안전한 코딩기법 131쪽) | 고정 오류 안내·원문 오류 비노출과 공격 입력 시험. 요청 추적 ID는 계약에 정한 제한된 형식만 허용한다. |
| `SW개발보안_obsidian/Security/Python-2023/제2장-시큐어코딩-가이드/제1절-입력데이터-검증-및-표현/017-12.-서버사이드-요청-위조.md` | 제2장 제1절 12, PDF 61~63쪽(안전한 코딩기법 61쪽) | 허용 대상 제한 원칙 참고. CodeQL의 빌드 도구 outbound URL 지적을 받아 다운로드 URL 전체를 상수로 고정하고 설정의 출처 필드가 다르면 전송 전에 거절한다. 서비스 API의 SSRF 발견·조치와는 구분한다. |

same-origin 대상 제한, 65초 제한시간, 일일 한도 안내, 고정 커밋/해시 검증은 이 프로젝트의 기술 판단이다. 서버 CSRF 서명·Origin 검증, 인가·저장·삭제 통제의 구현 완료를 주장하지 않는다.

기술 참고: [타입 생성](https://openapi-ts.dev/node), [openapi-fetch API](https://openapi-ts.dev/openapi-fetch/api).
