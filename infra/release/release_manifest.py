"""릴리스 manifest 생성과 배포용 images.env 변환 (#93 W12-04). 표준 라이브러리만 쓴다.

    # CI: 빌드한 이미지 digest와 저장소 상태로 manifest를 만든다
    python3 -I infra/release/release_manifest.py build --tag v0.1.0 --commit <40자 SHA> \
      --image backend=reconnect-backend@sha256:<64hex> ... \
      --sbom backend=<경로> ... --output release-manifest.json

    # EC2: manifest에서 Compose 치환용 이미지 변수만 뽑는다. 레지스트리 주소는 EC2가 자기 계정에서 만든다
    python3 -I infra/release/release_manifest.py images-env release-manifest.json \
      --registry <계정>.dkr.ecr.<리전>.amazonaws.com --output /run/reconnect/images.env

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
# 3: GPU 음성 이미지(speech-gpu)를 함께 게시한다. 이전 manifest로 GPU 이미지 없이 배포하지 않게 번호를 올렸다.
SCHEMA = 3
IMAGES = ("backend", "frontend", "speech", "speech-gpu")
IMAGE_ENV = {"backend": "BACKEND_IMAGE", "frontend": "FRONTEND_IMAGE", "speech": "SPEECH_IMAGE",
             "speech-gpu": "SPEECH_GPU_IMAGE"}
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


def migration_heads(versions: Path) -> list[str]:
    """실행하지 않고 revision/down_revision만 읽어 head를 계산한다."""
    revisions: set[str] = set()
    parents: set[str] = set()
    for path in sorted(versions.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        revision = _string_assignment(tree, "revision")
        if not isinstance(revision, str):
            raise ManifestError(f"{path.name}: revision 없음")
        revisions.add(revision)
        down = _string_assignment(tree, "down_revision")
        parents.update([down] if isinstance(down, str) else [d for d in (down or ()) if isinstance(d, str)])
    return sorted(revisions - parents)


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
        raise ManifestError(f"{', '.join(IMAGES)} 이미지가 모두 필요합니다")
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
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            manifest = build(ROOT, args.tag, args.commit, parse_pairs(args.image, "--image"), parse_pairs(args.sbom, "--sbom"))
            args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        else:
            text = images_env(json.loads(args.manifest.read_text(encoding="utf-8")), args.registry)
            args.output.write_text(text, encoding="utf-8")
    except (ManifestError, OSError, ValueError, SyntaxError) as error:
        print(error if isinstance(error, ManifestError) else "manifest 처리 실패", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
