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

콜백 code/state·토큰·본문이 로그에 남지 않도록 Nginx 접근·오류 로그는 비활성이다.
오류 관측은 backend의 민감정보 제거 로그와 상태 검사로 수행한다.
API 캐시는 끄고 모든 응답에 `Cache-Control: no-store`를 설정한다.
업로드는 프록시 7MiB 한도와 backend 6MiB 음성 한도를 함께 적용한다.
본문 임시 경로는 tmpfs이며 API 응답은 버퍼링/디스크 저장하지 않는다.

배포 환경에서 `nginx -t` 후 다음을 확인해야 한다: 알려진 도메인의 TLS 성공,
다른 SNI·Host 거절, 화면 경로 직접 새로고침, 실제 JSON·음성 요청 경로 보존,
업로드 한도, 콜백의 캐시 금지와 로그 미기록.

로컬에서는 공식 Nginx Windows 1.30.6 실행 파일로 `nginx -t`와 실제 HTTPS 요청을
검사했다. 임시 인증서·루프백 backend를 사용해 SPA 경로, API 접두사·쿼리 보존,
음성 응답의 Content-Type, 전달 헤더 위조 제거, no-store, 413 본문 제한,
잘못된 SNI·Host 거절, 콜백 로그 미기록을 확인했다. 운영 Linux 이미지와 실제
애플리케이션·인증서·음성 서비스는 별도 통합 검증이 필요하다.

실행 검사를 재현하려면 검토한 Nginx 실행 파일의 절대 경로를 `NGINX_TEST_BINARY`
환경변수에 넣고 같은 unittest 명령을 실행한다. 설정하지 않으면 실행 검사만 skip한다.
테스트에는 cryptography가 필요하다. 테스트가 생성한 인증서·개인키는 임시 폴더에서
사용 후 지우며 실행 파일이나 키를 저장소에 커밋하지 않는다.

근거: [Nginx proxy_pass URI 전달 규칙](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass),
[TLS 설정](https://nginx.org/en/docs/http/ngx_http_ssl_module.html).
