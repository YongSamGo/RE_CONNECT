# 운영 API 이미지 (#93 W12-04). 저장소 루트에서:
#   docker build -t reconnect-backend:local backend
# 베이스는 speech/Dockerfile과 같은 digest로 고정한다. 비밀값은 이미지에 넣지 않고 실행 시 env_file로 받는다.
FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS build
WORKDIR /build
COPY requirements.txt ./
# 해시 잠금 그대로, 소스 빌드 없이 wheel만 설치한다 (설치 스크립트 실행 차단).
RUN python -m venv --without-pip /opt/venv \
    && python -m pip --python /opt/venv install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

FROM python:3.12.15-slim-trixie@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1 AS runtime
WORKDIR /app
RUN python -m pip uninstall --yes pip
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 PYTHONUNBUFFERED=1 PATH=/opt/venv/bin:$PATH
COPY --from=build /opt/venv /opt/venv
COPY app ./app
COPY migrations ./migrations
# 운영 관리 명령(manage_*.py)은 이름을 나열하지 않고 모두 담는다. 새 명령(보관 정리·감사·백업 등)이 이미지에서 빠지지 않게 한다.
COPY alembic.ini manage_*.py ./
USER 10001:10001
EXPOSE 8000
# 내부 전용 /health/ready (DB·Redis 확인). 503이면 urlopen이 예외를 내 unhealthy가 된다.
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=3 \
    CMD ["/opt/venv/bin/python", "-I", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/ready', timeout=4)"]
ENTRYPOINT ["/opt/venv/bin/python", "-B", "-m", "app", "--host", "0.0.0.0"]
