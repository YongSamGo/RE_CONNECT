"""메모리 안에서 제한된 오디오만 16kHz mono PCM으로 변환한다."""

import io
import math
import struct
import time

import av
import numpy as np

MAX_UPLOAD = 6 * 1024 * 1024
RATE = 16000
MAX_SAMPLES = 90 * RATE
FORMATS = {'audio/wav': 'wav', 'audio/webm': 'matroska', 'audio/ogg': 'ogg', 'audio/mp4': 'mov'}
CODECS = {'audio/wav': {'pcm_s16le'}, 'audio/webm': {'opus', 'vorbis'},
          'audio/ogg': {'opus', 'vorbis'}, 'audio/mp4': {'aac'}}


class AudioRejected(Exception):
    def __init__(self, code='AUDIO_INVALID'):
        self.code = code
        super().__init__(code)


def _decode_audio(data: bytes, media: str, chunks: list) -> np.ndarray:
    if type(data) is not bytes or not 0 < len(data) <= MAX_UPLOAD or media not in FORMATS:
        raise AudioRejected()
    signature = ((media == 'audio/wav' and len(data) >= 44 and data[:4] == b'RIFF' and data[8:12] == b'WAVE'
                  and struct.unpack_from('<I', data, 4)[0] + 8 == len(data))
        or (media == 'audio/webm' and data.startswith(b'\x1aE\xdf\xa3'))
        or (media == 'audio/ogg' and data.startswith(b'OggS\x00'))
        or (media == 'audio/mp4' and len(data) >= 12 and data[4:8] == b'ftyp'))
    if not signature:
        raise AudioRejected()
    count, source_duration = 0, 0.0
    started = time.monotonic()

    def append(frames):
        nonlocal count
        for frame in frames:
            count += frame.samples
            if count > MAX_SAMPLES:
                raise AudioRejected('AUDIO_TOO_LONG')
            chunks.append(frame.to_ndarray().reshape(-1).astype(np.float32) / 32768.0)

    try:
        with av.open(io.BytesIO(data), mode='r', format=FORMATS[media],
                     options={'protocol_whitelist': '', 'enable_drefs': '0', 'use_absolute_path': '0'}) as container:
            # 파일명·URL·외부 playlist를 받지 않는다. 영상/첨부/복수 오디오도 거절한다.
            if len(container.streams) != 1 or len(container.streams.audio) != 1:
                raise AudioRejected()
            stream = container.streams.audio[0]
            codec = stream.codec_context
            if codec.name not in CODECS[media] or len(codec.layout.channels) not in (1, 2) or not 8000 <= codec.sample_rate <= 192000:
                raise AudioRejected()
            if media == 'audio/wav' and (codec.sample_rate != RATE or len(codec.layout.channels) != 1):
                raise AudioRejected()
            resampler = av.AudioResampler(format='s16', layout='mono', rate=RATE)
            for index, frame in enumerate(container.decode(audio=0)):
                if index >= 100000 or time.monotonic() - started > 5:
                    raise AudioRejected()
                if frame.sample_rate <= 0:
                    raise AudioRejected()
                source_duration += frame.samples / frame.sample_rate
                if source_duration > 90 + 1e-8:
                    raise AudioRejected('AUDIO_TOO_LONG')
                append(resampler.resample(frame))
            append(resampler.resample(None))
    except (av.FFmpegError, ValueError, TypeError, OSError, OverflowError):
        raise AudioRejected() from None
    if not chunks or count == 0:
        raise AudioRejected()
    return np.concatenate(chunks)


def decode_audio(data: bytes, media: str) -> np.ndarray:
    chunks, samples, accepted = [], None, False
    try:
        samples = _decode_audio(data, media, chunks)
        if not np.isfinite(samples).all():
            raise AudioRejected()
        # 디지털 무음/극미세 잡음 검사. 실제 발화 판정은 Whisper VAD가 추가 수행한다.
        rms = math.sqrt(float(np.mean(samples.astype(np.float64) ** 2)))
        if rms <= 0.00001:
            raise AudioRejected()
        accepted = True
        return samples
    finally:
        for chunk in chunks:
            chunk.fill(0)
        if samples is not None and not accepted:
            samples.fill(0)
