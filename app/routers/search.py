from fastapi import APIRouter, Query

from app.models.wiki_models import SearchResponse
from app.services import wiki_service

router = APIRouter(prefix="/search", tags=["Search"])


@router.get(
    "",
    response_model=SearchResponse,
    summary="Search the wiki",
    description="Full-text search across all Battle Nations wiki pages.",
)
async def search(
    q: str = Query(..., description="Search query, e.g. 'sniper' or 'barracks'"),
    limit: int = Query(10, ge=1, le=50, description="Max number of results"),
) -> SearchResponse:
    return await wiki_service.search(q, limit=limit)