"""공고 태그 검수용 사전도 운영자 역할·MFA 경계를 통과해야 한다."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.contracts.roles import CatalogRole
from app.core.business_errors import AppError
from tests.test_admin_opportunities import Operators, http_app


@pytest.mark.parametrize("outcome,status", [(None, 401), ("FORBIDDEN", 403), ("MFA_REQUIRED", 403), ("SESSION_EXPIRED", 401)])
def test_catalog_denies_access_before_reading_roles(outcome, status):
    app, client = http_app()
    lookup = AsyncMock(side_effect=AssertionError("인가 전 사전 조회"))
    app.state.role_service = SimpleNamespace(catalog_entries=lookup)
    if outcome is not None:
        app.state.member_service = Operators(outcome)
    response = client.get("/api/v1/admin/role-catalog")
    assert response.status_code == status
    lookup.assert_not_awaited()


def test_catalog_returns_only_review_fields_and_does_not_cache():
    app, client = http_app()
    app.state.member_service = Operators(SimpleNamespace(id=uuid4()))
    role = CatalogRole(id="library_assistant", name="자료 정리 도우미", description="합성 검수 역할",
                       skill_tags=["자료 정리"], aliases=[], experience_rules=[])
    lookup = AsyncMock(return_value=[role])
    app.state.role_service = SimpleNamespace(catalog_entries=lookup)
    response = client.get("/api/v1/admin/role-catalog")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == {"items": [{"id": role.id, "name": role.name, "description": role.description,
                                          "skill_tags": ["자료 정리"]}]}
    lookup.assert_awaited_once_with()


def test_catalog_failure_does_not_return_a_fallback_dictionary():
    app, client = http_app()
    app.state.member_service = Operators(SimpleNamespace(id=uuid4()))
    app.state.role_service = SimpleNamespace(catalog_entries=AsyncMock(side_effect=AppError("SERVICE_UNAVAILABLE")))
    response = client.get("/api/v1/admin/role-catalog")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
