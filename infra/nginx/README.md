# 운영 HTTPS·프런트·API 경로 (#91)

`nginx.conf.template`은 운영 Nginx 전체 설정이다. `/api/` 요청은 backend:8000으로
접두사를 유지해 전달하고 나머지 화면 경로는 React 빌드의 index.html로 연결한다.
`/assets/`의 누락 파일은 HTML 대신 404를 반환한다. 공개 리스너는 HTTPS 443 하나다.
도메인·인증서가 준비되지 않은 현재 상태는 운영 검증 완료가 아니다.

```bash
python infra/nginx/render_config.py --domain <실제-ASCII-도메인> --output <새-nginx.conf-경로>
python -m unittest discover -s infra/nginx/tests
```

생성기는 Nginx 변수 `$uri` 등을 그대로 보존하고 허용된 DNS 이름만 치환한다.
기존 출력 파일은 덮어쓰지 않는다. 생성된 설정은 읽기 전용으로
`/etc/nginx/nginx.conf`에 연결한다. `frontend/dist`는 `/usr/share/nginx/html`에,
인증서 체인·개인키는 `/run/secrets/tls-fullchain.pem`, `/run/secrets/tls-key.pem`에
읽기 전용으로 연결한다. 개인키는 저장소·빌드 컨텍스트에 넣지 않는다.
`/run/nginx`는 쓰기 가능한 tmpfs로 제공해야 한다. 기본 배포 이미지에 설정된
추가 공개 리스너나 예제 사이트는 함께 로드하지 않는다.

backend는 같은 사설 컨테이너 네트워크에서만 접근할 수 있어야 한다.
Nginx가 전달 헤더를 다시 만들지만, backend의 프록시 신뢰 대상도 Nginx 주소로
제한해야 한다. `--forwarded-allow-ips=*`를 공개 backend와 함께 쓰지 않는다.
Vite·PostgreSQL·Redis·Ollama·음성 포트는 호스트에 공개하지 않는다.

접근 로그는 stdout에 JSON으로 남기되 고정 경로 분류(`page`·`api`·`asset`),
상태 코드, 응답 바이트 수, 처리 시간만 기록한다. 원래 경로·쿼리·IP·쿠키·토큰·본문은
기록하지 않으며 OAuth 콜백은 접근 로그에서도 제외한다. 프록시에서 끝난 404·413·444는
관측할 수 있다. 요청 줄을 포함할 수 있는 오류 로그는 계속 끈다.
TLS 1.2는 ECDHE와 GCM/ChaCha20 암호군만 허용한다. TLS 1.3도 허용한다.

HTML·API·오류 응답은 `Cache-Control: no-store`이며, Vite의 해시 파일만 담는
`/assets/`의 200·206·304 응답에만 1년 immutable 캐시를 허용한다.
캐시 정책은 map으로 계산해 자산 응답에도 서버의 보안 헤더가 그대로 상속된다.
CSP는 `Content-Security-Policy-Report-Only`로 먼저 관측한다. 수집 서버로 보고서를
보내지 않고 브라우저 콘솔에서 확인하며, 운영 빌드의 스타일·이미지·음성 blob과
로그인 흐름의 호환성을 확인하기 전에는 CSP가 실행을 차단한다고 보지 않는다.

일반 API 본문은 프록시에서도 64KiB로 제한한다. 정확히
`/api/v1/journeys/{journey_id}/transcriptions` 경로에만 7MiB를 허용하고 backend의
6MiB 음성 한도도 유지한다. 요청은 전부 받은 뒤 backend로 넘기며 1MiB를 넘는
본문의 임시 파일은 `/run/nginx` tmpfs에 둔다. 느린 클라이언트가 backend 연결을
먼저 점유하지 않게 하는 조치이며, Nginx 자체의 연결·tmpfs 총량 제한을 대체하지 않는다.
API 응답은 음성 스트리밍을 위해 계속 버퍼링/디스크 저장하지 않는다.

