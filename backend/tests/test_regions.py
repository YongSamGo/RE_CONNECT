"""지원 지역 목록 경로 (`GET /api/v1/regions`)."""

from fastapi.testclient import TestClient

from app.contracts.regions import REGION_CATALOG_VERSION


def test_regions_returns_catalog_without_login(client: TestClient) -> None:
    response = client.get("/api/v1/regions")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == REGION_CATALOG_VERSION
    assert [province["id"] for province in body["provinces"]] == ["seoul", "gyeonggi", "incheon"]
    seoul = body["provinces"][0]
    assert seoul["name"] == "서울특별시"
    assert {"id": "yongsan", "name": "용산구"} in seoul["districts"]
    assert response.headers["Cache-Control"].startswith("public")
    assert response.headers["X-Request-ID"].startswith("req_")


def test_regions_rejects_other_methods(client: TestClient) -> None:
    # 405는 계약 코드가 없어 404로 답한다 (backend/README.md 공통 동작).
    response = client.post("/api/v1/regions", json={"provinces": []})

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"
