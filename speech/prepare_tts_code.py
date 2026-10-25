"""고정 공개 wheel의 12Hz 코드만 검증·수정한다. 받은 코드를 실행하지 않는다."""

import argparse
import hashlib
from http.client import HTTPException
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener
import zipfile

BASE = Path(__file__).resolve().parent
RECIPE = BASE / 'tts_compat' / 'recipe.json'
BUILD_ID = 'qwen12-tf519-r1'
OUTPUT = BASE / 'runtime_vendor' / BUILD_ID
UPSTREAM_URL = 'https://files.pythonhosted.org/packages/31/01/95f3ae26f5b7eb2105f69ad2c15af5a28b9ebdd1258a0b27541f5ebd6225/qwen_tts-0.1.1-py3-none-any.whl'
UPSTREAM_SHA = '11a290d8dabc7ef91a90c54478c8ab19b3edb1d85c0882313721892bdc4af15d'
UPSTREAM_SIZE = 113529
MEMBERS = frozenset('qwen_tts/' + name for name in (
    '__init__.py', 'core/__init__.py', 'core/models/__init__.py',
    'core/models/configuration_qwen3_tts.py', 'core/models/modeling_qwen3_tts.py',
    'core/models/processing_qwen3_tts.py', 'core/tokenizer_12hz/configuration_qwen3_tts_tokenizer_v2.py',
    'core/tokenizer_12hz/modeling_qwen3_tts_tokenizer_v2.py',
    'inference/qwen3_tts_model.py', 'inference/qwen3_tts_tokenizer.py'))
LICENSE_MEMBER = 'qwen_tts-0.1.1.dist-info/licenses/LICENSE'


class CodePreparationError(Exception):
    """외부 예외·URL·source 본문을 포함하지 않는 오류."""


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_recipe(path=RECIPE):
    try:
        recipe = json.loads(path.read_text(encoding='utf-8'))
        if (type(recipe['version']) is not int or recipe['version'] != 1 or recipe['build_id'] != BUILD_ID or set(recipe['files']) != MEMBERS
            or recipe['upstream'] != {'version': '0.1.1', 'url': UPSTREAM_URL, 'sha256': UPSTREAM_SHA, 'size': UPSTREAM_SIZE}):
            raise ValueError
        for record in recipe['files'].values():
            for key in ('before_sha256', 'after_sha256'):
                if not re.fullmatch('[0-9a-f]{64}', record[key]):
                    raise ValueError
        for key in ('compat_sha256', 'license_sha256', 'notice_sha256'):
            if not re.fullmatch('[0-9a-f]{64}', recipe[key]):
                raise ValueError
        return recipe
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        raise CodePreparationError('고정 TTS 코드 명세를 확인하지 못했습니다') from None


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        raise CodePreparationError('TTS 코드 배포 주소의 우회를 허용하지 않습니다')


def fetch_wheel():
    try:
        opener = build_opener(ProxyHandler({}), NoRedirects())
        with opener.open(Request(UPSTREAM_URL, headers={'Accept-Encoding': 'identity'}), timeout=60) as response:
            if response.status != 200 or response.headers.get('Content-Encoding', 'identity').lower() != 'identity':
                raise CodePreparationError('정상 TTS 코드 응답이 아닙니다')
            data = response.read(UPSTREAM_SIZE + 1)
        validate_wheel(data)
        return data
    except (HTTPError, URLError, HTTPException, TimeoutError, OSError):
        raise CodePreparationError('공식 TTS 코드 파일을 준비하지 못했습니다') from None


def validate_wheel(data):
    if len(data) != UPSTREAM_SIZE or digest(data) != UPSTREAM_SHA:
        raise CodePreparationError('공식 TTS 코드 파일의 크기 또는 해시가 다릅니다')


def apply_edits(data, record):
    if digest(data) != record['before_sha256']:
        raise CodePreparationError('수정 전 TTS 코드가 고정 원본과 다릅니다')
    try:
        lines = data.decode('utf-8').splitlines(keepends=True)
        boundary = len(lines)
        for edit in reversed(record['edits']):
            start, end = edit['start'], edit['end']
            if (type(start) is not int or type(end) is not int or not 0 <= start <= end <= boundary
                or lines[start:end] != edit['before'] or not all(isinstance(line, str) for line in edit['after'])):
                raise ValueError
            lines[start:end] = edit['after']
            boundary = start
        patched = ''.join(lines).encode('utf-8')
        if digest(patched) != record['after_sha256']:
            raise ValueError
        return patched
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise CodePreparationError('TTS 호환 수정이 고정 결과와 다릅니다') from None


def local_additions(recipe):
    try:
        # LF로 정규화해 Windows/Git checkout과 Linux가 같은 코드를 만든다.
        helper = (BASE / 'tts_compat' / 'compat.py').read_text(encoding='utf-8').encode('utf-8')
        license_text = (BASE / 'tts_compat' / 'UPSTREAM_LICENSE').read_bytes()
        notice = (BASE / 'tts_compat' / 'NOTICE').read_text(encoding='utf-8').encode('utf-8')
        if digest(helper) != recipe['compat_sha256'] or digest(license_text) != recipe['license_sha256'] or digest(notice) != recipe['notice_sha256']:
            raise ValueError
        return {'qwen_tts/compat.py': helper, 'LICENSE': license_text, 'NOTICE': notice}
    except (OSError, ValueError, UnicodeError):
        raise CodePreparationError('로컬 호환 코드 또는 라이선스를 확인하지 못했습니다') from None


