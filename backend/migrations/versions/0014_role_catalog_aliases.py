"""역할 사전 별칭 보강 (W08-04 · #61, #285). 근거·원칙은 docs/data/role-catalog.md.

경험 추출이 역할 사전의 표준 태그를 고를 때 인용에 태그 이름이나 별칭이 있어야 하므로(#285), 평가 페르소나의
실제 발화 표현(택시, 부녀회장 등)을 별칭으로 더한다. 값은 실행 시점의 문서를 읽지 않도록 여기에 고정한다.
이미 배포된 DB에서는 별칭이 0009 시드 값과 같은 행만 고친다. 운영자가 고친 행은 그대로 둔다.
"""

from alembic import op
import sqlalchemy as sa

revision = "0014_role_catalog_aliases"
down_revision = "0013_report_handling"
branch_labels = None
depends_on = None

# 역할 ID → (0009 시드 별칭, 새 별칭)
_ALIASES = {
    "learning_mentor": (
        [{"alias": "공부 지도", "skill_tag": "학습 지도"}, {"alias": "학습지도", "skill_tag": "학습 지도"}, {"alias": "숙제 지도", "skill_tag": "학습 지도"}, {"alias": "초등교육", "skill_tag": "초등 교육"}],
        [{"alias": "공부 지도", "skill_tag": "학습 지도"}, {"alias": "학습지도", "skill_tag": "학습 지도"}, {"alias": "숙제 지도", "skill_tag": "학습 지도"}, {"alias": "초등교육", "skill_tag": "초등 교육"}, {"alias": "담임", "skill_tag": "학습 지도"}],
    ),
    "facility_manager": (
        [{"alias": "건물 관리", "skill_tag": "시설 관리"}, {"alias": "시설관리", "skill_tag": "시설 관리"}, {"alias": "전기 점검", "skill_tag": "전기 설비 점검"}, {"alias": "설비 점검", "skill_tag": "전기 설비 점검"}],
        [{"alias": "건물 관리", "skill_tag": "시설 관리"}, {"alias": "시설관리", "skill_tag": "시설 관리"}, {"alias": "전기 점검", "skill_tag": "전기 설비 점검"}, {"alias": "설비 점검", "skill_tag": "전기 설비 점검"}, {"alias": "관리사무소", "skill_tag": "시설 관리"}, {"alias": "관리소장", "skill_tag": "시설 관리"}],
    ),
    "visitor_guide": (
        [{"alias": "민원 응대", "skill_tag": "민원 처리"}, {"alias": "민원 안내", "skill_tag": "민원 처리"}, {"alias": "고객 상담", "skill_tag": "고객 응대"}],
        [{"alias": "민원 응대", "skill_tag": "민원 처리"}, {"alias": "민원 안내", "skill_tag": "민원 처리"}, {"alias": "고객 상담", "skill_tag": "고객 응대"}, {"alias": "은행 창구", "skill_tag": "고객 응대"}],
    ),
    "meal_assistant": (
        [{"alias": "급식 조리", "skill_tag": "단체 급식 조리"}, {"alias": "반찬 조리", "skill_tag": "조리"}, {"alias": "요리", "skill_tag": "조리"}],
        [{"alias": "급식 조리", "skill_tag": "단체 급식 조리"}, {"alias": "반찬 조리", "skill_tag": "조리"}, {"alias": "요리", "skill_tag": "조리"}, {"alias": "경로식당", "skill_tag": "단체 급식 조리"}, {"alias": "반찬 만드는", "skill_tag": "조리"}],
    ),
    "community_organizer": (
        [{"alias": "모임 운영", "skill_tag": "주민 모임 운영"}, {"alias": "부녀회 운영", "skill_tag": "주민 모임 운영"}, {"alias": "행사 운영", "skill_tag": "행사 진행"}],
        [{"alias": "모임 운영", "skill_tag": "주민 모임 운영"}, {"alias": "부녀회 운영", "skill_tag": "주민 모임 운영"}, {"alias": "행사 운영", "skill_tag": "행사 진행"}, {"alias": "부녀회장", "skill_tag": "주민 모임 운영"}],
    ),
    "digital_guide": (
        [{"alias": "스마트폰 교육", "skill_tag": "디지털 기기 교육"}, {"alias": "키오스크 안내", "skill_tag": "디지털 기기 교육"}, {"alias": "프로그램 개발", "skill_tag": "소프트웨어 개발"}],
        [{"alias": "스마트폰 교육", "skill_tag": "디지털 기기 교육"}, {"alias": "키오스크 안내", "skill_tag": "디지털 기기 교육"}, {"alias": "프로그램 개발", "skill_tag": "소프트웨어 개발"}, {"alias": "개발자", "skill_tag": "소프트웨어 개발"}],
    ),
    "mobility_supporter": (
        [{"alias": "차량 운행", "skill_tag": "운전"}, {"alias": "택시 운전", "skill_tag": "운전"}],
        [{"alias": "차량 운행", "skill_tag": "운전"}, {"alias": "택시 운전", "skill_tag": "운전"}, {"alias": "택시", "skill_tag": "운전"}],
    ),
    "care_assistant": (
        [{"alias": "어르신 돌봄", "skill_tag": "노인 돌봄"}, {"alias": "간병", "skill_tag": "환자 돌봄"}, {"alias": "요양 보조", "skill_tag": "노인 돌봄"}],
        [{"alias": "어르신 돌봄", "skill_tag": "노인 돌봄"}, {"alias": "간병", "skill_tag": "환자 돌봄"}, {"alias": "요양 보조", "skill_tag": "노인 돌봄"}, {"alias": "간호조무사", "skill_tag": "환자 돌봄"}],
    ),
}


def _table():
    return sa.table("role_definitions", sa.column("id", sa.String), sa.column("aliases", sa.JSON))


def _replace(before, after):
    table, bind = _table(), op.get_bind()
    current = dict(bind.execute(sa.select(table.c.id, table.c.aliases).where(table.c.id.in_(list(_ALIASES)))).all())
    for role_id, values in _ALIASES.items():
        if current.get(role_id) == values[before]:
            bind.execute(sa.update(table).where(table.c.id == role_id).values(aliases=values[after]))


def upgrade():
    _replace(0, 1)


def downgrade():
    """이 마이그레이션이 더한 별칭만 되돌린다. 그 뒤 운영자가 고친 행은 그대로 둔다."""
    _replace(1, 0)
