"""원본/수정 해시와 경로를 검사하며 source 코드는 실행하지 않는 준비 경계."""

import copy
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('prepare_tts_code', ROOT / 'speech' / 'prepare_tts_code.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def record(before=b'one\ntwo\n', after=b'one\nthree\n'):
    return {'before_sha256': tool.digest(before), 'after_sha256': tool.digest(after),
        'edits': [{'start': 1, 'end': 2, 'before': ['two\n'], 'after': ['three\n']}]}


def tiny_bundle(monkeypatch, *, extra=None):
    # 테스트의 fake 원본도 고정 hash 검증을 거친다. 실제 공개 원본을 변경/실행하지 않는다.
    original = b'raise RuntimeError("source must never execute during preparation")\n'
    license_text, helper, notice = b'test license\n', b'test helper\n', b'test notice\n'
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for member in sorted(tool.MEMBERS):
            archive.writestr(member, original)
        archive.writestr(tool.LICENSE_MEMBER, license_text)
        if extra:
            # ZipInfo의 Windows 이름 자동 정규화 이전 원문도 검증 대상이다.
            info = zipfile.ZipInfo('placeholder')
            info.filename, info.orig_filename = extra[0], extra[0]
            archive.writestr(info, extra[1])
    data = buffer.getvalue()
    monkeypatch.setattr(tool, 'UPSTREAM_SHA', tool.digest(data))
    monkeypatch.setattr(tool, 'UPSTREAM_SIZE', len(data))
    recipe = {'files': {member: {'before_sha256': tool.digest(original),
        'after_sha256': tool.digest(original), 'edits': []} for member in tool.MEMBERS},
        'license_sha256': tool.digest(license_text), 'compat_sha256': tool.digest(helper), 'notice_sha256': tool.digest(notice)}
    monkeypatch.setattr(tool, 'local_additions', lambda recipe: {'qwen_tts/compat.py': helper, 'LICENSE': license_text, 'NOTICE': notice})
    return data, recipe


def test_actual_recipe_pins_only_ten_upstream_sources_and_current_local_helper():
    recipe = tool.read_recipe()
    assert len(recipe['files']) == 10
    assert not any('25hz' in name or '/cli/' in name for name in recipe['files'])
    assert set(tool.local_additions(recipe)) == {'qwen_tts/compat.py', 'LICENSE', 'NOTICE'}


@pytest.mark.parametrize('field,value', [('version', True), ('version', 2), ('upstream', {}),
    ('files', {}), ('compat_sha256', 'bad')])
def test_manifest_change_cannot_replace_pinned_origin_or_helper(tmp_path, field, value):
    recipe = tool.read_recipe()
    recipe[field] = value
    path = tmp_path / 'recipe.json'
    path.write_text(json.dumps(recipe), encoding='utf-8')
    with pytest.raises(tool.CodePreparationError):
        tool.read_recipe(path)


def test_exact_line_edit_validates_both_before_and_after_hashes():
    assert tool.apply_edits(b'one\ntwo\n', record()) == b'one\nthree\n'
    with pytest.raises(tool.CodePreparationError):
        tool.apply_edits(b'one\nchanged\n', record())
    damaged = record()
    damaged['after_sha256'] = '0' * 64
    with pytest.raises(tool.CodePreparationError):
        tool.apply_edits(b'one\ntwo\n', damaged)


@pytest.mark.parametrize('edit', [
    {'start': -1, 'end': 2, 'before': [], 'after': []},
    {'start': True, 'end': 2, 'before': ['two\n'], 'after': ['three\n']},
    {'start': 2, 'end': 1, 'before': [], 'after': []},
    {'start': 1, 'end': 2, 'before': ['different\n'], 'after': ['three\n']},
    {'start': 1, 'end': 2, 'before': ['two\n'], 'after': [0]},
])
def test_unexpected_patch_context_or_range_fails_closed(edit):
    value = record()
    value['edits'] = [edit]
    with pytest.raises(tool.CodePreparationError):
        tool.apply_edits(b'one\ntwo\n', value)


def test_patch_operations_cannot_overlap_or_change_original_coordinate_order():
    value = record()
    value['edits'] = [copy.deepcopy(value['edits'][0]), copy.deepcopy(value['edits'][0])]
    with pytest.raises(tool.CodePreparationError):
        tool.apply_edits(b'one\ntwo\n', value)


def test_archive_preparation_never_executes_source_and_verification_is_offline(monkeypatch, tmp_path):
    data, recipe = tiny_bundle(monkeypatch)
    root = tmp_path / 'generated'
    tool.prepare(data, recipe, root=root)
    tool.verify(recipe, root=root)
    assert len(list(root.rglob('*.py'))) == 11
    monkeypatch.setattr(tool, 'fetch_wheel', lambda: pytest.fail('must not fetch'))
    tool.prepare(b'unused because existing bundle is verified', recipe, root=root)


def test_damaged_wheel_never_creates_output(monkeypatch, tmp_path):
    data, recipe = tiny_bundle(monkeypatch)
    root = tmp_path / 'generated'
    with pytest.raises(tool.CodePreparationError):
        tool.prepare(data + b'changed', recipe, root=root)
    assert not root.exists()


@pytest.mark.parametrize('name', ['../outside.py', '/absolute.py', 'bad\\path.py'])
def test_zip_path_escape_is_rejected_even_for_unselected_members(monkeypatch, name):
    data, recipe = tiny_bundle(monkeypatch, extra=(name, b'not executed'))
    with pytest.raises(tool.CodePreparationError):
        tool.assemble(data, recipe)


def test_zip_declared_expansion_is_limited_before_member_read(monkeypatch):
    data, recipe = tiny_bundle(monkeypatch, extra=('unused.bin', b'x' * (2 * 1024**2)))
    with pytest.raises(tool.CodePreparationError):
        tool.assemble(data, recipe)


@pytest.mark.parametrize('name', ['../outside.py', '/absolute.py', 'C:/absolute.py', 'bad\\path.py'])
def test_output_path_cannot_leave_fixed_root(tmp_path, name):
    with pytest.raises(tool.CodePreparationError):
        tool.checked(tmp_path, name)


def test_existing_modified_source_is_not_replaced_or_deleted(monkeypatch, tmp_path):
    data, recipe = tiny_bundle(monkeypatch)
    root = tmp_path / 'generated'
    tool.prepare(data, recipe, root=root)
    target = root / 'qwen_tts' / '__init__.py'
    target.write_bytes(b'modified source')
    with pytest.raises(tool.CodePreparationError):
        tool.prepare(data, recipe, root=root)
    assert target.read_bytes() == b'modified source'


def test_unexpected_cached_bytecode_blocks_import_before_source_can_be_reused(monkeypatch, tmp_path):
    data, recipe = tiny_bundle(monkeypatch)
    root = tmp_path / 'generated'
    tool.prepare(data, recipe, root=root)
    cache = root / 'qwen_tts' / '__pycache__'
    cache.mkdir()
    (cache / '__init__.cpython-312.pyc').write_bytes(b'unknown bytecode')
    with pytest.raises(tool.CodePreparationError):
        tool.verify(recipe, root=root)


def test_redirect_is_rejected_without_exposing_target():
    with pytest.raises(tool.CodePreparationError) as caught:
        tool.NoRedirects().redirect_request(None, None, 302, '', {}, 'https://private.invalid/?token=private')
    assert 'private' not in str(caught.value)
