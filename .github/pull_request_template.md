## 무엇을 바꿨나

<!-- 한두 문장. 관련 기능(F1~F6)이나 이슈가 있으면 적기: Closes #번호 -->

## 관련 KISA 보안약점

<!--
이 PR이 다루거나 영향을 주는 약점을 KISA 이름으로 적는다. 없으면 "해당 없음".
찾는 곳: SW개발보안_obsidian/Security/INDEX.md → "다시잇다 기능별 탐색"
LLM 관련은 .claude/skills/kisa-secure-coding-python/references/llm-security.md 의 LLM-xx·AGT-xx
예: SQL 삽입 (INP-01), 부적절한 인가 (SEC-02), 프롬프트 인젝션 (LLM-01)
-->

-

## 어떻게 검증했나

<!-- 추가한 테스트, 직접 시도한 공격 입력, /kisa-review 결과 요약 등 -->

-

## 체크리스트

- [ ] 관련 KISA 보안약점을 위에 적었다 (없으면 "해당 없음")
- [ ] 약점별 공격 시나리오 테스트를 추가했다 (정상 입력 + 공격 입력)
- [ ] `CI 통과` 체크가 초록색이다 (gitleaks · Bandit · pip-audit · CodeQL · 숨은 문자 검사 등)
- [ ] 비밀값·개인정보가 코드·로그·커밋에 없다 (`.env`는 커밋하지 않고 `.env.example`만 갱신)
- [ ] 사용자 입력·외부 공고 원문·LLM 출력을 비신뢰 데이터로 처리했다
- [ ] LLM 프롬프트에서 외부 데이터(사용자 대화·공고 원문·저장된 LLM 출력)를 지시문과 분리했다 (LLM 코드가 없으면 체크)
- [ ] 에이전트 지시 파일(`.claude/`, `CLAUDE.md`, `AGENTS.md` 등)을 바꿨다면 사유를 아래에 적었다
- [ ] `# nosec`이나 `.gitleaks.toml` 예외를 추가했다면 사유를 아래에 적었다

## 리뷰어에게

<!-- 특히 봐줬으면 하는 부분, 판단이 애매했던 부분. 없으면 지워도 된다. -->

<!--
미조치 취약점의 위치·재현 방법은 여기(공개)에 적지 말고 팀 채널로 비공개 공유한다.
docs/security/kisa-review.md "결과 보관" 참고.
-->
