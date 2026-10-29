"""경험 추출(#30) 실측과 자동 채점 (#34).

실제 백엔드 `OllamaLLMAdapter` → `GroundedGenerationService.extract_experiences`로 페르소나 8명을 돌리고,
모델 원본 선택(턴 번호 포함)과 서버 검사 후 결과를 함께 채점한다. 입력은 모두 가상 인물이다.

저장소 루트에서, Ollama가 떠 있는 장비에서 백엔드 가상환경으로 실행한다.

    backend/.venv/bin/python -I eval/check_extraction.py --repeat 2 --out security-reports/extraction.json
    backend/.venv/bin/python -I eval/check_extraction.py --persona P04 --show   # 한 명의 추출 내용까지 출력
    backend/.venv/bin/python -I eval/check_extraction.py --repeat 2 --prompt-file eval/prompts/extraction-v3.txt  # 후보 비교

채점 항목(사람 검토를 대신하지 않는다. 문구의 의미 일치는 사람이 본다):
- accepted: 서버 근거 검사를 통과해 결과가 남았는지
- over_limit: 서비스 기본 제한시간(60초)을 넘었는지. 측정을 위해 Adapter 제한은 --timeout으로 늘린다
- turn_recall: 경험 턴(extraction_cases.json) 중 경험 설명으로 뽑힌 비율
- non_experience: 경험이 아닌 턴에서 뽑은 경험 수 (0이어야 함)
- skill_recall: 기대 프로필의 기술 태그가 결과의 기술·설명 구절과 겹치는 비율
- duration_recall: 기대 기간(햇수)이 결과의 기간 구절과 같은 비율
- whole_turn: 턴 문장 전체를 설명으로 인용한 수
- cert_as_skill: 자격증 구절을 기술로 인용한 수
- dropped: 모델이 낸 기간·기술 인용 중 서버가 버린 수(다른 턴·원문에 없음). 인용 단위로 버리는 #273 이후에만 의미가
  있다. 그 전 서비스는 인용 하나가 어긋나면 결과 전체를 거절해 accepted=False가 된다
- pairing_mismatch: 서버가 경험 하나를 통째로 빼서 모델 선택과 짝지을 수 없던 행. 턴 기반 지표는 0으로 둔다
- leaks: must_not_extract.exact 값이 결과에 나온 수 (0이어야 함)
"""

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERVICE_TIMEOUT = 60.0  # backend/app/core/config.py ollama_timeout_seconds 기본값
CASES = json.loads((ROOT / "eval/extraction_cases.json").read_text(encoding="utf-8"))["cases"]

_DIGITS = {"일": 1, "이": 2, "삼": 3, "사": 4, "오": 5, "육": 6, "칠": 7, "팔": 8, "구": 9}


def korean_number(text: str) -> int | None:
    """'이십오 년'·'25년'·'한 삼십 년' 같은 햇수 표현의 첫 숫자. 99까지만 다룬다. 개월은 햇수가 아니라 읽지 않는다."""
    match = re.search(r"(\d+)\s*(?=년|해)", text)
    if match:
        return int(match.group(1))
    # "오래"·"일했어요"를 숫자로 읽지 않도록 단어 시작이고 뒤에 단위가 올 때만 읽는다.
    match = re.search(r"(?<![가-힣])([일이삼사오육칠팔구]?십[일이삼사오육칠팔구]?|[일이삼사오육칠팔구])\s*(?=년|해)", text)
    if not match:
        return None
    word = match.group(1)
    if "십" not in word:
        return _DIGITS[word]
    tens, _, ones = word.partition("십")
    return (_DIGITS[tens] if tens else 1) * 10 + (_DIGITS[ones] if ones else 0)


def squash(text: str) -> str:
    return re.sub(r"[\s.,·()]", "", text)


def overlaps(expected: str, found: list[str]) -> bool:
    """기대 태그가 결과 구절 안에 있거나, 세 글자 이상인 결과 구절이 기대 태그 안에 있으면 일치로 본다.

    "관리"처럼 짧은 일반어가 긴 기대 태그("회계 장부 관리")에 들어 있다는 이유만으로 맞히지 않게 한다.
    """
    target = squash(expected)
    return bool(target) and any(target in squash(item) or (len(squash(item)) >= 3 and squash(item) in target)
                                for item in found)


