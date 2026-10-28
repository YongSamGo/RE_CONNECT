# 의사결정 기록 · 권장안

> main 병합 코드만을 분석한 자료가 아니다. `54d2daa` 작업 브랜치 스냅샷 기준이다. [브랜치 비교와 분석 범위](README.md)를 확인한다.

기준 `54d2daa3f25e6e39d2abf5585786676d09be7941`. 다음은 분석 권고이며 사용자 승인·기존 보류 결정을 바꾸지 않는다. P0/P1/P2는 작업 우선순위이고 코드 리뷰 심각도가 아니다.

## D1 · P0 · 실제 체험을 언제 열 것인가?

현재: 시작 UI/API는 있으나 안내는 명시적 게시가 필요하다. 운영 정보는 임의로 채울 수 없다.

- **권장: 승인 안내 후 제한 공개**: 운영 주체·문의·리전·보관/삭제 조건을 확정한 뒤 실제 경로를 연다. 검증 순서를 지키지만 시작이 늦어진다.
- **미리보기 유지**: 실데이터를 받지 않는 화면 연습을 유지한다. 실제 서비스 가치는 검증되지 않는다.

권장안: 안내 책임자를 지정하고 게시 후 별도 테스트 계정으로 첫 연속 여정을 검증한다.

영향: 동의→체험→저장 전체 경로를 여는 선행 조건이다.

담당 제안: 제품 리더 + 개인정보 책임자. 선행: 없음.

