"""Export an in-process response from the real public region router for #19.

No app settings, .env, DB, model or listening socket is needed. This is a router
contract check, not an end-to-end test of deployment or application middleware.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.contracts.regions import Region  # noqa: E402
from app.modules.regions.router import router  # noqa: E402


def main() -> None:
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    with TestClient(app) as client:
        response = client.get("/api/v1/regions")
        response.raise_for_status()
        body = response.json()
        # Verify every returned identifier is also accepted by backend Region.
        selections = [
            Region(province=province["id"], district=district["id"]).model_dump(mode="json")
            for province in body["provinces"]
            for district in province["districts"]
        ]
        print(json.dumps({
            "status": response.status_code,
            "content_type": response.headers["content-type"],
            "body": body,
            "openapi": app.openapi(),
            "selections": selections,
        }, ensure_ascii=True))


if __name__ == "__main__":
    main()
