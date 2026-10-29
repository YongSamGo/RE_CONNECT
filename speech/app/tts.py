"""검증한 로컬 CustomVoice만 사용한다. 화자/언어/지시/참조 음성은 고정한다."""

import importlib
import io
import os
from pathlib import Path
import sys
import unicodedata
import wave

import numpy as np

from app.device import selected_device, tts_options
from app.stt import ModelFailure
from prepare_models import BASE, load_manifest, prepare
import prepare_tts_code

RATE = 24000
MAX_WAV = 16 * 1024 * 1024


class TextRejected(Exception):
    """원문을 담지 않는 입력 오류."""


def validate_text(text):
    if (type(text) is not str or not 1 <= len(text) <= 2000 or not text.strip()
        or any(unicodedata.category(char) in {'Cc', 'Cf', 'Co', 'Cs', 'Zl', 'Zp'}
            and char not in '\n\t' for char in text)
        or '<|' in text or '|>' in text):
        # 모델의 대화 경계 토큰을 일반 표시 문장으로 해석하지 않는다.
        raise TextRejected()


class LocalTTS:
    def __init__(self, model):
        self.model = model

    @classmethod
    def load(cls):
        prepare_tts_code.verify()
        models = load_manifest()
        prepare(models, ['tts'], verify_only=True)
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        os.environ['HF_HUB_DISABLE_TELEMETRY'] = '1'
        # 검증 밖의 캐시 bytecode를 생성/재사용하지 않는다.
        sys.dont_write_bytecode = True
        directory = prepare_tts_code.OUTPUT.resolve()
        for name, module in tuple(sys.modules.items()):
            if name == 'qwen_tts' or name.startswith('qwen_tts.'):
                source = getattr(module, '__file__', None)
                if source is None or not Path(source).resolve().is_relative_to(directory):
                    raise ModelFailure()
        sys.path.insert(0, str(directory))
        try:
            qwen = importlib.import_module('qwen_tts')
        finally:
            sys.path.remove(str(directory))
        import torch
        torch.set_num_threads(2)
        model = qwen.Qwen3TTSModel.from_pretrained(
            str(BASE / 'models' / 'tts' / models['tts']['revision']),
            local_files_only=True, use_safetensors=True, trust_remote_code=False,
            **tts_options(selected_device(), torch))
        prepare_tts_code.verify()
        return cls(model)

    def synthesize(self, text):
        validate_text(text)
        waves, pcm, scaled = None, None, None
        buffer = io.BytesIO()
        try:
            import torch
            with torch.inference_mode():
                waves, rate = self.model.generate_custom_voice(
                    text=text, language='Korean', speaker='Sohee', instruct=None,
                    do_sample=True, subtalker_dosample=True,
                    max_new_tokens=1024, non_streaming_mode=True)
            if (type(rate) is not int or rate != RATE or not isinstance(waves, list) or len(waves) != 1):
                raise ModelFailure()
            samples = waves[0]
            if (not isinstance(samples, np.ndarray) or samples.ndim != 1 or samples.dtype.kind != 'f'
                or not samples.flags.writeable or not 1 <= samples.size <= (MAX_WAV - 44) // 2
                or not np.isfinite(samples).all()):
                raise ModelFailure()
            scaled = np.clip(samples, -1, 1)
            np.multiply(scaled, 32767, out=scaled)
            np.rint(scaled, out=scaled)
            pcm = scaled.astype('<i2')
            if not pcm.any():
                raise ModelFailure()
            with wave.open(buffer, 'wb') as recording:
                recording.setnchannels(1)
                recording.setsampwidth(2)
                recording.setframerate(RATE)
                recording.writeframes(memoryview(pcm))
            with buffer.getbuffer() as view:
                return bytearray(view)
        except Exception:
            raise ModelFailure() from None
        finally:
            # 반환 WAV만 다음 계층으로 넘긴다. 이 계층의 파형/PCM/인코더 버퍼는 비운다.
            for array in (pcm, scaled):
                if array is not None:
                    array.fill(0)
            if isinstance(waves, list):
                for array in waves:
                    if isinstance(array, np.ndarray) and array.flags.writeable:
                        array.fill(0)
            with buffer.getbuffer() as view:
                view[:] = b'\0' * len(view)
            buffer.close()
