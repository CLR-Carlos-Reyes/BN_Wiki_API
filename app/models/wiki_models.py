from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------

class AttackInfo(BaseModel):
    name: str
    power: int | None = None
    offense: int | None = None
    damage_type: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

class RankStats(BaseModel):
    rank: int
    hp: int | None = None
    armor: int | None = None
    offense: int | None = None
    defense: int | None = None
    attacks: list[AttackInfo] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class UnitResponse(BaseModel):
    name: str
    page_title: str
    unit_type: str | None = None        # Soldier, Vehicle, etc.
    description: str | None = None
    ranks: list[RankStats] = Field(default_factory=list)
    raw_template_params: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False


# ---------------------------------------------------------------------------
# Buildings
# ---------------------------------------------------------------------------

class BuildingProduction(BaseModel):
    resource: str
    amount: int | None = None
    period_seconds: int | None = None   # production cycle in seconds


class BuildingResponse(BaseModel):
    name: str
    page_title: str
    building_type: str | None = None    # Barracks, Factory, etc.
    description: str | None = None
    gold_cost: int | None = None
    xp_reward: int | None = None
    production: list[BuildingProduction] = Field(default_factory=list)
    raw_template_params: dict[str, Any] = Field(default_factory=dict)
    cached: bool = False


# ---------------------------------------------------------------------------
# Generic / search
# ---------------------------------------------------------------------------

class SearchResult(BaseModel):
    title: str
    snippet: str | None = None


class SearchResponse(BaseModel):
    query: str
    results: list[SearchResult]