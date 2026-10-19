"""고정한 공개 모델의 허용 파일만 준비한다. 다운로드한 코드는 실행하지 않는다."""

import argparse
import hashlib
from http.client import HTTPException
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

BASE = Path(__file__).resolve().parent
PINS = {
    'stt': ('Systran/faster-whisper-small', '536b0662742c02347bc0e980a01041f333bce120', {
        'config.json', 'model.bin', 'tokenizer.json', 'vocabulary.txt'}),
    'tts': ('Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice', '85e237c12c027371202489a0ec509ded67b5e4b5', {
        'config.json', 'generation_config.json', 'merges.txt', 'model.safetensors', 'preprocessor_config.json',
        'tokenizer_config.json', 'vocab.json', 'speech_tokenizer/config.json', 'speech_tokenizer/configuration.json',
        'speech_tokenizer/model.safetensors', 'speech_tokenizer/preprocessor_config.json'}),
}
HOSTS = frozenset({'huggingface.co', 'us.aws.cdn.hf.co', 'cdn-lfs.huggingface.co',
                  'cdn-lfs-us-1.hf.co', 'cas-bridge.xethub.hf.co'})


class PreparationError(Exception):
    """서명 URL이나 외부 예외 본문을 포함하지 않는 고정 오류."""


def check_url(url):
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname not in HOSTS or parsed.port not in (None, 443)
            or parsed.username is not None or parsed.password is not None or parsed.fragment):
            raise ValueError
    except (TypeError, ValueError, AttributeError):
        raise PreparationError('허용한 HTTPS 모델 배포 주소가 아닙니다') from None


class ModelRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        check_url(newurl)
        return super().redirect_request(request, fp, code, message, headers, newurl)


def open_model(url):
    check_url(url)
    # 준비 중에도 로컬 proxy 환경변수·쿠키·사용자 토큰을 전달하지 않는다.
    opener = build_opener(ProxyHandler({}), ModelRedirects())
    return opener.open(Request(url, headers={'Accept-Encoding': 'identity'}), timeout=60)


