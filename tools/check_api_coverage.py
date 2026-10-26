"""Compare mounted FastAPI operations with docs/api/openapi.yaml paths.

The parser intentionally reads only the indentation-based top-level ``paths``
mapping and its operation keys. It uses the standard library, so this check
does not add a YAML dependency to the backend.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable
from pathlib import Path


METHODS = {"get", "post", "patch", "delete"}
BASE_PATH = "/api/v1"
PATH_RE = re.compile(r"^  (/[^:\n]+):\s*(?:#.*)?$")
OPERATION_RE = re.compile(r"^    (get|post|patch|delete):\s*(?:#.*)?$", re.IGNORECASE)


def canonical_operations(text: str, base_path: str = BASE_PATH) -> set[tuple[str, str]]:
    """Read path/method pairs from only the top-level OpenAPI ``paths`` map."""
    result: set[tuple[str, str]] = set()
    in_paths = False
    current_path: str | None = None
    for line in text.splitlines():
        if not in_paths:
            in_paths = line == "paths:"
            continue
        if line and not line.startswith(" ") and not line.startswith("#"):
            break
        path_match = PATH_RE.match(line)
        if path_match:
            current_path = path_match.group(1)
            continue
        operation_match = OPERATION_RE.match(line)
        if current_path is not None and operation_match:
            path = current_path if current_path.startswith("/health/") else base_path + current_path
            result.add((path, operation_match.group(1).upper()))
    return result


def actual_operations(routes: Iterable[object]) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Return mounted HTTP operations and those excluded from generated schemas."""
    actual: set[tuple[str, str]] = set()
    hidden: set[tuple[str, str]] = set()
    for route in routes:
        contexts = getattr(route, "effective_route_contexts", None)
        if callable(contexts):
            candidates = (
                (context.path, getattr(context, "methods", None), context.include_in_schema)
                for context in contexts()
            )
        else:
            candidates = ((getattr(route, "path", ""), getattr(route, "methods", None),
                           getattr(route, "include_in_schema", True)),)
        for path, methods, include_in_schema in candidates:
            if not methods:
                continue
            target = actual if include_in_schema else hidden
            target.update((path, method.upper()) for method in methods if method.lower() in METHODS)
    return actual, hidden


def compare_operations(
    canonical: set[tuple[str, str]], actual: set[tuple[str, str]],
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    """Return expected contract operations without routes and routes outside contract."""
    return sorted(canonical - actual), sorted(actual - canonical)


def failure_status(strict: bool, missing: list[tuple[str, str]]) -> int:
    return 1 if strict and missing else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="fail if any canonical operation is unimplemented")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    contract_path = root / "docs/api/openapi.yaml"
    try:
        canonical = canonical_operations(contract_path.read_text(encoding="utf-8"))
        if not canonical:
            raise ValueError("paths 작업이 비어 있음")
        sys.path.insert(0, str(root / "backend"))
        from app.main import create_app

        app = create_app()
        actual, hidden = actual_operations(app.routes)
    except Exception as exc:
        print(f"API 계약 비교 준비 실패 ({type(exc).__name__})", file=sys.stderr)
        return 2

    missing, extra = compare_operations(canonical, actual)
    print(f"계약 작업: {len(canonical)}")
    print(f"실제 라우트 작업: {len(actual)}")
    print(f"스키마 제외 라우트: {len(hidden)}")
    for method, path in missing:
        label = "미구현 admin" if path.startswith(BASE_PATH + "/admin/") else "미구현 계약"
        print(f"{label}: {method} {path}")
    for method, path in extra:
        print(f"계약 외 실제 라우트: {method} {path}")
    for method, path in sorted(hidden):
        print(f"스키마 제외 분류: {method} {path}")
    if failure_status(args.strict, missing):
        return failure_status(args.strict, missing)
    if not args.strict:
        print("보고 전용 실행입니다. 필수 계약 누락은 --strict에서 실패합니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