## 인증서 발급·갱신과 접속 링크

공개 포트는 443만 사용하므로 ACME HTTP-01은 쓰지 않고 DNS-01로 발급·갱신한다.
운영자가 선택한 ACME 클라이언트를 별도 관리 환경의 스케줄러에서 실행하고,
DNS 자격증명은 검증 TXT 레코드 변경에 필요한 권한만 부여한다. 앱 컨테이너에는
DNS 자격증명을 주지 않는다. 클라이언트·DNS 제공자·실행 주기와 갱신 실패/만료
알림 담당자는 실제 도메인 배포 전에 정해야 하며, 이 PR은 갱신 자동화를 구현하지 않는다.

갱신 시 인증서·키 쌍을 같은 디렉터리에 안전하게 교체하고 `nginx -t` 성공 후
`nginx -s reload`로 반영한다. 컨테이너를 사용하면 인증서 디렉터리를 읽기 전용으로
연결해 파일 교체가 보이게 하거나, 파일 단위 마운트라면 컨테이너를 재생성한다.
실패 시 기존 인증서를 유지하고 운영자에게 알린다. 실제 도메인의 발급·갱신 모의시험과
외부 TLS 확인 전에는 배포 완료로 판정하지 않는다.

문자·QR·공식 안내 링크에는 반드시 `https://`를 넣는다. `http://` 링크는 연결에
실패하며 80 포트 리다이렉트는 이 구성에 없다. HTTP 진입을 지원하려면 네트워크
보안 그룹과 HTTPS 전용 운영 원칙을 함께 검토해야 한다.

배포 환경에서 `nginx -t` 후 다음을 확인해야 한다: 알려진 도메인의 TLS 성공,
다른 SNI·Host 거절, 화면 경로 직접 새로고침, 실제 JSON·음성 요청 경로 보존,
업로드 한도, 콜백의 캐시 금지와 로그 미기록.

로컬에서는 공식 Nginx Windows 1.30.6 실행 파일로 `nginx -t`와 실제 HTTPS 요청을
검사했다. 임시 인증서·루프백 backend를 사용해 SPA 경로, API 접두사·쿼리 보존,
음성 응답의 Content-Type, 전달 헤더 위조 제거, no-store, 413 본문 제한,
잘못된 SNI·Host 거절, 콜백 로그 미기록을 확인했다. 운영 Linux 이미지와 실제
애플리케이션·인증서·음성 서비스는 별도 통합 검증이 필요하다.

실행 검사는 정상 자산의 캐시·보안 헤더, 오류 캐시 금지, API/녹음 경로별 한도,
미완료 업로드의 backend 도달 차단, TLS 1.2 구형 암호군 거절, 안전한 접근 로그도 확인한다.
CI의 backend Python 잡은 렌더러 테스트와 생성기의 Bandit 검사를 실행한다.
CI에 `NGINX_TEST_BINARY`를 설정하지 않은 상태에서는 실제 Nginx 실행 검사만 skip하며,
운영 Linux 이미지 검증을 대신하지 않는다.

실행 검사를 재현하려면 검토한 Nginx 실행 파일의 절대 경로를 `NGINX_TEST_BINARY`
환경변수에 넣고 같은 unittest 명령을 실행한다. 설정하지 않으면 실행 검사만 skip한다.
테스트에는 cryptography가 필요하다. 테스트가 생성한 인증서·개인키는 임시 폴더에서
사용 후 지우며 실행 파일이나 키를 저장소에 커밋하지 않는다.

근거: [Nginx proxy_pass URI 전달 규칙](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass),
[TLS 설정](https://nginx.org/en/docs/http/ngx_http_ssl_module.html),
[요청 버퍼링](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_request_buffering),
[DNS-01 검증](https://letsencrypt.org/docs/challenge-types/#dns-01-challenge).