def load_manifest(path=BASE / 'model-manifest.json'):
    try:
        data = json.loads(path.read_text(encoding='utf-8'))
        if set(data) != {'version', 'models'} or type(data['version']) is not int or data['version'] != 1 or set(data['models']) != set(PINS):
            raise ValueError
        for name, (repository, revision, allowed) in PINS.items():
            model = data['models'][name]
            if set(model) != {'repository', 'revision', 'files'} or model['repository'] != repository or model['revision'] != revision:
                raise ValueError
            if type(model['files']) is not list or len(model['files']) != len(allowed):
                raise ValueError
            seen = set()
            for item in model['files']:
                if set(item) != {'path', 'size', 'sha256'} or item['path'] not in allowed or item['path'] in seen:
                    raise ValueError
                if (type(item['size']) is not int or not 0 < item['size'] <= 3 * 1024**3
                    or not isinstance(item['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', item['sha256'])):
                    raise ValueError
                seen.add(item['path'])
            if seen != allowed:
                raise ValueError
        if sum(file['size'] for model in data['models'].values() for file in model['files']) > 4 * 1024**3:
            raise ValueError
        return data['models']
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise PreparationError('고정 모델 명세 형식을 확인해 주세요') from None


def checked_path(root, relative):
    # 고정 명세에도 경로 탈출을 허용하지 않는다. 기존 링크/Windows junction도 따라가지 않는다.
    parts = PurePosixPath(relative).parts
    if not parts or any(part in ('.', '..') or not re.fullmatch('[A-Za-z0-9_.-]+', part) for part in parts):
        raise PreparationError('모델 파일 경로를 확인해 주세요')
    current = root
    for part in ('', *parts):
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise PreparationError('모델 저장 경로에 링크를 사용할 수 없습니다')
    target = root.joinpath(*parts)
    if not target.resolve().is_relative_to(root.resolve()):
        raise PreparationError('모델 저장 경로를 벗어났습니다')
    return target


def verify_file(path, item):
    if not path.is_file() or path.stat().st_size != item['size']:
        raise PreparationError('모델 파일 크기가 고정 명세와 다릅니다')
    digest = hashlib.sha256()
    with path.open('rb') as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != item['sha256']:
        raise PreparationError('모델 파일 해시가 고정 명세와 다릅니다')


def download_file(path, item, url, *, open_response=open_model):
    # 손상된 기존 파일도 자동 덮어쓰지 않는다. 이미 정상인 파일만 재사용한다.
    if path.exists():
        verify_file(path, item)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with open_response(url) as response:
            check_url(response.url)
            if response.status != 200 or response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise PreparationError('압축되거나 정상 상태가 아닌 모델 응답입니다')
            length = response.headers.get('Content-Length')
            if length is not None and length != str(item['size']):
                raise PreparationError('모델 응답 크기가 고정 명세와 다릅니다')
            digest, size = hashlib.sha256(), 0
            with tempfile.NamedTemporaryFile(dir=path.parent, prefix='.prepare-', suffix='.partial', delete=False) as output:
                temporary = Path(output.name)
                while chunk := response.read(min(1024 * 1024, item['size'] - size + 1)):
                    size += len(chunk)
                    if size > item['size']:
                        raise PreparationError('모델 응답이 고정 크기를 초과했습니다')
                    digest.update(chunk)
                    output.write(chunk)
                if size != item['size'] or digest.hexdigest() != item['sha256']:
                    raise PreparationError('받은 모델 파일의 크기 또는 해시가 다릅니다')
                output.flush()
                os.fsync(output.fileno())
        if path.exists():
            raise PreparationError('준비 중 같은 모델 경로가 생성됐습니다')
        temporary.replace(path)
        temporary = None
    except (HTTPError, URLError, HTTPException, TimeoutError, OSError):
        raise PreparationError('모델 파일을 준비하지 못했습니다. 연결과 로컬 경로를 확인해 주세요') from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare(models, names, *, verify_only=False, root=BASE / 'models', open_response=open_model):
    # root 인자는 시험에서만 바꾼다. CLI는 저장소 speech/models/만 사용한다.
    if root.is_symlink() or root.is_junction():
        raise PreparationError('모델 저장 경로에 링크를 사용할 수 없습니다')
    lock = None
    if not verify_only:
        root.mkdir(parents=True, exist_ok=True)
        try:
            lock = root / '.prepare.lock'
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise PreparationError('다른 모델 준비 작업 또는 남아 있는 잠금이 있습니다') from None
        os.close(descriptor)
    try:
        for name in names:
            model = models[name]
            directory = checked_path(root, f"{name}/{model['revision']}")
            if directory.exists():
                expected = {item['path'] for item in model['files']}
                for existing in directory.rglob('*'):
                    relative = existing.relative_to(directory).as_posix()
                    checked_path(directory, relative)
                    if existing.is_file() and relative not in expected:
                        raise PreparationError('모델 폴더에 허용하지 않은 파일이 있습니다')
            for item in model['files']:
                target = checked_path(root, f"{name}/{model['revision']}/{item['path']}")
                if verify_only:
                    verify_file(target, item)
                else:
                    url = f"https://huggingface.co/{model['repository']}/resolve/{model['revision']}/{item['path']}"
                    download_file(target, item, url, open_response=open_response)
                print(f"{name}: verified {item['path']} ({item['size']} bytes)", flush=True)
    finally:
        if lock is not None:
            lock.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description='고정 STT/TTS 파일 준비·SHA-256 검증 (코드/모델 실행 없음)')
    parser.add_argument('--model', choices=['stt', 'tts', 'all'], default='all')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    try:
        models = load_manifest()
        prepare(models, list(PINS) if args.model == 'all' else [args.model], verify_only=args.verify_only)
    except (PreparationError, OSError) as error:
        # 외부 예외/서명 URL은 출력하지 않는다. 파일시스템 오류도 고정 문구로 바꾼다.
        print(str(error) if isinstance(error, PreparationError) else '모델 저장 경로에 접근하지 못했습니다')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
