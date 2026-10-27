"""고정 Qwen3 모델 준비 전용 CLI. 서버·추론·ollama pull을 실행하지 않는다."""

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import time
import urllib.parse
import urllib.request


MANIFEST_SHA256 = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
MANIFEST_FILE = Path(__file__).with_name("ollama-manifest.json")
MANIFEST_PATH = Path("manifests/registry.ollama.ai/library/qwen3/4b")
REGISTRY = "https://registry.ollama.ai/v2/library/qwen3/blobs/"
# 공식 registry의 307 목적지(2026-10-20 확인). 다른 CDN은 검토 후 명시적으로 추가한다.
DOWNLOAD_HOSTS = frozenset({
    "registry.ollama.ai",
    "dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com",
})
CHUNK_SIZE = 1024 * 1024


class PreparationError(Exception):
    """원문·응답·서명 URL을 포함하지 않는 준비 오류."""


def validate_url(url: str) -> None:
    parts = urllib.parse.urlsplit(url)
    if (parts.scheme != "https" or parts.hostname not in DOWNLOAD_HOSTS
            or parts.username is not None or parts.password is not None
            or parts.port not in (None, 443) or parts.fragment or "\\" in url):
        raise PreparationError("허용하지 않은 다운로드 목적지")


class RegistryRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def open_blob(url: str):
    validate_url(url)
    # 프록시·사용자 인증 설정을 추론/준비 경로에 상속하지 않는다.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RegistryRedirect())
    request = urllib.request.Request(url, headers={"Accept-Encoding": "identity"})
    return opener.open(request, timeout=30)


def pinned_manifest() -> tuple[bytes, list[dict]]:
    raw = MANIFEST_FILE.read_bytes()
    if len(raw) != 859 or hashlib.sha256(raw).hexdigest() != MANIFEST_SHA256:
        raise PreparationError("고정 매니페스트 검증 실패")
    data = json.loads(raw)
    return raw, [data["config"], *data["layers"]]


def plain_path(path: Path) -> None:
    """개인 전용 준비 폴더에서 링크·junction을 통한 저장 위치 변경을 거절한다."""
    for part in (path, *path.parents):
        if part.is_symlink() or part.is_junction():
            raise PreparationError("링크 경로는 사용할 수 없음")


def ensure_directory(path: Path) -> None:
    plain_path(path)
    path.mkdir(parents=True, exist_ok=True)
    plain_path(path)
    if not path.is_dir():
        raise PreparationError("준비 폴더가 아님")


def verify_file(path: Path, size: int, digest: str) -> None:
    plain_path(path)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != size:
        raise PreparationError("파일 종류 또는 크기 불일치")
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        remaining = size
        while remaining:
            chunk = stream.read(min(CHUNK_SIZE, remaining))
            if not chunk:
                raise PreparationError("파일이 잘림")
            remaining -= len(chunk)
            checksum.update(chunk)
        if stream.read(1):
            raise PreparationError("파일 크기 초과")
    if checksum.hexdigest() != digest:
        raise PreparationError("파일 해시 불일치")


def publish(stream, destination: Path, size: int, digest: str) -> None:
    """정확한 크기·해시를 확인한 뒤 게시한다. 기존 파일은 덮어쓰지 않는다."""
    ensure_directory(destination.parent)
    plain_path(destination)
    fd, name = tempfile.mkstemp(prefix=".prepare-", dir=destination.parent)
    temporary = Path(name)
    try:
        checksum = hashlib.sha256()
        count = 0
        deadline = time.monotonic() + 1800
        with os.fdopen(fd, "wb") as output:
            while True:
                if time.monotonic() > deadline:
                    raise PreparationError("다운로드 시간 초과")
                chunk = stream.read(min(CHUNK_SIZE, size - count + 1))
                if not chunk:
                    break
                count += len(chunk)
                if count > size:
                    raise PreparationError("다운로드 크기 초과")
                checksum.update(chunk)
                output.write(chunk)
            if count != size or checksum.hexdigest() != digest:
                raise PreparationError("다운로드 크기 또는 해시 불일치")
            output.flush()
            os.fsync(output.fileno())
        # link는 이미 존재하는 목적지에서 실패하므로 외부 파일을 교체하지 않는다.
        os.link(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def preparation_lock(root: Path):
    lock = root / ".prepare-lock"
    try:
        lock.mkdir()
    except FileExistsError:
        raise PreparationError("준비 작업 잠금이 존재함") from None
    try:
        yield
    finally:
        lock.rmdir()


def prepare(root: Path) -> None:
    raw, entries = pinned_manifest()
    ensure_directory(root)
    with preparation_lock(root):
        manifest = root / MANIFEST_PATH
        if manifest.exists() or manifest.is_symlink():
            verify_file(manifest, len(raw), MANIFEST_SHA256)
        for entry in entries:
            digest = entry["digest"]
            path = root / "blobs" / digest.replace(":", "-")
            if path.exists() or path.is_symlink():
                verify_file(path, entry["size"], digest.removeprefix("sha256:"))
                continue
            with open_blob(REGISTRY + digest) as response:
                if response.status != 200 or response.headers.get("Content-Encoding", "identity") != "identity":
                    raise PreparationError("다운로드 응답 형식 불일치")
                length = response.headers.get("Content-Length")
                if length is not None and length != str(entry["size"]):
                    raise PreparationError("다운로드 길이 불일치")
                publish(response, path, entry["size"], digest.removeprefix("sha256:"))
        # 모델 전체를 확인하기 전에는 Ollama가 볼 매니페스트를 게시하지 않는다.
        if not manifest.exists():
            import io

            publish(io.BytesIO(raw), manifest, len(raw), MANIFEST_SHA256)
    verify(root)


def verify(root: Path) -> None:
    """네트워크·런타임·추론 없이 디스크 파일만 확인한다."""
    raw, entries = pinned_manifest()
    plain_path(root)
    verify_file(root / MANIFEST_PATH, len(raw), MANIFEST_SHA256)
    for entry in entries:
        verify_file(root / "blobs" / entry["digest"].replace(":", "-"),
                    entry["size"], entry["digest"].removeprefix("sha256:"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "verify"))
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[2] / "models/ollama")
    args = parser.parse_args()
    # resolve()로 링크를 숨기지 않는다. 경로는 운영자가 고르고 웹 API로 받지 않는다.
    root = Path(os.path.abspath(args.root))
    try:
        (prepare if args.action == "prepare" else verify)(root)
    except Exception as exc:
        print(f"Ollama 모델 준비 실패 ({type(exc).__name__})")
        return 1
    print("qwen3:4b: 매니페스트 1개·blob 5개 크기/SHA-256 검증 완료 (추론 미실행)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
