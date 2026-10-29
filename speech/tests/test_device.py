from types import SimpleNamespace

import pytest

from app.device import selected_device, stt_options, tts_options


def test_default_cpu_and_explicit_gpu(monkeypatch):
    monkeypatch.delenv('SPEECH_DEVICE', raising=False)
    assert selected_device() == 'cpu'
    assert stt_options('cpu')['compute_type'] == 'int8'
    monkeypatch.setenv('SPEECH_DEVICE', 'cuda')
    assert selected_device() == 'cuda'
    assert stt_options('cuda')['compute_type'] == 'float16'


@pytest.mark.parametrize('value', ['', 'auto', 'cuda:1', 'https://example.test', 'CPU'])
def test_invalid_device_never_falls_back(monkeypatch, value):
    monkeypatch.setenv('SPEECH_DEVICE', value)
    with pytest.raises(ValueError):
        selected_device()


def test_t4_uses_float32_and_missing_cuda_fails():
    torch = SimpleNamespace(float32=object(), cuda=SimpleNamespace(is_available=lambda: True))
    assert tts_options('cuda', torch) == dict(device_map='cuda', dtype=torch.float32, attn_implementation='eager')
    torch.cuda.is_available = lambda: False
    with pytest.raises(ValueError):
        tts_options('cuda', torch)
    assert tts_options('cpu', torch)['device_map'] == 'cpu'


def test_cuda_locks_keep_cpu_constraints_and_separate_ct2_libraries():
    from pathlib import Path
    import re
    base = Path(__file__).resolve().parents[1]
    expected = {name: version for name, version in re.findall(r'^([a-z0-9-]+)==([^\s\\]+)',
        (base / 'tts_compat/requirements.txt').read_text(), re.M) if name != 'torch'}
    actual = dict(re.findall(r'^([a-z0-9-]+)==([^\s\\]+)', (base / 'gpu/constraints.in').read_text(), re.M))
    assert actual == expected
    main = (base / 'gpu/requirements.txt').read_text()
    ct2 = (base / 'gpu/ct2-requirements.txt').read_text()
    assert 'torch==2.14.1+cu130' in main
    assert '5359b255ac68c0cabb8293952b38e00f0d1a570815cd87f19b61af702c071410' in main
    assert 'nvidia-cudnn-cu12==' not in main and 'nvidia-cudnn-cu12==' in ct2
    assert 'nvidia-cudnn-cu13==' in main and 'nvidia-cudnn-cu13==' not in ct2
