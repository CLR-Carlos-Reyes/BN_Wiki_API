from fastapi import APIRouter, HTTPException

from app.models.wiki_models import BuildingResponse
from app.services import wiki_service

router = APIRouter(prefix="/buildings", tags=["Buildings"])


@router.get(
    "/{page_title}",
    response_model=BuildingResponse,
    summary="Get building stats by wiki page title",
    description=(
        "Fetches and returns production output, gold cost, and XP reward "
        "for a Battle Nations building. Use the exact wiki page title, e.g. `Barracks` or `Iron_Mine`."
    ),
)
async def get_building(page_title: str) -> BuildingResponse:
    building = await wiki_service.get_building(page_title)
    if building is None:
        raise HTTPException(
            status_code=404,
            detail=f"Building page '{page_title}' not found on the wiki.",
        )
    return building