def score(persona: dict, case: dict, plan, preview) -> dict:
    """plan: 모델 원본 ExtractionPlan(없으면 None). preview: 서버 검사 후 ExperiencePreview(실패면 None)."""
    turns = persona["interview"]
    expected = persona["expected_profile"]["experiences"]
    result = {"accepted": preview is not None, "experiences": 0, "expected": len(expected), "turn_recall": 0.0,
              "non_experience": 0, "skill_recall": 0.0, "duration_recall": 0.0, "whole_turn": 0,
              "cert_as_skill": 0, "dropped": 0, "leaks": 0, "pairing_mismatch": False}
    if plan is None or preview is None:
        return result
    # 서버는 경험을 통째로 버리지 않으면 순서를 유지한다. 원본 선택과 결과를 짝지어 턴 번호를 얻는다.
    # 서버가 경험 하나를 통째로 뺐다면(예: 소유하지 않은 기존 ID) 짝이 맞지 않으므로 그 행만 표시하고 넘어간다.
    if len(plan.experiences) != len(preview.experiences):
        texts = [text for item in preview.experiences for text in (item.description, item.duration_note or "", *item.skill_tags)]
        result.update(experiences=len(preview.experiences), pairing_mismatch=True,
                      leaks=sum(value in text for value in persona["must_not_extract"]["exact"] for text in texts))
        return result
    pairs = list(zip(plan.experiences, preview.experiences, strict=True))
    used_turns = {selected.description.turn_index for selected, _ in pairs}
    experience_turns = set(case["experience_turns"])
    skills = [skill for _, item in pairs for skill in item.skill_tags]
    phrases = skills + [item.description for _, item in pairs]
    durations = [korean_number(item.duration_note) for _, item in pairs if item.duration_note]
    expected_skills = [tag for item in expected for tag in item["skill_tags"]]
    expected_years = [korean_number(item["duration_note"]) for item in expected if item.get("duration_note")]
    texts = phrases + [item.duration_note or "" for _, item in pairs]
    result.update(
        experiences=len(pairs),
        turn_recall=round(len(used_turns & experience_turns) / len(experience_turns), 2),
        non_experience=sum(selected.description.turn_index not in experience_turns for selected, _ in pairs),
        skill_recall=round(sum(overlaps(tag, phrases) for tag in expected_skills) / len(expected_skills), 2) if expected_skills else 1.0,
        duration_recall=round(sum(year in durations for year in expected_years) / len(expected_years), 2) if expected_years else 1.0,
        whole_turn=sum(squash(item.description) == squash(turns[selected.description.turn_index]) for selected, item in pairs),
        cert_as_skill=sum(any(squash(cert) in squash(skill) for cert in case["certifications"]) for skill in skills),
        dropped=sum(len(selected.skills) + (selected.duration is not None) for selected, _ in pairs)
        - sum(len(item.skill_tags) + (item.duration_note is not None) for _, item in pairs),
        leaks=sum(value in text for value in persona["must_not_extract"]["exact"] for text in texts),
    )
    return result


class Recording:
    """Adapter를 감싸 모델 원본 선택을 남긴다. 결과·요청은 바꾸지 않는다."""

    def __init__(self, adapter):
        self.adapter, self.plan = adapter, None

    async def generate_structured(self, **kwargs):
        self.plan = None
        self.plan = await self.adapter.generate_structured(**kwargs)
        return self.plan


async def run(args) -> list[dict]:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.adapters.ollama import OllamaLLMAdapter
    from app.modules.generation import prompts
    from app.modules.generation.service import GroundedGenerationService

    prompt_version = prompts.PROMPT_VERSION
    if args.prompt_file:
        # 후보 비교용. 서비스는 호출 때 prompts.EXTRACTION을 읽으므로 이 실행 안에서만 바뀐다.
        prompts.EXTRACTION = args.prompt_file.read_text(encoding="utf-8").strip()
        prompt_version = args.prompt_file.stem

    recording = Recording(OllamaLLMAdapter(base_url=args.base_url, model=args.model, timeout_seconds=args.timeout,
                                           num_predict=2048, num_ctx=16384, think=False, max_response_bytes=1_048_576))
    service = GroundedGenerationService(recording)
    rows = []
    for attempt in range(1, args.repeat + 1):
        for persona_id in args.persona or sorted(CASES):
            persona = json.loads((ROOT / f"eval/personas/{persona_id}.json").read_text(encoding="utf-8"))
            started = time.monotonic()
            try:
                preview, error = await service.extract_experiences(user_texts=persona["interview"]), None
            except Exception as exc:  # 측정 도구: 예외 종류만 남기고 원문은 출력하지 않는다
                preview, error = None, type(exc).__name__
            latency = round(time.monotonic() - started, 2)
            row = {"persona": persona_id, "attempt": attempt, "prompt": prompt_version, "latency_s": latency,
                   "over_limit": latency > SERVICE_TIMEOUT, "error": error,
                   **score(persona, CASES[persona_id], recording.plan, preview)}
            if args.show and preview is not None:
                row["found"] = [[item.description, item.duration_note, item.skill_tags] for item in preview.experiences]
            rows.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            save(args.out, rows)
    return rows


def summary(rows: list[dict]) -> dict:
    count = len(rows)
    total = lambda key: sum(row.get(key, 0) for row in rows)
    return {"runs": count, "accepted": total("accepted"), "over_limit": total("over_limit"),
            "latency_max_s": max((row.get("latency_s", 0) for row in rows), default=0),
            **{key: round(total(key) / count, 2) for key in ("turn_recall", "skill_recall", "duration_recall")},
            **{key: total(key) for key in ("non_experience", "whole_turn", "cert_as_skill", "dropped", "leaks", "pairing_mismatch")}}


def save(path: Path | None, rows: list[dict]) -> None:
    """행마다 다시 써서, 중간에 멈춰도 그때까지 잰 결과가 남게 한다."""
    if path is not None and rows:
        path.write_text(json.dumps({"summary": summary(rows), "rows": rows}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def positive(value: str) -> int:
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("1 이상이어야 합니다")
    return number


def main() -> int:
    parser = argparse.ArgumentParser(description="경험 추출 실측·자동 채점")
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", default="qwen3:4b")
    parser.add_argument("--timeout", type=float, default=600.0, help="측정용 Adapter 제한(초). 서비스 제한 초과 여부는 따로 표시")
    parser.add_argument("--repeat", type=positive, default=1)
    parser.add_argument("--persona", action="append", choices=sorted(CASES))
    parser.add_argument("--show", action="store_true", help="추출 내용까지 출력(가상 인물만)")
    parser.add_argument("--prompt-file", type=Path, help="경험 추출 지시문 후보(eval/prompts/). 없으면 서비스의 현재 지시문")
    parser.add_argument("--out", type=Path, help="결과 JSON 저장 경로(security-reports/ 아래 권장)")
    args = parser.parse_args()
    rows = asyncio.run(run(args))
    print("SUMMARY " + json.dumps(summary(rows), ensure_ascii=False))
    # 근거 검사 실패·개인정보 누출·경험 아닌 턴 추출은 실패로 본다.
    return 0 if all(row["accepted"] and not row["leaks"] and not row["non_experience"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
