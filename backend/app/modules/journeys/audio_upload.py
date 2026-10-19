"""audio 한 part만 받는 제한 multipart. 임시 파일·폼 spool·파일명을 사용하지 않는다."""

from email import policy
from email.parser import BytesHeaderParser
import re

from app.adapters.internal_speech import MAX_AUDIO_BYTES
from app.core.business_errors import AppError


class InvalidAudioUpload(Exception):
    pass


def _headers(raw):
    if not raw or len(raw) > 4096 or b'\x00' in raw:
        raise InvalidAudioUpload
    lines = raw.split(b'\r\n')
    if any(not line or line[:1] in (b' ', b'\t') or b'\n' in line or b'\r' in line or b':' not in line for line in lines):
        raise InvalidAudioUpload
    message = BytesHeaderParser(policy=policy.default).parsebytes(raw + b'\r\n\r\n')
    keys = [key.lower() for key in message.keys()]
    if len(keys) != len(set(keys)) or message.defects or any(getattr(message[key], 'defects', ()) for key in message.keys()):
        raise InvalidAudioUpload
    return message


def parse_audio_upload(body: bytes, content_type: str) -> tuple[bytes, str]:
    """RFC7578의 경계를 좁혀 audio 하나만 허용한다. 일반 multipart 파서가 아니다."""
    if len(body) > MAX_AUDIO_BYTES + 8192:
        raise AppError('PAYLOAD_TOO_LARGE')
    try:
        if not isinstance(content_type, str) or len(content_type) > 512 or not content_type.isascii() or any(ord(c) < 32 for c in content_type):
            raise InvalidAudioUpload
        header = _headers(b'Content-Type: ' + content_type.encode('ascii'))
        if header.get_content_type() != 'multipart/form-data' or set(header['Content-Type'].params) != {'boundary'}:
            raise InvalidAudioUpload
        boundary = header.get_boundary()
        if not isinstance(boundary, str) or not re.fullmatch(r"[0-9A-Za-z'()+_,./:=?-]{1,70}", boundary):
            raise InvalidAudioUpload
        delimiter = b'--' + boundary.encode('ascii')
        start, close = delimiter + b'\r\n', b'\r\n' + delimiter + b'--'
        if not body.startswith(start):
            raise InvalidAudioUpload
        if body.endswith(close + b'\r\n'):
            end = len(body) - len(close) - 2
        elif body.endswith(close):
            end = len(body) - len(close)
        else:
            raise InvalidAudioUpload
        separator = body.find(b'\r\n\r\n', len(start), len(start) + 4100)
        if separator < 0 or separator + 4 > end:
            raise InvalidAudioUpload
        raw_headers = body[len(start):separator]
        part = _headers(raw_headers)
        if set(key.lower() for key in part.keys()) != {'content-disposition', 'content-type'}:
            raise InvalidAudioUpload
        disposition = part['Content-Disposition']
        if (part.get_content_disposition() != 'form-data' or disposition.params.get('name') != 'audio'
            or not set(disposition.params) <= {'name', 'filename'} or re.search(br';\s*filename\*\s*=', raw_headers, re.I)):
            raise InvalidAudioUpload
        audio = body[separator + 4:end]
        if not audio or b'\r\n' + delimiter in audio:
            raise InvalidAudioUpload
        if len(audio) > MAX_AUDIO_BYTES:
            raise AppError('PAYLOAD_TOO_LARGE')
        # 파일명·경로는 읽거나 반환하지 않는다. 전송 바이트를 디코딩/변환하지 않는다.
        return audio, str(part['Content-Type'])
    except (ValueError, TypeError, UnicodeError, IndexError):
        raise InvalidAudioUpload from None
