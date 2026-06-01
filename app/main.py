import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.core.cache import close_redis
from app.core.config import settings
from app.routers import buildings, search, units
from app.services.wiki_client import close_client

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    logger.info("Starting up %s", settings.api_title)
    yield
    logger.info("Shutting down – closing connections")
    await close_client()
    await close_redis()


app = FastAPI(
    title=settings.api_title,
    version="1.0.0",
    description=(
        "REST API that extracts and normalises data from the "
        "[Battle Nations Wiki](https://battlenations.miraheze.org) "
        "via the MediaWiki API, with Redis caching."
    ),
    lifespan=lifespan,
)

app.include_router(units.router)
app.include_router(buildings.router)
app.include_router(search.router)


@app.get("/", tags=["Health"])
async def root() -> JSONResponse:
    return JSONResponse({"status": "ok", "service": settings.api_title})


@app.get("/health", tags=["Health"])
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})