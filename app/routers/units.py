from fastapi import APIRouter, HTTPException

from app.models.wiki_models import UnitResponse
from app.services import wiki_service

router = APIRouter(prefix="/units", tags=["Units"])


@router.get(
    "/{page_title}",
    response_model=UnitResponse,
    summary="Get unit stats by wiki page title",
)
async def get_unit(page_title: str) -> UnitResponse:
    unit = await wiki_service.get_unit(page_title)
    if unit is None:
        raise HTTPException(
            status_code=404,
            detail=f"Unit page '{page_title}' not found on the wiki.",
        )
    return unit
# 6/6/2026