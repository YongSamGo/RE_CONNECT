"""지원 지역 목록 경로.

프로필 지역 입력과 공고 검색이 같은 목록을 쓴다(D15). 로그인 없이 볼 수 있는 공개 정적 자료라 화면이 캐시해도 된다.
"""

from fastapi import APIRouter, Response

from app.contracts.regions import REGION_CATALOG, RegionCatalog

router = APIRouter(tags=["공고"])

# 목록이 바뀌면 version이 올라간다. 하루가 지나면 화면이 다시 받는다.
_CACHE_CONTROL = "public, max-age=86400"


@router.get("/regions", response_model=RegionCatalog, operation_id="listRegions")
async def list_regions(response: Response) -> RegionCatalog:
    response.headers["Cache-Control"] = _CACHE_CONTROL
    return REGION_CATALOG
