"""
Wikitext parser for Battle Nations wiki pages.

Unit pages use:
  {{UnitProfile|unit type=Soldier|...}}   — basic info
  {{UnitRanksBox|hp=55;60;65;70;75;85|defense=50;55;...}}  — semicolon-separated per-rank stats
  {{AttackBox|name=Shoot|rank=1|damagetype=Piercing|mindmg=22|maxdmg=26|baseoffense=46}}

Building pages use:
  {{BuildingProfile|...}} or similar infobox
  {{BuildCost|gold=250|iron=5|time=360}}
"""

import logging
import re
from typing import Any

import mwparserfromhell

from app.models.wiki_models import (
    AttackInfo,
    BuildingProduction,
    BuildingResponse,
    RankStats,
    UnitResponse,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int(value: str | None) -> int | None:
    if value is None:
        return None
    cleaned = re.sub(r"[^\d]", "", str(value).strip())
    return int(cleaned) if cleaned else None


def _str(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)  # strip [[links]]
    s = re.sub(r"\{\{[^}]+\}\}", "", s).strip()               # strip {{templates}}
    return s or None


def _template_params(template) -> dict[str, str]:
    params: dict[str, str] = {}
    for param in template.params:
        key = str(param.name).strip()
        val = str(param.value).strip()
        params[key] = val
    return params


def _find_template(wikicode, *names: str):
    """Find the first template whose name matches any of the given names (case-insensitive)."""
    targets = [n.lower() for n in names]
    for t in wikicode.filter_templates():
        if str(t.name).strip().lower() in targets:
            return t
    return None


def _parse_semicolon_list(value: str | None) -> list:
    """
    Parse a semicolon-separated stat list like '55; 60; 65; 70; 75; 85'
    into a list of ints, one per rank.
    """
    if not value:
        return []
    parts = [p.strip() for p in value.split(";")]
    result = []
    for p in parts:
        cleaned = re.sub(r"[^\d]", "", p)
        result.append(int(cleaned) if cleaned else None)
    return result


# ---------------------------------------------------------------------------
# Unit parser
# ---------------------------------------------------------------------------

def parse_unit(wikitext: str, page_title: str) -> UnitResponse:
    wikicode = mwparserfromhell.parse(wikitext)

    # --- Profile (basic info) ---
    profile = _find_template(wikicode, "unitprofile")
    profile_params = _template_params(profile) if profile else {}

    unit_type = _str(profile_params.get("unit type") or profile_params.get("unit_type"))

    # --- UnitRanksBox (per-rank stats as semicolon lists) ---
    ranks_box = _find_template(wikicode, "unitranksbox")
    ranks: list[RankStats] = []

    if ranks_box:
        rp = _template_params(ranks_box)
        logger.debug("UnitRanksBox params for %s: %s", page_title, list(rp.keys()))

        hp_vals      = _parse_semicolon_list(rp.get("hp"))
        defense_vals = _parse_semicolon_list(rp.get("defense"))
        bravery_vals = _parse_semicolon_list(rp.get("bravery"))
        dodge_vals   = _parse_semicolon_list(rp.get("dodge"))
        armor_vals   = _parse_semicolon_list(rp.get("armor") or rp.get("armour"))
        offense_vals = _parse_semicolon_list(rp.get("offense"))
        uv_vals      = _parse_semicolon_list(rp.get("uv"))

        num_ranks = max(
            len(hp_vals), len(defense_vals), len(armor_vals),
            len(offense_vals), len(bravery_vals), 0
        )

        def _get(lst, idx):
            return lst[idx] if idx < len(lst) else None

        for i in range(num_ranks):
            extra = {}
            bravery = _get(bravery_vals, i)
            dodge = _get(dodge_vals, i)
            uv = _get(uv_vals, i)
            if bravery is not None:
                extra["bravery"] = bravery
            if dodge is not None:
                extra["dodge"] = dodge
            if uv is not None:
                extra["unit_value"] = uv

            ranks.append(RankStats(
                rank=i + 1,
                hp=_get(hp_vals, i),
                armor=_get(armor_vals, i),
                offense=_get(offense_vals, i),
                defense=_get(defense_vals, i),
                extra=extra,
            ))

    # --- AttackBox templates ---
    attacks_by_rank = _parse_attack_boxes(wikicode)
    for rank_stat in ranks:
        rank_stat.attacks = attacks_by_rank.get(rank_stat.rank, [])

    return UnitResponse(
        name=page_title,
        page_title=page_title,
        unit_type=unit_type,
        description=None,
        ranks=ranks,
        raw_template_params=profile_params,
    )


def _parse_attack_boxes(wikicode) -> dict:
    """Parse all {{AttackBox}} templates. Returns {unlock_rank: [AttackInfo, ...]}"""
    result: dict[int, list[AttackInfo]] = {}
    for t in wikicode.filter_templates():
        if str(t.name).strip().lower() != "attackbox":
            continue
        p = _template_params(t)
        unlock_rank = _int(p.get("rank")) or 1
        mindmg = _int(p.get("mindmg"))
        maxdmg = _int(p.get("maxdmg"))
        avg_power = None
        if mindmg is not None and maxdmg is not None:
            avg_power = (mindmg + maxdmg) // 2

        extra = {}
        for k, field in [("min_dmg", "mindmg"), ("max_dmg", "maxdmg"),
                          ("crit", "basecrit"), ("range", "range"),
                          ("ammo_used", "ammoused"), ("num_attacks", "numattacks"),
                          ("targets", "targets")]:
            v = p.get(field)
            if v:
                parsed = _int(v) if field not in ("range", "targets") else _str(v)
                if parsed is not None:
                    extra[k] = parsed

        attack = AttackInfo(
            name=_str(p.get("name")) or "Unknown",
            power=avg_power,
            offense=_int(p.get("baseoffense") or p.get("offense")),
            damage_type=_str(p.get("damagetype") or p.get("damage_type")),
            extra=extra,
        )
        result.setdefault(unlock_rank, []).append(attack)
    return result


# ---------------------------------------------------------------------------
# Building parser
# ---------------------------------------------------------------------------

RESOURCE_FIELD_ALIASES = {
    "iron": "Iron", "coal": "Coal", "oil": "Oil", "wood": "Wood",
    "food": "Food", "plasma": "Plasma", "titanium": "Titanium", "uranium": "Uranium",
}


def parse_building(wikitext: str, page_title: str) -> BuildingResponse:
    wikicode = mwparserfromhell.parse(wikitext)

    # Try common building profile template names
    profile = _find_template(wikicode, "buildingprofile", "building", "structure", "infobox")
    profile_params = _template_params(profile) if profile else {}

    # Cost info from {{BuildCost}}
    build_cost = _find_template(wikicode, "buildcost")
    cost_params = _template_params(build_cost) if build_cost else {}

    name = _str(profile_params.get("name")) or page_title
    building_type = _str(profile_params.get("type") or profile_params.get("building type"))
    description = _str(profile_params.get("description") or profile_params.get("desc"))

    gold_cost = _int(cost_params.get("gold") or profile_params.get("gold"))
    xp_reward = _int(cost_params.get("xp") or profile_params.get("xp"))

    production = _parse_building_production(profile_params, wikicode)

    all_params = {**profile_params, **cost_params}

    return BuildingResponse(
        name=name,
        page_title=page_title,
        building_type=building_type,
        description=description,
        gold_cost=gold_cost,
        xp_reward=xp_reward,
        production=production,
        raw_template_params=all_params,
    )


def _parse_building_production(params: dict, wikicode) -> list[BuildingProduction]:
    production: list[BuildingProduction] = []

    # Layout 1: production/produces field
    resource_name = _str(params.get("production") or params.get("produces") or params.get("resource"))
    if resource_name:
        production.append(BuildingProduction(
            resource=resource_name,
            amount=_int(params.get("amount") or params.get("productionamount")),
            period_seconds=_parse_time(params.get("time") or params.get("productiontime")),
        ))

    # Layout 2: per-resource keys (iron=10, irontime=3600)
    for field, label in RESOURCE_FIELD_ALIASES.items():
        if field in params:
            amount_val = _int(params.get(field))
            if amount_val is not None:
                production.append(BuildingProduction(
                    resource=label,
                    amount=amount_val,
                    period_seconds=_parse_time(params.get(f"{field}time")),
                ))

    return production


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

_TIME_PATTERNS = [
    (r"(\d+)\s*h(?:our)?s?", 3600),
    (r"(\d+)\s*m(?:in(?:ute)?s?)?", 60),
    (r"(\d+)\s*s(?:ec(?:ond)?s?)?", 1),
]


def _parse_time(value: str | None) -> int | None:
    if value is None:
        return None
    value = str(value).strip()
    if value.isdigit():
        return int(value)
    total = 0
    matched = False
    for pattern, multiplier in _TIME_PATTERNS:
        for m in re.finditer(pattern, value, re.I):
            total += int(m.group(1)) * multiplier
            matched = True
    return total if matched else None
# 6/6/2026