def assemble(data, recipe):
    validate_wheel(data)
    result = local_additions(recipe)
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = archive.infolist()
            names = [item.filename for item in members]
            if len(names) != len(set(names)) or len(names) > 50 or sum(item.file_size for item in archive.infolist()) > 2 * 1024**2:
                raise ValueError
            for name in [item.orig_filename for item in members]:
                parts = PurePosixPath(name).parts
                if not parts or any(part in ('..', '.') or not re.fullmatch('[A-Za-z0-9_.-]+', part) for part in parts):
                    raise ValueError
            if not MEMBERS.issubset(names) or digest(archive.read(LICENSE_MEMBER)) != recipe['license_sha256']:
                raise ValueError
            for member in sorted(MEMBERS):
                result[member] = apply_edits(archive.read(member), recipe['files'][member])
        return result
    except (zipfile.BadZipFile, ValueError, KeyError, OSError):
        raise CodePreparationError('공식 TTS 코드 묶음을 확인하지 못했습니다') from None


def checked(root, name):
    parts = PurePosixPath(name).parts
    if not parts or any(not re.fullmatch('[A-Za-z0-9_.-]+', part) or part in ('.', '..') for part in parts):
        raise CodePreparationError('TTS 코드 저장 경로가 허용 범위를 벗어났습니다')
    current = root
    for part in ('', *parts):
        current = current / part
        if current.is_symlink() or current.is_junction():
            raise CodePreparationError('TTS 코드 경로에 링크를 사용할 수 없습니다')
    if not current.resolve().is_relative_to(root.resolve()):
        raise CodePreparationError('TTS 코드 저장 경로가 허용 범위를 벗어났습니다')
    return current


def expected_hashes(recipe):
    return {**{name: value['after_sha256'] for name, value in recipe['files'].items()},
        'qwen_tts/compat.py': recipe['compat_sha256'], 'LICENSE': recipe['license_sha256'], 'NOTICE': recipe['notice_sha256']}


def verify(recipe=None, *, root=OUTPUT):
    if root == OUTPUT:
        checked(BASE, OUTPUT.relative_to(BASE).as_posix())
    recipe = read_recipe() if recipe is None else recipe
    expected = expected_hashes(recipe)
    if not root.is_dir() or root.is_symlink() or root.is_junction():
        raise CodePreparationError('준비된 TTS 코드 폴더가 없습니다')
    actual = set()
    try:
        for path in root.rglob('*'):
            name = path.relative_to(root).as_posix()
            checked(root, name)
            if path.is_file():
                actual.add(name)
                if name not in expected or path.stat().st_size > 2 * 1024**2 or digest(path.read_bytes()) != expected[name]:
                    raise CodePreparationError('준비된 TTS 코드에 변경 또는 알 수 없는 파일이 있습니다')
        if actual != set(expected):
            raise CodePreparationError('준비된 TTS 코드 파일이 누락됐습니다')
    except OSError:
        raise CodePreparationError('준비된 TTS 코드 파일에 접근하지 못했습니다') from None


def prepare(data, recipe=None, *, root=OUTPUT):
    if root == OUTPUT:
        checked(BASE, OUTPUT.relative_to(BASE).as_posix())
    recipe = read_recipe() if recipe is None else recipe
    if root.exists() or root.is_symlink():
        verify(recipe, root=root)
        return
    files = assemble(data, recipe)
    root.parent.mkdir(parents=True, exist_ok=True)
    root.mkdir()
    # 생성한 파일만 쓰며, 기존 소스·환경·손상 파일을 덮어쓰거나 삭제하지 않는다.
    for name, contents in files.items():
        path = checked(root, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as output:
            output.write(contents)
            output.flush()
            os.fsync(output.fileno())
    verify(recipe, root=root)


def main():
    parser = argparse.ArgumentParser(description='고정 12Hz TTS 코드 준비/검증. 모델 실행 없음')
    parser.add_argument('--verify-only', action='store_true')
    parser.add_argument('--wheel', type=Path, help='이미 받은 고정 원본 wheel (해시 검사 필수)')
    args = parser.parse_args()
    try:
        recipe = read_recipe()
        if args.verify_only or OUTPUT.exists():
            verify(recipe)
        else:
            if args.wheel:
                with args.wheel.open('rb') as source:
                    data = source.read(UPSTREAM_SIZE + 1)
            else:
                data = fetch_wheel()
            prepare(data, recipe)
        print('고정 12Hz TTS 코드 검증 완료 (모델 적재/합성 아님)')
    except (CodePreparationError, OSError) as error:
        print(str(error) if isinstance(error, CodePreparationError) else 'TTS 코드 파일에 접근하지 못했습니다')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
