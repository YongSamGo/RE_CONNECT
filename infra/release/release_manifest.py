"""릴리스 manifest 생성과 배포용 images.env 변환 (#93 W12-04). 표준 라이브러리만 쓴다.

    # CI: 빌드한 이미지 digest와 저장소 상태로 manifest를 만든다
    python3 -I infra/release/release_manifest.py build --tag v0.1.0 --commit <40자 SHA> \
      --image backend=reconnect-backend@sha256:<64hex> ... \
      --sbom backend=<경로> ... --output release-manifest.json

    # EC2: manifest에서 Compose 치환용 이미지 변수만 뽑는다. 레지스트리 주소는 EC2가 자기 계정에서 만든다
    python3 -I infra/release/release_manifest.py images-env release-manifest.json \
      --registry <계정>.dkr.ecr.<리전>.amazonaws.com --output /run/reconnect/images.env

    # EC2: 지금 운영 중인 릴리스의 태그 체크아웃에서, 이전 릴리스로 이미지만 되돌려도 되는지 판정한다 (#97 W12-08)
    python3 -I infra/release/release_manifest.py rollback-check --current current.json --target target.json

manifest에는 비밀값·개인정보를 넣지 않는다. 라이브러리(잠금 파일)·모델(manifest)·프롬프트·마이그레이션 버전과
이미지 digest를 같은 릴리스로 묶어 기록한다. manifest는 공개 Release에 첨부되므로 AWS 계정 ID가 든
레지스트리 주소를 넣지 않고 저장소 이름과 digest만 기록한다.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# 2: 이미지 참조에서 레지스트리 주소를 뺐다 (공개 Release에 AWS 계정 ID를 남기지 않는다).
SCHEMA = 2
IMAGES = ("backend", "frontend", "speech")
IMAGE_ENV = {"backend": "BACKEND_IMAGE", "frontend": "FRONTEND_IMAGE", "speech": "SPEECH_IMAGE"}
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
# EC2가 붙이는 ECR 주소. 다른 레지스트리나 경로·포트·셸 문자를 받지 않는다.
REGISTRY = re.compile(r"^[0-9]{12}\.dkr\.ecr\.[a-z]{2}(?:-[a-z]+)+-[0-9]\.amazonaws\.com$")


def _check_image(name: str, ref: object) -> None:
    """manifest의 이미지는 reconnect-<이름>@sha256:<64hex> 하나만 받는다. 레지스트리·태그를 거절한다."""
    repository, sep, digest = ref.partition("@") if isinstance(ref, str) else ("", "", "")
    if not sep or repository != f"reconnect-{name}" or not DIGEST.fullmatch(digest):
        raise ManifestError(f"{name}: reconnect-{name}@sha256:<64hex> 형식이 아닙니다")
TAG = re.compile(r"^v[0-9]+\.[0-9]+\.[0-9]+(?:-rc\.[0-9]+)?$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")

LOCKFILES = (
    "backend/requirements.txt",
    "frontend/package-lock.json",
    "speech/requirements.txt",
    "speech/tts_compat/requirements.txt",
    "speech/gpu/requirements.txt",
    "speech/gpu/ct2-requirements.txt",
)
DOCKERFILES = ("backend/Dockerfile", "frontend/Dockerfile", "speech/Dockerfile", "speech/Dockerfile.gpu")
MODEL_MANIFESTS = ("speech/model-manifest.json", "backend/tools/ollama-manifest.json")
COMPOSE_FILES = ("infra/compose.prod.yaml", "infra/compose.models.yaml")


class ManifestError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def base_images(dockerfile: Path) -> list[str]:
    """FROM 줄의 외부 이미지. 모두 digest로 고정돼 있어야 한다."""
    refs = []
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].upper() == "FROM":
            if "@sha256:" not in parts[1]:
                raise ManifestError(f"{dockerfile.name}: digest로 고정하지 않은 베이스 이미지")
            if parts[1] not in refs:
                refs.append(parts[1])
    return refs


def _string_assignment(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    return None


def migration_graph(versions: Path) -> tuple[dict[str, tuple[str, ...]], dict[str, bool]]:
    """실행하지 않고 revision/down_revision/rollback_safe만 읽는다. (revision → 부모들, revision → 이전 앱 호환)

    rollback_safe는 리뷰어가 "이 마이그레이션을 적용한 DB에서 바로 앞 릴리스의 앱이 그대로 동작한다"고
    확인한 경우에만 True로 둔다. 없거나 True가 아닌 값은 호환되지 않는 것으로 본다.
    """
    graph: dict[str, tuple[str, ...]] = {}
    safe: dict[str, bool] = {}
    for path in sorted(versions.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = _string_assignment(tree, "revision")
        if not isinstance(revision, str) or revision in graph:
            raise ManifestError(f"{path.name}: revision 없음 또는 중복")
        down = _string_assignment(tree, "down_revision")
        graph[revision] = (down,) if isinstance(down, str) else tuple(d for d in (down or ()) if isinstance(d, str))
        safe[revision] = _string_assignment(tree, "rollback_safe") is True
    return graph, safe


def migration_heads(versions: Path) -> list[str]:
    graph, _ = migration_graph(versions)
    parents = {parent for parents in graph.values() for parent in parents}
    return sorted(set(graph) - parents)


def _ancestors(graph: dict[str, tuple[str, ...]], heads: list[str]) -> set[str]:
    """head 자신을 포함해 적용된 revision 전체. 그래프에 없는 부모는 거절한다."""
    seen: set[str] = set()
    stack = list(heads)
    while stack:
        revision = stack.pop()
        if revision in seen:
            continue
        if revision not in graph:
            raise ManifestError("대상 릴리스의 마이그레이션을 이 체크아웃에서 찾을 수 없습니다")
        seen.add(revision)
        stack.extend(graph[revision])
    return seen


def _release_summary(manifest: object, label: str) -> dict[str, object]:
    """rollback-check에 쓰는 항목만 형식을 확인해 꺼낸다."""
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA:
        raise ManifestError(f"{label}: manifest 형식 오류")
    tag = manifest.get("tag")
    migrations = manifest.get("migrations")
    heads = migrations.get("heads") if isinstance(migrations, dict) else None
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise ManifestError(f"{label}: 태그 형식 오류")
    if not isinstance(heads, list) or not heads or not all(isinstance(h, str) for h in heads) or len(set(heads)) != len(heads):
        raise ManifestError(f"{label}: migrations.heads 형식 오류")
    images = manifest.get("images")
    if not isinstance(images, dict) or set(images) != set(IMAGES):
        raise ManifestError(f"{label}: manifest 이미지 목록 오류")
    for name in IMAGES:
        _check_image(name, images[name])
    hashed = {}
    for key in ("models", "compose", "prompts"):
        value = manifest.get(key)
        if not isinstance(value, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in value.items()):
            raise ManifestError(f"{label}: {key} 형식 오류")
        hashed[key] = value
    return {"tag": tag, "heads": sorted(heads), **hashed}


def _release_order(tag: str) -> tuple[int, int, int, int, int]:
    """vMAJOR.MINOR.PATCH(-rc.N)의 순서. 같은 버전이면 rc가 정식보다 앞이다."""
    match = re.fullmatch(r"v([0-9]+)\.([0-9]+)\.([0-9]+)(?:-rc\.([0-9]+))?", tag)
    if not match:
        raise ManifestError("태그 형식 오류")
    major, minor, patch, rc = match.groups()
    return (int(major), int(minor), int(patch), 0 if rc is not None else 1, int(rc or 0))


def rollback_check(current: object, target: object, versions: Path) -> dict[str, object]:
    """운영 중인 릴리스(current)에서 이전 릴리스(target)로 이미지만 되돌려도 되는지 판정한다.

    DB는 downgrade하지 않는다. 그래서 target 이후 적용된 마이그레이션이 모두 rollback_safe일 때만
    이미지 되돌리기를 허용하고, 하나라도 아니면 restore_required(스냅샷 복원 + 삭제 재적용)로 판정한다.
    versions는 current 릴리스 태그 체크아웃의 마이그레이션 폴더여야 한다.
    """
    now = _release_summary(current, "current")
    before = _release_summary(target, "target")
    if _release_order(before["tag"]) >= _release_order(now["tag"]):
        raise ManifestError("target이 current보다 이전 릴리스가 아닙니다. 되돌리기가 아닙니다")
    graph, safe = migration_graph(versions)
    if migration_heads(versions) != now["heads"]:
        raise ManifestError("체크아웃의 마이그레이션 head가 current 릴리스와 다릅니다. current 태그에서 실행하세요")
    applied = _ancestors(graph, now["heads"])
    kept = _ancestors(graph, before["heads"])
    if not kept <= applied:
        raise ManifestError("target의 마이그레이션이 current에 포함되지 않습니다. 되돌리기가 아닙니다")
    after_target = sorted(applied - kept)
    unsafe = [revision for revision in after_target if not safe[revision]]
    if not after_target:
        verdict = "images_only"
    elif not unsafe:
        verdict = "schema_compatible"
    else:
        verdict = "restore_required"
    changed = {
        key: sorted(k for k in set(now[key]) | set(before[key]) if now[key].get(k) != before[key].get(k))
        for key in ("models", "compose", "prompts")
    }
    return {
        "verdict": verdict,
        "current": now["tag"],
        "target": before["tag"],
        "migrations_after_target": after_target,
        "not_rollback_safe": unsafe,
        "models_changed": changed["models"],
        "compose_changed": changed["compose"],
        "prompts_changed": changed["prompts"],
    }


def prompt_versions(root: Path) -> dict[str, str]:
    tree = ast.parse((root / "backend/app/modules/generation/prompts.py").read_text(encoding="utf-8"))
    version = _string_assignment(tree, "PROMPT_VERSION")
    if not isinstance(version, str):
        raise ManifestError("PROMPT_VERSION 없음")
    return {"generation": version}


def parse_pairs(pairs: list[str], label: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs:
        name, sep, value = pair.partition("=")
        if not sep or name not in IMAGES or name in result:
            raise ManifestError(f"{label}: 이름은 {', '.join(IMAGES)} 중 하나를 한 번씩")
        result[name] = value
    return result


def build(root: Path, tag: str, commit: str, images: dict[str, str], sboms: dict[str, str]) -> dict[str, object]:
    if not TAG.fullmatch(tag):
        raise ManifestError("태그는 vMAJOR.MINOR.PATCH 형식이어야 합니다")
    if not COMMIT.fullmatch(commit):
        raise ManifestError("커밋은 40자 SHA여야 합니다")
    if set(images) != set(IMAGES):
        raise ManifestError("backend·frontend·speech 이미지가 모두 필요합니다")
    for name, ref in images.items():
        _check_image(name, ref)
    return {
        "schema": SCHEMA,
        "tag": tag,
        "commit": commit,
        "images": dict(sorted(images.items())),
        "base_images": {path: base_images(root / path) for path in DOCKERFILES},
        "lockfiles": {path: sha256_file(root / path) for path in LOCKFILES},
        "models": {path: sha256_file(root / path) for path in MODEL_MANIFESTS},
        "prompts": prompt_versions(root),
        "migrations": {"heads": migration_heads(root / "backend/migrations/versions")},
        "compose": {path: sha256_file(root / path) for path in COMPOSE_FILES},
        "sbom": {name: sha256_file(Path(path)) for name, path in sorted(sboms.items())},
    }


def images_env(manifest: object, registry: str) -> str:
    if not REGISTRY.fullmatch(registry):
        raise ManifestError("--registry는 <12자리 계정>.dkr.ecr.<리전>.amazonaws.com 이어야 합니다")
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or not isinstance(manifest.get("images"), dict):
        raise ManifestError("manifest 형식 오류")
    images = manifest["images"]
    if set(images) != set(IMAGES):
        raise ManifestError("manifest 이미지 목록 오류")
    lines = []
    for name in IMAGES:
        _check_image(name, images[name])
        lines.append(f"{IMAGE_ENV[name]}={registry}/{images[name]}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("build")
    make.add_argument("--tag", required=True)
    make.add_argument("--commit", required=True)
    make.add_argument("--image", action="append", default=[])
    make.add_argument("--sbom", action="append", default=[])
    make.add_argument("--output", required=True, type=Path)
    env = commands.add_parser("images-env")
    env.add_argument("manifest", type=Path)
    env.add_argument("--registry", required=True)
    env.add_argument("--output", required=True, type=Path)
    back = commands.add_parser("rollback-check", help="종료 코드 0: 이미지만 되돌림, 2: 스냅샷 복원 필요, 1: 판정 불가")
    back.add_argument("--current", required=True, type=Path)
    back.add_argument("--target", required=True, type=Path)
    back.add_argument("--versions", type=Path, default=ROOT / "backend/migrations/versions")
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            manifest = build(ROOT, args.tag, args.commit, parse_pairs(args.image, "--image"), parse_pairs(args.sbom, "--sbom"))
            args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        elif args.command == "rollback-check":
            result = rollback_check(
                json.loads(args.current.read_text(encoding="utf-8")),
                json.loads(args.target.read_text(encoding="utf-8")),
                args.versions,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 2 if result["verdict"] == "restore_required" else 0
        else:
            text = images_env(json.loads(args.manifest.read_text(encoding="utf-8")), args.registry)
            args.output.write_text(text, encoding="utf-8")
    except (ManifestError, OSError, ValueError, SyntaxError) as error:
        print(error if isinstance(error, ManifestError) else "manifest 처리 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
