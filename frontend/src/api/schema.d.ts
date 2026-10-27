/** Generated from docs/api/openapi.yaml. Run npm run api:generate; do not edit. */
export interface paths {
    "/admin/audit": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 최소 감사 기록 조회
         * @description 기간은 최대 30일(보관기간과 같음)이다. 개인 본문·OTP·토큰은 기록에 없다.
         */
        get: operations["listAudit"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/mfa/verify": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 운영자 MFA 확인
         * @description 운영자 역할이 있는 회원 세션만 쓸 수 있다(아니면 403 `FORBIDDEN`). OTP가 틀리면 403 `MFA_INVALID`이다.
         *     같은 OTP는 다시 쓸 수 없다. OTP 값은 로그·감사 기록에 남기지 않는다.
         *
         *     - 실패는 세션이 아니라 **운영자 계정** 단위로 센다. 로그아웃·재로그인으로 초기화되지 않는다.
         *     - 연속 5회 실패하면 15분 잠그고 429 `MFA_LOCKED`(`Retry-After` 포함)로 응답한다. 잠금 중에는 OTP를 확인하지 않는다.
         *     - 성공하면 실패 횟수를 0으로 되돌린다. 실패와 잠금은 감사 기록(`mfa.fail`, `mfa.lock`)에 남긴다.
         */
        post: operations["verifyMfa"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/operations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 수집·모델·제한 상태
         * @description 운영자 역할과 MFA가 필요하다. 오류 메시지·주소·비밀값은 넣지 않는다.
         */
        get: operations["getOperations"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/opportunities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 운영자 공고 목록
         * @description 운영자 역할과 MFA가 필요하다. 기본 정렬은 갱신이 최근인 순이다.
         */
        get: operations["listAdminOpportunities"];
        put?: never;
        /**
         * 공식 자료로 공고 수동 등록
         * @description 공식 자료 수동 출처(`source`) 하나를 고르고, 공고 내용(`content`)과 원문 근거(`evidence`)를 함께 보낸다.
         *     근거 규칙은 수동 입력 명령(`python -m app.manual_intake`, docs/data/manual-intake.md)과 같다.
         *     - `content.source_url`과 `evidence.url`은 같은 공식 상세 주소여야 한다(50+포털·고용24·1365의 허용 경로만). 다른 접수 주소는 `application_url` 근거가 필요하다.
         *     - `evidence.quotes`에는 필수 7개(`title`, `organization_name`, `activity_type`, `application_method`, `application_instructions`, `recruitment_status`, `requirements`)와, 값을 넣은 선택 필드마다 원문 인용을 넣는다.
         *     - `evidence.observed_at`은 지금부터 48시간 안의 원문 확인 시각이다. 연락처·HTML 흔적이 든 값은 받지 않는다(422).
         *     등록하면 `pending` 버전 1이 되고 승인 전에는 공개되지 않는다.
         *     같은 출처에 공식 URL·기관·제목·마감이 같은 공고가 이미 있으면 자동 병합하지 않고 409 `VERSION_CONFLICT`로 거절한다. 기존 공고를 찾아 수정(PATCH)한다.
         */
        post: operations["createAdminOpportunity"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/opportunities/{opportunity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 운영자 공고 상세 (검수 비교용)
         * @description 최신 버전 내용과 공개본 내용, 바뀐 필드, 중요 변경 여부를 함께 준다.
         */
        get: operations["getAdminOpportunity"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 공고 수정 (새 검수 대기 버전)
         * @description 바꿀 필드만 보낸다. 저장하면 새 `pending` 버전이 되고 공개본은 승인 전까지 그대로다.
         *     중요 변경 필드가 바뀌면 `important_change=true`가 되어 공개본의 추천·지원서 생성을 보류한다.
         *     - `base_version`이 현재 최신 버전이 아니면 409 `VERSION_CONFLICT`다. 다른 수정·수집을 덮어쓰지 않는다.
         *     - 바꾼 필드는 등록과 같은 일반 텍스트 규칙(연락처·HTML 흔적 거절)으로 검사한다. 공식 URL을 바꾸면 허용 경로여야 하고, `role_tags`는 역할 사전의 키만 받는다.
         *     - 출처를 다시 확인한 것이 아니므로 `source_checked_at`은 기준 버전 값을 유지한다.
         *     - 같은 원문을 다시 수집하면 이 수정본을 되돌리지 않는다. 원문이 실제로 바뀐 경우만 새 `pending` 버전을 만들고, 그때도 `role_tags`·`skill_tags`는 이어받는다(docs/api/README.md D34).
         */
        patch: operations["updateAdminOpportunity"];
        trace?: never;
    };
    "/admin/opportunities/{opportunity_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 검수 대기 공고 승인·공개
         * @description `pending` → `approved`만 허용한다. 공개 필수 항목(제목·기관·지역 또는 원격·모집 상태·HTTPS 공식 원문·접수 경로)이
         *     빠졌으면 422로 빠진 필드를 알려 준다. 승인하면 이 버전이 공개본이 되고 감사 기록을 남긴다.
         */
        post: operations["approveOpportunity"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/opportunities/{opportunity_id}/close": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 모집 종료 처리
         * @description 추천에서 빼는 방향이라 재검수 없이 바로 반영한다. `basis=other`이면 `note`가 필수다.
         *     수집 실패나 일시 누락은 종료 근거가 아니다.
         */
        post: operations["closeOpportunity"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/opportunities/{opportunity_id}/hide": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 공고 비공개
         * @description 공개 목록·상세·추천에서 즉시 뺀다. 저장 지원서에는 `opportunity_closed` 재검토 표시가 붙는다.
         */
        post: operations["hideOpportunity"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/opportunities/{opportunity_id}/reject": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 검수 대기 공고 반려 (계획 §5 보완 계약)
         * @description `pending` → `rejected`만 허용한다. 운영자 역할과 MFA가 필요하고 감사 기록을 남긴다.
         *     `rejected`는 그 버전에서 끝나는 상태다. 다시 고치려면 PATCH로 새 `pending` 버전을 만든다.
         *     `reason_code=other`이면 `note`가 필수다. 메모에 개인정보를 적지 않는다.
         */
        post: operations["rejectOpportunity"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 공고 오류 신고 목록 */
        get: operations["listReports"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/admin/reports/{report_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 신고 처리
         * @description `received` → `in_progress` → `resolved`·`dismissed`. `resolved`·`dismissed`이면 `resolution_note`가 필수다.
         *     공고 수정·종료는 공고 API로 따로 한다.
         */
        patch: operations["updateReport"];
        trace?: never;
    };
    "/auth/kakao/callback": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 카카오 인가 결과 처리
         * @description 카카오가 보내는 GET이라 CSRF 헤더 대신 세션 결합 state로 보호한다(로그인 CSRF 방지).
         *
         *     - 쿼리 `state`가 **요청 세션에 저장된 state**와 같을 때만 처리하고, 쓴 state는 바로 지운다.
         *       세션이 없거나, 다른 세션이 발급한 state이거나, 만료·재사용이면 카카오 토큰 교환을 하지 않고 `status=failed`로 보낸다.
         *     - `login`·`save`가 성공하면 세션을 교체(새 세션·새 CSRF 쿠키)하고, 시작 세션의 저장 대기를 새 세션으로 옮긴 뒤 시작 세션의 진행 중 체험을 지운다(새 세션으로 옮기지 않는다).
         *     - `reauth`는 세션을 교체하지 않는다. 지금 로그인한 계정과 같은 카카오 계정이면 5분 동안 재인증 상태(`GET /me`의 `user.reauth_until`)가 되고, 다른 계정이면 세션을 그대로 두고 `status=failed`로 보낸다.
         *     - 인증 성공만으로 자료를 저장하지 않는다.
         *     - 결과는 항상 화면의 `/auth/result`로 보내며 code·state·오류 설명을 Location에 남기지 않는다.
         */
        get: operations["kakaoCallback"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/kakao/start": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 카카오 로그인 시작
         * @description 브라우저 이동으로 부른다. GET이지만 OAuth state를 발급하므로 아래 규칙으로 보호한다.
         *
         *     - 새 state(가능하면 PKCE `code_verifier` 포함)를 만들어 **현재 세션에 저장**한다. 1회용, 10분 만료.
         *       세션당 최대 3개를 두고 기존 state를 덮어쓰지 않는다(넘치면 가장 오래된 것부터 버린다).
         *       그래서 다른 사이트가 이 경로로 보내도 진행 중인 로그인·저장 흐름은 끊기지 않는다.
         *     - state에는 목적(`purpose`)만 기록한다. 저장 대기는 state가 아니라 세션에 결합돼 있다.
         *     - `purpose=reauth`는 로그인한 회원의 탈퇴 전 재인증이다. 비회원 세션이면 카카오로 가지 않고 `/auth/result?purpose=reauth&status=failed`로 보낸다.
         *     - `purpose=save`인데 세션에 저장 대기가 없거나 만료됐으면 카카오로 가지 않고 `/auth/result?purpose=save&status=expired`로 보낸다.
         *     - 세션이 없으면 익명 세션을 만든다.
         */
        get: operations["startKakaoLogin"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 로그아웃
         * @description 회원 세션을 폐기하고 새 익명 세션을 준다. 진행 중이던 체험은 함께 지운다.
         */
        post: operations["logout"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/save-intents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 로그인 저장 대기 발급 (계획 §5 보완 계약)
         * @description 비회원 세션이 소유한 체험의 확정 프로필·승인 지원서만 받는다. 서버가 그 승인본을 조회해
         *     Redis에 복사하고 10분 동안 이 세션에 결합한다. 같은 세션의 이전 저장 대기는 폐기한다.
         *
         *     - 지원서를 담으려면 프로필도 함께 담아야 한다(비회원은 근거 프로필이 저장돼 있지 않다).
         *     - 이후 `GET /auth/kakao/start?purpose=save`로 로그인을 시작한다. URL에는 아무 참조도 넣지 않는다.
         *     - 회원 세션에서 부르면 409 `ALREADY_SIGNED_IN`이다. 회원은 체험 참조로 바로 저장한다.
         */
        post: operations["createSaveIntent"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/auth/save-intents/{save_intent_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * 현재 세션의 저장 대기 취소
         * @description 비회원 또는 회원의 현재 세션에 결합된 정확한 대기만 폐기한다.
         *     이미 취소·소비·만료됐거나 다른 세션의 ID여도 204이며 타인의 대기에는 영향이 없다.
         *     회원 저장과 같은 소유자 잠금으로 직렬화한다. 먼저 끝난 저장본은 되돌리지 않는다.
         *     저장 동의를 철회하거나 로그인·체험·이미 저장한 자료를 삭제하지 않는다.
         *     쿼리와 본문은 허용하지 않는다.
         */
        delete: operations["cancelSaveIntent"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/consents": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 처리 목적별 동의 기록
         * @description `ai_processing`은 비회원 세션에도 기록한다. `storage`는 회원만 가능하다(비회원은 401).
         *     `notice_version`이 현재 안내문 버전이 아니면 422(`notice_version`, `invalid_value`). 이미 같은 동의가 있으면 그대로 200.
         */
        post: operations["createConsent"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/consents/notices": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 서버가 확정 게시한 현재 목적별 안내문
         * @description 공개 텍스트만 제공한다. 게시되지 않은 목적은 null이며 버전만 설정된 경우에도 안내문을 만들지 않는다.
         *     login_available은 저장/계정 안내문 게시와 제공자 구성이 모두 있을 때만 true다.
         *     안내문 조회는 동의 수락이 아니며 수락 시 서버가 현재 버전을 다시 검사한다.
         */
        get: operations["getConsentNotices"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/consents/withdraw": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 동의 철회와 관련 자료 삭제
         * @description - `ai_processing` 철회: 진행 중인 체험과 임시 자료를 지운다. 늦게 끝난 AI 결과도 저장하지 않는다.
         *     - `storage` 철회: 저장 프로필 전 버전과 지원서를 지운다(회원만).
         *
         *     동의가 없던 목적을 철회해도 200이며 삭제 수는 0이다.
         *     유효한 회원 철회는 다른 기기를 포함한 이전 세션·임시 체험도 정리하고 호출자를 새 회원 세션으로 전환한다. 익명 AI 철회는 새 익명 세션으로 전환한다. 저장 이력·실패 관리 재시도는 회원 삭제와 같은 경계를 사용한다. 이미 철회한 목적은 다른 목적의 자료·활성 체험을 지우지 않는다.
         */
        post: operations["withdrawConsent"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/drafts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 자기 저장 지원서 목록
         * @description 최근 저장 순이다. 근거 프로필·공고가 바뀐 문서는 `review_reasons`가 붙는다.
         */
        get: operations["listSavedDrafts"];
        put?: never;
        /**
         * 승인한 지원서를 암호화 저장
         * @description `source.type=journey`는 회원이 체험의 승인 지원서를, `source.type=save_intent`는 로그인 왕복 직후 저장 대기의 지원서를 저장한다.
         *
         *     - 근거 프로필이 회원 저장본과 연결되지 않으면 409 `PROFILE_NOT_SAVED`. 화면은 프로필도 함께 저장하겠다는 동의를 받고 `POST /profiles/me/versions`를 먼저 부른다.
         *     - 기존 문서를 갱신하려면 `document_id`와 `base_document_version`을 함께 넣는다.
         */
        post: operations["saveDraft"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/drafts/{document_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 저장 지원서 상세
         * @description 자기 문서만 볼 수 있다. 다른 사람 문서는 404다. 운영자도 볼 수 없다.
         */
        get: operations["getSavedDraft"];
        put?: never;
        post?: never;
        /**
         * 저장 지원서 삭제
         * @description 그 문서의 모든 버전을 지운다. 없는 문서·다른 사람 문서는 404다. 다른 저장 문서·프로필은 유지하며 이전 회원 세션·임시 체험은 종료해 늦은 저장을 차단한다. 호출자는 새 회원 세션으로 전환한다. 삭제 이력·실패 재시도는 프로필 삭제와 같은 경계를 사용한다.
         */
        delete: operations["deleteSavedDraft"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/live": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 프로세스 생존 확인 (내부 전용) */
        get: operations["healthLive"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 요청 처리 준비 확인 (내부 전용)
         * @description DB·Redis가 정상이면 200, 아니면 503. 모델·음성 서비스 장애는 `degraded`로 200을 유지해
         *     공개 공고 조회를 계속한다. 버전·주소·오류 메시지는 넣지 않는다.
         */
        get: operations["healthReady"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 체험 시작
         * @description 먼저 `POST /consents`(purpose=ai_processing)로 동의를 기록한다. `ai_notice_version`이 동의한 현재 안내문 버전이 아니면 403 `CONSENT_REQUIRED`.
         *
         *     - 회원이 `saved_profile`을 넘기면 그 저장본을 이 체험의 확정본 1번으로 가져온다. 비회원이 넘기면 401.
         *     - 체험은 생성 후 최대 2시간, 마지막 사용자 행동 후 30분이 지나면 만료된다. 자동 조회는 시간을 늘리지 않는다.
         *     - 비회원은 IP별, 회원은 계정별 하루 60회 생성 한도에 포함된다.
         */
        post: operations["createJourney"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * 체험 종료와 임시 자료 삭제
         * @description 대화·전사·초안·추천·지원서 초안·준비 상태를 지운다. 진행 중인 AI 작업이 나중에 끝나도 결과를 저장하지 않는다.
         *     이미 만료됐거나 없는 체험도 204로 응답한다(멱등).
         */
        delete: operations["deleteJourney"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/drafts": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 지원서 초안 만들기 (AI 생성·직접 작성·저장 문서 가져오기)
         * @description - `generate`: 로컬 모델이 선택한 확정 사실을 서버가 자기소개 초안으로 조립한다. AI 처리 동의가 필요하다. 지원동기는 추정하지 않고 빈칸으로 두며 직접 작성 안내를 `warnings`로 알린다.
         *     - `manual`: 빈 초안. AI를 호출하지 않는다.
         *     - `from_saved`: 현재 회원과 AI 동의를 확인하고 `saved_document`의 자기 문서·정확한 버전을 복호화해 새 임시 초안으로 복사한다. 같은 공고의 현재 공개 버전과 현재 체험의 확정 프로필을 지정한다. 근거가 저장 당시와 다르면 경고하며 본문은 자동으로 바꾸지 않는다. 기존 승인 시각은 복사하지 않고 `revision: 1`, `approved_at: null`로 시작한다. 익명은 401, 다른 회원·없는 문서는 404다.
         *
         *     종료·비공개·재검수 중인 공고는 409 `OPPORTUNITY_NOT_AVAILABLE`, 확정본이 없으면 409 `PROFILE_NOT_CONFIRMED`.
         *     초안은 체험 안에 임시로 있고, 승인과 저장은 별도 요청이다. 최대 32개 초안·128회 생성 예약을 허용한다.
         *     생성 실패·취소된 키는 새 키로 재시도한다. 같은 키의 완료 재생은 추론이나 체험 수명 연장을 반복하지 않는다.
         */
        post: operations["createJourneyDraft"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/drafts/{draft_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 소유 체험 지원서와 현재 재검토 사유 조회
         * @description 유효한 자기 체험 안의 특정 지원서만 조회한다. 목록·이전 세션·대화 복원 API가 아니다.
         *     원래 profile_version/opportunity/본문/approved_at/revision은 보존하고 현재 근거 변화만 review_reasons/warnings로 알린다.
         *     조회는 체험 유휴 수명을 연장하지 않는다. AI 동의나 모델 호출이 필요하지 않다.
         */
        get: operations["getJourneyDraft"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 지원서 초안 수정
         * @description 본문 전체를 바꾼다. 수정하면 승인이 풀리고(`approved_at=null`) 다시 승인해야 저장할 수 있다.
         *     지원서 자체의 base_revision으로 CAS하며 프로필/체험 리비전과 구분한다.
         *     근거가 변경되거나 공고가 닫혀도 직접 작성한 편집은 유지할 수 있으나 새 승인은 유효성 검사 뒤에만 가능하다.
         */
        patch: operations["updateJourneyDraft"];
        trace?: never;
    };
    "/journeys/{journey_id}/drafts/{draft_id}/approve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 지원서 초안 사용자 승인
         * @description 승인한 리비전만 복사·저장·저장 대기에 쓸 수 있다. 외부 신청은 하지 않는다.
         *     현재 지원서 리비전과 원래 확정 프로필/공고 버전의 유효성을 다시 검사한다.
         *     과거 편집/승인 요청, 재확정된 프로필, 바뀐 공개 공고 버전은 409이며 본문을 자동 갱신하지 않는다.
         *     승인은 회원 저장을 수행하지 않는다. 저장 API 연결 시에도 승인 리비전과 근거를 다시 검사해야 한다.
         */
        post: operations["approveJourneyDraft"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 확인한 답변 보내기와 다음 질문·프로필 초안 받기
         * @description AI 처리 동의가 필요하다. 로컬 Qwen3가 프로필 초안을 추출하고 다음 질문을 하나 만든다.
         *     결과는 Pydantic 검증과 근거 참조 검사를 통과한 것만 돌려준다. 확정은 별도 요청이다.
         *     직접 입력은 null 전사 참조를 쓴다. 전사 ID가 있으면 같은 세션/체험의 유효한 전사인지 확인하고 사용자가 확인·수정해 보낸 text만 추출에 사용한다. 전사 원문을 자동으로 덧붙이지 않는다.
         *     경험은 원문 근거로 추가하고 기존 직접 편집 경험·다른 프로필 필드·확정본은 덮어쓰지 않는다.
         *     실패/취소 시 본문과 초안은 반영하지 않는다. 완료 응답 재전송은 당시 리비전을 그대로 반환하므로 화면은 최신 편집과 구분해야 한다.
         */
        post: operations["createMessage"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/profile": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 현재 프로필 초안과 확정 상태
         * @description 자동 조회는 체험의 유휴 시간을 늘리지 않는다.
         */
        get: operations["getJourneyProfile"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * 프로필 초안 직접 수정
         * @description 초안 전체를 바꾼다. 새 경험은 id를 null로 보내면 서버가 부여한다. 이전 확정본은 재확정 전까지 유지된다.
         *     AI를 호출하지 않으므로 AI 동의 없이도 쓸 수 있다.
         */
        patch: operations["updateJourneyProfile"];
        trace?: never;
    };
    "/journeys/{journey_id}/profile/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 프로필 확정과 버전 부여
         * @description 현재 초안을 새 확정 버전으로 만든다. 경험·희망 지역·활동 유형이 1개 이상이어야 하며, 비어 있으면 422(`required`).
         *     재확정하면 추천·자격 결과는 새 버전으로 다시 계산하고, 기존 지원서 초안은 `profile_changed` 재검토 대상이 된다.
         */
        post: operations["confirmJourneyProfile"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/role-exclusions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 현재 체험의 전체 역할 제외 목록 조회
         * @description 후보 목록에 표시되지 않는 역할도 포함한다. 전체 교체 PUT에서 기존 선택을 보존하기 위해 사용한다. 확정 프로필이 없으면 409이며 조회로 체험 수명을 연장하지 않는다.
         */
        get: operations["getRoleExclusions"];
        /**
         * 현재 체험의 추천에서 제외할 역할 지정
         * @description 제외 목록 전체를 바꾼다. 빈 배열이면 모두 복원한다. 프로필 사실은 바뀌지 않고 저장되지도 않는다.
         *     공고 `role_tags`에 제외한 역할이 하나라도 있으면 맞춤 추천에서 뺀다. 공개 공고 검색에는 적용하지 않는다.
         *     확정 프로필이 없으면 409 `PROFILE_NOT_CONFIRMED`.
         */
        put: operations["putRoleExclusions"];
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/roles": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 확정 경험 근거가 있는 역할 후보
         * @description 역할 사전과 확정 경험을 연결한 후보다. 근거 경험이 없는 역할은 내지 않는다. 확정본이 없으면 409 `PROFILE_NOT_CONFIRMED`.
         *     `excluded`는 현재 체험의 제외 상태다.
         */
        get: operations["getRoleCandidates"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/journeys/{journey_id}/transcriptions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 녹음 전사 (로컬 STT)
         * @description AI 처리 동의가 필요하다. 원본 음성은 메모리·tmpfs에서만 처리하고 전사 후 바로 정리한다.
         *     전사 결과는 자동으로 프로필에 쓰이지 않는다. 사용자가 확인·수정한 텍스트를 `messages`로 보낸다.
         *     같은 키/파일 해시의 완료 재생은 새 STT나 체험 수명 연장을 하지 않는다. 실패/취소된 키는 새 키로 재시도한다.
         *     원본 음성/파일명은 Redis에 저장하지 않는다. 전사 결과와 참조는 같은 체험 해시 안에 두며 종료/만료 시 함께 폐기한다.
         *     현재 단일 audio part만 받는 메모리 전용 업로드를 사용한다. 압축 codec/무음 검사는 내부 모델 서버 #31의 구현/실측을 기다린다.
         *     실제 내부 모델 서비스가 준비되지 않으면 503이며 가상 전사로 대체하지 않는다.
         *     90초를 넘는 녹음은 422(`audio`, `out_of_range`), 6MiB를 넘으면 413이다.
         *
         *     - 서버는 Content-Type을 믿지 않고 파일 시그니처(WebM·Ogg·MP4·RIFF/WAVE)와 디코더 프로브(길이·코덱)로 형식을 확인한다.
         *       맞지 않으면 422(`audio`, `invalid_value`). 디코더는 허용 코덱만 쓰고 시간·메모리 제한을 둔다.
         *     - 화면은 압축 형식(webm/opus 또는 mp4/aac)을 권장한다. WAV는 16kHz·16비트 모노로만 보낸다(90초 약 2.9MB).
         *       44.1kHz 이상 WAV는 90초 전에 6MiB를 넘어 413이 된다.
         */
        post: operations["createTranscription"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 현재 세션의 계정·권한·동의·저장 대기 상태
         * @description 비회원 세션도 200을 돌려준다(`authenticated=false`). 화면은 시작할 때 이 경로를 불러
         *     CSRF 쿠키와 동의 상태를 받는다. 세션이 없으면 익명 세션 쿠키를, CSRF 쿠키가 없거나 세션과 맞지 않으면 새 CSRF 쿠키를 내려준다.
         */
        get: operations["getMe"];
        put?: never;
        post?: never;
        /**
         * 회원 탈퇴
         * @description `GET /auth/kakao/start?purpose=reauth`로 5분 안에 재인증한 세션만 가능하다(아니면 403 `REAUTH_REQUIRED`).
         *     세션·체험·계정 연결·동의·저장 프로필·지원서를 지우고 세션을 폐기한다. 최소 삭제 이력만 30일 남는다.
         *     삭제 요청을 영속화해 이전 인증을 차단한 뒤 DB 밖 최소 이력 저장·Redis 정리·SQL 삭제를 완료한다. 실패는 pending/failed 관리 재시도 대상이며 완료로 응답하지 않는다. 운영 이력 어댑터 미설정 시 실제 삭제 전에 503이다.
         */
        delete: operations["deleteAccount"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/opportunities": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 공개 공고 목록·검색
         * @description 승인된 공개 공고 중 모집 중·확인 필요(`unknown`) 공고만 보여 준다. 모집 종료는 빠진다.
         *     정렬은 마감이 가까운 순(마감 없음은 뒤), 같으면 공고 ID 순이다. 역할 제외는 적용하지 않는다. AI 장애 중에도 쓸 수 있다.
         */
        get: operations["listOpportunities"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/opportunities/{opportunity_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 공개 공고 상세
         * @description 승인된 최신 공개본을 돌려준다(모집 중·종료·확인 필요 포함). 숨김·반려·검수 대기만 있는 공고는 404.
         *     중요 변경이 검수 대기 중이면 `change_pending=true`이고 추천·지원서 생성은 보류된다.
         */
        get: operations["getOpportunity"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/opportunities/{opportunity_id}/eligibility": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 확정 프로필과 공고 조건 대조
         * @description 규칙 기반 판정이며 LLM이 결과를 정하거나 바꾸지 않는다(Plan/04 F07). 미해석 조건은 통과로 처리하지 않는다.
         *     `opportunity_version`이 최신 공개본이 아니면 409 `VERSION_CONFLICT`.
         */
        post: operations["checkEligibility"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/opportunities/{opportunity_id}/preparation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** 공식 서류·절차·접수 안내 */
        get: operations["getPreparation"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/profiles/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 현재 저장 프로필
         * @description 저장본이 없으면 `saved=null`로 200이다.
         */
        get: operations["getSavedProfile"];
        put?: never;
        post?: never;
        /**
         * 저장 프로필 전체 삭제
         * @description 모든 저장 버전과 그 프로필에서 나온 지원서를 함께 지운다. 저장본이 없어도 204다. 이전 회원 세션·임시 체험도 정리해 늦은 저장을 차단하고 호출자는 새 회원 세션으로 전환한다. DB 밖 이력 저장이 실패하면 완료로 응답하지 않고 관리 재시도가 필요하다.
         */
        delete: operations["deleteSavedProfile"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/profiles/me/versions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 확정 프로필을 새 저장 버전으로 저장
         * @description 회원은 체험 참조(`source.type=journey`)로, 로그인 왕복 직후에는 저장 대기(`source.type=save_intent`)로 저장한다.
         *
         *     - 저장 동의가 없으면 403 `CONSENT_REQUIRED`.
         *     - 기존 저장본이 있으면 `base_saved_version`에 그 버전을 넣어 교체를 확인한다. 저장본이 없으면 `null`.
         *     - 현재 저장본과 내용이 같으면 새 버전을 만들지 않고 200으로 그 버전을 돌려준다.
         */
        post: operations["saveProfileVersion"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/recommendations": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 확정 프로필로 맞춤 공고 추천
         * @description AI를 호출하지 않는 계산이다(Plan/04 F06 정렬 기준). 승인·모집 중·신선도 확인·재검수 보류가 아닌 공고만 후보다.
         *     전체 자격이 미충족인 공고는 빼고, `kind=journey`이면 그 체험의 역할 제외를 적용한다.
         *     참조한 버전이 현재 확정본이 아니면 409 `VERSION_CONFLICT`. 근거 경험을 만들 수 없는 공고는 맞춤 추천에서 빠진다.
         */
        post: operations["createRecommendations"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/regions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * 지원 지역 목록 (시·도와 시·군·구)
         * @description 프로필의 희망·거주 지역과 공고 검색이 같은 목록을 쓴다. 공개 정적 자료라 화면이 캐시해도 된다.
         */
        get: operations["listRegions"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/reports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 공고 오류 신고
         * @description 비회원도 신고할 수 있다. 같은 멱등 키로 다시 보내면 첫 접수 결과를 돌려주고 중복 신고를 만들지 않는다. 공고 오류 유형 중심으로 받고, 설명에는 개인정보를 적지 않도록 화면에서 안내한다.
         *     `type=other`이면 `note`가 필수(422 `required_with`).
         */
        post: operations["createReport"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/speech": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * 화면에 보이는 자료 읽어주기 (계획 §5 TTS 읽기 참조)
         * @description 임의 텍스트는 받지 않는다. 서버가 참조를 해석해 접근 권한·버전·필드를 확인한 뒤 그 텍스트만 읽는다.
         *
         *     - 공개 공고도 AI 처리 동의가 있어야 한다(403 `CONSENT_REQUIRED`).
         *     - 참조한 버전이 최신이 아니면 409 `VERSION_CONFLICT`. 화면은 새로 불러온 뒤 다시 요청한다.
         *     - 한 조각은 최대 2,000자. 더 긴 필드는 `segment`로 이어서 요청한다.
         *     - 음성을 보관하지 않으므로 완료된 멱등 키를 다시 쓰면 409 `REQUEST_ALREADY_COMPLETED`.
         */
        post: operations["createSpeech"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        AdminOpportunity: {
            /** @description 공개본 대비 바뀐 필드. 공개본이 없으면 빈 배열 */
            changed_fields: string[];
            content: components["schemas"]["OpportunityInput"];
            /** Format: uuid */
            id: string;
            /** @description 중요 변경 필드가 바뀌었는지(docs/api/README.md §2.7). true면 공개본 추천을 보류 중이다 */
            important_change: boolean;
            /** @description 비교용 공개본 내용. 공개본이 없으면 null */
            published_content: null | components["schemas"]["OpportunityInput"];
            /** @description 현재 공개 중인 버전. 없으면 null */
            published_version: number | null;
            /** @enum {string} */
            review_status: "pending" | "approved" | "rejected" | "hidden";
            source: {
                external_id: string | null;
                name: string;
                /** Format: uuid */
                source_id: string;
            };
            /** Format: date-time */
            source_checked_at: string;
            /** Format: date-time */
            updated_at: string;
            /** @description 최신 버전(검수 대상). 검수 요청의 base_version으로 쓴다 */
            version: number;
        };
        AdminOpportunityList: {
            items: components["schemas"]["AdminOpportunitySummary"][];
            page: number;
            page_size: number;
            total: number;
        };
        AdminOpportunitySummary: {
            /** Format: uuid */
            id: string;
            important_change: boolean;
            organization_name: string;
            published_version: number | null;
            /** @enum {string} */
            recruitment_status: "open" | "closed" | "unknown";
            /** @enum {string} */
            review_status: "pending" | "approved" | "rejected" | "hidden";
            /** Format: date-time */
            source_checked_at: string;
            title: string;
            /** Format: date-time */
            updated_at: string;
            version: number;
        };
        AdminReport: {
            /** Format: date-time */
            created_at: string;
            note: string | null;
            opportunity: components["schemas"]["OpportunityRef"];
            opportunity_title: string;
            /** Format: uuid */
            report_id: string;
            resolution_note: string | null;
            status: components["schemas"]["ReportStatus"];
            type: components["schemas"]["ReportType"];
            /** Format: date-time */
            updated_at: string;
            /** @description 처리 요청의 base_version으로 쓴다 */
            version: number;
        };
        AdminReportList: {
            items: components["schemas"]["AdminReport"][];
            page: number;
            page_size: number;
            total: number;
        };
        /** @description 최소 메타데이터만. 개인 프로필·지원서 본문, OTP, 토큰은 넣지 않는다 */
        AuditEvent: {
            /** @enum {string} */
            action: "opportunity.create" | "opportunity.update" | "opportunity.approve" | "opportunity.reject" | "opportunity.hide" | "opportunity.close" | "report.update" | "mfa.verify" | "mfa.fail" | "mfa.lock" | "role.grant" | "role.revoke" | "access.denied";
            /** Format: uuid */
            actor_id: string | null;
            /** @enum {string} */
            actor_role: "operator" | "user" | "system";
            /** Format: date-time */
            at: string;
            /** Format: uuid */
            event_id: string;
            request_id: string;
            /** @enum {string} */
            result: "success" | "denied" | "failed";
            /** Format: uuid */
            target_id: string | null;
            /** @enum {string|null} */
            target_type: "opportunity" | "report" | "user" | null;
        };
        AuditList: {
            items: components["schemas"]["AuditEvent"][];
            page: number;
            page_size: number;
            total: number;
        };
        BaseRevision: {
            base_revision: number;
        };
        /** @enum {string} */
        ComponentState: "ok" | "loading" | "fail";
        ConfirmedVersion: {
            /** Format: date-time */
            confirmed_at: string;
            version: number;
        };
        ConsentCreate: {
            /** @description 화면에 보여 준 안내문 버전. 현재 버전이 아니면 422 */
            notice_version: string;
            purpose: components["schemas"]["ConsentPurpose"];
        };
        /**
         * @description ai_processing = EC2 자체 AI 처리(대화·음성·읽어주기), storage = 회원 영구 저장
         * @enum {string}
         */
        ConsentPurpose: "ai_processing" | "storage";
        ConsentState: {
            /** Format: date-time */
            granted_at: string;
            notice_version: string;
            purpose: components["schemas"]["ConsentPurpose"];
        };
        ConsentWithdraw: {
            purpose: components["schemas"]["ConsentPurpose"];
        };
        ConsentWithdrawResult: {
            /** @description 철회와 함께 지운 자료 수. ai_processing은 진행 중 체험, storage는 저장 프로필·지원서 */
            deleted: {
                documents: number;
                journeys: number;
                profile_versions: number;
            };
            purpose: components["schemas"]["ConsentPurpose"];
            /** Format: date-time */
            withdrawn_at: string;
        };
        DraftCreate: {
            /**
             * @description generate = 로컬 AI 초안(AI 동의 필요), manual = 빈 초안(AI 호출 없음), from_saved = 자기 저장 문서 가져오기
             * @enum {string}
             */
            mode: "generate" | "manual" | "from_saved";
            opportunity: components["schemas"]["OpportunityRef"];
            /** @description 이 체험의 확정 프로필 버전 */
            profile_version: number;
            /** @description mode=from_saved일 때만. 그 밖에는 null */
            saved_document: null | {
                /** Format: uuid */
                document_id: string;
                version: number;
            };
        };
        DraftSaveRequest: {
            base_document_version: number | null;
            /**
             * Format: uuid
             * @description 기존 저장 문서를 갱신할 때만. base_document_version과 함께 보낸다
             */
            document_id: string | null;
            source: components["schemas"]["SaveIntentSource"] | components["schemas"]["JourneyDraftSource"];
        };
        DraftSaveResult: {
            /** Format: uuid */
            document_id: string;
            /** @description 연결한 회원 저장 프로필 버전 */
            profile_version: number;
            /** Format: date-time */
            saved_at: string;
            version: number;
        };
        /** @description 본문 전체를 바꾼다. 수정하면 승인이 풀린다 */
        DraftUpdate: {
            base_revision: number;
            motivation: string;
            self_introduction: string;
        };
        EligibilityRequest: {
            /** @description 화면에 보이는 공고 버전. 최신 공개본이 아니면 409 */
            opportunity_version: number;
            profile: components["schemas"]["ProfileRef"];
        };
        EligibilityResult: {
            conditions: {
                /** @enum {string} */
                field: "age" | "residence_region" | "certification" | "completed_course" | "weekday" | "hours_per_week" | "other";
                /** Format: uuid */
                requirement_id: string;
                result: components["schemas"]["EligibilityStatus"];
                /**
                 * @description result=unknown일 때 확인이 필요한 이유
                 * @enum {string|null}
                 */
                review_reason: "missing_profile_value" | "unclear_requirement" | "age_boundary" | "reference_date_missing" | "unsupported_group" | null;
                source_evidence: string;
                /** @description 비교한 사용자 값. 프로필에 없으면 null */
                user_value: components["schemas"]["EligibilityUserValue"];
            }[];
            /** Format: date-time */
            evaluated_at: string;
            groups: {
                /** Format: uuid */
                group_id: string;
                /** @enum {string} */
                operator: "and" | "or";
                result: components["schemas"]["EligibilityStatus"];
            }[];
            no_requirements: boolean;
            opportunity: components["schemas"]["OpportunityRef"];
            overall: components["schemas"]["EligibilityStatus"];
            profile: components["schemas"]["ProfileRef"];
        };
        /**
         * @description satisfied 조건 충족, not_satisfied 미충족, unknown 확인 필요
         * @enum {string}
         */
        EligibilityStatus: "satisfied" | "not_satisfied" | "unknown";
        EligibilitySummary: {
            needs_review_count: number;
            /** @description 원문에 필수조건이 없다고 검수한 공고. 선발을 보장한다는 뜻이 아니다 */
            no_requirements: boolean;
            overall: components["schemas"]["EligibilityStatus"];
        };
        /** @description 비교한 확정 프로필 값. null은 미확인, 빈 배열은 없음 확인이며 거주지는 단일 Region이다 */
        EligibilityUserValue: null | number | components["schemas"]["Region"] | number[] | string[];
        /** @description 모든 오류의 공통 본문. 원본 입력·SQL·토큰·파일 경로·예외 추적을 넣지 않는다 */
        Error: {
            code: components["schemas"]["ErrorCode"];
            /** @description 422에만 붙는다 */
            fields?: components["schemas"]["FieldError"][];
            /** @description 사용자에게 보여 줄 한국어 문장 */
            message: string;
            /** @description 서버가 붙인 추적 ID. 클라이언트 멱등 키와 다르다 */
            request_id: string;
        };
        /**
         * @description 상태 코드별 의미는 docs/api/README.md §2.5
         * @enum {string}
         */
        ErrorCode: "UNAUTHENTICATED" | "SESSION_EXPIRED" | "FORBIDDEN" | "CSRF_FAILED" | "MFA_REQUIRED" | "MFA_INVALID" | "MFA_LOCKED" | "CONSENT_REQUIRED" | "REAUTH_REQUIRED" | "NOT_FOUND" | "SAVE_INTENT_NOT_FOUND" | "VERSION_CONFLICT" | "IDEMPOTENCY_KEY_REUSED" | "REQUEST_IN_PROGRESS" | "REQUEST_ALREADY_COMPLETED" | "PROFILE_NOT_CONFIRMED" | "PROFILE_NOT_SAVED" | "DRAFT_NOT_APPROVED" | "OPPORTUNITY_NOT_AVAILABLE" | "INVALID_STATE_TRANSITION" | "ALREADY_SIGNED_IN" | "PAYLOAD_TOO_LARGE" | "VALIDATION_FAILED" | "RATE_LIMITED" | "DAILY_QUOTA_EXCEEDED" | "INFERENCE_BUSY" | "INTERNAL_ERROR" | "MODEL_UNAVAILABLE" | "AI_TIMEOUT" | "SERVICE_UNAVAILABLE";
        Experience: {
            description: string;
            /** @description 사용자가 말한 기간. 불명확하면 추정하지 않고 null */
            duration_note: string | null;
            /**
             * Format: uuid
             * @description 서버가 부여한 경험 ID
             */
            id: string;
            skill_tags: string[];
        };
        ExperienceInput: {
            description: string;
            /** @description 사용자가 말한 기간. 불명확하면 추정하지 않고 null */
            duration_note: string | null;
            /**
             * Format: uuid
             * @description 기존 경험은 서버가 부여한 ID, 새 경험은 null
             */
            id: string | null;
            skill_tags: string[];
        };
        FieldError: {
            /** @description 점 경로. 예 `profile.preferred_regions[0].district` */
            path: string;
            /** @enum {string} */
            reason: "required" | "invalid_type" | "invalid_value" | "too_long" | "too_short" | "out_of_range" | "unknown_field" | "required_with";
        };
        Journey: {
            /** @description 저장 프로필로 시작했으면 확정본 1번, 아니면 null */
            confirmed: null | components["schemas"]["ConfirmedVersion"];
            /**
             * Format: date-time
             * @description 생성 후 2시간. 활동으로 늘어나지 않는다
             */
            expires_at: string;
            first_message: components["schemas"]["Message"];
            /**
             * Format: date-time
             * @description 마지막 사용자 행동 후 30분
             */
            idle_expires_at: string;
            /** Format: uuid */
            journey_id: string;
            revision: number;
        };
        JourneyCreate: {
            /** @description 사용자가 동의한 AI 처리 안내문 버전 */
            ai_notice_version: string;
            /** @description 회원이 자기 저장 프로필로 시작할 때만. 비회원은 null */
            saved_profile: null | {
                /** Format: uuid */
                profile_id: string;
                version: number;
            };
        };
        JourneyDraft: {
            /**
             * Format: date-time
             * @description 사용자 승인 시각. 미승인·수정 후에는 null
             */
            approved_at: string | null;
            /** Format: uuid */
            draft_id: string;
            /** @enum {string} */
            mode: "generate" | "manual" | "from_saved";
            motivation: string;
            opportunity: components["schemas"]["OpportunityRef"];
            profile_version: number;
            /** @description 비어 있지 않으면 화면에 재검토 필요를 표시한다 */
            review_reasons: components["schemas"]["ReviewReason"][];
            revision: number;
            self_introduction: string;
            /** @description 근거 검증에서 뺀 문장 등 사용자에게 알릴 내용 */
            warnings: string[];
        };
        JourneyDraftSource: {
            /** Format: uuid */
            draft_id: string;
            /** Format: uuid */
            journey_id: string;
            /** @description 승인한 임시 지원서의 리비전 */
            revision: number;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "journey";
        };
        JourneyProfileSource: {
            /** Format: uuid */
            journey_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "journey";
            /** @description 체험의 확정 프로필 버전 */
            version: number;
        };
        /** @description 공식 원문 근거. 서버는 주소를 열거나 조회하지 않는다. 진위나 승인의 증명이 아니라 검수 대조용이다 */
        ManualEvidence: {
            /**
             * @description 공식 원문을 직접 대조했다는 운영자 확인
             * @constant
             */
            confirmed_official: true;
            /**
             * Format: date-time
             * @description 원문을 확인한 시각. 지금부터 48시간 안이어야 한다
             */
            observed_at: string;
            /** @description 필드별 원문 인용(각 300자 이내, 연락처·꺾쇠 없음). 필수 7개와 값을 넣은 선택 필드마다 하나씩 */
            quotes: {
                [key: string]: string;
            };
            /**
             * Format: uri
             * @description content.source_url과 같은 공식 상세 주소
             */
            url: string;
        };
        Me: {
            authenticated: boolean;
            /** @description 현재 유효한 동의만. 철회·폐기 버전은 빠진다 */
            consents: components["schemas"]["ConsentState"][];
            pending_save_intent: null | components["schemas"]["PendingSaveIntent"];
            user: null | {
                /** Format: uuid */
                id: string;
                /** @description 운영자 MFA를 이 세션에서 완료했는지. 일반 사용자는 항상 false */
                mfa_verified: boolean;
                /**
                 * Format: date-time
                 * @description 탈퇴 전 재인증이 유효한 시각. 재인증하지 않았거나 지났으면 null
                 */
                reauth_until: string | null;
                roles: ("user" | "operator")[];
            };
        };
        Message: {
            /** Format: date-time */
            created_at: string;
            /** Format: uuid */
            message_id: string;
            text: string;
        };
        MessageCreate: {
            base_revision: number;
            /** @description 사용자가 확인한 텍스트. 전사 결과를 고쳤다면 고친 내용 */
            text: string;
            /**
             * Format: uuid
             * @description 음성 입력이면 전사 ID, 직접 입력이면 null
             */
            transcription_id: string | null;
        };
        MessageResult: {
            /** @description 다음 질문. 더 물을 것이 없으면 null */
            assistant_message: null | components["schemas"]["Message"];
            /** @enum {string} */
            next_step: "continue" | "review_profile";
            /** @description 사용자에게 보여 줄 주의사항(예. 건강 상세 정보는 저장하지 않음) */
            notices: string[];
            profile: components["schemas"]["ProfileDraftView"];
            revision: number;
            /** Format: uuid */
            user_message_id: string;
        };
        MfaStatus: {
            /**
             * Format: date-time
             * @description 이 세션의 MFA 확인 만료 시각
             */
            expires_at: string;
            /** @constant */
            mfa_verified: true;
        };
        MfaVerify: {
            otp: string;
        };
        NoticeCatalog: {
            ai_processing: components["schemas"]["PublishedNotice"] | null;
            login_available: boolean;
            storage: components["schemas"]["PublishedNotice"] | null;
        };
        Operations: {
            /** Format: date-time */
            checked_at: string;
            limits: {
                inference_daily_limit: number;
                inference_today: number;
                slots_in_use: number;
                slots_total: number;
            };
            models: {
                llm: components["schemas"]["ComponentState"];
                stt: components["schemas"]["ComponentState"];
                tts: components["schemas"]["ComponentState"];
            };
            sources: {
                consecutive_failures: number;
                /** Format: date-time */
                last_run_at: string | null;
                /** @enum {string|null} */
                last_status: "success" | "partial" | "failed" | null;
                /** Format: date-time */
                last_success_at: string | null;
                name: string;
                /** Format: uuid */
                source_id: string;
                /** @description 마지막 성공이 48시간을 넘어 이 출처 공고의 추천을 보류 중 */
                stale: boolean;
            }[];
            stores: {
                db: components["schemas"]["ComponentState"];
                redis: components["schemas"]["ComponentState"];
            };
        };
        /** @description 공개 공고 상세. 내부 필드(source_id, external_id, content_hash, review_status)는 내보내지 않는다 */
        Opportunity: {
            /** @description 원격이 아닌 공고의 활동 지역. 모르면 null(지역 기준 추천에서 제외) */
            activity_region: null | components["schemas"]["Region"];
            /** @enum {string} */
            activity_type: "employment" | "volunteering";
            application_instructions: string;
            /** @enum {string} */
            application_method: "online" | "phone" | "visit" | "email" | "mixed";
            /** Format: uri */
            application_url: string;
            /** @description 중요 변경이 검수 대기 중. true면 화면에 "변경 확인 중"을 표시하고 추천·지원서 생성을 보류한다 */
            change_pending: boolean;
            compensation_text: string | null;
            /**
             * Format: date-time
             * @description 공식 시각이 제공된 경우에만
             */
            deadline_at: string | null;
            /**
             * Format: date
             * @description 날짜만 제공된 마감. 시각을 만들어 붙이지 않는다
             */
            deadline_date: string | null;
            /**
             * @description 공식 원문 설명(일반 텍스트). 검색 계산과 상세 표시에 쓰고 검수 대상이다.
             *     값이 없으면 null이며 설명을 만들어 채우지 않는다
             */
            description_text: string | null;
            /** @description 원문이 5,000자를 넘어 앞부분만 저장했으면 true */
            description_truncated: boolean;
            hours_per_week: number | null;
            /** Format: uuid */
            id: string;
            is_public_job: boolean | null;
            location_text: string | null;
            organization_name: string;
            paid: boolean | null;
            /** @enum {string} */
            recruitment_status: "open" | "closed" | "unknown";
            remote_allowed: boolean | null;
            required_documents: string[] | null;
            /** @description 빈 배열은 "명시된 필수조건 없음"으로 검수한 상태 */
            requirements: components["schemas"]["Requirement"][];
            /** Format: date-time */
            reviewed_at: string;
            role_tags: components["schemas"]["RoleId"][];
            schedule_text: string | null;
            skill_tags: string[];
            /** Format: date-time */
            source_checked_at: string;
            /** Format: uri */
            source_url: string;
            title: string;
            version: number;
        };
        OpportunityApproveRequest: {
            base_version: number;
            /** @description 검수 사유(확인한 원문·변경 내용). 개인정보를 적지 않는다 */
            note: string;
        };
        OpportunityCloseRequest: {
            base_version: number;
            /**
             * @description 모집 종료 근거
             * @enum {string}
             */
            basis: "source_closed" | "deadline_passed" | "organization_notice" | "report_confirmed" | "other";
            /** @description basis=other이면 필수 */
            note: string | null;
        };
        OpportunityCreate: {
            content: components["schemas"]["OpportunityInput"];
            evidence: components["schemas"]["ManualEvidence"];
            /**
             * @description 공식 자료 수동 출처. 순서대로 50+포털, 고용24, 1365다
             * @enum {string}
             */
            source: "manual_50plus" | "manual_work24" | "manual_volunteer";
        };
        OpportunityHideRequest: {
            base_version: number;
            note: string;
        };
        /** @description 운영자가 등록·수정하는 공고 내용. 저장하면 새 pending 버전이 되고 승인 전에는 공개되지 않는다 */
        OpportunityInput: {
            activity_region: null | components["schemas"]["Region"];
            /** @enum {string} */
            activity_type: "employment" | "volunteering";
            application_instructions: string;
            /** @enum {string} */
            application_method: "online" | "phone" | "visit" | "email" | "mixed";
            /** Format: uri */
            application_url: string;
            compensation_text: string | null;
            /** Format: date-time */
            deadline_at: string | null;
            /** Format: date */
            deadline_date: string | null;
            description_text: string | null;
            hours_per_week: number | null;
            is_public_job: boolean | null;
            location_text: string | null;
            organization_name: string;
            paid: boolean | null;
            /** @enum {string} */
            recruitment_status: "open" | "closed" | "unknown";
            remote_allowed: boolean | null;
            required_documents: string[] | null;
            /** @description 새 조건의 id는 클라이언트가 UUID로 만든다 */
            requirements: components["schemas"]["Requirement"][];
            role_tags: components["schemas"]["RoleId"][];
            schedule_text: string | null;
            skill_tags: string[];
            /** Format: uri */
            source_url: string;
            title: string;
        };
        OpportunityList: {
            items: components["schemas"]["OpportunitySummary"][];
            page: number;
            page_size: number;
            total: number;
        };
        OpportunityPatch: {
            /** @description 수정 기준 버전(현재 최신 버전). 최신이 아니면 409 */
            base_version: number;
            /** @description 바꿀 필드만. 형식은 OpportunityInput과 같다 */
            changes: {
                activity_region?: null | components["schemas"]["Region"];
                /** @enum {string} */
                activity_type?: "employment" | "volunteering";
                application_instructions?: string;
                /** @enum {string} */
                application_method?: "online" | "phone" | "visit" | "email" | "mixed";
                /** Format: uri */
                application_url?: string;
                compensation_text?: string | null;
                /** Format: date-time */
                deadline_at?: string | null;
                /** Format: date */
                deadline_date?: string | null;
                description_text?: string | null;
                hours_per_week?: number | null;
                is_public_job?: boolean | null;
                location_text?: string | null;
                organization_name?: string;
                paid?: boolean | null;
                /** @enum {string} */
                recruitment_status?: "open" | "closed" | "unknown";
                remote_allowed?: boolean | null;
                required_documents?: string[] | null;
                /** @description 새 조건의 id는 클라이언트가 UUID로 만든다 */
                requirements?: components["schemas"]["Requirement"][];
                role_tags?: components["schemas"]["RoleId"][];
                schedule_text?: string | null;
                skill_tags?: string[];
                /** Format: uri */
                source_url?: string;
                title?: string;
            };
        };
        OpportunityRef: {
            /** Format: uuid */
            id: string;
            version: number;
        };
        OpportunityRejectRequest: {
            /** @description 검수 중인 pending 버전 */
            base_version: number;
            /** @description 개인정보를 적지 않는다 */
            note: string | null;
            /**
             * @description source_unverifiable 공식 원문·접수 경로 확인 불가, out_of_scope 지역·유형 범위 밖,
             *     recruitment_closed 이미 모집 종료, duplicate 같은 공고가 이미 있음,
             *     insufficient_information 필수 정보 부족, inappropriate_content 부적절한 내용, other 기타(메모 필수)
             * @enum {string}
             */
            reason_code: "source_unverifiable" | "out_of_scope" | "recruitment_closed" | "duplicate" | "insufficient_information" | "inappropriate_content" | "other";
        };
        OpportunityReviewResult: {
            /** Format: uuid */
            id: string;
            /** @enum {string} */
            review_status: "pending" | "approved" | "rejected" | "hidden";
            /** Format: date-time */
            reviewed_at: string;
            version: number;
        };
        OpportunitySummary: {
            activity_region: null | components["schemas"]["Region"];
            /** @enum {string} */
            activity_type: "employment" | "volunteering";
            change_pending: boolean;
            /** Format: date-time */
            deadline_at: string | null;
            /** Format: date */
            deadline_date: string | null;
            /** Format: uuid */
            id: string;
            is_public_job: boolean | null;
            organization_name: string;
            paid: boolean | null;
            /** @enum {string} */
            recruitment_status: "open" | "closed" | "unknown";
            remote_allowed: boolean | null;
            title: string;
            version: number;
        };
        PendingSaveIntent: {
            /** @description 로그인한 회원의 현재 저장 프로필 버전. 있으면 화면이 교체 여부를 묻고 base_saved_version으로 보낸다 */
            existing_saved_profile_version: number | null;
            /** Format: date-time */
            expires_at: string;
            /** Format: uuid */
            save_intent_id: string;
            targets: components["schemas"]["SaveIntentTargets"];
        };
        /** @description 공식 서류·절차·접수 안내. 공고에 없는 서류를 더하지 않는다. 외부 이동은 신청 완료가 아니다 */
        Preparation: {
            application_instructions: string;
            /** @enum {string} */
            application_method: "online" | "phone" | "visit" | "email" | "mixed";
            /** Format: uri */
            application_url: string;
            change_pending: boolean;
            /** Format: date-time */
            deadline_at: string | null;
            /** Format: date */
            deadline_date: string | null;
            opportunity: components["schemas"]["OpportunityRef"];
            /** @enum {string} */
            recruitment_status: "open" | "closed" | "unknown";
            /** @description null이면 공고에 제출 서류가 명시되지 않음 */
            required_documents: string[] | null;
            /** Format: uri */
            source_url: string;
        };
        ProfileConfirmResult: {
            /** Format: date-time */
            confirmed_at: string;
            profile: components["schemas"]["ProfileRef"];
            revision: number;
        };
        /**
         * @description Plan/02 §2 프로필 계약. null은 미확인, 빈 배열은 "없다고 확인함"이다.
         *     예외로 experiences·preferred_regions·activity_types의 빈 배열은 "아직 입력하지 않음"이며 missing_for_recommendation으로 다시 묻는다.
         *     추천을 시작하려면 확정본에 experiences·preferred_regions·activity_types가 1개 이상 있어야 한다.
         */
        ProfileContent: {
            /** @description 활동 수행 조건. 진단명·상세 병력은 받지 않는다 */
            activity_constraints: string[] | null;
            activity_types: ("employment" | "volunteering")[];
            /** @description 1=월 ~ 7=일 */
            available_weekdays: number[] | null;
            birth_year: number | null;
            certifications: string[] | null;
            completed_courses: string[] | null;
            experiences: components["schemas"]["Experience"][];
            hours_per_week: number | null;
            mobility_note: string | null;
            /** @enum {string|null} */
            paid_preference: "paid" | "unpaid" | "any" | null;
            preferred_regions: components["schemas"]["Region"][];
            /** @description 거주 자격 대조용. 희망 활동 지역과 다르다 */
            residence_region: null | components["schemas"]["Region"];
            /** @constant */
            schema_version: 1;
            skills: string[];
        };
        /**
         * @description 프로필 초안 수정 요청용. ProfileContent와 같고, 새 경험만 id를 null로 보낸다.
         *     추천을 시작하려면 확정본에 experiences·preferred_regions·activity_types가 1개 이상 있어야 한다.
         */
        ProfileContentInput: {
            /** @description 활동 수행 조건. 진단명·상세 병력은 받지 않는다 */
            activity_constraints: string[] | null;
            activity_types: ("employment" | "volunteering")[];
            /** @description 1=월 ~ 7=일 */
            available_weekdays: number[] | null;
            birth_year: number | null;
            certifications: string[] | null;
            completed_courses: string[] | null;
            experiences: components["schemas"]["ExperienceInput"][];
            hours_per_week: number | null;
            mobility_note: string | null;
            /** @enum {string|null} */
            paid_preference: "paid" | "unpaid" | "any" | null;
            preferred_regions: components["schemas"]["Region"][];
            /** @description 거주 자격 대조용. 희망 활동 지역과 다르다 */
            residence_region: null | components["schemas"]["Region"];
            /** @constant */
            schema_version: 1;
            skills: string[];
        };
        ProfileDraftView: {
            /** @description 현재 확정본. 아직 없으면 null */
            confirmed: null | components["schemas"]["ConfirmedVersion"];
            draft: components["schemas"]["ProfileContent"];
            evidence: components["schemas"]["ProfileEvidence"][];
            /** @description 확정 후 수정한 내용이 있어 재확정이 필요하면 true. 이때 추천은 이전 확정본 기준이다 */
            has_unconfirmed_changes: boolean;
            /** @description 추천 시작에 필요한데 비어 있는 항목 */
            missing_for_recommendation: ("experiences" | "preferred_regions" | "activity_types")[];
            /** @description 체험 리비전(편집 상태 변경 번호). 변경 요청의 base_revision으로 쓴다 */
            revision: number;
        };
        /** @description 초안 항목이 어느 대화 메시지에서 나왔는지. 확정본·저장본에는 복제하지 않는다 */
        ProfileEvidence: {
            message_ids: string[];
            /** @description 예: experiences[0] */
            path: string;
        };
        /** @description 확정 프로필 참조. 클라이언트가 프로필 본문을 보내 확정 검사를 우회할 수 없다 */
        ProfileRef: {
            /** Format: uuid */
            id: string;
            /**
             * @description journey = 체험의 확정본(id는 체험 ID), saved = 회원 저장본(id는 저장 프로필 ID)
             * @enum {string}
             */
            kind: "journey" | "saved";
            version: number;
        };
        ProfileSaveRequest: {
            /** @description 교체할 현재 저장본 버전. 저장본이 없으면 null. 최신이 아니면 409 */
            base_saved_version: number | null;
            source: components["schemas"]["SaveIntentSource"] | components["schemas"]["JourneyProfileSource"];
        };
        ProfileSaveResult: {
            /** @description false면 같은 내용의 기존 저장본을 연결했다 */
            created: boolean;
            replaced_version: number | null;
            /** Format: date-time */
            saved_at: string;
            version: number;
        };
        /** @description 초안 전체를 바꾼다. 새 경험은 id를 null로 보낸다 */
        ProfileUpdate: {
            base_revision: number;
            draft: components["schemas"]["ProfileContentInput"];
        };
        /** @enum {string} */
        Province: "seoul" | "gyeonggi" | "incheon";
        PublishedNotice: {
            aws_region: string;
            body: string;
            contact: string;
            controller: string;
            deletion: string;
            retention: string;
            title: string;
            version: string;
        };
        Readiness: {
            checks: {
                /** @enum {string} */
                db: "ok" | "fail";
                /** @enum {string} */
                llm: "ok" | "fail";
                /** @enum {string} */
                redis: "ok" | "fail";
                /** @enum {string} */
                speech: "ok" | "fail";
            };
            /** @enum {string} */
            status: "ready" | "degraded" | "unavailable";
        };
        /** @description 내부 정렬 점수는 내보내지 않는다. 신청 성공 확률로 표현하지 않는다 */
        Recommendation: {
            eligibility: components["schemas"]["EligibilitySummary"];
            matched: {
                experience_ids: string[];
                keywords: string[];
                role_ids: components["schemas"]["RoleId"][];
                skill_tags: string[];
            };
            opportunity: components["schemas"]["OpportunitySummary"];
            rank: number;
        };
        RecommendationList: {
            /** @description 프로필을 수정 중이라 이전 확정본 기준이면 true. 화면에 "이전 확정 프로필 기준"을 표시한다 */
            based_on_previous_confirmed: boolean;
            /** Format: date-time */
            generated_at: string;
            /** @description 정렬 순서대로. 화면은 상위 5건을 먼저 보여 준다. 0건이어도 필수조건을 완화하지 않는다 */
            items: components["schemas"]["Recommendation"][];
            profile: components["schemas"]["ProfileRef"];
        };
        RecommendationRequest: {
            /** @description 선택 필터. 프로필 조건을 좁히기만 하고 필수조건을 완화하지 않는다 */
            filters: {
                activity_types?: ("employment" | "volunteering")[];
                paid?: boolean;
                regions?: components["schemas"]["Region"][];
            };
            profile: components["schemas"]["ProfileRef"];
        };
        Region: {
            /** @description 서버 지역 목록의 시·군·구 식별값. null이면 시·도 전체 */
            district: string | null;
            province: components["schemas"]["Province"];
        };
        RegionCatalog: {
            provinces: {
                districts: {
                    id: string;
                    name: string;
                }[];
                id: components["schemas"]["Province"];
                name: string;
            }[];
            /** @description 지역 목록 버전. 목록이 바뀌면 올라간다 */
            version: string;
        };
        ReportCreate: {
            /** @description 선택 설명. 개인정보를 적지 않도록 화면에서 안내한다. type=other이면 필수 */
            note: string | null;
            opportunity: components["schemas"]["OpportunityRef"];
            type: components["schemas"]["ReportType"];
        };
        ReportReceipt: {
            /** Format: date-time */
            received_at: string;
            /** Format: uuid */
            report_id: string;
        };
        /** @enum {string} */
        ReportStatus: "received" | "in_progress" | "resolved" | "dismissed";
        /** @enum {string} */
        ReportType: "already_closed" | "wrong_requirements" | "wrong_schedule_or_location" | "wrong_application_method" | "broken_link" | "other";
        ReportUpdate: {
            base_version: number;
            /** @description resolved·dismissed이면 필수 */
            resolution_note: string | null;
            /** @enum {string} */
            status: "in_progress" | "resolved" | "dismissed";
        };
        /**
         * @description 필드별 허용 연산과 값 (Plan/02 §4 표와 같다):
         *
         *     | field | operator | value |
         *     |---|---|---|
         *     | age | gte, lte | integer (만 나이) |
         *     | age | between | [min, max] integer 2개 |
         *     | residence_region | in | Region[] |
         *     | certification, completed_course | has_all, has_any | string[] |
         *     | weekday | includes_all, includes_any | integer[] (1=월 ~ 7=일) |
         *     | hours_per_week | gte, lte | number |
         *     | other | null | null (clarity=needs_review) |
         *
         *     표에 없는 조합은 422. 해석하지 못한 조건은 field=other, clarity=needs_review와 원문 근거로 보존한다.
         */
        Requirement: {
            /** @enum {string} */
            clarity: "clear" | "needs_review";
            /** @enum {string} */
            field: "age" | "residence_region" | "certification" | "completed_course" | "weekday" | "hours_per_week" | "other";
            /** Format: uuid */
            group_id: string | null;
            /** @enum {string|null} */
            group_operator: "and" | "or" | null;
            /** Format: uuid */
            id: string;
            /** @enum {string|null} */
            operator: "gte" | "lte" | "between" | "in" | "has_all" | "has_any" | "includes_all" | "includes_any" | null;
            /**
             * Format: date
             * @description 연령 등 판정 기준일
             */
            reference_date: string | null;
            /** @description 원문 조건 문장 */
            source_evidence: string;
            value: components["schemas"]["RequirementValue"];
        };
        /** @description Requirement 연산별 값. 허용 조합은 Requirement 설명의 표를 따른다 */
        RequirementValue: null | number | number[] | string[] | components["schemas"]["Region"][];
        /**
         * @description profile_changed 근거 프로필이 재확정됨, opportunity_changed 공고 중요 변경, opportunity_closed 모집 종료·비공개
         * @enum {string}
         */
        ReviewReason: "profile_changed" | "opportunity_changed" | "opportunity_closed";
        RoleCandidate: {
            description: string;
            /** @description 이 역할과 연결한 확정 경험. 근거가 없는 역할은 후보로 내지 않는다 */
            evidence: {
                /** Format: uuid */
                experience_id: string;
                skill_tags: string[];
            }[];
            excluded: boolean;
            name: string;
            role_id: components["schemas"]["RoleId"];
        };
        RoleCandidates: {
            items: components["schemas"]["RoleCandidate"][];
            profile_version: number;
            revision: number;
        };
        RoleExclusions: {
            revision: number;
            role_ids: components["schemas"]["RoleId"][];
        };
        RoleExclusionUpdate: {
            base_revision: number;
            role_ids: components["schemas"]["RoleId"][];
        };
        /** @description 역할 사전(RoleDefinition)의 키. 공고 role_tags도 같은 키를 쓴다 */
        RoleId: string;
        SavedDraft: {
            /** Format: date-time */
            approved_at: string;
            /** Format: uuid */
            document_id: string;
            motivation: string;
            opportunity: components["schemas"]["OpportunityRef"];
            opportunity_title: string;
            organization_name: string;
            profile_version: number;
            review_reasons: components["schemas"]["ReviewReason"][];
            /** Format: date-time */
            saved_at: string;
            self_introduction: string;
            version: number;
        };
        SavedDraftList: {
            items: components["schemas"]["SavedDraftSummary"][];
            page: number;
            page_size: number;
            total: number;
        };
        SavedDraftSummary: {
            /** Format: uuid */
            document_id: string;
            opportunity: components["schemas"]["OpportunityRef"];
            opportunity_title: string;
            organization_name: string;
            review_reasons: components["schemas"]["ReviewReason"][];
            /** Format: date-time */
            saved_at: string;
            version: number;
        };
        SavedProfile: {
            /** Format: date-time */
            confirmed_at: string;
            content: components["schemas"]["ProfileContent"];
            /**
             * Format: uuid
             * @description ProfileRef(kind=saved)의 id
             */
            profile_id: string;
            /** Format: date-time */
            saved_at: string;
            version: number;
        };
        SavedProfileResponse: {
            /** @description 저장본이 없으면 null */
            saved: null | components["schemas"]["SavedProfile"];
        };
        SaveIntent: {
            /**
             * Format: date-time
             * @description 발급 후 10분
             */
            expires_at: string;
            /**
             * Format: uuid
             * @description opaque 참조. URL에 넣지 않는다
             */
            save_intent_id: string;
            targets: components["schemas"]["SaveIntentTargets"];
        };
        /**
         * @description profile·draft 중 하나 이상. draft가 있으면 profile도 필수.
         *     둘 다 null이면 422 `fields: [{path: profile, reason: required}]`, draft만 있으면 422 `fields: [{path: profile, reason: required_with}]`.
         */
        SaveIntentCreate: {
            draft: null | {
                /** Format: uuid */
                draft_id: string;
                /** @description 승인한 임시 지원서의 리비전 */
                revision: number;
            };
            /** Format: uuid */
            journey_id: string;
            profile: null | {
                /** @description 이 체험의 확정 프로필 버전 */
                version: number;
            };
        };
        SaveIntentSource: {
            /** Format: uuid */
            save_intent_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            type: "save_intent";
        };
        SaveIntentTargets: {
            draft: boolean;
            profile: boolean;
        };
        SpeechRequest: {
            /** @description 2,000자 단위 조각 번호(0부터). 응답 헤더 X-Speech-Segment-Count를 넘으면 422 */
            segment: number;
            target: components["schemas"]["SpeechTarget"];
        };
        /** @description 화면에 보이는 자료의 참조. 대상마다 읽을 수 있는 필드가 정해져 있다 */
        SpeechTarget: components["schemas"]["SpeechTargetJourneyMessage"] | components["schemas"]["SpeechTargetJourneyDraft"] | components["schemas"]["SpeechTargetSavedDraft"] | components["schemas"]["SpeechTargetOpportunity"];
        SpeechTargetJourneyDraft: {
            /** Format: uuid */
            draft_id: string;
            /** @enum {string} */
            field: "self_introduction" | "motivation";
            /** Format: uuid */
            journey_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "journey_draft";
            revision: number;
        };
        SpeechTargetJourneyMessage: {
            /** Format: uuid */
            journey_id: string;
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "journey_message";
            /**
             * Format: uuid
             * @description 체험의 AI 질문 메시지
             */
            message_id: string;
        };
        SpeechTargetOpportunity: {
            /** @enum {string} */
            field: "title" | "description_text" | "schedule_text" | "location_text" | "compensation_text" | "application_instructions";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "opportunity";
            /** Format: uuid */
            opportunity_id: string;
            version: number;
        };
        SpeechTargetSavedDraft: {
            /** Format: uuid */
            document_id: string;
            /** @enum {string} */
            field: "self_introduction" | "motivation";
            /**
             * @description discriminator enum property added by openapi-typescript
             * @enum {string}
             */
            kind: "saved_draft";
            version: number;
        };
        Transcription: {
            duration_seconds: number;
            /** @description 사용자가 확인·수정한 뒤 messages로 보낸다. 원본 음성은 보관하지 않는다 */
            text: string;
            /** Format: uuid */
            transcription_id: string;
        };
    };
    responses: {
        /** @description 운영자 역할 없음·MFA 미완료·CSRF 실패 */
        AdminForbidden: {
            headers: {
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 버전·상태 충돌, 멱등 키 충돌 */
        Conflict: {
            headers: {
                "Retry-After": components["headers"]["RetryAfter"];
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 권한·CSRF·MFA·동의 실패 */
        Forbidden: {
            headers: {
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 없는 자원 또는 접근할 수 없는 사적 자원(둘을 구분하지 않음) */
        NotFound: {
            headers: {
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 요청 크기 초과 (JSON 64KiB, 녹음 6MiB) */
        PayloadTooLarge: {
            headers: {
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 모델·내부 서비스 일시 장애 */
        ServiceUnavailable: {
            headers: {
                "Retry-After": components["headers"]["RetryAfter"];
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 호출·동시성 제한 */
        TooManyRequests: {
            headers: {
                "Retry-After": components["headers"]["RetryAfter"];
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 미인증·세션 만료 */
        Unauthorized: {
            headers: {
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
        /** @description 입력 형식·범위 오류 */
        ValidationFailed: {
            headers: {
                "X-Request-ID": components["headers"]["XRequestId"];
                [name: string]: unknown;
            };
            content: {
                "application/json": components["schemas"]["Error"];
            };
        };
    };
    parameters: {
        /** @description 회원 저장 지원서 문서 ID */
        DocumentId: string;
        /** @description 체험 안의 임시 지원서 ID */
        DraftId: string;
        /**
         * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
         *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
         */
        IdempotencyKey: string;
        /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
        JourneyId: string;
        OpportunityId: string;
        Page: number;
        PageSize: number;
        ReportId: string;
    };
    requestBodies: never;
    headers: {
        /** @description 개인 자료·음성 응답은 저장하지 않는다 */
        NoStore: "no-store";
        /** @description 다시 시도할 수 있을 때까지의 초 */
        RetryAfter: number;
        /**
         * @description 세션 쿠키(`__Host-rc_session`: HttpOnly; Secure; SameSite=Lax; Path=/)와
         *     CSRF 쿠키(`__Host-rc_csrf`: Secure; SameSite=Strict; Path=/)를 새로 만들거나 바꿀 때만 붙는다.
         *     로그인·로그아웃·탈퇴에서는 두 쿠키를 모두 교체한다.
         */
        SetSessionCookies: string;
        /** @description 서버가 붙인 추적 ID. 오류 본문의 `request_id`와 같다 */
        XRequestId: string;
    };
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    listAudit: {
        parameters: {
            query: {
                from: string;
                page?: components["parameters"]["Page"];
                page_size?: components["parameters"]["PageSize"];
                to: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 감사 기록 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AuditList"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    verifyMfa: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MfaVerify"];
            };
        };
        responses: {
            /** @description MFA 확인 완료 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MfaStatus"];
                };
            };
            401: components["responses"]["Unauthorized"];
            /** @description 운영자 아님·OTP 불일치 */
            403: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            422: components["responses"]["ValidationFailed"];
            /** @description OTP 실패로 잠김·호출 한도 */
            429: {
                headers: {
                    "Retry-After": components["headers"]["RetryAfter"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getOperations: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 운영 상태 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Operations"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            429: components["responses"]["TooManyRequests"];
        };
    };
    listAdminOpportunities: {
        parameters: {
            query?: {
                /** @description true면 중요 변경 검수 대기만 */
                important_change?: boolean;
                page?: components["parameters"]["Page"];
                page_size?: components["parameters"]["PageSize"];
                q?: string;
                recruitment_status?: "open" | "closed" | "unknown";
                review_status?: "pending" | "approved" | "rejected" | "hidden";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 공고 목록 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminOpportunityList"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createAdminOpportunity: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpportunityCreate"];
            };
        };
        responses: {
            /** @description 검수 대기 공고. 같은 키·같은 입력의 재전송도 201로 첫 결과를 돌려준다 */
            201: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminOpportunity"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getAdminOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 운영자 공고 상세 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminOpportunity"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    updateAdminOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpportunityPatch"];
            };
        };
        responses: {
            /** @description 새 검수 대기 버전 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminOpportunity"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    approveOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpportunityApproveRequest"];
            };
        };
        responses: {
            /** @description 승인 완료 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpportunityReviewResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            /** @description 형식 오류·공개 필수 항목 누락 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    closeOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpportunityCloseRequest"];
            };
        };
        responses: {
            /** @description 종료 완료 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpportunityReviewResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    hideOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpportunityHideRequest"];
            };
        };
        responses: {
            /** @description 비공개 완료 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpportunityReviewResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    rejectOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OpportunityRejectRequest"];
            };
        };
        responses: {
            /** @description 반려 완료 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpportunityReviewResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            /** @description 권한·CSRF·MFA 실패 */
            403: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            404: components["responses"]["NotFound"];
            /** @description 기준 버전 충돌·pending이 아님 */
            409: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            413: components["responses"]["PayloadTooLarge"];
            /** @description 형식 오류 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    listReports: {
        parameters: {
            query?: {
                page?: components["parameters"]["Page"];
                page_size?: components["parameters"]["PageSize"];
                status?: components["schemas"]["ReportStatus"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 신고 목록 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminReportList"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    updateReport: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                report_id: components["parameters"]["ReportId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReportUpdate"];
            };
        };
        responses: {
            /** @description 처리한 신고 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminReport"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["AdminForbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    kakaoCallback: {
        parameters: {
            query?: {
                code?: string;
                error?: string;
                error_description?: string;
                state?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 화면 결과 경로로 이동 */
            302: {
                headers: {
                    /** @description `/auth/result?purpose={login|save|reauth}&status={success|cancelled|failed|expired}` */
                    Location?: string;
                    "Set-Cookie": components["headers"]["SetSessionCookies"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            429: components["responses"]["TooManyRequests"];
        };
    };
    startKakaoLogin: {
        parameters: {
            query: {
                purpose: "login" | "save" | "reauth";
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 카카오 인가 페이지 또는 화면 결과 경로로 이동 */
            302: {
                headers: {
                    /** @description 카카오 인가 URL, `/auth/result?purpose=save&status=expired`, 또는 `/auth/result?purpose=reauth&status=failed` */
                    Location?: string;
                    "Set-Cookie": components["headers"]["SetSessionCookies"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    logout: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 로그아웃 완료 */
            204: {
                headers: {
                    "Set-Cookie": components["headers"]["SetSessionCookies"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
        };
    };
    createSaveIntent: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SaveIntentCreate"];
            };
        };
        responses: {
            /** @description 저장 대기 발급 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SaveIntent"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            /** @description 버전 충돌·미확정·미승인·회원 세션·멱등 키 충돌 */
            409: {
                headers: {
                    "Retry-After": components["headers"]["RetryAfter"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            413: components["responses"]["PayloadTooLarge"];
            /** @description 형식 오류 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    cancelSaveIntent: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                save_intent_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 현재 세션의 일치하는 대기 폐기 또는 이미 없음 */
            204: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createConsent: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConsentCreate"];
            };
        };
        responses: {
            /** @description 이미 같은 동의가 있음 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConsentState"];
                };
            };
            /** @description 동의 기록 */
            201: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConsentState"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getConsentNotices: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 현재 게시 상태 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["NoticeCatalog"];
                };
            };
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    withdrawConsent: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ConsentWithdraw"];
            };
        };
        responses: {
            /** @description 철회 완료 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ConsentWithdrawResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    listSavedDrafts: {
        parameters: {
            query?: {
                page?: components["parameters"]["Page"];
                page_size?: components["parameters"]["PageSize"];
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 저장 지원서 목록 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedDraftList"];
                };
            };
            401: components["responses"]["Unauthorized"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    saveDraft: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DraftSaveRequest"];
            };
        };
        responses: {
            /** @description 저장 완료 */
            201: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["DraftSaveResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            /** @description 버전 충돌·근거 프로필 미저장·미승인·멱등 키 충돌 */
            409: {
                headers: {
                    "Retry-After": components["headers"]["RetryAfter"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getSavedDraft: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 회원 저장 지원서 문서 ID */
                document_id: components["parameters"]["DocumentId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 저장 지원서 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedDraft"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    deleteSavedDraft: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 회원 저장 지원서 문서 ID */
                document_id: components["parameters"]["DocumentId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 삭제 완료 */
            204: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    healthLive: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 살아 있음 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        /** @constant */
                        status: "ok";
                    };
                };
            };
        };
    };
    healthReady: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 준비됨 또는 AI 기능만 저하 */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
            /** @description DB 또는 Redis 장애 */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Readiness"];
                };
            };
        };
    };
    createJourney: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["JourneyCreate"];
            };
        };
        responses: {
            /** @description 체험 생성 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Journey"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    deleteJourney: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 삭제 완료 */
            204: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createJourneyDraft: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DraftCreate"];
            };
        };
        responses: {
            /** @description 임시 지원서 초안 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JourneyDraft"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            /** @description 공고 이용 불가·미확정·멱등 키 충돌 */
            409: {
                headers: {
                    "Retry-After": components["headers"]["RetryAfter"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getJourneyDraft: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 체험 안의 임시 지원서 ID */
                draft_id: components["parameters"]["DraftId"];
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 원래 지원서와 현재 재검토 안내 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JourneyDraft"];
                };
            };
            401: components["responses"]["Unauthorized"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    updateJourneyDraft: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 체험 안의 임시 지원서 ID */
                draft_id: components["parameters"]["DraftId"];
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["DraftUpdate"];
            };
        };
        responses: {
            /** @description 수정한 초안 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JourneyDraft"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    approveJourneyDraft: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 체험 안의 임시 지원서 ID */
                draft_id: components["parameters"]["DraftId"];
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BaseRevision"];
            };
        };
        responses: {
            /** @description 승인한 초안 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["JourneyDraft"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createMessage: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["MessageCreate"];
            };
        };
        responses: {
            /** @description 다음 질문과 갱신된 초안 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResult"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getJourneyProfile: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 초안과 확정 상태 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileDraftView"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    updateJourneyProfile: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileUpdate"];
            };
        };
        responses: {
            /** @description 수정한 초안 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileDraftView"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    confirmJourneyProfile: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["BaseRevision"];
            };
        };
        responses: {
            /** @description 확정한 프로필 참조 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileConfirmResult"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            /** @description 추천에 필요한 최소 항목 누락 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getRoleExclusions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 현재 전체 제외 목록과 리비전 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleExclusions"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    putRoleExclusions: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RoleExclusionUpdate"];
            };
        };
        responses: {
            /** @description 반영한 제외 목록 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleExclusions"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            /** @description 형식 오류·없는 역할 ID */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getRoleCandidates: {
        parameters: {
            query?: {
                /** @description 생략하면 현재 확정본 */
                profile_version?: number;
            };
            header?: never;
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 역할 후보 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RoleCandidates"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createTranscription: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path: {
                /** @description 사적 자원 참조. 인증 수단이 아니며 서버가 세션 소유권을 함께 확인한다 */
                journey_id: components["parameters"]["JourneyId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** @description 녹음 파일. 최대 90초·6MiB. WebM·Ogg·MP4 압축 형식 권장, WAV는 16kHz·16비트 모노 */
                    audio: Blob;
                };
            };
        };
        responses: {
            /** @description 전사 결과 */
            201: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Transcription"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            /** @description 형식 오류·지원하지 않는 음성 형식·90초 초과 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getMe: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 현재 상태 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "Set-Cookie": components["headers"]["SetSessionCookies"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Me"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    deleteAccount: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 탈퇴 완료 */
            204: {
                headers: {
                    "Set-Cookie": components["headers"]["SetSessionCookies"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            401: components["responses"]["Unauthorized"];
            /** @description 재인증 필요·CSRF 실패 */
            403: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    listOpportunities: {
        parameters: {
            query?: {
                activity_type?: "employment" | "volunteering";
                /** @description province와 함께만 쓴다. 지역 목록에 없으면 422 */
                district?: string;
                page?: components["parameters"]["Page"];
                page_size?: components["parameters"]["PageSize"];
                province?: components["schemas"]["Province"];
                /** @description 제목·기관·역할·역량·설명 검색어 */
                q?: string;
            };
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 공고 목록 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OpportunityList"];
                };
            };
            /** @description 검색 조건 오류 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getOpportunity: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 공개 공고 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Opportunity"];
                };
            };
            404: components["responses"]["NotFound"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    checkEligibility: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["EligibilityRequest"];
            };
        };
        responses: {
            /** @description 판정 결과 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["EligibilityResult"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getPreparation: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                opportunity_id: components["parameters"]["OpportunityId"];
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 신청 준비 안내 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Preparation"];
                };
            };
            404: components["responses"]["NotFound"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    getSavedProfile: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 현재 저장본 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SavedProfileResponse"];
                };
            };
            401: components["responses"]["Unauthorized"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    deleteSavedProfile: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 삭제 완료 */
            204: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content?: never;
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    saveProfileVersion: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProfileSaveRequest"];
            };
        };
        responses: {
            /** @description 같은 내용의 저장본이 있어 그 버전을 연결 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileSaveResult"];
                };
            };
            /** @description 새 저장 버전 */
            201: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProfileSaveResult"];
                };
            };
            401: components["responses"]["Unauthorized"];
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createRecommendations: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RecommendationRequest"];
            };
        };
        responses: {
            /** @description 추천 목록 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RecommendationList"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    listRegions: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description 지역 목록 */
            200: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RegionCatalog"];
                };
            };
            429: components["responses"]["TooManyRequests"];
        };
    };
    createReport: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReportCreate"];
            };
        };
        responses: {
            /** @description 신고 접수 */
            201: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReportReceipt"];
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            409: components["responses"]["Conflict"];
            413: components["responses"]["PayloadTooLarge"];
            422: components["responses"]["ValidationFailed"];
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
    createSpeech: {
        parameters: {
            query?: never;
            header: {
                /**
                 * @description 클라이언트가 만든 UUID. 같은 키·같은 입력은 첫 결과를 다시 돌려주고 새로 실행하지 않는다.
                 *     같은 키·다른 입력은 409 `IDEMPOTENCY_KEY_REUSED`, 처리 중이면 409 `REQUEST_IN_PROGRESS`.
                 */
                "Idempotency-Key": components["parameters"]["IdempotencyKey"];
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["SpeechRequest"];
            };
        };
        responses: {
            /** @description 한국어 음성 */
            200: {
                headers: {
                    "Cache-Control": components["headers"]["NoStore"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    /** @description 이 필드의 전체 조각 수 */
                    "X-Speech-Segment-Count"?: number;
                    [name: string]: unknown;
                };
                content: {
                    "audio/wav": Blob;
                };
            };
            403: components["responses"]["Forbidden"];
            404: components["responses"]["NotFound"];
            /** @description 버전 충돌·멱등 키 충돌 */
            409: {
                headers: {
                    "Retry-After": components["headers"]["RetryAfter"];
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            413: components["responses"]["PayloadTooLarge"];
            /** @description 형식 오류·허용하지 않는 필드·범위 밖 조각 */
            422: {
                headers: {
                    "X-Request-ID": components["headers"]["XRequestId"];
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["Error"];
                };
            };
            429: components["responses"]["TooManyRequests"];
            503: components["responses"]["ServiceUnavailable"];
        };
    };
}
