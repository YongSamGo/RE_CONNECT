"""Run the actual app locally for HTTP contract tests, without reading .env."""

import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

import uvicorn  # noqa: E402

from app.core.config import Settings  # noqa: E402


def main() -> None:
    port = int(sys.argv[1])
    if not 1 <= port <= 65535:
        raise ValueError("Invalid test port")
    settings = Settings(_env_file=None, app_env="test")
    # main.py also constructs its module-level app during import. Use the same
    # explicit settings there; never load a developer's .env for a test server.
    with patch("app.core.config.get_settings", return_value=settings):
        from app.main import create_app
    app = create_app(settings)
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, log_level="warning")


if __name__ == "__main__":
    main()
