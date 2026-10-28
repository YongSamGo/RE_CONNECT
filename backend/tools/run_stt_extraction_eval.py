"""Run the synthetic STT transcript set through the project's real Ollama extraction path."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import httpx
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.adapters.ollama import OllamaLLMAdapter  # noqa: E402
from app.modules.generation.service import GroundedGenerationService  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    parser.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "qwen3:4b"))
    parser.add_argument("--output", type=Path, default=ROOT / "security-reports/stt_extraction_latest.json")
    parser.add_argument("--concurrency", type=int, default=1, help="Maximum simultaneous extraction requests")
    parser.add_argument("--limit", type=int, help="Run only the first N cases (useful for a short concurrency pilot)")
    args = parser.parse_args()
    if args.concurrency < 1:
        parser.error("--concurrency must be at least 1")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    cases = json.loads((ROOT / "eval/stt_extraction_cases.json").read_text(encoding="utf-8"))["cases"]
    if args.limit is not None:
        cases = cases[:args.limit]
    try:
        with httpx.Client(timeout=5, follow_redirects=False, trust_env=False) as client:
            tags = client.get(args.base_url + "/api/tags").raise_for_status().json()
            model_info = next(item for item in tags["models"] if item["name"] == args.model)
            runtime_version = client.get(args.base_url + "/api/version").raise_for_status().json()["version"]
            model_digest = model_info["digest"]
    except Exception as exc:
        print(f"Ollama 모델 정보를 확인할 수 없습니다 ({type(exc).__name__})", file=sys.stderr)
        return 2
    adapter = OllamaLLMAdapter(
        base_url=args.base_url,
        model=args.model,
        timeout_seconds=60,
        num_predict=2048,
        think=False,
        max_response_bytes=1_048_576,
        num_ctx=16_384,
    )
    service = GroundedGenerationService(adapter)

    async def run() -> tuple[list[dict[str, object]], float]:
        if not await adapter.is_ready():
            raise RuntimeError(f"Ollama에서 모델을 확인할 수 없습니다: {args.base_url} / {args.model}")
        semaphore = asyncio.Semaphore(args.concurrency)
        run_started = time.perf_counter()

        async def run_case(case: dict[str, object]) -> dict[str, object]:
            async with semaphore:
                started = time.perf_counter()
                try:
                    preview = await service.extract_experiences(user_texts=case["transcript"])
                    result = {"experiences": [item.model_dump(mode="json") for item in preview.experiences],
                              "excluded_turn_indices": preview.excluded_turn_indices,
                              "requires_confirmation": preview.requires_confirmation}
                    error = None
                except Exception as exc:  # Preserve a per-case failure without exposing raw model error details.
                    result, error = None, type(exc).__name__
            return {"id": case["id"], "result": result, "error_type": error,
                    "elapsed_seconds": round(time.perf_counter() - started, 3)}

        results = await asyncio.gather(*(run_case(case) for case in cases))
        return results, round(time.perf_counter() - run_started, 3)

    try:
        results, wall_seconds = asyncio.run(run())
    except Exception as exc:
        print(f"실행 실패: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    output = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "model_digest": model_digest,
        "ollama_version": runtime_version,
        "base_url": args.base_url,
        "temperature": 0,
        "think": False,
        "num_ctx": 16_384,
        "concurrency": args.concurrency,
        "wall_seconds": wall_seconds,
        "cases": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report = ["# 로컬 Qwen3 STT 대본 경험 추출 비교", "",
              f"- 모델: `{args.model}` (`{model_digest}`)", f"- Ollama: `{runtime_version}`",
              f"- 실행 시각(UTC): `{output['generated_at']}`",
              f"- 조건: temperature=0, think=false, num_ctx=16384, 동시 요청={args.concurrency}",
              f"- 총 경과 시간: {wall_seconds}초",
              f"- 평균 요청 처리 시간(대기 제외): {round(sum(item['elapsed_seconds'] for item in results) / len(results), 3)}초", "",
              "각 대본과 결과를 읽고 `review_focus`를 참고해 직접 판정하세요. 이 문서는 자동 정답 판정이 아닙니다.", ""]
    by_id = {item["id"]: item for item in results}
    for case in cases:
        item = by_id[case["id"]]
        report.extend([f"## {case['id']} · {case['persona']}", "",
                       f"잡음 요소: {', '.join(case['noise'])}", "", "### STT 대본", ""])
        report.extend(f"{index}. {turn}" for index, turn in enumerate(case["transcript"], start=1))
        report.extend(["", "### Qwen3 추출 결과", "", "```json",
                       json.dumps(item["result"], ensure_ascii=False, indent=2) if item["result"] else
                       json.dumps({"error_type": item["error_type"]}, ensure_ascii=False, indent=2),
                       "```", "", f"처리 시간: {item['elapsed_seconds']}초", "",
                       f"직접 검토할 점: {case['review_focus']}", ""])
    report_path = args.output.with_suffix(".md")
    report_path.write_text("\n".join(report), encoding="utf-8")
    print(f"{len(results)}개 사례 결과 저장: {args.output}")
    print(f"비교 보고서 저장: {report_path}")
    for item in results:
        count = len((item["result"] or {}).get("experiences", [])) if item["result"] else "실패"
        print(f"{item['id']}: 경험 {count}건" + (f" ({item['error_type']})" if item["error_type"] else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
