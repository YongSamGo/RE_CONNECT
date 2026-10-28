"""지원 지역 목록과 `Region` (Plan/02 §2, `GET /regions`).

프로필의 희망·거주 지역, 공고 활동 지역, 거주 조건, 공고 검색이 모두 이 목록으로 검증한다.
화면은 `GET /api/v1/regions`로 같은 목록을 받는다.

- 시·도: 서울·경기·인천. 시·군·구 식별값은 영문 slug이고 같은 시·도 안에서만 유일하다.
- 경기도는 시·군 단위까지만 둔다. 수원·성남 등의 일반구는 나누지 않는다.
- 인천은 2026-07-01 행정체제 개편 뒤 기준이다(중구·동구 → 제물포구·영종구, 서구 → 서해구·검단구).
- 외부 출처의 지역코드는 출처마다 체계가 달라 여기 두지 않는다. 출처별 매핑은 수집기(#46)가 맡고,
  개편 전 코드처럼 하나로 정해지지 않는 값은 자동 확정하지 않는다.

목록을 바꾸면 `REGION_CATALOG_VERSION`을 올린다. 화면이 캐시한 목록을 새로 받게 하기 위해서다.
"""

from typing import Literal

from pydantic import BaseModel, Field, StrictStr, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from app.contracts.fields import CONTRACT_CONFIG

REGION_CATALOG_VERSION = "2026-10-16"

Province = Literal["seoul", "gyeonggi", "incheon"]

PROVINCE_NAMES: dict[Province, str] = {
    "seoul": "서울특별시",
    "gyeonggi": "경기도",
    "incheon": "인천광역시",
}

# (slug, 이름). 화면 표시 순서를 그대로 쓴다.
DISTRICTS: dict[Province, tuple[tuple[str, str], ...]] = {
    "seoul": (
        ("jongno", "종로구"),
        ("jung", "중구"),
        ("yongsan", "용산구"),
        ("seongdong", "성동구"),
        ("gwangjin", "광진구"),
        ("dongdaemun", "동대문구"),
        ("jungnang", "중랑구"),
        ("seongbuk", "성북구"),
        ("gangbuk", "강북구"),
        ("dobong", "도봉구"),
        ("nowon", "노원구"),
        ("eunpyeong", "은평구"),
        ("seodaemun", "서대문구"),
        ("mapo", "마포구"),
        ("yangcheon", "양천구"),
        ("gangseo", "강서구"),
        ("guro", "구로구"),
        ("geumcheon", "금천구"),
        ("yeongdeungpo", "영등포구"),
        ("dongjak", "동작구"),
        ("gwanak", "관악구"),
        ("seocho", "서초구"),
        ("gangnam", "강남구"),
        ("songpa", "송파구"),
        ("gangdong", "강동구"),
    ),
    "gyeonggi": (
        ("suwon", "수원시"),
        ("seongnam", "성남시"),
        ("uijeongbu", "의정부시"),
        ("anyang", "안양시"),
        ("bucheon", "부천시"),
        ("gwangmyeong", "광명시"),
        ("pyeongtaek", "평택시"),
        ("dongducheon", "동두천시"),
        ("ansan", "안산시"),
        ("goyang", "고양시"),
        ("gwacheon", "과천시"),
        ("guri", "구리시"),
        ("namyangju", "남양주시"),
        ("osan", "오산시"),
        ("siheung", "시흥시"),
        ("gunpo", "군포시"),
        ("uiwang", "의왕시"),
        ("hanam", "하남시"),
        ("yongin", "용인시"),
        ("paju", "파주시"),
        ("icheon", "이천시"),
        ("anseong", "안성시"),
        ("gimpo", "김포시"),
        ("hwaseong", "화성시"),
        ("gwangju", "광주시"),
        ("yangju", "양주시"),
        ("pocheon", "포천시"),
        ("yeoju", "여주시"),
        ("yeoncheon", "연천군"),
        ("gapyeong", "가평군"),
        ("yangpyeong", "양평군"),
    ),
    "incheon": (
        ("jemulpo", "제물포구"),
        ("yeongjong", "영종구"),
        ("michuhol", "미추홀구"),
        ("yeonsu", "연수구"),
        ("namdong", "남동구"),
        ("bupyeong", "부평구"),
        ("gyeyang", "계양구"),
        ("seo", "서해구"),
        ("geomdan", "검단구"),
        ("ganghwa", "강화군"),
        ("ongjin", "옹진군"),
    ),
}

_DISTRICT_IDS: dict[Province, frozenset[str]] = {
    province: frozenset(slug for slug, _ in districts) for province, districts in DISTRICTS.items()
}


def is_known_district(province: Province, district: str) -> bool:
    return district in _DISTRICT_IDS[province]


class Region(BaseModel):
    """시·도와 시·군·구. `district`가 `null`이면 해당 시·도 전체다."""

    model_config = CONTRACT_CONFIG

    province: Province
    district: StrictStr | None = Field(pattern=r"^[a-z0-9_]{2,40}$")

    @field_validator("district")
    @classmethod
    def _district_in_catalog(cls, district: str | None, info: ValidationInfo) -> str | None:
        # province가 이미 틀렸으면 그 오류만 낸다.
        province = info.data.get("province")
        if district is not None and province is not None and not is_known_district(province, district):
            raise PydanticCustomError("unknown_district", "지역 목록에 없는 시·군·구")
        return district


class DistrictEntry(BaseModel):
    model_config = CONTRACT_CONFIG

    id: str
    name: str


class ProvinceEntry(BaseModel):
    model_config = CONTRACT_CONFIG

    id: Province
    name: str
    districts: list[DistrictEntry]


class RegionCatalog(BaseModel):
    model_config = CONTRACT_CONFIG

    version: str
    provinces: list[ProvinceEntry]


REGION_CATALOG = RegionCatalog(
    version=REGION_CATALOG_VERSION,
    provinces=[
        ProvinceEntry(
            id=province,
            name=PROVINCE_NAMES[province],
            districts=[DistrictEntry(id=slug, name=name) for slug, name in districts],
        )
        for province, districts in DISTRICTS.items()
    ],
)
