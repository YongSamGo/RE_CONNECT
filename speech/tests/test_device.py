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
