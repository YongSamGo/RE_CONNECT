"""가상 체험과 실제 Redis/SQLite/API로 초안 응답을 프론트 계약에 대조한다."""

import json
import os
from pathlib import Path
import sys
from unittest.mock import patch
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.core.config import Settings  # noqa: E402

with patch("app.core.config.get_settings", return_value=Settings(_env_file=None, app_env="test")):
    from app.main import create_app
    from tests.test_admission import with_redis
    from tests.test_consents import csrf
    from tests.test_journey_drafts import body, setup
    from tests.persistence_helpers import open_test_database

import httpx  # noqa: E402


async def scenario(admission, admission_store, redis):
    with open_test_database("sqlite") as db:
        issued, sessions, journeys, journey, identity, runtime, service = await setup(admission, admission_store, redis, db)
        app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
        app.state.session_service, app.state.admission_service, app.state.draft_service = sessions, admission, service
        result = {}
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://testserver") as client:
                client.cookies.set("__Host-rc_session", issued.token)
                await client.get("/api/v1/me")
                # 수동 작성은 추론 동의 없이 동작해야 하며 AI 호출은 거절한다.
                await redis.hdel(journeys.store.session_key(issued.session.digest), "ai_notice_version", "ai_granted_ms")
                path = f"/api/v1/journeys/{journey.journey_id}/drafts"
                headers = {**csrf(client), "Idempotency-Key": str(uuid4())}
                denied = await client.post(path, json=body("generate").model_dump(mode="json"), headers=headers)
                result["ai_without_consent"] = denied.status_code
                response = await client.post(path, json=body().model_dump(mode="json"), headers=headers)
                assert response.status_code == 201, response.text
                result["created"] = response.json()
                assert (await client.post(path, json=body().model_dump(mode="json"), headers=headers)).json() == response.json()
                target = path + "/" + response.json()["draft_id"]
                edited_body = {"base_revision": 1, "self_introduction": "가상 도서관 경험을 정리했습니다.", "motivation": "가상 공고의 활동을 희망합니다."}
                response = await client.patch(target, json=edited_body, headers=csrf(client))
                assert response.status_code == 200, response.text
                result["edited"] = response.json()
                response = await client.post(target + "/approve", json={"base_revision": 2}, headers=csrf(client))
                assert response.status_code == 200, response.text
                result["approved"] = response.json()
                result["stale_patch"] = (await client.patch(target, json=edited_body, headers=csrf(client))).status_code
                response = await client.get(target)
                assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
                result["current"] = response.json()
                result["inference_calls"] = runtime.calls
                response = await client.patch(target, json={**edited_body, "base_revision": 3, "motivation": "수정한 가상 지원동기"}, headers=csrf(client))
                assert response.status_code == 200, response.text
                result["changed"] = response.json()
                other = await sessions.issue()
                client.cookies.set("__Host-rc_session", other.token)
                result["other_owner"] = (await client.get(target)).status_code
        finally:
            await journeys.end(issued.session, journey.journey_id)
        print(json.dumps(result, ensure_ascii=True))


if not os.environ.get("PERSISTENCE_TEST_REDIS_URL"):
    raise RuntimeError("PERSISTENCE_TEST_REDIS_URL must point to an isolated test Redis")
with_redis(scenario)
