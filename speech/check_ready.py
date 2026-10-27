"""모델을 import하지 않는 loopback readiness 검사. 본문/외부 오류를 출력하지 않는다."""

import json
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def main():
    try:
        with build_opener(ProxyHandler({}), NoRedirects()).open('http://127.0.0.1:8001/health/ready', timeout=2) as response:
            body = response.read(4097)
            if (response.status != 200 or len(body) > 4096
                or response.headers.get('Content-Type', '').split(';', 1)[0].lower() != 'application/json'
                or response.headers.get('Content-Encoding', 'identity').lower() != 'identity'):
                return 1
            data = json.loads(body)
            return 0 if (data == {'protocol_version': 1, 'status': 'ready', 'stt': True, 'tts': True}
                and type(data.get('protocol_version')) is int and type(data.get('stt')) is bool
                and type(data.get('tts')) is bool) else 1
    except Exception:
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
