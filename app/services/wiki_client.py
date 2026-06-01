import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Shared async client — initialised on first use
_client: httpx.AsyncClient | None = None

HEADERS = {
    "User-Agent": "BNWikiAPI/1.0 (https://github.com/yourname/bn-wiki-api; contact@example.com)"
}


async def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            base_url=settings.wiki_base_url,
            headers=HEADERS,
            timeout=15.0,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None


async def fetch_wikitext(title: str) -> str | None:
    """
    Fetch raw wikitext for *title* via the MediaWiki API.
    Returns None if the page does not exist.
    """
    client = await _get_client()
    params: dict[str, Any] = {
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "content",
        "rvslots": "main",
        "format": "json",
        "formatversion": "2",
    }
    logger.info("Fetching wikitext for page: %s", title)
    response = await client.get("", params=params)
    response.raise_for_status()

    data = response.json()
    pages: list[dict] = data.get("query", {}).get("pages", [])

    if not pages or pages[0].get("missing"):
        logger.warning("Page not found on wiki: %s", title)
        return None

    return pages[0]["revisions"][0]["slots"]["main"]["content"]


async def search_pages(query: str, limit: int = 10) -> list[dict]:
    """Full-text search — returns list of {title, snippet} dicts."""
    client = await _get_client()
    params: dict[str, Any] = {
        "action": "query",
        "list": "search",
        "srsearch": query,
        "srlimit": limit,
        "format": "json",
        "formatversion": "2",
    }
    response = await client.get("", params=params)
    response.raise_for_status()
    return response.json().get("query", {}).get("search", [])


async def fetch_category_members(category: str, limit: int = 100) -> list[str]:
    """Return page titles in a category (e.g. 'Category:Units')."""
    client = await _get_client()
    params: dict[str, Any] = {
        "action": "query",
        "list": "categorymembers",
        "cmtitle": category,
        "cmlimit": limit,
        "cmtype": "page",
        "format": "json",
        "formatversion": "2",
    }
    response = await client.get("", params=params)
    response.raise_for_status()
    members = response.json().get("query", {}).get("categorymembers", [])
    return [m["title"] for m in members]