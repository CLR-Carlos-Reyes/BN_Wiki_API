"""
Wikitext parser for Battle Nations wiki pages.

The wiki uses MediaWiki templates (infoboxes) such as:
  {{Unit|hp1=100|hp2=120|...|armor1=0|...|offense1=50|...}}
  {{Building|gold=500|xp=25|production=Iron|amount=10|time=3600}}

Because exact template names / parameter names vary per page, this module
uses heuristics to detect the most likely infobox and extract numbers.

If the wiki template structure changes, update the field name lists below.
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

MAX_RANKS = 9  # Battle Nations max rank (boss-strike units go to 9)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _int(value: str | None) -> int | None:
    """Safely parse a wikitext field value to int."""
    if value is None:
        return None
    cleaned = re.sub(r"[^\d]", "", str(value).strip())
    return int(cleaned) if cleaned else None


def _str(value: str | None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    # Strip wikilinks [[Foo|Bar]] → Bar
    s = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", s)
    return s or None


def _template_params(template) -> dict[str, str]:
    """Return {param_name: param_value} for a parsed template."""
    params: dict[str, str] = {}
    for param in template.params:
        key = str(param.name).strip()
        val = str(param.value).strip()
        params[key] = val
    return params


def _find_infobox(wikicode, keywords: list[str]):
    """
    Return the first template whose name contains any of *keywords* (case-insensitive).
    Falls back to the largest template on the page if nothing matches.
    """
    all_templates = wikicode.filter_templates()
    for kw in keywords:
        kw_lower = kw.lower()
        for t in all_templates:
            if kw_lower in str(t.name).lower():
                return t

    # Fallback: template with the most parameters
    if all_templates:
        return max(all_templates, key=lambda t: len(t.params))
    return None


# ---------------------------------------------------------------------------
# Unit parser
# ---------------------------------------------------------------------------

UNIT_KEYWORDS = ["unit", "soldier", "vehicle", "infobox"]


def parse_unit(wikitext: str, page_title: str) -> UnitResponse:
    wikicode = mwparserfromhell.parse(wikitext)
    infobox = _find_infobox(wikicode, UNIT_KEYWORDS)

    if infobox is None:
        logger.warning("No unit infobox found for %s", page_title)
        return UnitResponse(name=page_title, page_title=page_title)

    params = _template_params(infobox)
    logger.debug("Unit params for %s: %s", page_title, list(params.keys()))

    # Friendly name (may differ from page title)
    name = _str(params.get("name")) or page_title

    # Unit type / classification
    unit_type = _str(
        params.get("type") or params.get("class") or params.get("unittype")
    )

    # Description / lore
    description = _str(params.get("description") or params.get("desc"))

    # Build per-rank stats
    # Common patterns: hp1..hp6, armor1..armor6, offense1..offense6, defense1..defense6
    ranks: list[RankStats] = []
    for r in range(1, MAX_RANKS + 1):
        suffix = str(r)

        hp = _int(params.get(f"hp{suffix}") or params.get(f"health{suffix}"))
        armor = _int(params.get(f"armor{suffix}") or params.get(f"armour{suffix}"))
        offense = _int(params.get(f"offense{suffix}") or params.get(f"off{suffix}"))
        defense = _int(params.get(f"defense{suffix}") or params.get(f"def{suffix}"))

        # Collect any extra rank-specific keys
        extra: dict[str, Any] = {}
        for key, val in params.items():
            if key.endswith(suffix) and key not in (
                f"hp{suffix}", f"health{suffix}",
                f"armor{suffix}", f"armour{suffix}",
                f"offense{suffix}", f"off{suffix}",
                f"defense{suffix}", f"def{suffix}",
            ):
                extra[key[: -len(suffix)]] = _str(val)

        # Only include ranks that have at least one value on the wiki
        if any(v is not None for v in (hp, armor, offense, defense)) or extra:
            # Per-rank attacks (attack1name, attack1power, ...)
            attacks = _parse_attacks_for_rank(params, r)
            ranks.append(
                RankStats(
                    rank=r,
                    hp=hp,
                    armor=armor,
                    offense=offense,
                    defense=defense,
                    attacks=attacks,
                    extra=extra,
                )
            )

    return UnitResponse(
        name=name,
        page_title=page_title,
        unit_type=unit_type,
        description=description,
        ranks=ranks,
        raw_template_params=params,
    )


def _parse_attacks_for_rank(params: dict[str, str], rank: int) -> list[AttackInfo]:
    """
    Look for attack entries keyed as attack{rank}name, attack{rank}power, etc.
    Also handles a flat single-rank format: attackname, attackpower.
    """
    attacks: list[AttackInfo] = []
    r = str(rank)

    # Multi-attack pattern: attack1_1name, attack1_2name  OR  attack11name ...
    # We look for any key matching attack{rank}*name
    attack_name_keys = [
        k for k in params
        if re.match(rf"attack{r}[\d_]*name", k, re.I)
    ]
    if not attack_name_keys and rank == 1:
        # Fallback: attackname (no rank suffix)
        attack_name_keys = [k for k in params if re.match(r"attack\d*name", k, re.I)]

    for name_key in attack_name_keys:
        prefix = name_key[: name_key.lower().index("name")]
        attacks.append(
            AttackInfo(
                name=_str(params[name_key]) or "Unknown",
                power=_int(params.get(f"{prefix}power")),
                offense=_int(params.get(f"{prefix}offense") or params.get(f"{prefix}off")),
                damage_type=_str(params.get(f"{prefix}type") or params.get(f"{prefix}damagetype")),
            )
        )

    return attacks


# ---------------------------------------------------------------------------
# Building parser
# ---------------------------------------------------------------------------

BUILDING_KEYWORDS = ["building", "structure", "infobox"]

# Maps known resource-field names to human-readable labels
RESOURCE_FIELD_ALIASES = {
    "production": "production",
    "produces": "production",
    "resource": "resource",
    "iron": "Iron",
    "coal": "Coal",
    "oil": "Oil",
    "wood": "Wood",
    "food": "Food",
    "gold": "Gold",
    "plasma": "Plasma",
    "titanium": "Titanium",
    "uranium": "Uranium",
}


def parse_building(wikitext: str, page_title: str) -> BuildingResponse:
    wikicode = mwparserfromhell.parse(wikitext)
    infobox = _find_infobox(wikicode, BUILDING_KEYWORDS)

    if infobox is None:
        logger.warning("No building infobox found for %s", page_title)
        return BuildingResponse(name=page_title, page_title=page_title)

    params = _template_params(infobox)
    logger.debug("Building params for %s: %s", page_title, list(params.keys()))

    name = _str(params.get("name")) or page_title
    building_type = _str(params.get("type") or params.get("buildingtype"))
    description = _str(params.get("description") or params.get("desc"))

    gold_cost = _int(params.get("gold") or params.get("cost") or params.get("goldcost"))
    xp_reward = _int(params.get("xp") or params.get("experience") or params.get("xpreward"))

    production = _parse_building_production(params)

    return BuildingResponse(
        name=name,
        page_title=page_title,
        building_type=building_type,
        description=description,
        gold_cost=gold_cost,
        xp_reward=xp_reward,
        production=production,
        raw_template_params=params,
    )


def _parse_building_production(params: dict[str, str]) -> list[BuildingProduction]:
    """
    Handles several production field layouts:
      production=Iron | amount=10 | time=3600
      produces=Gold   | goldamount=500
      iron=10 | irontime=3600
    """
    production: list[BuildingProduction] = []

    # Layout 1: production/produces + amount + time
    resource_name = _str(
        params.get("production") or params.get("produces") or params.get("resource")
    )
    if resource_name:
        prod = BuildingProduction(
            resource=resource_name,
            amount=_int(params.get("amount") or params.get("productionamount")),
            period_seconds=_parse_time(
                params.get("time") or params.get("productiontime") or params.get("cycle")
            ),
        )
        production.append(prod)

    # Layout 2: per-resource keys  (iron=10, irontime=3600, etc.)
    for field, label in RESOURCE_FIELD_ALIASES.items():
        if field in ("production", "produces", "resource"):
            continue
        if field in params:
            amount_val = _int(params.get(field))
            time_val = _parse_time(params.get(f"{field}time") or params.get(f"{field}cycle"))
            if amount_val is not None:
                production.append(
                    BuildingProduction(resource=label, amount=amount_val, period_seconds=time_val)
                )

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
    """
    Convert a human-readable time string to seconds.
    Accepts: "1h", "30m", "3600s", "1h 30m", bare integers (treated as seconds).
    """
    if value is None:
        return None
    value = str(value).strip()

    # Bare integer → seconds
    if value.isdigit():
        return int(value)

    total = 0
    matched = False
    for pattern, multiplier in _TIME_PATTERNS:
        for m in re.finditer(pattern, value, re.I):
            total += int(m.group(1)) * multiplier
            matched = True

    return total if matched else None