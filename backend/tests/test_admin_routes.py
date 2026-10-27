"""운영자 경로에 개인 본문 기능이 없는지 (W07-06 · #57 "개인 본문 조회 경로 검토").

`/admin/*` 경로와 응답 칸을 검토한 목록으로 고정한다. 운영자 경로나 응답 칸이 새로 생기면 이 시험이
실패하므로, 개인 프로필·지원서·대화 본문을 운영자에게 내보내지 않는지 다시 검토하고 목록을 고친다.
"""

from fastapi.routing import iter_route_contexts

from app.core.config import Settings
from app.main import create_app

REVIEW_RESULT = {"id", "version", "review_status", "reviewed_at"}
AUDIT_LIST = {"items", "page", "page_size", "total",
              "event_id", "at", "actor_id", "actor_role", "action", "target_type", "target_id", "result", "request_id"}
REVIEWED = {
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/approve"): REVIEW_RESULT,
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/reject"): REVIEW_RESULT,
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/hide"): REVIEW_RESULT,
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/close"): REVIEW_RESULT,
    ("GET", "/api/v1/admin/audit"): AUDIT_LIST,
}
# 회원 개인 자료 계약에서 쓰는 본문 칸 이름. 운영자 응답에는 하나도 없어야 한다.
PERSONAL = {"profile", "experiences", "self_introduction", "motivation", "transcript", "messages", "content",
            "answers", "details", "note", "resolution_note", "phone", "email", "name", "birth_date"}


def admin_routes():
    app = create_app(Settings(_env_file=None, app_env="test", public_origin="https://testserver"))
    routes = {}
    for route in iter_route_contexts(app.routes):
        if route.path is not None and "/admin" in route.path:
            for method in route.methods or ():
                routes[(method, route.path)] = route
    return routes


def property_names(schema, definitions=None):
    definitions = schema.get("$defs", {}) if definitions is None else definitions
    names = set()
    for key, value in schema.items():
        if key == "properties":
            names |= set(value)
        if key == "$ref":
            names |= property_names(definitions[value.rsplit("/", 1)[1]], definitions)
        elif isinstance(value, dict):
            names |= property_names(value, definitions)
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    names |= property_names(item, definitions)
    return names


def test_admin_routes_are_the_reviewed_set():
    assert set(admin_routes()) == set(REVIEWED)


def test_admin_responses_carry_only_reviewed_minimal_fields():
    for key, route in admin_routes().items():
        names = property_names(route.response_model.model_json_schema())
        assert names == REVIEWED[key], key
        assert not names & PERSONAL, key
