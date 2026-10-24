"""내부 모델 프로세스. IPC에는 pickle 대신 크기가 제한된 JSON/bytes만 쓴다."""

from dataclasses import dataclass
import json
import multiprocessing
import threading

from app.audio import AudioRejected, MAX_UPLOAD
from app.stt import LocalSTT, Transcript
from app.tts import LocalTTS, MAX_WAV, TextRejected

MAX_META = 16384
ENDED = b'operation-ended-v1'


def erase(audio):
    if isinstance(audio, bytearray):
        audio[:] = b'\0' * len(audio)


def encode(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf-8')


def model_process(connection, stt_loader, tts_loader):
    stt = tts = None
    try:
        try:
            stt = stt_loader() if stt_loader is not None else None
        except Exception:
            stt = None
        try:
            tts = tts_loader() if tts_loader is not None else None
        except Exception:
            tts = None
        connection.send_bytes(encode({'stt': stt is not None, 'tts': tts is not None}))
        while True:
            command = payload = result = metadata = audio = None
            try:
                command = json.loads(connection.recv_bytes(MAX_META))
                if command['kind'] == 'stt':
                    payload = connection.recv_bytes(MAX_UPLOAD)
                    if stt is None:
                        metadata = {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'}
                    else:
                        result = stt.transcribe(payload, command['media'])
                        metadata = {'text': result.text, 'duration_seconds': result.duration_seconds}
                elif command['kind'] == 'tts':
                    if tts is None:
                        metadata = {'code': 'RUNTIME_TEMPORARILY_UNAVAILABLE'}
                    else:
                        audio = tts.synthesize(command['text'])
                        if not isinstance(audio, bytearray) or not 1 <= len(audio) <= MAX_WAV:
                            raise ValueError
                        metadata = {'wav': True}
                else:
                    raise ValueError
            except AudioRejected as error:
                metadata = {'code': error.code}
            except TextRejected:
                metadata = {'code': 'TEXT_INVALID'}
            except (EOFError, OSError):
                return
            except Exception:
                metadata = {'code': 'RUNTIME_UNAVAILABLE'}
            try:
                connection.send_bytes(encode(metadata))
                if metadata == {'wav': True}:
                    connection.send_bytes(audio)
            finally:
                erase(audio)
                # 원문/출력 참조를 다음 요청까지 보관하지 않는다.
                command = payload = result = metadata = audio = None
            # 데이터 전송만으로 종료를 주장하지 않는다. 정리 후 별도 확인을 보낸다.
            connection.send_bytes(ENDED)
    except (EOFError, OSError, BrokenPipeError):
        pass
    finally:
        connection.close()


@dataclass(repr=False)
class Outcome:
    value: object = None
    code: str | None = None
    ended: bool = True


class ProcessRuntime:
    def __init__(self, *, stt_loader=LocalSTT.load, tts_loader=LocalTTS.load, startup_timeout=120):
        self._stt_loader, self._tts_loader = stt_loader, tts_loader
        self._startup_timeout = startup_timeout
        self._process = self._connection = None
        self._loaded = {'stt': False, 'tts': False}
        self._stop_lock = threading.Lock()
        self._stopping = False

    @property
    def readiness(self):
        process = self._process
        alive = process is not None and process.is_alive()
        return {kind: alive and value for kind, value in self._loaded.items()}

    def start(self):
        context = multiprocessing.get_context('spawn')
        parent, child = context.Pipe(duplex=True)
        try:
            with self._stop_lock:
                if self._stopping:
                    parent.close()
                    child.close()
                    return
                self._connection = parent
                self._process = context.Process(target=model_process,
                    args=(child, self._stt_loader, self._tts_loader), daemon=True)
                self._process.start()
                child.close()  # 부모의 복제된 송신 끝이 EOF를 막지 않게 한다.
            if not parent.poll(self._startup_timeout):
                raise TimeoutError
            loaded = json.loads(parent.recv_bytes(MAX_META))
            if set(loaded) != {'stt', 'tts'} or any(type(value) is not bool for value in loaded.values()):
                raise ValueError
            self._loaded = loaded
        except Exception:
            child.close()
            self.stop()

    def stop(self):
        with self._stop_lock:
            self._stopping = True
            self._loaded = {'stt': False, 'tts': False}
            process = self._process
            if process is not None and process.pid is not None:
                try:
                    if process.is_alive():
                        process.terminate()
                    process.join(2)
                    if process.is_alive():
                        process.kill()
                        process.join(2)
                    if process.is_alive():
                        return False
                except (OSError, ValueError, AssertionError):
                    return False
            if self._connection is not None:
                self._connection.close()
                self._connection = None
            self._process = None
            return True

    def execute(self, kind, value, media=None):
        audio = None
        try:
            connection = self._connection
            if connection is None or not self.readiness.get(kind, False):
                return Outcome(code='RUNTIME_TEMPORARILY_UNAVAILABLE')
            if kind == 'stt':
                connection.send_bytes(encode({'kind': kind, 'media': media}))
                connection.send_bytes(value)
            elif kind == 'tts':
                connection.send_bytes(encode({'kind': kind, 'text': value}))
            else:
                raise ValueError
            metadata = json.loads(connection.recv_bytes(MAX_META))
            if metadata == {'wav': True} and kind == 'tts':
                audio = bytearray(connection.recv_bytes(MAX_WAV))
                if not audio:
                    raise ValueError
                result = Outcome(value=audio)
            elif set(metadata) == {'code'} and metadata['code'] in (
                'RUNTIME_TEMPORARILY_UNAVAILABLE', 'RUNTIME_UNAVAILABLE', 'AUDIO_INVALID', 'AUDIO_TOO_LONG', 'TEXT_INVALID'):
                result = Outcome(code=metadata['code'])
            elif kind == 'stt' and set(metadata) == {'text', 'duration_seconds'}:
                if (type(metadata['text']) is not str or not 1 <= len(metadata['text']) <= 2000
                    or type(metadata['duration_seconds']) not in (int, float)
                    or not 0 < metadata['duration_seconds'] <= 90):
                    raise ValueError
                result = Outcome(value=Transcript(**metadata))
            else:
                raise ValueError
            if connection.recv_bytes(64) != ENDED:
                raise ValueError
            return result
        except Exception:
            erase(audio)
            return Outcome(code='RUNTIME_UNAVAILABLE', ended=self.stop())
