import io
import json
from types import SimpleNamespace

import pytest

import check_ready


@pytest.mark.parametrize('change,accepted', [({}, True), ({'protocol_version': True}, False),
    ({'stt': 1}, False), ({'tts': False}, False), ({'extra': 'field'}, False), ({'status': 'not_ready'}, False)])
def test_health_probe_requires_exact_typed_ready_payload(monkeypatch, change, accepted):
    body = json.dumps(dict(protocol_version=1, status='ready', stt=True, tts=True) | change).encode()
    install(monkeypatch, body)
    assert check_ready.main() == (0 if accepted else 1)


def install(monkeypatch, body, *, status=200, media='application/json', encoding='identity'):
    class Response(io.BytesIO):
        headers = {'Content-Type': media, 'Content-Encoding': encoding}
    response = Response(body)
    response.status = status
    def open(url, timeout):
        assert url == 'http://127.0.0.1:8001/health/ready' and timeout == 2
        return response
    monkeypatch.setattr(check_ready, 'build_opener', lambda *args: SimpleNamespace(open=open))


@pytest.mark.parametrize('kwargs', [{'body': b'x' * 4097}, {'body': b'not-json'},
    {'body': b'{}', 'status': 503}, {'body': b'{}', 'media': 'text/html'}, {'body': b'{}', 'encoding': 'gzip'}])
def test_health_probe_rejects_invalid_bounded_responses_without_printing(monkeypatch, capsys, kwargs):
    install(monkeypatch, **kwargs)
    assert check_ready.main() == 1
    assert capsys.readouterr().out == ''
