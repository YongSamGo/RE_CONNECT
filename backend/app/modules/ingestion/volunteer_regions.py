"""1365 평가 표본에서 검수한 시도/시군구 코드 쌍 (#263·#264).

전국 코드표가 아니다. 특히 인천 개편 전 중구·동구·서구 코드를 새 구로 추정하지 않는다.
근거·확장 절차: docs/data/volunteer-region-codes.md.
"""

VERIFIED_REGIONS: dict[tuple[str, str], tuple[str, str]] = {
    ("6110000", "3030000"): ("seoul", "seongdong"),
    ("6110000", "3040000"): ("seoul", "gwangjin"),
    ("6110000", "3100000"): ("seoul", "nowon"),
    ("6410000", "3780000"): ("gyeonggi", "seongnam"),
    ("6410000", "3830000"): ("gyeonggi", "anyang"),
    ("6410000", "3940000"): ("gyeonggi", "goyang"),
    ("6410000", "4020000"): ("gyeonggi", "gunpo"),
    ("6280000", "3520000"): ("incheon", "yeonsu"),
    ("6280000", "3530000"): ("incheon", "namdong"),
}
