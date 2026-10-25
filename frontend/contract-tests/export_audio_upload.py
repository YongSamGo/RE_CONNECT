"""클라이언트가 만든 가상 multipart를 실제 제한 업로드 파서로 검증한다. 파일 저장 없음."""

import base64
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'backend'))

from app.modules.journeys.audio_upload import parse_audio_upload  # noqa: E402

data = json.loads(sys.stdin.read(9 * 1024 * 1024))
audio, media = parse_audio_upload(base64.b64decode(data['body'], validate=True), data['content_type'])
print(json.dumps({'size': len(audio), 'sha256': hashlib.sha256(audio).hexdigest(), 'content_type': media}))
