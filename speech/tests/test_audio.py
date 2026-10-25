import io
from fractions import Fraction
import wave

import av
import numpy as np
import pytest

from app.audio import AudioRejected, MAX_UPLOAD, decode_audio


def wav(seconds=1, *, frames=None, silent=False, rate=16000, width=2):
    count = frames if frames is not None else int(seconds * rate)
    buffer = io.BytesIO()
    with wave.open(buffer, 'wb') as output:
        output.setparams((1, width, rate, count, 'NONE', 'not compressed'))
        values = np.zeros(count, dtype='<i2') if silent else (np.sin(np.arange(count) * (2 * np.pi * 220 / rate)) * 5000).astype('<i2')
        output.writeframes(values.tobytes() if width == 2 else b'\x01' * count * width)
    return buffer.getvalue()


def encoded(format, codec, *, rate=48000, seconds=1, video=False):
    buffer = io.BytesIO()
    with av.open(buffer, 'w', format=format) as container:
        stream = container.add_stream(codec, rate=rate)
        stream.layout = 'mono'
        image = None
        if video:
            image = container.add_stream('mpeg4', rate=1)
            image.width, image.height = 16, 16
        count = int(seconds * rate)
        values = (np.sin(np.arange(count) * (2 * np.pi * 220 / rate)) * 5000).astype(np.int16)
        frame = av.AudioFrame.from_ndarray(values.reshape(1, -1), format='s16', layout='mono')
        frame.sample_rate = rate
        frame.pts, frame.time_base = 0, Fraction(1, rate)
        for packet in stream.encode(frame):
            container.mux(packet)
        for packet in stream.encode(None):
            container.mux(packet)
        if video:
            video_frame = av.VideoFrame.from_ndarray(np.zeros((16, 16, 3), dtype=np.uint8), format='rgb24')
            video_frame.pts, video_frame.time_base = 0, Fraction(1, 1)
            for packet in image.encode(video_frame):
                container.mux(packet)
            for packet in image.encode(None):
                container.mux(packet)
    return buffer.getvalue()


@pytest.mark.parametrize('format,codec,media', [('webm', 'libopus', 'audio/webm'), ('ogg', 'libopus', 'audio/ogg'), ('mp4', 'aac', 'audio/mp4')])
def test_actual_compressed_bytes_decode_to_mono_float32_16khz(format, codec, media):
    output = decode_audio(encoded(format, codec), media)
    assert output.dtype == np.float32 and output.ndim == 1
    assert 15000 < len(output) < 17000 and np.max(np.abs(output)) > 0.05


def test_actual_wav_boundary_is_90_seconds_and_one_more_sample_is_rejected():
    assert len(decode_audio(wav(seconds=90), 'audio/wav')) == 90 * 16000
    with pytest.raises(AudioRejected, match='AUDIO_TOO_LONG'):
        decode_audio(wav(frames=90 * 16000 + 1), 'audio/wav')


def test_actual_compressed_length_is_checked_after_decode_not_from_signature():
    with pytest.raises(AudioRejected, match='AUDIO_TOO_LONG'):
        decode_audio(encoded('ogg', 'libopus', seconds=90.1), 'audio/ogg')


@pytest.mark.parametrize('kind', ['silence', 'empty', 'wrong-signature', 'fake-container', 'too-large', 'wrong-rate', 'wrong-width', 'wrong-mime'])
def test_invalid_audio_and_silence_are_rejected(kind):
    data, media = wav(), 'audio/wav'
    if kind == 'silence':
        data = wav(silent=True)
    elif kind == 'empty':
        data = b''
    elif kind == 'wrong-signature':
        data = b'not audio'
    elif kind == 'fake-container':
        data, media = b'\x1aE\xdf\xa3bad container', 'audio/webm'
    elif kind == 'too-large':
        data = b'OggS\x00' + b'x' * MAX_UPLOAD
        media = 'audio/ogg'
    elif kind == 'wrong-rate':
        data = wav(rate=44100)
    elif kind == 'wrong-width':
        data = wav(width=4)
    else:
        media = 'text/plain'
    with pytest.raises(AudioRejected, match='AUDIO_INVALID'):
        decode_audio(data, media)


def test_video_container_and_unapproved_codec_are_rejected():
    for data, media in [(encoded('mp4', 'aac', video=True), 'audio/mp4'), (encoded('mp4', 'alac'), 'audio/mp4')]:
        with pytest.raises(AudioRejected, match='AUDIO_INVALID'):
            decode_audio(data, media)


def test_decode_intermediate_buffers_are_erased_without_erasing_accepted_result(monkeypatch):
    concatenate = np.concatenate
    observed = []
    def record(chunks):
        result = concatenate(chunks)
        observed.append((list(chunks), result))
        return result
    monkeypatch.setattr('app.audio.np.concatenate', record)
    output = decode_audio(wav(), 'audio/wav')
    assert output.any() and all(not chunk.any() for chunk in observed[-1][0])
    with pytest.raises(AudioRejected):
        decode_audio(wav(silent=True), 'audio/wav')
    assert not observed[-1][1].any() and all(not chunk.any() for chunk in observed[-1][0])
