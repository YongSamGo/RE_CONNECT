# 운영 Nginx 이미지: React 빌드 결과만 담는다 (#93 W12-04). 저장소 루트에서:
#   docker build --build-context api=docs/api -t reconnect-frontend:local frontend
# 빌드 스크립트가 ../docs/api/openapi.yaml과 생성 타입을 대조하므로 계약 폴더를 별도 컨텍스트로 넘긴다.
# Nginx 설정(nginx.conf)·TLS 인증서는 이미지에 넣지 않고 실행 시 읽기 전용으로 연결한다 (infra/nginx, #91).
FROM node:24.22.1-trixie-slim@sha256:43b9ba1142b8dcf33fa8f922ca1be85714adc444e0586c7cf7726daaeabc1bea AS build
WORKDIR /src/frontend
COPY package.json package-lock.json ./
# 악성 패키지의 설치 스크립트가 빌드 중 실행되지 않게 한다 (CI와 같은 방식).
RUN npm ci --ignore-scripts --no-audit --no-fund
COPY --from=api openapi.yaml /src/docs/api/openapi.yaml
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.30.6-alpine@sha256:f5116ed4606f3eb015dd4a8e28cb9b351476dc0ad4bc6e9f93b19cec130cdf03 AS runtime
# 기본 예제 사이트(8080 리스너)와 정적 파일을 지워 운영 설정만 로드되게 한다.
# 실행에 필요 없는 curl을 빼고, 베이스 이후 나온 Alpine 보안 수정판을 반영한다 (릴리스 판정의 수정판 있는 HIGH).
USER root
RUN apk del --no-cache curl \
    && apk upgrade --no-cache \
    && rm -f /etc/nginx/conf.d/*.conf && rm -rf /usr/share/nginx/html/*
COPY --from=build /src/frontend/dist /usr/share/nginx/html
USER 101:101
EXPOSE 443
