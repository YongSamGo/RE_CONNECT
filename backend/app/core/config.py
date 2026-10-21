"""환경변수 설정.

값은 루트 `.env` 또는 실행 환경의 환경변수에서 읽는다. `.env`는 모든 서비스가 함께 쓰므로
이 서비스가 모르는 항목은 무시한다. 비밀값이 생기면 `SecretStr`로 받아 로그·repr에 드러나지 않게 한다.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, IPvAnyAddress, SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def default_env_file(config_path: Path) -> Path | None:
    """backend/app/core/config.py 기준 저장소 루트의 .env.

    컨테이너처럼 패키지가 얕은 경로에 놓이면 루트를 계산할 수 없으므로 None을 돌려주고 환경변수만 쓴다.
    파일이 없어도 pydantic-settings는 환경변수만 읽는다.
    """
    parents = config_path.resolve().parents
    return parents[3] / ".env" if len(parents) > 3 else None


_ROOT_ENV_FILE = default_env_file(Path(__file__))


def canonical_origin(value: str) -> str:
    if not value.isascii() or not value.isprintable() or any(char in value for char in (" ", "\\", ",", "?", "#")):
        raise ValueError("허용하지 않는 Origin 형식")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ValueError("허용하지 않는 Origin 형식") from None
    if (
        parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username is not None
        or parsed.password is not None or parsed.path or parsed.query or parsed.fragment
    ):
        raise ValueError("Origin에는 scheme과 host 및 port만 허용합니다")
    host = parsed.hostname.lower()
    host = f"[{host}]" if ":" in host else host
    suffix = f":{port}" if port is not None and port != (443 if parsed.scheme == "https" else 80) else ""
    return f"{parsed.scheme}://{host}{suffix}"


class Settings(BaseSettings):
    kakao_rest_api_key: SecretStr | None = None
    kakao_client_secret: SecretStr | None = None
    kakao_app_id: int | None = Field(default=None, gt=0)
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # 기본값을 production으로 두어, 설정을 빠뜨려도 개발용 기능(API 문서 화면 등)이 켜지지 않게 한다.
    app_env: Literal["development", "test", "production"] = "production"

    database_url: SecretStr | None = None
    redis_url: SecretStr | None = None
    # 32바이트 HMAC 키를 hex 64자로 공급한다. Redis 한도 키에 원 IP를 넣지 않는다.
    request_limit_key: SecretStr | None = None
    # 운영자가 런타임 정지·배출을 확인한 Redis 제어 레코드의 세대. 자동 생성하지 않는다.
    inference_control_epoch: UUID | None = None

    # 실제 운영 안내문(#9)을 확정한 뒤 설정한다. 예제 버전을 기본값으로 승인하지 않는다.
    ai_notice_version: str | None = Field(default=None, pattern=r"^[a-z0-9._-]{1,32}$", max_length=32)
    storage_notice_version: str | None = Field(default=None, pattern=r"^[a-z0-9._-]{1,32}$", max_length=32)
    # 확정 안내문의 공개 텍스트. 기본 미설정; 안내문 버전만으로 실제 화면을 활성화하지 않는다.
    consent_notices_json: str | None = Field(default=None, max_length=65536, repr=False)
    # DB·소스·DB 백업 밖에서 제공하는 키 버전 → base64 32바이트 master key의 JSON.
    data_encryption_keys: SecretStr | None = None
    data_encryption_active_key_id: str | None = None
    # POSIX 개발 시험용. 운영 보관 위치/권한/백업 분리가 확정된 어댑터는 별도 연결한다.
    deletion_journal_directory: Path | None = None

    # 상태 확인에서 구성 요소 하나를 기다리는 최대 시간(초).
    health_check_timeout_seconds: float = 2.0

    # 내부 Ollama (W04-02). 주소는 Compose 내부 서비스로 고정하고 사용자 요청으로 바꾸지 않는다 (Plan/05 §2).
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "qwen3:4b"
    # 요청 하나의 전체 시간(초). AI 처리 제한(60초, Plan/05 §3)을 넘지 않는다.
    ollama_timeout_seconds: float = Field(default=60.0, gt=0, le=60)
    # 출력 토큰 상한. 넘으면 응답이 잘리고(`done_reason=length`) 형식 오류로 처리한다.
    ollama_num_predict: int = Field(default=2048, gt=0, le=8192)
    ollama_num_ctx: int = Field(default=16384, ge=12288, le=32768)
    # 구조화 추출은 추론 과정을 쓰지 않는다 (Plan/03 §3). 모델이 think를 지원하지 않으면 None으로 두어 보내지 않는다.
    ollama_think: bool | None = False
    ollama_max_response_bytes: int = Field(default=1_048_576, gt=0)

    # 프론트와 API가 공유하는 단일 출처. 비어 있으면 API 변경 요청은 거절한다.
    public_origin: str | None = None
    # Uvicorn의 전달 헤더를 신뢰할 직접 연결 프록시 IP만 허용한다. wildcard/CIDR 기본 신뢰 없음.
    trusted_proxy_ips: list[IPvAnyAddress] = Field(default_factory=list, max_length=10)

    @field_validator("public_origin")
    @classmethod
    def _public_origin(cls, value: str | None, info: ValidationInfo) -> str | None:
        if value is None:
            return None
        origin = canonical_origin(value)
        if not origin.startswith("https://") and info.data.get("app_env") != "development":
            raise ValueError("운영 Origin은 HTTPS여야 합니다")
        return origin

    @field_validator("ollama_base_url")
    @classmethod
    def _internal_origin_only(cls, value: str) -> str:
        """경로·쿼리·계정 정보가 없는 http(s) 출처만 받는다. 끝의 `/`는 뗀다."""
        url = urlsplit(value)
        if url.scheme not in ("http", "https") or not url.hostname:
            raise ValueError("ollama_base_url은 http(s) 주소여야 합니다")
        if url.username or url.password or url.query or url.fragment or url.path not in ("", "/"):
            raise ValueError("ollama_base_url에는 출처(scheme://host:port)만 적습니다")
        return value.rstrip("/")

    @property
    def docs_enabled(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
