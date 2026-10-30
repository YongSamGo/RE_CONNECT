"""운영자 경로에 개인 본문 기능이 없는지 (W07-06 · #57 "개인 본문 조회 경로 검토").

`/admin/*` 경로와 응답 칸을 검토한 목록으로 고정한다. 운영자 경로나 응답 칸이 새로 생기면 이 시험이
실패하므로, 개인 프로필·지원서·대화 본문을 운영자에게 내보내지 않는지 다시 검토하고 목록을 고친다.
"""

from fastapi.routing import iter_route_contexts

from app.core.config import Settings
from app.main import create_app
from app.modules.operators.models import MfaStatus

REVIEW_RESULT = {"id", "version", "review_status", "reviewed_at"}
AUDIT_LIST = {"items", "page", "page_size", "total",
              "event_id", "at", "actor_id", "actor_role", "action", "target_type", "target_id", "result", "request_id"}
ADMIN_OPPORTUNITY_LIST = {"items", "page", "page_size", "total", "id", "version", "title", "organization_name",
                          "recruitment_status", "review_status", "important_change", "published_version",
                          "source_checked_at", "updated_at"}
ADMIN_OPPORTUNITY = {
    "id", "version", "external_id", "source_id", "source", "title", "organization_name", "activity_type", "is_public_job",
    "role_tags", "skill_tags", "activity_region", "province", "district", "location_text", "remote_allowed",
    "schedule_text", "hours_per_week", "paid", "compensation_text", "description_text", "requirements",
    "required_documents", "application_method", "application_instructions", "application_url", "source_url",
    "deadline_date", "deadline_at", "recruitment_status", "review_status", "important_change", "changed_fields",
    "published_version", "published_content", "source_checked_at", "updated_at", "source_evidence", "clarity",
    "field", "value", "content", "name", "operator", "group_id", "group_operator", "reference_date",
}
ADMIN_REPORT = {"id", "report_id", "version", "type", "status", "note", "resolution_note", "opportunity",
                "opportunity_title", "created_at", "updated_at"}
REVIEWED = {
    ("GET", "/api/v1/admin/role-catalog"): {"items", "id", "name", "description", "skill_tags"},
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/approve"): REVIEW_RESULT,
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/reject"): REVIEW_RESULT,
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/hide"): REVIEW_RESULT,
    ("POST", "/api/v1/admin/opportunities/{opportunity_id}/close"): REVIEW_RESULT,
    ("GET", "/api/v1/admin/audit"): AUDIT_LIST,
    ("POST", "/api/v1/admin/mfa/verify"): {"mfa_verified", "expires_at"},
    ("GET", "/api/v1/admin/opportunities"): ADMIN_OPPORTUNITY_LIST,
    ("POST", "/api/v1/admin/opportunities"): ADMIN_OPPORTUNITY,
    ("GET", "/api/v1/admin/opportunities/{opportunity_id}"): ADMIN_OPPORTUNITY,
    ("PATCH", "/api/v1/admin/opportunities/{opportunity_id}"): ADMIN_OPPORTUNITY,
    ("GET", "/api/v1/admin/reports"): ADMIN_REPORT | {"items", "page", "page_size", "total"},
    ("PATCH", "/api/v1/admin/reports/{report_id}"): ADMIN_REPORT,
}
# response_model 없이 JSONResponse를 직접 만드는 경로는 실제로 쓰는 응답 모델로 본다.
RESPONSE_MODELS = {("POST", "/api/v1/admin/mfa/verify"): MfaStatus}
# 회원 개인 자료 계약에서 쓰는 본문 칸 이름. 운영자 응답에는 하나도 없어야 한다.
PERSONAL = {"profile", "experiences", "self_introduction", "motivation", "transcript", "messages", "content",
            "answers", "details", "note", "resolution_note", "phone", "email", "name", "birth_date"}
# 검토 후 허용한 같은 이름의 칸. 회원 개인 자료가 아니라 경로마다 뜻이 다르다.
# - 공고 경로: content는 공고 원문 내용(요건·근거 묶음), name은 기관·출처 이름이다.
# - 신고 경로: note는 신고 설명, resolution_note는 처리 사유다. W07-05 설계상 운영자가 처리하려고 보는 칸이며,
#   암호화해 저장하고 종결 30일 뒤 지운다(docs/data/persistence.md). 다른 운영자 경로에서는 계속 막는다.
_OPPORTUNITY_ALLOWED = {"content", "name"}
_REPORT_ALLOWED = {"note", "resolution_note"}
PERSONAL_ALLOWED = {
    # 역할 사전의 name은 역할 이름이며 회원 이름을 반환하지 않는다.
    ("GET", "/api/v1/admin/role-catalog"): {"name"},
    ("POST", "/api/v1/admin/opportunities"): _OPPORTUNITY_ALLOWED,
    ("GET", "/api/v1/admin/opportunities/{opportunity_id}"): _OPPORTUNITY_ALLOWED,
    ("PATCH", "/api/v1/admin/opportunities/{opportunity_id}"): _OPPORTUNITY_ALLOWED,
    ("GET", "/api/v1/admin/reports"): _REPORT_ALLOWED,
    ("PATCH", "/api/v1/admin/reports/{report_id}"): _REPORT_ALLOWED,
}


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
        model = route.response_model or RESPONSE_MODELS[key]
        names = property_names(model.model_json_schema())
        assert names == REVIEWED[key], key
        assert not names & (PERSONAL - PERSONAL_ALLOWED.get(key, set())), key
