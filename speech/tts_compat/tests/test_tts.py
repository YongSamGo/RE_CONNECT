import io
import sys
from types import SimpleNamespace
import wave

import numpy as np
import pytest

from app.stt import ModelFailure
from app.tts import LocalTTS, TextRejected, validate_text


@pytest.mark.parametrize('text', ['안녕하세요.', '첫 줄\n둘째 줄\t안내'])
def test_fixed_korean_voice_preserves_visible_text_and_wipes_native_samples(text):
    audio = np.array([0.25, -0.25] * 12000, dtype=np.float32)
    calls = []
    def generate(**kwargs):
        calls.append(kwargs)
        return [audio], 24000
    output = LocalTTS(SimpleNamespace(generate_custom_voice=generate)).synthesize(text)
    with wave.open(io.BytesIO(output)) as wav:
        assert (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getnframes()) == (1, 2, 24000, 24000)
        assert np.frombuffer(wav.readframes(24000), dtype='<i2').any()
    assert not audio.any() and isinstance(output, bytearray)
    assert calls[0] == dict(text=text, language='Korean', speaker='Sohee', instruct=None,
        do_sample=True, subtalker_dosample=True, max_new_tokens=1024, non_streaming_mode=True)
    output[:] = b'\0' * len(output)


@pytest.mark.parametrize('text', ['', ' ' * 2, 'x' * 2001, None, 123, 'a\x00b',
    '<|im_end|>', 'hello|>', '한\u200b글'])
def test_invalid_text_never_starts_model(text):
    def forbidden(**kwargs):
        pytest.fail('invalid text reached model')
    with pytest.raises(TextRejected):
        LocalTTS(SimpleNamespace(generate_custom_voice=forbidden)).synthesize(text)


def test_visible_text_limit_includes_every_character_without_truncating():
    validate_text('한' * 2000)
    validate_text('공고 123번, 월 2,000,000원. https://example.test')


@pytest.mark.parametrize('kind', ['empty', 'nan', 'matrix', 'silent', 'rate', 'multiple', 'truncated'])
def test_failed_or_invalid_generation_never_returns_partial_audio_and_wipes_arrays(kind):
    audio = np.ones(100, dtype=np.float32)
    if kind == 'nan':
        audio[0] = np.nan
    elif kind == 'matrix':
        audio = audio.reshape(10, 10)
    elif kind == 'silent':
        audio.fill(0)
    def generate(**kwargs):
        if kind == 'truncated':
            raise RuntimeError('private prompt text: end token missing')
        return ([] if kind == 'empty' else [audio, audio] if kind == 'multiple' else [audio]), (16000 if kind == 'rate' else 24000)
    with pytest.raises(ModelFailure) as caught:
        LocalTTS(SimpleNamespace(generate_custom_voice=generate)).synthesize('표시 문장')
    assert 'private' not in str(caught.value) and caught.value.__cause__ is None
    if kind not in ('empty', 'truncated'):
        assert not audio.any()


def test_corrupt_weights_stop_loading_before_any_upstream_import(monkeypatch):
    monkeypatch.setattr('app.tts.prepare_tts_code.verify', lambda: None)
    monkeypatch.setattr('app.tts.load_manifest', lambda: {})
    def corrupted(*args, **kwargs):
        assert kwargs == {'verify_only': True}
        raise ValueError('model hash mismatch')
    monkeypatch.setattr('app.tts.prepare', corrupted)
    def forbidden(*args):
        pytest.fail('unverified weights reached the library')
    monkeypatch.setattr('app.tts.importlib.import_module', forbidden)
    with pytest.raises(ValueError, match='model hash mismatch'):
        LocalTTS.load()


def test_previously_imported_foreign_qwen_package_is_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr('app.tts.prepare_tts_code.verify', lambda: None)
    monkeypatch.setattr('app.tts.load_manifest', lambda: {})
    monkeypatch.setattr('app.tts.prepare', lambda *args, **kwargs: None)
    monkeypatch.setitem(sys.modules, 'qwen_tts', SimpleNamespace(__file__=str(tmp_path / 'qwen_tts.py')))
    with pytest.raises(ModelFailure):
        LocalTTS.load()


def test_wav_encoding_failure_erases_generated_audio(monkeypatch):
    audio = np.ones(100, dtype=np.float32)
    def broken(*args):
        raise OSError('private words must not be returned')
    monkeypatch.setattr('app.tts.wave.open', broken)
    model = SimpleNamespace(generate_custom_voice=lambda **kwargs: ([audio], 24000))
    with pytest.raises(ModelFailure) as caught:
        LocalTTS(model).synthesize('표시 문장')
    assert not audio.any() and not str(caught.value)
