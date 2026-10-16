# W02-08.b / #19 · 실제 지역 라우터 계약 대조

기준: `docs/api/openapi.yaml`, backend `app/modules/regions/router.py`·`app/contracts/regions.py`, frontend `src/features/regions/catalog.ts`.

기존 API 타입 생성·클라이언트를 재작성하지 않고 이미 구현된 공개 지역 API만 대조한다. 정적 예시나 복사한 지역 JSON을 실제 서버 응답처럼 사용하지 않는다. Python `TestClient`가 실제 지역 라우터를 테스트용 FastAPI 앱에 마운트해 ASGI 응답을 얻는다. 서비스 설정·`.env`·DB·Redis·모델·네트워크 수신 포트는 사용하지 않는다. 전체 앱의 미들웨어·인증·배포·브라우저 HTTP 통합을 통과했다고 해석하면 안 된다.

## 실행

저장소 루트에서 Python 3.12 환경을 준비한다. Windows에서는 `python3.12` 대신 `py -3.12`를 사용할 수 있다.

```powershell
py -3.12 -m venv backend/.venv
backend/.venv/Scripts/python.exe -m pip install --require-hashes -r backend/requirements.txt
cd frontend
npm ci --ignore-scripts
npm run test:backend-contract
```

Linux/macOS에서는 `python3.12 -m venv backend/.venv`와 `backend/.venv/bin/python -m pip install --require-hashes -r backend/requirements.txt`를 사용한다. 기존 환경을 쓰려면 `CONTRACT_PYTHON`에 Python 실행 파일 경로를 설정한다. 이 값은 셸 명령이 아니라 `execFileSync`의 실행 파일 하나로 전달된다. 환경이 없거나 내보내기가 실패하면 시험도 실패하며 모의 데이터로 대체하지 않는다.

기본 `npm test`는 Python 없는 프론트 단위 시험을 유지한다. 새 계약 시험은 별도 명령이지만 기존 CI의 프론트 job에서 필수로 실행한다. 새 테스트와 구성 파일도 build의 TypeScript 검사 대상이다. 테스트 전용 Ajv와 YAML 파서는 devDependencies에 정확한 버전으로 고정하며 브라우저 엔트리에서 가져오지 않는다.

## 검사 범위

1. 실제 지역 라우터 응답의 200·JSON media type 및 전체 본문을 원본 OpenAPI 응답 스키마와 대조한다. FastAPI가 생성한 동일 경로의 응답 스키마에도 통과해야 한다.
2. 기존 프론트 파서가 실제 버전·시도·시군구 식별값과 표시명을 손실 없이 처리하는지 확인한다. Python `Region` 모델이 받아들인 모든 반환 지역을 FE 선택 검사에도 통과시킨다.
3. 선언하지 않은 필드를 넣으면 `additionalProperties: false` 계약이 실패하는지 확인한다. FE의 표시용 투영이 알 수 없는 필드를 버리더라도 계약 이탈을 놓치지 않는다.
4. 계약의 버전 제약을 의도적으로 바꾼 복제 스키마가 실제 응답을 거절하는지 확인한다. 원본 계약 파일은 수정하지 않는다.
5. 존재하지 않거나 다른 시도의 시군구를 선택하면 지역 전체로 넓히지 않고 거절하는지 확인한다.

OpenAPI 3.1에 맞춰 Ajv의 JSON Schema 2020-12 클래스를 사용한다([공식 문서](https://ajv.js.org/json-schema.html#draft-2020-12-breaking)). OpenAPI 컨테이너인 `components`만 annotation 키워드로 등록하며 다른 알 수 없는 스키마 키워드는 strict 검사로 거절한다. YAML은 JSON_SCHEMA로 읽고 외부 스키마 다운로드·임의 태그 실행은 하지 않는다. 전체 API·모든 JSON Schema 형식의 자동 검증기를 서비스 런타임에 도입한 작업은 아니다.

## 보안 근거·한계

AGENTS.md → 이미 확인한 Security/INDEX.md → 진단가이드의 `SW개발보안_obsidian/Security/SW-Diagnosis-2021/제2장-소프트웨어-개발보안/제3절-설계단계-보안설계-기준/023-1.5-웹-서비스-요청-및-결과-검증.md`(제2장 제3절 1.5, PDF 64~71쪽)의 요청·응답 검증 원칙을 적용했다. Python 구현 가이드를 진단 기준으로 대체하지 않았으며 원문 예제를 실행하지 않았다. Ajv 선택·프로세스 20초 제한·1MiB 출력 상한·셸 미사용·환경 격리는 테스트 도구의 기술 판단이다.

출력은 공개 지역·스키마·지역 모델 입력뿐이며 사용자 프로필·음성·비밀값을 내보내지 않는다. `.github/workflows/ci.yml` 변경 사유는 이 계약 검사도 CI에서 누락 없이 실행하기 위해서다. 기존 권한·고정 action SHA·캐시 정책은 유지한다. 향후 PR에는 저장소 CODEOWNERS 검토가 필요하다. GitHub 원격 CI 성공이나 #19 전체 완료는 로컬 검사만으로 주장하지 않는다.
