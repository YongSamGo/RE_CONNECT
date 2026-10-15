"""환경변수 설정.

값은 루트 `.env` 또는 실행 환경의 환경변수에서 읽는다. `.env`는 모든 서비스가 함께 쓰므로
이 서비스가 모르는 항목은 무시한다. 비밀값이 생기면 `SecretStr`로 받아 로그·repr에 드러나지 않게 한다.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def default_env_file(config_path: Path) -> Path | None:
    """backend/app/core/config.py 기준 저장소 루트의 .env.

    컨테이너처럼 패키지가 얕은 경로에 놓이면 루트를 계산할 수 없으므로 None을 돌려주고 환경변수만 쓴다.
    파일이 없어도 pydantic-settings는 환경변수만 읽는다.
    """
    parents = config_path.resolve().parents
    return parents[3] / ".env" if len(parents) > 3 else None


_ROOT_ENV_FILE = default_env_file(Path(__file__))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_ROOT_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # 기본값을 production으로 두어, 설정을 빠뜨려도 개발용 기능(API 문서 화면 등)이 켜지지 않게 한다.
    app_env: Literal["development", "test", "production"] = "production"

    # 상태 확인에서 구성 요소 하나를 기다리는 최대 시간(초).
    health_check_timeout_seconds: float = 2.0

    @property
    def docs_enabled(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()
