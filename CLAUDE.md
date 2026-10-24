# CLAUDE.md — 다시잇다(RE_CONNECT)

팀 공통 지침은 AGENTS.md에 있고 Codex와 함께 쓴다. 공통 규칙은 그 파일에서 고치고, 여기에는 Claude Code 전용 내용만 둔다.

@AGENTS.md

## Claude Code 전용

- 보안 점검은 `/kisa-review` 명령으로 한다. 대상 지정과 옵션(`--code-only`, `--supply-chain`, `--llm-only`, `PR <번호>`, `--comment`)은 [docs/security/kisa-review.md](docs/security/kisa-review.md#사용)를 따른다.
- 명령 없이 "KISA 기준으로 보안 점검해줘"라고 하면 `kisa-secure-coding-python` 스킬(`.claude/skills/`)이 쓰인다.
- 개인 지시는 `~/.claude/CLAUDE.md`나 `CLAUDE.local.md`(커밋하지 않음)에, 개인 권한 설정은 `.claude/settings.local.json`(커밋하지 않음)에 둔다.
