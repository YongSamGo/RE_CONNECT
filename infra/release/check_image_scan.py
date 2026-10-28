"""Trivy 이미지 검사 결과의 릴리스 판정 (#93 W12-04). 표준 라이브러리만 쓴다.

    trivy image --format json --output scan.json <이미지>
    python3 -I infra/release/check_image_scan.py --image speech --scan scan.json \
      --accept infra/release/image-scan-accept.json

판정 기준
- CRITICAL은 수정판 유무와 관계없이 실패한다.
- HIGH 중 수정판이 있는 것은 실패한다. 이미지를 다시 빌드하거나 패키지를 올린다.
- HIGH 중 수정판이 없는 것은 수용 목록에 사유·만료일이 있어야 통과한다. 목록 변경은 Code Owner 승인을 받는다.
- 만료된 수용 항목이 하나라도 있으면 실패한다. 만료일은 기록일로부터 90일을 넘길 수 없다.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

MAX_ACCEPT_DAYS = 90
VULNERABILITY_ID = re.compile(r"^(CVE-\d{4}-\d{4,}|GHSA(-[23456789cfghjmpqrvwx]{4}){3})$")
IMAGE = re.compile(r"^(backend|frontend|speech)$")


class ScanError(ValueError):
    pass


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._+:@/-]", "?", text)[:128]


def findings(scan: object) -> Iterable[tuple[str, str, str, bool]]:
    """(취약점 ID, 패키지, 심각도, 수정판 있음)."""
    if not isinstance(scan, Mapping):
        raise ScanError("Trivy 결과 형식 오류")
    results = scan.get("Results") or []
    if not isinstance(results, list):
        raise ScanError("Trivy 결과 형식 오류")
    for result in results:
        if not isinstance(result, Mapping):
            raise ScanError("Trivy 결과 형식 오류")
        for item in result.get("Vulnerabilities") or []:
            if not isinstance(item, Mapping) or not isinstance(item.get("VulnerabilityID"), str):
                raise ScanError("Trivy 취약점 항목 형식 오류")
            fixed = bool(item.get("FixedVersion")) or item.get("Status") == "fixed"
            yield item["VulnerabilityID"], str(item.get("PkgName", "")), str(item.get("Severity", "UNKNOWN")), fixed


def load_accepted(document: object, image: str, today: dt.date) -> tuple[set[str], list[str]]:
    """이 이미지에 유효한 수용 ID와 오류 목록."""
    if not isinstance(document, Mapping) or not isinstance(document.get("accepted"), list):
        raise ScanError("수용 목록 형식 오류")
    accepted: set[str] = set()
    errors: list[str] = []
    for entry in document["accepted"]:
        if not isinstance(entry, Mapping):
            raise ScanError("수용 항목 형식 오류")
        vid, target = entry.get("id"), entry.get("image")
        reason, recorded, expires = entry.get("reason"), entry.get("recorded"), entry.get("expires")
        if not isinstance(vid, str) or not VULNERABILITY_ID.fullmatch(vid) or not isinstance(target, str) or not IMAGE.fullmatch(target):
            raise ScanError("수용 항목의 id·image 형식 오류")
        if not isinstance(reason, str) or len(reason.strip()) < 10:
            raise ScanError(f"{vid}: 수용 사유가 필요합니다")
        try:
            recorded_on = dt.date.fromisoformat(str(recorded))
            expires_on = dt.date.fromisoformat(str(expires))
        except ValueError:
            raise ScanError(f"{vid}: recorded·expires는 YYYY-MM-DD") from None
        if not recorded_on <= expires_on <= recorded_on + dt.timedelta(days=MAX_ACCEPT_DAYS):
            raise ScanError(f"{vid}: 만료일은 기록일부터 {MAX_ACCEPT_DAYS}일 이내")
        if target != image:
            continue
        if expires_on < today:
            errors.append(f"{vid}: 수용 기한 만료({expires_on.isoformat()}), 다시 검토하세요")
            continue
        accepted.add(vid)
    return accepted, errors


def judge(scan: object, accept: object, image: str, today: dt.date) -> tuple[list[str], dict[str, int]]:
    accepted, errors = load_accepted(accept, image, today)
    counts = {"critical": 0, "high_fixable": 0, "high_unfixed_accepted": 0, "high_unfixed_unreviewed": 0, "other": 0}
    for vid, package, severity, fixed in findings(scan):
        # 결과는 GitHub 워크플로 명령(::error::)으로 출력하므로 줄바꿈·제어 문자를 남기지 않는다.
        label = f"{_safe(vid)} ({_safe(package)})"
        if severity == "CRITICAL":
            counts["critical"] += 1
            errors.append(f"CRITICAL {label}")
        elif severity == "HIGH" and fixed:
            counts["high_fixable"] += 1
            errors.append(f"HIGH 수정판 있음 {label}")
        elif severity == "HIGH" and vid in accepted:
            counts["high_unfixed_accepted"] += 1
        elif severity == "HIGH":
            counts["high_unfixed_unreviewed"] += 1
            errors.append(f"HIGH 수정판 없음·미검토 {label}")
        else:
            counts["other"] += 1
    return sorted(set(errors)), counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--image", required=True, choices=["backend", "frontend", "speech"])
    parser.add_argument("--scan", required=True, type=Path)
    parser.add_argument("--accept", required=True, type=Path)
    parser.add_argument("--today", type=dt.date.fromisoformat, default=None, help="시험용 기준일")
    args = parser.parse_args(argv)
    today = args.today or dt.datetime.now(dt.timezone.utc).date()
    try:
        scan = json.loads(args.scan.read_text(encoding="utf-8"))
        accept = json.loads(args.accept.read_text(encoding="utf-8"))
        errors, counts = judge(scan, accept, args.image, today)
    except (ScanError, OSError, ValueError) as error:
        print(error if isinstance(error, ScanError) else "검사 결과를 읽지 못했습니다", file=sys.stderr)
        return 1
    print(f"{args.image}: " + ", ".join(f"{key}={value}" for key, value in counts.items()))
    for error in errors:
        print(f"::error::{args.image}: {error}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
