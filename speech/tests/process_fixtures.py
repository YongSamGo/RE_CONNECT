"""spawn에서 import할 수 있는 공개 가상 모델. 실제 모델 시험과 구분한다."""

import io
import signal
import time
import wave

from app.audio import AudioRejected
from app.stt import Transcript


class STT:
    def transcribe(self, data, media):
        assert media == 'audio/wav' and data == b'audio'
        return Transcript('가상 시험 응답', 1.0)


class TTS:
    def synthesize(self, text):
        with io.BytesIO() as buffer:
            with wave.open(buffer, 'wb') as recording:
                recording.setparams((1, 2, 24000, 1200, 'NONE', 'not compressed'))
                recording.writeframes(b'\x10\x00' * 1200)
            return bytearray(buffer.getvalue())


class BrokenSTT:
    def __init__(self, code):
        self.code = code

    def transcribe(self, *args):
        if self.code == 'AUDIO_TOO_LONG':
            raise AudioRejected(self.code)
        raise ValueError('private user body')


class BlockingSTT:
    def __init__(self, entered, finish, ignore_terminate=False):
        self.entered, self.finish = entered, finish
        self.ignore_terminate = ignore_terminate

    def transcribe(self, *args):
        if self.ignore_terminate:
            signal.signal(signal.SIGTERM, signal.SIG_IGN)
        self.entered.set()
        # 강제 종료한 자식이 Condition.wait에 남으면 부모의 Event.set도 기다릴 수 있다.
        # native 연산 모형은 공유 동기화 객체의 종료 통지에 의존하지 않는다.
        time.sleep(30)
        return Transcript('가상 시험 응답', 1.0)
