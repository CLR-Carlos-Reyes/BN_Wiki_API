"""
wiki_service.py
---------------
Orchestrates the full request pipeline:
  1. Check Redis cache
  2. Fetch raw wikitext from Miraheze MediaWiki API
  3. Parse + normalise
  4. Store in cache with TTL
  5. Return typed response model
"""

import logging
from typing import Literal

from app.core.cache import cache_get, cache_set
from app.models.wiki_models import (
    BuildingResponse,
    SearchResponse,
    SearchResult,
    UnitResponse,
)
from app.services import parser, wiki_client

logger = logging.getLogger(__name__)

PageKind = Literal["unit", "building"]

# Cache key prefixes
_PREFIX: dict[PageKind, str] = {
    "unit": "bn:unit:",
    "building": "bn:building:",
}


# ---------------------------------------------------------------------------
# Unit
# ---------------------------------------------------------------------------

async def get_unit(page_title: str) -> UnitResponse | None:
    cache_key = _PREFIX["unit"] + _normalise_key(page_title)

    # 1. Cache check
    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("Serving unit '%s' from cache", page_title)
        result = UnitResponse(**cached)
        result.cached = True
        return result

    # 2. Fetch wikitext
    wikitext = await wiki_client.fetch_wikitext(page_title)
    if wikitext is None:
        return None

    # 3. Parse
    unit = parser.parse_unit(wikitext, page_title)

    # 4. Cache store
    await cache_set(cache_key, unit.model_dump())

    return unit


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------

async def get_building(page_title: str) -> BuildingResponse | None:
    cache_key = _PREFIX["building"] + _normalise_key(page_title)

    cached = await cache_get(cache_key)
    if cached is not None:
        logger.info("Serving building '%s' from cache", page_title)
        result = BuildingResponse(**cached)
        result.cached = True
        return result

    wikitext = await wiki_client.fetch_wikitext(page_title)
    if wikitext is None:
        return None

    building = parser.parse_building(wikitext, page_title)
    await cache_set(cache_key, building.model_dump())

    return building


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

async def search(query: str, limit: int = 10) -> SearchResponse:
    cache_key = f"bn:search:{_normalise_key(query)}:{limit}"

    cached = await cache_get(cache_key)
    if cached is not None:
        return SearchResponse(**cached)

    raw_results = await wiki_client.search_pages(query, limit=limit)
    results = [
        SearchResult(
            title=r["title"],
            snippet=_strip_html(r.get("snippet", "")),
        )
        for r in raw_results
    ]
    response = SearchResponse(query=query, results=results)
    await cache_set(cache_key, response.model_dump(), ttl=600)  # shorter TTL for search
    return response


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise_key(title: str) -> str:
    """Lower-case, spaces → underscores for consistent cache keys."""
    return title.strip().lower().replace(" ", "_")


def _strip_html(text: str) -> str:
    """Remove MediaWiki HTML snippets from search results."""
    import re
    return re.sub(r"<[^>]+>", "", text).strip()