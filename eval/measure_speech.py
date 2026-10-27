"""내부 음성 서비스의 TTS·STT 지연 측정 (#34). 입력은 가상 문장만 쓴다.

음성 서비스(`speech:8001`)와 같은 내부 네트워크의 컨테이너 안에서 실행한다. 음성 이미지에 Python·numpy가
있으므로 그 이미지를 진입점만 바꿔 쓴다. 절차는 docs/ai/runtime-measurement.md를 따른다.

    docker run --rm --network reconnect-speech-cpu_speech --read-only --tmpfs /tmp:size=64m \\
      --entrypoint /opt/venv/bin/python -v "$PWD/eval:/eval:ro" reconnect-speech-cpu:local \\
      -I /eval/measure_speech.py --source /eval/personas

1. 문장을 하나씩 TTS로 합성해 지연·음성 길이를 잰다(서비스 제한 55초).
2. 합성 음성을 이어 붙여 약 15·30·60·89초 WAV를 만들고 STT 지연과 문자 오류율(CER)을 잰다.
   합성 음성 기준이라 실제 사람 녹음(#10)보다 오류율이 낮게 나온다.

TTS가 시간 초과되면 음성 런타임은 설계상 스스로 재시작하지 않는다(speech/PROCESS_RUNTIME.md). 그 뒤 요청은
모두 실패하므로 첫 실패에서 합성을 멈추고 이미 모은 음성으로 STT만 잰다. 다시 재려면 컨테이너를 재시작한다.
"""

import argparse
import io
import json
import re
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy as np

BASE = "http://speech:8001"  # backend InternalSpeechAdapter와 같은 고정 주소
RATE = 16000
SERVICE_LIMIT = 55.0  # speech/app/service.py 요청 마감
STT_TARGETS = (15, 30, 60, 89)
GAP = np.zeros(int(0.4 * RATE), np.float32)


def sentences(source: Path) -> list[str]:
    """speech_cases.json(제외 표시가 아닌 문장) 또는 personas 폴더(interview 전체)."""
    if source.is_dir():
        return [turn for path in sorted(source.glob("P0*.json"))
                for turn in json.loads(path.read_text(encoding="utf-8"))["interview"]]
    cases = json.loads(source.read_text(encoding="utf-8"))["cases"]
    return [case["text"] for case in cases if case.get("filter") != "exclude"]


def call(path: str, body: bytes, content_type: str, timeout: float = 120) -> tuple[int, bytes, float]:
    request = urllib.request.Request(BASE + path, data=body, method="POST",
                                     headers={"Content-Type": content_type, "X-Speech-Request-ID": str(uuid.uuid4())})
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # nosec B310 - 고정 내부 주소
            return response.status, response.read(), time.monotonic() - started
    except urllib.error.HTTPError as error:
        return error.code, error.read(), time.monotonic() - started


def wait_ready(attempts: int = 120) -> None:
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(BASE + "/health/ready", timeout=3) as response:  # nosec B310
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(2)
    raise SystemExit("음성 서비스가 준비되지 않았습니다")


def pcm16k(wav_bytes: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(wav_bytes)) as recording:
        rate = recording.getframerate()
        samples = np.frombuffer(recording.readframes(recording.getnframes()), "<i2").astype(np.float32)
    if rate != RATE:
        count = int(len(samples) * RATE / rate)
        samples = np.interp(np.linspace(0, len(samples) - 1, count), np.arange(len(samples)), samples)
    return samples


def to_wav(samples: np.ndarray) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(RATE)
        recording.writeframes(np.clip(samples, -32768, 32767).astype("<i2").tobytes())
    return buffer.getvalue()


def cer(reference: str, hypothesis: str) -> float:
    """공백·문장부호를 뺀 문자 오류율. 숫자 표기 차이(삼십 ↔ 30)는 오류로 센다."""
    ref, hyp = (re.sub(r"[^가-힣a-z0-9]", "", text.lower()) for text in (reference, hypothesis))
    row = list(range(len(hyp) + 1))
    for i, a in enumerate(ref, 1):
        previous, row[0] = row[0], i
        for j, b in enumerate(hyp, 1):
            previous, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, previous + (a != b))
    return row[len(hyp)] / max(len(ref), 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="음성 서비스 TTS·STT 지연 측정")
    parser.add_argument("--source", type=Path, required=True, help="speech_cases.json 또는 personas 폴더")
    parser.add_argument("--seconds", type=float, default=92, help="STT용으로 모을 합성 음성 길이")
    parser.add_argument("--long-text", action="store_true", help="문장 6개를 이은 긴 TTS 1건도 잰다(시간 초과 시 이후 측정 불가)")
    args = parser.parse_args()
    texts = sentences(args.source)
    wait_ready()
    tts, stt, clips = [], [], []
    if args.long_text:
        long_text = " ".join(texts[:6])
        status, _, seconds = call("/internal/speech", json.dumps({"text": long_text}).encode(), "application/json")
        tts.append({"chars": len(long_text), "status": status, "latency_s": round(seconds, 2), "audio_s": None, "long": True})
        print(json.dumps(tts[-1], ensure_ascii=False), flush=True)
    for text in texts if not tts or tts[-1]["status"] == 200 else []:
        status, body, seconds = call("/internal/speech", json.dumps({"text": text}).encode(), "application/json")
        audio = pcm16k(body) if status == 200 else None
        tts.append({"chars": len(text), "status": status, "latency_s": round(seconds, 2),
                    "audio_s": round(len(audio) / RATE, 2) if audio is not None else None})
        print(json.dumps(tts[-1], ensure_ascii=False), flush=True)
        if audio is None:
            break
        clips.append((text, audio))
        if sum(len(clip) + len(GAP) for _, clip in clips) / RATE >= args.seconds:
            break
    for target in STT_TARGETS:
        parts, reference = [], []
        for text, clip in clips:
            if (sum(map(len, parts)) + len(clip)) / RATE > target:
                break
            parts += [clip, GAP]
            reference.append(text)
        if not parts:
            continue
        audio = np.concatenate(parts)
        status, body, seconds = call("/internal/transcriptions", to_wav(audio), "audio/wav")
        row = {"target_s": target, "audio_s": round(len(audio) / RATE, 2), "status": status, "latency_s": round(seconds, 2)}
        if status == 200:
            row["cer"] = round(cer(" ".join(reference), json.loads(body)["text"]), 3)
        stt.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    ok = [row for row in tts if row["status"] == 200]
    result = {"tts_ok": len(ok), "tts_failed": len(tts) - len(ok),
              "tts_latency_max_s": max((row["latency_s"] for row in ok), default=None),
              "tts_over_limit": sum(row["latency_s"] > SERVICE_LIMIT or row["status"] != 200 for row in tts),
              "stt": stt}
    print("SUMMARY " + json.dumps(result, ensure_ascii=False))
    return 0 if tts and not result["tts_failed"] and all(row["status"] == 200 for row in stt) else 1


if __name__ == "__main__":
    raise SystemExit(main())
