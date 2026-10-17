# LLM·AI 도구 보안 점검 기준 — LLM-01~10, AGT-01~04

| 항목 | 내용 |
|---|---|
| 기준 | OWASP 「Top 10 for LLM Applications」 2025 (<https://genai.owasp.org/llm-top-10/>) |
| 성격 | KISA 가이드 49개 항목에 없는 위험이다. 이 파일의 판정 기준·탐지 신호는 OWASP 항목을 다시잇다 스택에 맞게 **이 스킬이 정의**한 것이며 원문 번역이 아니다. 보고서에 인용할 때 "OWASP LLM Top 10(2025) 기준, 스킬 해석"이라고 적는다 |
| ID | `LLM-01`~`LLM-10`은 OWASP `LLM01`~`LLM10`과 **번호가 같다**. 세부 점검은 `LLM-01-1`처럼 하위 번호를 쓴다. `AGT-01`~`AGT-04`는 저장소 내용이 AI 개발 도구를 조종하는 경로로, OWASP 목록 밖이라 따로 둔다 |
| 관련 문서 | README 5.1 원칙 3·4, 5.3 "가이드에 독립 항목이 없는 위험", `Plan/03_Architecture_and_Dependencies.md` §1.2, `Plan/05_Engineering_Constraints.md` §2·§3, 이슈 #113 |

## 이 파일의 사용법

- `SKILL.md`의 인덱스로 항목을 고른 뒤 `grep -n "### LLM-01" references/llm-security.md`처럼 그 항목만 읽는다.
- **코드가 있으면** 다른 항목과 같이 Source → Sink 흐름으로 판정한다. 판정 값은 `취약 / 확인 필요 / 양호 / 해당없음`이다.
- **코드가 없으면** (지금처럼 `backend/`가 아직 없을 때) 각 항목의 "설계 판정"으로 설계 문서(`Plan/`, README 5장)를 판정한다. 판정 값은 설계 기준(SR)과 같이 `충족 / 부분충족 / 미충족 / 해당없음`을 쓰고 ID 옆에 `(설계)`를 붙인다. 예: `LLM-01 (설계) 부분충족`.
- 설계에 적혀 있다고 구현이 맞다고 보지 않는다. 코드가 생기면 같은 항목을 코드 기준으로 다시 판정한다.
- 심각도(높음/중간/낮음)는 OWASP 원문에 없는 값이며 우선순위용이다.

## 다시잇다 LLM 구성 — 점검 전에 확인

문서마다 LLM 방식이 다르다. **먼저 실제로 구현된 방식을 확인**하고, 둘 다 있으면 둘 다 점검한다.

| 방식 | 근거 문서 | 호출 경로 | 점검 시 특히 볼 것 |
|---|---|---|---|
| 로컬 LLM | `Plan/03` §1.2, `Plan/05` §2 | FastAPI LLM Adapter → 내부 Ollama `/api/chat` (Qwen3, `format`에 JSON Schema, `stream=false`) | 모델 digest 고정(LLM-03), Ollama 포트 비공개·`OLLAMA_NO_CLOUD=1`(LLM-02·06), 공유 GPU 슬롯·`num_predict`(LLM-10), thinking 출력 미저장(LLM-02·07) |
| 외부 LLM API | README 2장 (OpenAI API) | FastAPI → 공급자 SDK/HTTPS | API 키 관리(SEC-06), 전송 전 마스킹·공급자 보관/학습 설정(LLM-02), 모델 ID 스냅샷 고정(LLM-03), 비용 상한(LLM-10) |

**비신뢰 Source** (README 5.1 원칙 3): 사용자 대화(음성 전사 포함), 외부 공고 원문(수집 데이터), LLM 출력, 그리고 **이전에 LLM이 만들어 DB에 저장한 값**(저장된 인젝션이 다음 프롬프트로 다시 들어간다).

**Sink**: LLM 프롬프트, 프로필·지원서 저장(DB), 화면 출력, 외부 URL 요청, 로그.

## 항목 인덱스

| ID | 항목 | OWASP 2025 | 심각도 | 관련 KISA·스킬 항목 | 세부 점검 |
|---|---|---|---|---|---|
| LLM-01 | 프롬프트 인젝션 | LLM01 Prompt Injection | 높음 | INP-02(유사), SR1-4 | 01-1 직접, 01-2 간접, 01-3 지시문·데이터 분리, 01-4 인젝션 표본 테스트 |
| LLM-02 | 민감정보 노출 | LLM02 Sensitive Information Disclosure | 높음 | SEC-05, ERR-01 | 02-1 전송 전 최소화·마스킹, 02-2 로그·저장, 02-3 공급자 보관·학습, 02-4 다른 사용자 정보 혼입 |
| LLM-03 | 모델·AI 구성요소 공급망 | LLM03 Supply Chain | 중간~높음 | SEC-15, COD-05, SCP-09·15, RM-11 | 03-1 모델·가중치 출처·digest, 03-2 원격 코드·pickle, 03-3 SDK·런타임 버전 |
| LLM-04 | 데이터·모델 오염 | LLM04 Data and Model Poisoning | 중간 | INP-12 | 04-1 수집 공고 오염, 04-2 프롬프트 예시·템플릿 출처, 04-3 미세조정·학습 데이터 |
| LLM-05 | 부적절한 출력 처리 | LLM05 Improper Output Handling | 높음 | INP-01·02·04·07·12, COD-05 | 05-1 스키마 검증, 05-2 출력 → 위험 Sink, 05-3 근거 참조 검증 |
| LLM-06 | 과도한 권한 | LLM06 Excessive Agency | 높음(도구 있을 때) | SEC-01·02 | 06-1 도구·함수 호출, 06-2 사용자 확인 없는 상태 변경, 06-3 모델 런타임 권한 |
| LLM-07 | 시스템 프롬프트 노출 | LLM07 System Prompt Leakage | 중간 | SEC-06, SEC-13 | 07-1 프롬프트 속 비밀·내부정보, 07-2 노출 탐지(카나리), 07-3 프롬프트에 의존한 보안 통제 |
| LLM-08 | 벡터·임베딩 약점 | LLM08 Vector and Embedding Weaknesses | 중간(해당 시) | SEC-02 | 08-1 사용자별 격리, 08-2 임베딩 입력 출처 |
| LLM-09 | 잘못된 정보(환각) | LLM09 Misinformation | 중간 | — | 09-1 자격 판정의 규칙 기반 처리, 09-2 근거·출처 표시, 09-3 평가 표본 |
| LLM-10 | 무제한 소비 | LLM10 Unbounded Consumption | 중간 | SEC-16, TIM-02 | 10-1 입력·출력 크기, 10-2 호출 한도·동시 실행, 10-3 시간 제한·재시도, 10-4 비용 상한 |
| AGT-01 | 저장소의 숨은 문자 | — (OWASP 밖) | 높음 | — | CI `숨은 문자·지시문 점검` |
| AGT-02 | 에이전트 지시 파일 변경 통제 | — | 중간 | SCP-14 | CODEOWNERS, PR 사유 |
| AGT-03 | 저장소 데이터 속 지시문 | — | 중간 | — | 의도한 표본 표시, 새 지시문 경고 |
| AGT-04 | AI 개발 도구 권한 설정 | — | 중간 | SCP-14, SCP-20 | 저장소에 커밋된 도구 설정 |

---

## LLM 기능 (OWASP LLM Top 10)

### LLM-01. 프롬프트 인젝션 — 심각도 높음

- OWASP: LLM01:2025 Prompt Injection. CWE-1427(LLM 프롬프트 입력의 부적절한 중화).
- 위험: 사용자 대화나 외부 데이터에 든 문장이 지시문으로 해석돼 모델이 원래 작업을 벗어난다. 다시잇다에서는 말하지 않은 자격증이 프로필에 들어가거나(오추출), 시스템 설정이 노출되거나, 공고 원문의 문장이 추천·지원서 초안을 조작하는 형태로 나타난다.

**세부 점검**

| ID | 내용 | Source |
|---|---|---|
| LLM-01-1 | 직접 인젝션: 사용자가 대화·음성으로 "지시 무시", "설정 보여줘"를 말한다 | 사용자 대화, STT 전사 |
| LLM-01-2 | 간접 인젝션: 공고 원문·기관 설명·저장된 프로필 값에 든 지시문이 다른 사용자의 요청에서 실행된다 | 수집 공고, DB에 저장된 LLM 출력 |
| LLM-01-3 | 지시문과 데이터 분리: 비신뢰 텍스트가 시스템 지시문과 같은 문자열로 결합된다 | 프롬프트 조립 코드 |
| LLM-01-4 | 인젝션 표본 테스트: 직접·간접 인젝션 표본이 자동 테스트로 돈다 | `eval/` 표본 |

**탐지 신호**

```bash
# LLM 호출 지점
rg -n --type py -e 'ollama|/api/(chat|generate)' -e '\b(openai|anthropic)\b' -e '(chat\.completions|responses|messages)\.create\('
# 시스템 지시문에 변수를 f-string·format·+로 결합 (LLM-01-3 후보)
rg -n --type py -e '(system|instruction|prompt)\w*\s*=\s*f["\x27]' -e '["\x27]role["\x27]\s*:\s*["\x27]system["\x27][^}]*(f["\x27]|\.format\(|\+\s*\w)'
# 공고 원문·프로필 값이 프롬프트로 들어가는 지점
rg -n --type py -e '(posting|notice|job|announcement|description|raw_text|body)\w*' -g '*prompt*' -g '*llm*' -g '*adapter*'
```

**판정 기준**

- 정탐(`취약`)
  - 비신뢰 텍스트(사용자 대화, 공고 원문, 저장된 LLM 출력)가 `system` 메시지 안에 결합되거나, 지시문과 데이터가 구분 없이 한 문자열로 들어간다 (LLM-01-3).
  - 모델 출력이 별도 검증 없이 프로필·지원서에 저장되어 인젝션이 사실로 남는다 (LLM-05와 함께 보고).
  - 공고 원문을 요약·추천 근거로 쓰는데 원문 속 지시문을 데이터로 다루는 처리(구분자·역할 분리·출력 스키마 고정)가 하나도 없다 (LLM-01-2).
- 오탐(`양호` 또는 `확인 필요`)
  - 비신뢰 텍스트가 `user` 메시지(또는 명확한 구분자로 감싼 데이터 블록)에만 들어가고, 출력이 JSON Schema·Pydantic으로 고정되며, 저장 전에 사용자 확인을 거친다 → `양호`. 프롬프트 지시문만으로 막는다고 적혀 있으면 `확인 필요`로 둔다 (지시문은 우회될 수 있다).
  - 모델 출력이 화면 표시에만 쓰이고 저장·행동으로 이어지지 않으면 심각도를 낮춘다.
- 주의: "필터로 '무시하라' 같은 문구를 지운다"는 방어로 인정하지 않는다. 우회가 쉽다. 판정 근거는 **분리·출력 고정·권한 최소화·사용자 확인**이다.

**설계 판정** (코드가 없을 때)

| 판정 | 조건 |
|---|---|
| 충족 | 설계에 ① 비신뢰 텍스트를 지시문과 분리 ② 출력 스키마 고정 ③ 도구 접근 금지 ④ 저장 전 사용자 확인 ⑤ 인젝션 표본 테스트가 모두 있다 |
| 부분충족 | 위 다섯 중 일부만 있다 |
| 미충족 | 비신뢰 데이터·인젝션에 대한 언급이 없다 |

다시잇다 설계 근거 위치: README 5.1 원칙 3, 5.3 "프롬프트 인젝션", `Plan/05` §2 위협 표("API → 로컬 LLM/STT/TTS: 개인정보·인젝션·환각"), `Plan/03` §1.2(JSON Schema·Pydantic 재검증), `Plan/Implementation_Plan.md` W04-02·W04-03.

**조치**

- 지시문은 `system` 메시지에 고정 문자열로 두고, 비신뢰 텍스트는 `user` 메시지 안에 구분된 데이터 블록으로 넣는다. 공고 원문은 "요약할 자료"로만 전달한다.
- 출력은 JSON Schema로 고정하고 Pydantic으로 다시 검증한다(LLM-05). 프로필에 반영할 값은 사용자에게 보여 주고 확인을 받는다.
- 도구·함수 호출을 쓰지 않는다(LLM-06).
- 테스트: `eval/personas/P07.json`(직접 인젝션 표본, PR #112)을 자동 테스트로 돌린다 — `must_not_extract` 항목이 프로필에 없고 시스템 설정이 응답에 없어야 한다(#30). 간접 인젝션은 지시문을 넣은 가짜 공고 표본으로 추천·요약 결과가 바뀌지 않는지 본다(#65).

### LLM-02. 민감정보 노출 — 심각도 높음

- OWASP: LLM02:2025 Sensitive Information Disclosure. CWE-359.
- 위험: 대화 원문·경력·건강·생활 조건이 모델에 필요 이상 전달되거나, 프롬프트·응답이 로그·추론 과정(thinking)·공급자 쪽에 남거나, 다른 사용자의 정보가 응답에 섞인다.

| ID | 점검 |
|---|---|
| LLM-02-1 | 전송 전 최소화·마스킹: 연락처·주민등록번호·상세 병력을 LLM 입력 전에 탐지·안내·제거하는가 (`Plan/05` §2) |
| LLM-02-2 | 로그·저장: 프롬프트·응답·전사 원문·thinking 출력이 `logging`·`print`·오류 응답·DB에 남지 않는가 (SEC-05, ERR-01) |
| LLM-02-3 | 공급자 보관·학습: 외부 API면 데이터 보관·학습 사용 설정과 리전을 확인했는가. 로컬이면 `OLLAMA_NO_CLOUD=1`·외부 추론 전환 금지가 설정에 있는가 |
| LLM-02-4 | 다른 사용자 정보 혼입: 프롬프트에 넣는 프로필·이전 대화가 요청한 사용자의 것인지 소유자 확인을 거치는가 (SEC-02). 프로세스 전역 캐시·대화 버퍼를 사용자 간에 공유하지 않는가 (ENC-01) |

```bash
rg -n --type py -e '(logger|logging|log)\.\w+\([^)]*(prompt|messages|content|transcript|response|thinking)' -e 'print\([^)]*(prompt|messages|response)'
rg -n -e 'OLLAMA_NO_CLOUD' -e 'OLLAMA_HOST' -e '(store|data_retention|training)\s*[:=]' -g '*.py' -g '*.env*' -g 'docker-compose*.y*ml' -g 'compose*.y*ml'
```

- 정탐: 프롬프트·응답 원문을 로그에 남김, 마스킹 없이 전체 대화·프로필을 전송, thinking 출력을 저장·표시, 소유자 확인 없이 프로필을 조회해 프롬프트에 넣음.
- 오탐: 요청 ID·토큰 수·지연 시간만 로그에 남김. 마스킹은 패턴 필터라 완전하지 않으므로 "마스킹이 있다"만으로 `양호`라고 하지 않고, 최소 전달(필요한 필드만 선택) 여부를 함께 본다.
- 설계 판정: 최소 전달·마스킹·원문 로그 금지·외부 전송 금지(또는 공급자 설정)가 모두 있으면 충족. 근거: README 5.1 원칙 4, `Plan/05` §2.

### LLM-03. 모델·AI 구성요소 공급망 — 심각도 중간~높음

- OWASP: LLM03:2025 Supply Chain. 로드맵 RM-11(AI 구성요소 관리)과 연결된다.

| ID | 점검 |
|---|---|
| LLM-03-1 | 모델·가중치 출처: Ollama 모델은 태그만이 아니라 digest를, Hugging Face 모델(faster-whisper·Qwen3-TTS)은 `revision`(커밋 해시)을 고정하는가. 공식 배포원·라이선스를 기록했는가 (`Plan/03` §1.2, SCP-09) |
| LLM-03-2 | 원격 코드·역직렬화: `trust_remote_code=True`, 검증 없는 `torch.load`/pickle 가중치(COD-05), 런타임 모델 다운로드(SEC-15, SCP-15) |
| LLM-03-3 | SDK·런타임 버전: LLM SDK·Ollama 이미지·음성 서비스 이미지의 버전·다이제스트 고정 (SCP-01·13). 외부 API면 별칭(`latest`)이 아닌 날짜가 붙은 모델 ID |

```bash
rg -n -e 'ollama\s+(pull|run)' -e 'qwen3?[:@]' -e 'image:\s*\S*ollama' -e 'FROM\s+\S*ollama' -g '*' --hidden -g '!.git'
rg -n --type py -e 'trust_remote_code\s*=\s*True' -e 'from_pretrained\(' -e 'hf_hub_download\(' -e 'snapshot_download\(' -e 'revision\s*='
```

- 정탐: 태그만 쓰고 digest·revision이 없음(`확인 필요`, 운영 배포면 `취약`), `trust_remote_code=True`, 사용자 요청으로 모델 이름·주소·가중치 URL을 바꿀 수 있음.
- 설계 판정: `Plan/03` §1.2의 "평가 후 태그·모델 digest 고정", `Plan/05` §2 "임의 모델·원격 코드 사용 금지"가 있으면 충족(설계). 실제 고정값은 코드·Compose에서 다시 본다.

### LLM-04. 데이터·모델 오염 — 심각도 중간

- OWASP: LLM04:2025 Data and Model Poisoning.
- 다시잇다는 모델을 학습시키지 않는다(`Plan/03` §1.2). 그래서 오염 경로는 **수집 공고**와 **프롬프트에 넣는 예시·템플릿**이다.

| ID | 점검 |
|---|---|
| LLM-04-1 | 수집 공고 오염: 출처 허용 목록(고정 API·검수한 기관)만 수집하는가, 원문 길이 제한(`Plan/05` §3 공고 본문 5,000자), 수정 이력·검수 상태를 남기는가 (`worker/`) |
| LLM-04-2 | 프롬프트 예시·템플릿: few-shot 예시와 프롬프트 템플릿이 저장소(리뷰 대상)에 있고 버전이 붙는가. DB·외부에서 템플릿을 불러오지 않는가 |
| LLM-04-3 | 미세조정·학습: 사용자 대화·음성을 학습·평가 자료로 보관하지 않는가. 미세조정이 없으면 `해당없음` |

- 정탐: 임의 URL에서 공고를 수집(INP-12와 함께), 검수 없는 공고를 추천 근거로 바로 사용, 프롬프트 템플릿을 런타임에 외부에서 받음.

### LLM-05. 부적절한 출력 처리 — 심각도 높음

- OWASP: LLM05:2025 Improper Output Handling. CWE-1426(생성형 AI 출력의 부적절한 검증).
- 위험: LLM 출력은 비신뢰 데이터다(README 5.1 원칙 3). 검증 없이 저장·실행·표시하면 기존 KISA 약점이 그대로 생긴다.

| ID | 점검 |
|---|---|
| LLM-05-1 | 스키마 검증: 출력을 JSON Schema(`format`)로 받고 Pydantic으로 다시 검증하는가. `extra="allow"`·`Any`·`dict` 필드가 없는가. 검증 실패 시 저장하지 않고 거부하는가(fail-closed) |
| LLM-05-2 | 위험 Sink: 출력이 SQL(INP-01), `eval`/템플릿(INP-02), HTML(INP-04), 리다이렉트(INP-07), 서버 요청 URL(INP-12), 역직렬화(COD-05)에 들어가는가 |
| LLM-05-3 | 근거 참조 검증: 추출 값이 사용자 발화·공고 원문의 실제 위치를 가리키는지 확인하는가 (`Plan/03` §1.2 "근거 참조를 다시 검증") |

```bash
rg -n --type py -e 'json\.loads\(\s*\w*(response|content|output|result)' -e 'model_validate_json\(' -e 'extra\s*=\s*["\x27]allow' -e ':\s*(Any|dict)\b'
rg -n -e 'dangerouslySetInnerHTML' -e 'innerHTML\s*=' -e 'v-html' -g '*.ts' -g '*.tsx' -g '*.js' -g '*.vue'
```

- 정탐: `json.loads` 결과를 검증 없이 ORM 모델에 `**kwargs`로 저장, 출력 문자열을 HTML로 렌더링, 출력 속 URL로 서버가 요청을 보냄.
- 오탐: Pydantic 모델(`extra="forbid"`)로 검증한 뒤 필드 단위로 저장하고 화면은 일반 텍스트로 렌더링 → `양호`.
- 설계 판정: JSON Schema + Pydantic 재검증 + 근거 참조 검증 + 일반 텍스트 렌더링(`Plan/05` §2 "브라우저 출력")이 있으면 충족.

### LLM-06. 과도한 권한 — 심각도 높음(도구가 있을 때)

- OWASP: LLM06:2025 Excessive Agency. CWE-250.

| ID | 점검 |
|---|---|
| LLM-06-1 | 도구·함수 호출: `tools`·`functions`·`tool_choice`를 쓰는가. 쓰면 도구 목록이 읽기 전용·최소인지, 외부 발송·파일 접근·URL 요청 도구가 없는지 (README 5.3) |
| LLM-06-2 | 사용자 확인: 모델 출력이 사용자 확인 없이 프로필 확정·지원서 제출·외부 기관 전송 같은 상태 변경으로 이어지지 않는가 |
| LLM-06-3 | 모델 런타임 권한: Ollama·음성 서비스 포트가 외부에 열리지 않고 FastAPI만 호출하는가. 관리 API(`/api/pull`, `/api/delete`, `/api/create`)를 앱이 호출하지 않는가 (`Plan/03` §1.2, `Plan/05` §2) |

```bash
rg -n --type py -e '\btools\s*=' -e 'tool_choice' -e 'function_call' -e '"type"\s*:\s*"function"'
rg -n -e '11434' -e '/api/(pull|push|delete|create|copy)' -g '*.py' -g '*.y*ml' -g 'Dockerfile*' -g '*.conf'
```

- 정탐: 도구 호출로 파일·네트워크·DB 쓰기 가능, Compose에서 `11434:11434`로 Ollama 포트 공개, 모델 출력으로 바로 외부 제출.
- 설계 판정: "도구 접근 금지"(`Plan/05` §2), "외부 기관 자동 제출 MVP 제외"(README 1장), "Ollama 포트 비공개"가 있으면 충족.

### LLM-07. 시스템 프롬프트 노출 — 심각도 중간

- OWASP: LLM07:2025 System Prompt Leakage.
- 시스템 프롬프트는 언젠가 노출된다고 가정한다. 노출 자체보다 **프롬프트에 비밀이 있거나 보안 통제를 프롬프트에 맡긴 것**이 약점이다.

| ID | 점검 |
|---|---|
| LLM-07-1 | 프롬프트 속 비밀·내부정보: API 키·내부 주소·DB 구조·다른 사용자 정보·운영 정책 세부가 프롬프트에 없는가 (SEC-06·13) |
| LLM-07-2 | 노출 탐지: 시스템 프롬프트에 카나리 문자열(무작위 토큰)을 넣고, 응답에 그 문자열이나 프롬프트 원문 일부가 있으면 응답을 막고 기록하는가. 인젝션 표본 P07의 "시스템 설정 보여줘"로 시험한다 |
| LLM-07-3 | 프롬프트에 의존한 통제: 권한·한도·개인정보 필터링을 "모델에게 하지 말라고 지시"하는 것으로만 처리하지 않는가 (서버 코드에서 강제해야 한다) |

- 정탐: 프롬프트 템플릿에 비밀값·내부 URL, 권한 판단을 프롬프트 지시로만 처리.
- 카나리가 없다는 것만으로는 `확인 필요`(낮음)로 둔다. 07-1·07-3이 지켜지면 노출 영향이 작다.

### LLM-08. 벡터·임베딩 약점 — 심각도 중간(해당 시)

- OWASP: LLM08:2025 Vector and Embedding Weaknesses.
- 현재 `Plan/05` §1에서 pgvector·의미 검색은 **초기 유예(P2)** 다. 도입 전에는 `해당없음(미도입)`으로 적는다. README 2장에는 pgvector가 있으니 도입 여부를 코드로 확인한다.
- 도입 시 점검: ① 검색 쿼리에 사용자·권한 필터가 항상 붙는가(다른 사용자 프로필 임베딩이 검색되지 않음, SEC-02) ② 임베딩 대상이 검수된 공고·본인 데이터뿐인가(LLM-04) ③ 삭제·동의 철회 시 임베딩도 지워지는가.

### LLM-09. 잘못된 정보(환각) — 심각도 중간

- OWASP: LLM09:2025 Misinformation.
- 위험: 시니어에게 없는 자격 요건을 충족한다고 하거나, 마감·지원 자격을 잘못 안내해 실제 손해(헛걸음, 신청 실패)로 이어진다.

| ID | 점검 |
|---|---|
| LLM-09-1 | 자격 판정: 나이·지역·자격증 같은 자격 요건 판정은 LLM이 아니라 규칙 코드로 하는가. LLM은 추출·설명만 하는가 |
| LLM-09-2 | 근거·출처: 추천·설명에 공고 원문 출처와 확인 시점을 함께 보여 주는가. 근거를 찾지 못한 값은 "확인 필요"로 표시하는가 |
| LLM-09-3 | 평가 표본: `eval/eligibility_cases.json`과 페르소나 표본(PR #112)으로 오판·환각을 측정하는가 (#10, #30, #65) |

- 설계 판정: README 6장 "자격 오판·환각 시나리오 통과", `Plan/03`의 근거 참조 검증이 있으면 부분충족 이상. 규칙 기반 자격 판정이 명시돼 있으면 충족.

### LLM-10. 무제한 소비 — 심각도 중간

- OWASP: LLM10:2025 Unbounded Consumption. CWE-770. README 5.3 "LLM 호출 비용 상한"이 이 항목이다.

| ID | 점검 | 다시잇다 기본값 (`Plan/05` §3) |
|---|---|---|
| LLM-10-1 | 입력·출력 크기: 요청 본문·대화·공고 길이 제한, 출력 토큰 상한(`num_predict`, `max_tokens`) | 대화 1회 2,000자, 공고 5,000자, JSON 64KiB |
| LLM-10-2 | 호출 한도·동시 실행: 사용자·IP·전역 한도를 Redis에서 원자적으로 집계, 공유 추론 슬롯 | 회원·비회원 하루 60회, 전체 하루 500회, 사용자별 동시 1개 |
| LLM-10-3 | 시간 제한·재시도: 요청당 제한시간, 재시도 횟수 제한, Adapter·런타임 재시도 중첩 없음 | 60초, 일시 오류 1회 |
| LLM-10-4 | 비용 상한: 외부 API면 계정·키 단위 지출 한도. 로컬이면 GPU·메모리 고갈 시 429·503 | 슬롯 부족 429, 모델 장애 503 |

```bash
rg -n --type py -e 'num_predict|max_tokens|max_output_tokens|num_ctx' -e 'timeout\s*=' -e '(retry|retries|max_retries)\s*='
rg -n --type py -e 'RateLimit|rate_limit|limiter|INCR|incr\(|expire\(' -e 'Semaphore|slot'
```

- 정탐: LLM 호출에 timeout 없음, 출력 상한 없음, 한도 집계가 비원자적(조회 후 증가, TIM-01), 한도 초과 요청도 모델을 실행.

---

## 저장소 → AI 개발 도구 (AGT)

AI 개발 도구(Claude Code, Codex, Copilot 등)는 저장소의 문서·지시 파일·PR 본문을 읽고 그대로 따를 수 있다. 사람 리뷰를 통과한 텍스트가 도구를 조종하는 경로를 점검한다. 지시 파일: 어느 폴더에 있든 `.claude/`, `.codex/`, `.cursor/`, `.gemini/`, `CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `AGENTS.override.md`, `GEMINI.md`, `.mcp.json`, `.vscode/mcp.json`, `.cursorrules`, `.windsurfrules`, 그리고 `.github/copilot-instructions.md` 등. 하위 폴더에서 도구를 열면 그 폴더의 지시 파일도 쓰이므로 최상위만 보지 않는다 (`.github/scripts/check_hidden_text.py`의 `AGENT_PATHSPECS`, `.github/CODEOWNERS`와 같은 범위).

### AGT-01. 저장소의 숨은 문자 — 심각도 높음

- 위험: 폭 없는 문자, 글자 방향 제어(Trojan Source, CVE-2021-42574), 유니코드 태그 문자, 연속된 이체 선택자는 화면에 보이지 않지만 도구는 읽는다. 리뷰어가 보지 못한 지시문을 숨길 수 있다.
- 자동 점검: CI `숨은 문자·지시문 점검` 잡이 git이 추적하는 텍스트 파일 전체와 경로 이름을 검사하고, 발견하면 **실패**한다. 허용은 파일 맨 앞 BOM, 이모지 사이 ZWJ, 글자 뒤 이체 선택자 1개, 줄 끝 CRLF뿐이다. 단독 CR(터미널에서 앞 문장을 덮어씀)도 실패다.
- 인코딩 우회: UTF-16으로 저장하거나 잘못된 바이트를 하나 넣으면 UTF-8 검사를 피할 수 있다. 그래서 NUL이 있거나 UTF-8로 읽히지 않는 텍스트 파일도 실패로 본다. 진짜 바이너리는 스크립트의 `BINARY_EXTENSIONS`나 `.gitattributes`의 `binary`로 지정한다.
- 수동 점검: `python -I .github/scripts/check_hidden_text.py` (저장소 최상위). PR 본문·이슈·댓글은 CI가 검사하지 않으므로, AI 도구에 PR·이슈를 읽힐 때는 도구가 이를 데이터로 다루는지 확인한다.
- 판정: CI 잡이 `ci-ok`의 `needs`에 있고 브랜치 보호의 필수 체크가 `CI 통과`이면 `양호`. 잡이 없거나 실패를 무시하면 `취약`. 설정만 보고 `양호`로 두지 말고, 검사를 건너뛰는 경로(바이너리로 보는 확장자·`.gitattributes`의 `binary` 지정, 경고로만 끝나는 경우)가 PR에서 늘었는지도 확인한다. 회귀 시험은 `.github/scripts/test_check_hidden_text.py`이고 CI가 검사 전에 돌린다.

### AGT-02. 에이전트 지시 파일 변경 통제 — 심각도 중간

- 위험: `.claude/commands/`·스킬·`CLAUDE.md`를 바꾸면 이후 팀원이 실행하는 AI 도구의 동작이 바뀐다. CI 워크플로·`.gitleaks.toml`을 바꾸면 점검 자체를 끌 수 있다.
- 점검: `.github/CODEOWNERS`가 지시 파일·`.github/`·`.gitleaks.toml`·`.gitattributes`를 덮는가, 지정 리뷰어가 **두 명 이상**인가(작성자 본인 승인은 인정되지 않음), 브랜치 보호에서 "Require review from Code Owners"가 켜져 있는가(`gh api repos/{owner}/{repo}/branches/develop/protection`의 `require_code_owner_reviews`), PR 템플릿에 변경 사유 항목이 있는가.
- 지정 리뷰를 피하는 경로
  - **심볼릭 링크**: 지시 파일을 링크로 만들면 diff에는 대상 경로 한 줄만 보이고, 대상 파일(예: `docs/guide.md`)은 CODEOWNERS·의심 문구 검사 밖이다. CI는 지시 경로의 심볼릭 링크를 실패로 처리한다.
  - **`.gitattributes` 숨김**: `-diff`·`binary`·`linguist-generated`가 걸린 지시 파일은 PR 화면에서 내용이 접히거나 "Binary file not shown"으로 숨는다. CI는 이것도 실패로 처리한다.
  - **다른 파일 끌어오기**: Claude Code의 `@경로` import처럼 지시 파일이 다른 파일을 읽어 들이면, 끌려온 파일은 CODEOWNERS 밖일 수 있다. CI가 잡지 못하므로 지시 파일에 `@경로`가 추가되면 대상 파일도 지시 파일로 보고 리뷰한다.
- 판정: 셋 다 있으면 `양호`, CODEOWNERS만 있고 보호 설정이 꺼져 있으면 `확인 필요`(리뷰 요청만 붙고 강제되지 않음).

### AGT-03. 저장소 데이터 속 지시문 — 심각도 중간

- 위험: 문서·데이터 파일·평가 표본·수집 공고 샘플에 든 "이전 지시를 무시하라"류 문장을 AI 도구가 작업 지시로 따른다.
- 점검
  - 의도한 인젝션 표본(`eval/personas/P07.json` 등)은 파일 안에 표본이라는 표시(`test_focus`, `notes`)가 있는가.
  - 에이전트 지시 파일에 새로 추가된 줄의 의심 문구(지시 무시·사용자에게 숨김·권한 사칭·비밀값 외부 전송·권한 확인 우회)는 CI가 PR에서 **경고**로 표시한다. 보안 문서가 예시로 쓰는 경우가 있어 실패시키지 않는다. 리뷰어가 의도한 내용인지 확인한다.
  - AI 도구를 쓰는 사람은 도구가 읽은 파일·웹 페이지·도구 출력 속 지시를 따르지 않게 설정·지시했는가 (도구 기본 동작 확인).
- 판정: 표시 없는 지시문이 지시 파일 밖(일반 문서·데이터)에 있으면 `확인 필요`. 지시 파일 안에 있으면 `취약`.

### AGT-04. AI 개발 도구 권한 설정 — 심각도 중간

- 위험: 저장소에 커밋된 도구 설정(`.claude/settings.json`, `.mcp.json`, `.vscode/mcp.json`, `.gemini/settings.json` 등)이 모든 셸 명령 자동 허용, 권한 확인 생략, 외부 MCP 서버 연결을 켜 두면 저장소를 연 팀원의 PC에서 확인 없이 명령이 실행될 수 있다.
- 점검

```bash
rg --files --hidden -g '!.git' -g '**/.claude/settings*.json' -g '.mcp.json' -g '**/.vscode/mcp.json' -g '**/.cursor/**' -g '**/.codex/**' -g '**/.gemini/**' -g '**/.vscode/settings.json'
rg -n --hidden -e '"Bash\(\*\)"|"Bash"\s*[,\]]' -e 'bypassPermissions|dangerously' -e '"hooks"' -e '"command"\s*:' -g '**/.claude/**' -g '.mcp.json' -g '**/.vscode/mcp.json' -g '**/.gemini/**'
```

- 판정: 모든 명령 허용·권한 생략(Codex의 `approval_policy = "never"`·`sandbox_mode = "danger-full-access"` 포함)이 커밋돼 있으면 `취약`. hooks·MCP 서버·Codex 규칙의 `decision = "allow"`는 실행 명령과 출처(버전 고정 여부)를 확인해 `확인 필요`로 두고 SCP-14·SCP-20과 함께 본다. 차단(deny·`forbidden`)·확인(ask·`prompt`) 규칙만 있으면 `양호`. 설정 파일이 없으면 `해당없음`.
- 팀 공용 차단 규칙과 그 한계는 [AGENTS.md "도구 권한 설정"](../../../../AGENTS.md#도구-권한-설정)에 있다 (#125).

---

## 보고 형식

`/kisa-review` 보고서의 `## LLM·AI 도구 점검` 섹션에 아래 표를 쓰고, `취약`·`확인 필요`는 `상세`에 다른 항목과 같은 형식으로 적는다.

```markdown
## LLM·AI 도구 점검
- 기준: OWASP Top 10 for LLM Applications 2025 (스킬 해석), 저장소 → AI 도구 경로(AGT)
- LLM 방식: 로컬(Ollama + Qwen3) / 외부 API / 미구현(설계 판정)

| ID | 항목 | 판정 | 심각도 | 근거 위치 |
|---|---|---|---|---|
| LLM-01 (설계) | 프롬프트 인젝션 | 부분충족 | 높음 | Plan/05 §2 — 표본 자동 테스트 없음 (LLM-01-4) |
| AGT-01 | 저장소의 숨은 문자 | 양호 | — | .github/workflows/ci.yml hidden-text, ci-ok needs |
```

설계 판정의 `미충족`·`부분충족`은 PR 댓글 등급을 매길 때 `확인 필요`로 본다(`/kisa-review` 4절).