근거: [backend/app/modules/consents/notices.py:37](index.html#source=notices), [frontend/src/features/journeys/JourneyStart.tsx:19](index.html#source=start), [docs/progress/implementation-gates-20261025.md:23](index.html#source=gates).

## D2 · P0 · 검수·공개 공고를 어떤 순서로 확보할 것인가?

현재: 수집은 pending까지만 자동 연결된다. 운영자 서버/MFA 연결이 남았다. 기존 문서의 승인 공고는 0/20이다.

- **권장: MFA·검수 연결 후 소량 표본**: 권한·감사와 승인 경로를 완성하고 취업/봉사 공고 20건 목표를 검수한다. 초기 준비 비용이 든다.
- **추가 수집기 먼저**: 원문은 늘지만 승인된 추천 후보가 늘지는 않는다. 운영 병목이 남는다.

권장안: 기존 #52 보류 결정과 #228 상태를 담당자가 확인한 뒤, 승인된 순서로 검수 서버 경로를 연결한다.

영향: 추천·자격·준비 안내·지원서의 공통 입력을 만든다. 과거 결정을 자동 변경하지 않는다.

담당 제안: 백엔드/보안 + 공고 운영. 선행: D1.

근거: [frontend/src/features/admin/AdminPage.tsx:40](index.html#source=adminui), [backend/app/modules/auth/members.py:48](index.html#source=mfa), [backend/app/modules/ingestion/runner.py:26](index.html#source=collect), [docs/progress/implementation-gates-20261025.md:23](index.html#source=gates).

## D3 · P0 · 무엇을 릴리스 증거로 인정할 것인가?

분석 당시: 스냅샷에만 있는 커밋은 최신 `origin/develop` 대비 232개이며, 반대로 develop에만 있는 커밋도 7개다. 단위·대역 시험과 운영 배포 증거는 다르다. 기준과 비교 ref는 [README](README.md)에서 확인한다.

- **권장: 대표 여정의 같은 HEAD 증거**: 가상 계정으로 실제 브라우저·PostgreSQL·Redis·모델·HTTPS를 연결한다. 준비 비용이 있지만 단절을 찾는다.
- **화면별 대역 시험만 유지**: 반복 회귀는 빠르지만 실 인증·동의·수명·모델 장애를 보장하지 않는다.

권장안: 정확 HEAD의 원격 CI와 G1~G6 실제 검증을 분리 기록한다. 문서의 과거 시험을 현재 통과로 재사용하지 않는다.

영향: 통합·릴리스 신뢰도를 결정한다. 브랜치 정리·충돌 해소·PR 분할도 남아 있다.

담당 제안: 통합 담당 + QA. 선행: D1, D2.

근거: [docs/progress/implementation-gates-20261025.md:23](index.html#source=gates), [backend/tests/test_anonymous_journey_flow.py:36](index.html#source=anon_test), [.github/workflows/ci.yml:41](index.html#source=ci).

## D4 · P1 · 벡터 검색을 지금 도입할 것인가?

현재: 현재 0.7 태그 + 0.3 키워드 순위와 근거 출력이 구현돼 있다. 최신 Plan/03도 초기 pgvector 제외다.

- **권장: 현재 계산 유지·표본 평가**: 작은 검수 공고 집합으로 누락/오추천을 측정한다. 설명·재현성이 좋지만 의미 차이를 놓칠 수 있다.
- **임베딩/pgvector 추가**: 어휘 차이를 보완할 가능성이 있다. 인덱스·버전·삭제·품질 평가 비용이 추가된다.

권장안: 공고·역할 사전과 판정 기준을 먼저 확보한다. 재현율 부족이 확인된 경우에만 의미 검색을 별도 비교한다.

영향: 성급한 인프라 확장을 피하고 제품 품질 근거에 시간을 쓴다.

담당 제안: 추천 담당 + 제품 리더. 선행: D2.

근거: [backend/app/modules/recommendations/ranking.py:47](index.html#source=rank), [Plan/03_Architecture_and_Dependencies.md:18](index.html#source=plan).

## D5 · P1 · 모델·음성·GPU 범위를 어디까지 약속할 것인가?

현재: 어댑터·제어·CPU/CUDA 후보 구성은 있다. 실 GPU 공존·한국어 지연·OOM은 이번에 검증하지 않았다.

- **권장: 텍스트부터 순차 검증**: 기존 EC2 자체 텍스트·STT·TTS 방향을 유지한다. 텍스트 경로부터 입증하고 이어 음성 공존·품질을 확인한다.
- **텍스트·음성 병행 검증**: 담당자를 분리할 수 있다. GPU·슬롯·메모리·프로세스 통합 시험은 공동으로 완료해야 한다.

권장안: 실측 품질·P95 지연·메모리·정상 종료를 보고 모델과 호스트를 결정한다. 용량을 추정해 약속하거나 외부 AI로 자동 전환하지 않는다.

영향: MVP 일정과 운영 비용에 직접 영향을 준다. 텍스트만으로 기존 음성 요구사항이 완료된 것은 아니다.

담당 제안: AI/음성 담당 + 인프라. 선행: D1.

근거: [backend/app/adapters/ollama.py:35](index.html#source=llm), [backend/app/adapters/internal_speech.py:51](index.html#source=speechadapter), [Plan/03_Architecture_and_Dependencies.md:18](index.html#source=plan), [Plan/05_Engineering_Constraints.md:33](index.html#source=constraints), [docs/progress/implementation-gates-20261025.md:23](index.html#source=gates).

## D6 · P1 · 회원 저장·삭제의 운영 준비 기준은 무엇인가?

현재: 암호화와 삭제 재적용 구조는 있다. 실제 카카오·키/IAM/KMS·RDS 복원 연습은 남아 있다.

- **권장: 익명 체험과 저장 출시 분리**: 임시 체험을 먼저 검증하고 저장은 실 인증·삭제 복구 시험 후 연다. 저장 가치 확인은 늦어진다.
- **동시 공개**: 유지 가능한 프로필을 바로 제공한다. 인증·동의·키·복구의 완료 조건이 더 많다.

권장안: 영구 저장은 별도 승인 게이트로 관리한다. 복원 후 삭제 재적용과 실패 재시도를 실제 역할로 연습한다.

영향: 개인정보 수명과 운영 책임을 명확히 한다.

담당 제안: 보안 + 인프라 + 회원 담당. 선행: D1, D3.

근거: [backend/app/modules/saved_profiles/service.py:36](index.html#source=save), [backend/app/core/encryption.py:143](index.html#source=cipher), [backend/app/modules/deletions/service.py:18](index.html#source=delete), [backend/app/modules/deletions/service.py:69](index.html#source=recover), [docs/progress/implementation-gates-20261025.md:23](index.html#source=gates).

## D7 · P2 · 어느 설계·부채를 유지하고 정리할 것인가?

현재: 모듈형 모놀리스·Protocol·공개 포인터·사용자 확정 경계는 현재 목적에 맞다. README의 AI/검색 스택은 최신 설계와 다르다.

- **권장: 경계 유지·문서와 조립 정리**: 새 기능보다 기준 문서·상태 증거·진입 연결을 먼저 맞춘다. 짧은 정리 시간이 필요하다.
- **실행 서비스 분리**: 배포 독립성은 늘지만 분산 오류·정합성 비용이 증가한다. 현 표본 규모에서 필요성 미확인.

권장안: README를 최신 Plan/03와 정합화하는 별도 문서 작업을 제안한다. main.py는 조립 책임을 유지하며 변경 영향 추적을 개선한다.

영향: 병렬 개발은 계약·도메인 경계로 나눈다. 프로필/공고 버전 변경은 추천·초안·저장 담당과 함께 검토한다.

담당 제안: 아키텍처 담당 + 문서 담당. 선행: 없음.

근거: [backend/app/main.py:110](index.html#source=app), [Plan/03_Architecture_and_Dependencies.md:18](index.html#source=plan), [backend/app/modules/journeys/service.py:179](index.html#source=confirm), [backend/app/persistence/operations.py:190](index.html#source=publish).

## D8 · P0 · 취업·봉사 두 유형으로 MVP를 명시할 것인가?

현재: 원기획 PDF 13쪽·README는 교육·멘토링·지역활동을 포함한다. 현재 ActivityType 계약은 employment/volunteering뿐이다. 범위 축소 승인 여부는 확인하지 못했다.

- **권장: 두 유형의 완결 범위를 우선 결정**: 리더가 축소 범위를 명시하고 요구사항·설명·평가를 맞춘다. 원기획의 다양한 참여 가치는 후속 과제로 남는다.
- **기획서의 모든 유형 유지**: 공통 계약·DB 제약·정규화·검색·화면·자격/추천 시험을 함께 확장해야 한다. 일정 위험이 커진다.

권장안: 현재 마감·가용 인력을 확인하고 범위를 명시적으로 승인한다. 다른 유형을 취업/봉사로 임의 분류하지 않는다.

영향: 제품의 약속·공고 확보 목표·제출 설명을 좌우한다. 기존 Plan/05의 마감 기록은 2026-10-30 18시이나 공식 일정·현재 인력은 재조회하지 않았다.

담당 제안: 제품 최종 의사결정권자. 선행: 없음.

근거: [backend/app/contracts/fields.py:20](index.html#source=types), [Plan/05_Engineering_Constraints.md:33](index.html#source=constraints), [docs/progress/implementation-gates-20261025.md:23](index.html#source=gates).\n