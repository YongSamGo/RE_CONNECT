"""모델 다운로드 도구의 고정 명세/해시/경로/실패 정리 (가중치 실행 없음)."""

import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
from urllib.error import URLError

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare_models', ROOT / 'speech' / 'prepare_models.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
DATA = b'fixed synthetic model'
ITEM = {'path': 'model.safetensors', 'size': len(DATA), 'sha256': hashlib.sha256(DATA).hexdigest()}
URL = 'https://huggingface.co/Qwen/example/resolve/fixed/model.safetensors'


class Response(io.BytesIO):
    url, status = URL, 200
    def __init__(self, body=DATA, headers=None):
        super().__init__(body)
        self.headers = {'Content-Length': str(len(body)), **(headers or {})}


def test_actual_manifest_matches_only_pinned_repositories_and_permitted_files():
    models = tool.load_manifest()
    assert len(models['stt']['files']) == 4 and len(models['tts']['files']) == 11
    assert sum(file['size'] for model in models.values() for file in model['files']) == 2984595982
    assert all(file['sha256'] for model in models.values() for file in model['files'])


@pytest.mark.parametrize('kind', ['repository', 'revision', 'path', 'duplicate', 'size', 'hash', 'extra', 'missing'])
def test_manifest_rejects_unpinned_or_unexpected_inputs(tmp_path, kind):
    raw = json.loads((ROOT / 'speech' / 'model-manifest.json').read_text(encoding='utf-8'))
    model = raw['models']['stt']
    if kind in {'repository', 'revision'}:
        model[kind] = 'untrusted'
    elif kind == 'path':
        model['files'][0]['path'] = '../code.py'
    elif kind == 'duplicate':
        model['files'][1] = copy.deepcopy(model['files'][0])
    elif kind == 'size':
        model['files'][0]['size'] = True
    elif kind == 'hash':
        model['files'][0]['sha256'] = '0' * 63
    elif kind == 'extra':
        model['files'][0]['url'] = 'https://untrusted.invalid/'
    else:
        model['files'].pop()
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(raw), encoding='utf-8')
    with pytest.raises(tool.PreparationError):
        tool.load_manifest(path)


@pytest.mark.parametrize('url', ['http://huggingface.co/a', 'https://huggingface.co.evil.invalid/a',
    'https://user:token@huggingface.co/a', 'https://huggingface.co:444/a', 'https://127.0.0.1/a',
    'https://us.aws.cdn.hf.co/a#fragment', 'file:///tmp/model', 'https://huggingface.co:bad/a'])
def test_redirect_destination_is_https_and_exact_official_host_only(url):
    with pytest.raises(tool.PreparationError):
        tool.check_url(url)


@pytest.mark.parametrize('relative', ['../outside', '/outside', 'stt/../../outside', 'C:/outside', 'stt\\outside', '.'])
def test_target_path_cannot_escape_model_folder(tmp_path, relative):
    with pytest.raises(tool.PreparationError):
        tool.checked_path(tmp_path, relative)


def test_verified_download_is_atomic_and_existing_valid_file_does_not_fetch_again(tmp_path):
    target = tmp_path / 'weights' / ITEM['path']
    tool.download_file(target, ITEM, URL, open_response=lambda url: Response())
    assert target.read_bytes() == DATA
    assert not list(target.parent.glob('*.partial'))
    tool.download_file(target, ITEM, URL, open_response=lambda url: pytest.fail('must not fetch twice'))


@pytest.mark.parametrize('mode', ['hash', 'truncated', 'oversize', 'compressed', 'length', 'status', 'host', 'connection', 'stream'])
def test_failed_download_never_leaves_a_model_or_partial_and_does_not_print_signed_url(tmp_path, mode):
    target = tmp_path / ITEM['path']
    def response(url):
        if mode == 'connection':
            raise URLError('private signed URL and query')
        result = Response()
        if mode == 'hash':
            result = Response(b'x' * len(DATA))
        elif mode == 'truncated':
            result = Response(DATA[:-1], {'Content-Length': str(len(DATA))})
        elif mode == 'oversize':
            result = Response(DATA + b'extra', {'Content-Length': str(len(DATA))})
        elif mode == 'compressed':
            result.headers['Content-Encoding'] = 'gzip'
        elif mode == 'length':
            result.headers['Content-Length'] = '9' * 5000
        elif mode == 'status':
            result.status = 503
        elif mode == 'host':
            result.url = 'https://evil.invalid/?signed=private'
        elif mode == 'stream':
            result.read = lambda size: (_ for _ in ()).throw(ConnectionResetError('private URL'))
        return result
    with pytest.raises(tool.PreparationError) as caught:
        tool.download_file(target, ITEM, URL, open_response=response)
    assert not target.exists() and not list(tmp_path.glob('*.partial'))
    assert 'private' not in str(caught.value)


def test_corrupt_existing_file_is_preserved_without_network_or_replacement(tmp_path):
    target = tmp_path / ITEM['path']
    target.write_bytes(b'x' * len(DATA))
    with pytest.raises(tool.PreparationError):
        tool.download_file(target, ITEM, URL, open_response=lambda url: pytest.fail('unexpected network'))
    assert target.read_bytes() == b'x' * len(DATA)


def tiny_models():
    return {'stt': {'repository': 'Systran/faster-whisper-small', 'revision': 'fixed', 'files': [ITEM]}}


def test_prepare_verification_is_offline_and_unknown_files_are_rejected(tmp_path):
    tool.prepare(tiny_models(), ['stt'], root=tmp_path, open_response=lambda url: Response())
    assert not (tmp_path / '.prepare.lock').exists()
    tool.prepare(tiny_models(), ['stt'], root=tmp_path, verify_only=True,
        open_response=lambda url: pytest.fail('offline verification must not fetch'))
    extra = tmp_path / 'stt' / 'fixed' / 'unexpected.py'
    extra.write_text('not executed', encoding='utf-8')
    with pytest.raises(tool.PreparationError):
        tool.prepare(tiny_models(), ['stt'], root=tmp_path, verify_only=True)


def test_foreign_lock_is_preserved_and_own_lock_is_removed_on_failure(tmp_path):
    lock = tmp_path / '.prepare.lock'
    lock.write_text('another task', encoding='utf-8')
    with pytest.raises(tool.PreparationError):
        tool.prepare(tiny_models(), ['stt'], root=tmp_path)
    assert lock.read_text(encoding='utf-8') == 'another task'
    lock.unlink()
    with pytest.raises(tool.PreparationError):
        tool.prepare(tiny_models(), ['stt'], root=tmp_path, open_response=lambda url: Response(b'wrong'))
    assert not lock.exists()


def test_symbolic_link_is_not_followed_for_read_or_download(tmp_path):
    outside = tmp_path / 'outside'
    outside.mkdir()
    root = tmp_path / 'models'
    root.mkdir()
    link = root / 'stt'
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        # Windows의 일반 권한에서도 같은 정책을 junction으로 검증한다.
        import subprocess
        result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
        assert result.returncode == 0
    with pytest.raises(tool.PreparationError):
        tool.prepare(tiny_models(), ['stt'], root=root, open_response=lambda url: pytest.fail('must not fetch'))
    assert list(outside.iterdir()) == []
