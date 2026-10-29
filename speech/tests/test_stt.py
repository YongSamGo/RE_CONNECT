from types import SimpleNamespace

import numpy as np
import pytest

from app.audio import AudioRejected
from app.stt import LocalSTT, ModelFailure


def test_actual_generator_is_consumed_and_audio_is_erased_after_result(monkeypatch):
    samples = np.ones(16000, dtype=np.float32)
    monkeypatch.setattr('app.stt.decode_audio', lambda data, media: samples)
    calls = []
    class Model:
        def transcribe(self, audio, **kwargs):
            assert audio is samples and audio.any()
            calls.append(kwargs)
            def segments():
                calls.append('native inference completed')
                yield SimpleNamespace(text=' 가상 경험')
                yield SimpleNamespace(text='입니다.')
            return segments(), None
    output = LocalSTT(Model()).transcribe(b'test', 'audio/wav')
    assert output.text == '가상 경험입니다.' and output.duration_seconds == 1
    assert calls[0]['language'] == 'ko' and calls[0]['vad_filter'] is True
    assert calls[1] == 'native inference completed'
    assert not samples.any() and '가상' not in repr(output)


@pytest.mark.parametrize('mode', ['error', 'empty', 'too-long', 'hidden'])
def test_failure_never_exposes_model_body_and_erases_audio(monkeypatch, mode):
    samples = np.ones(100, dtype=np.float32)
    monkeypatch.setattr('app.stt.decode_audio', lambda data, media: samples)
    class Model:
        def transcribe(self, audio, **kwargs):
            def segments():
                if mode == 'error':
                    raise ValueError('private user words')
                if mode != 'empty':
                    yield SimpleNamespace(text='x' * 2001 if mode == 'too-long' else 'hidden\x00body')
            return segments(), None
    with pytest.raises(AudioRejected if mode == 'empty' else ModelFailure) as caught:
        LocalSTT(Model()).transcribe(b'test', 'audio/wav')
    assert not samples.any() and 'private' not in str(caught.value) and caught.value.__cause__ is None
