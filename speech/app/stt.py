"""해시 검증된 로컬 Whisper만 사용한다. 요청 중 모델을 받지 않는다."""

from dataclasses import dataclass
import os
import unicodedata

from app.audio import AudioRejected, RATE, decode_audio
from prepare_models import BASE, load_manifest, prepare


class ModelFailure(Exception):
    """모델 원문/라이브러리 오류를 응답·로그로 내보내지 않는다."""


@dataclass(frozen=True, repr=False)
class Transcript:
    text: str
    duration_seconds: float


class LocalSTT:
    def __init__(self, model):
        self.model = model

    @classmethod
    def load(cls):
        models = load_manifest()
        prepare(models, ['stt'], verify_only=True)
        directory = BASE / 'models' / 'stt' / models['stt']['revision']
        os.environ['HF_HUB_OFFLINE'] = '1'
        os.environ['TRANSFORMERS_OFFLINE'] = '1'
        from faster_whisper import WhisperModel
        # CPU 검증용 고정 설정이다. GPU/EC2 성능을 추정하거나 자동 사용하지 않는다.
        return cls(WhisperModel(str(directory), device='cpu', compute_type='int8', cpu_threads=2,
            num_workers=1, local_files_only=True))

    def transcribe(self, data: bytes, media: str) -> Transcript:
        samples = None
        try:
            samples = decode_audio(data, media)
            segments, info = self.model.transcribe(samples, language='ko', beam_size=5, temperature=0,
                condition_on_previous_text=False, vad_filter=True, vad_parameters={'min_silence_duration_ms': 500})
            parts, size = [], 0
            for segment in segments:  # faster-whisper의 실제 연산은 이 generator 소비 중 수행된다.
                if not isinstance(segment.text, str):
                    raise ModelFailure()
                size += len(segment.text)
                if size > 2000:
                    raise ModelFailure()
                parts.append(segment.text)
            text = unicodedata.normalize('NFC', ''.join(parts)).strip()
            if not text:
                raise AudioRejected()
            if len(text) > 2000 or any(unicodedata.category(char).startswith('C') for char in text):
                raise ModelFailure()
            return Transcript(text, len(samples) / RATE)
        except (AudioRejected, ModelFailure):
            raise
        except Exception:
            raise ModelFailure() from None
        finally:
            # 재사용하는 모델과 달리 오디오 배열/참조는 요청 밖에 보관하지 않는다.
            if samples is not None:
                samples.fill(0)
