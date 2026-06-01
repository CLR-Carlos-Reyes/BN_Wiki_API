"""
Tests for app/services/parser.py

These use realistic-looking Battle Nations infobox wikitext so you can
run them without a live wiki or Redis connection.
"""

import pytest
from app.services.parser import parse_unit, parse_building, _parse_time


# ---------------------------------------------------------------------------
# Fixtures – fake wikitext
# ---------------------------------------------------------------------------

UNIT_WIKITEXT = """
{{Unit
|name=Trooper
|type=Soldier
|description=The backbone of the 95th Rifle Company.
|hp1=100|armor1=0|offense1=50|defense1=50
|hp2=115|armor2=0|offense2=55|defense2=55
|hp3=130|armor3=0|offense3=60|defense3=60
|hp4=150|armor4=0|offense4=65|defense4=65
|hp5=170|armor5=0|offense5=70|defense5=70
|hp6=200|armor6=0|offense6=75|defense6=75
|attack1name=Rifle Shot|attack1power=20|attack1type=Ballistic
}}

The Trooper is the basic infantry unit.
"""

UNIT_WITH_ARMOR_WIKITEXT = """
{{Unit
|name=Riot Trooper
|type=Soldier
|hp1=120|armor1=40|offense1=45|defense1=45
|hp6=220|armor6=90|offense6=90|defense6=90
}}
"""

BUILDING_WIKITEXT = """
{{Building
|name=Iron Mine
|type=Resource
|description=Mines iron ore from the ground.
|gold=1500
|xp=30
|production=Iron
|amount=15
|time=1h
}}
"""

BUILDING_MULTI_WIKITEXT = """
{{Building
|name=Gold Vault
|type=Storage
|gold=2000
|xp=50
|gold=500
|goldtime=30m
}}
"""


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

def test_parse_unit_basic():
    unit = parse_unit(UNIT_WIKITEXT, "Trooper")
    assert unit.name == "Trooper"
    assert unit.unit_type == "Soldier"
    assert "backbone" in (unit.description or "")
    assert len(unit.ranks) == 6


def test_parse_unit_rank_values():
    unit = parse_unit(UNIT_WIKITEXT, "Trooper")
    r1 = unit.ranks[0]
    assert r1.rank == 1
    assert r1.hp == 100
    assert r1.armor == 0
    assert r1.offense == 50
    assert r1.defense == 50

    r6 = unit.ranks[5]
    assert r6.rank == 6
    assert r6.hp == 200


def test_parse_unit_attacks():
    unit = parse_unit(UNIT_WIKITEXT, "Trooper")
    r1 = unit.ranks[0]
    assert len(r1.attacks) == 1
    assert r1.attacks[0].name == "Rifle Shot"
    assert r1.attacks[0].power == 20
    assert r1.attacks[0].damage_type == "Ballistic"


def test_parse_unit_with_armor():
    unit = parse_unit(UNIT_WITH_ARMOR_WIKITEXT, "Riot_Trooper")
    assert unit.name == "Riot Trooper"
    r1 = next(r for r in unit.ranks if r.rank == 1)
    assert r1.armor == 40
    r6 = next(r for r in unit.ranks if r.rank == 6)
    assert r6.armor == 90


def test_parse_unit_missing_page():
    unit = parse_unit("No infobox here, just text.", "Unknown_Unit")
    assert unit.name == "Unknown_Unit"
    assert unit.ranks == []


# ---------------------------------------------------------------------------
# Building tests
# ---------------------------------------------------------------------------

def test_parse_building_basic():
    b = parse_building(BUILDING_WIKITEXT, "Iron_Mine")
    assert b.name == "Iron Mine"
    assert b.building_type == "Resource"
    assert b.gold_cost == 1500
    assert b.xp_reward == 30


def test_parse_building_production():
    b = parse_building(BUILDING_WIKITEXT, "Iron_Mine")
    assert len(b.production) >= 1
    iron = next((p for p in b.production if p.resource == "Iron"), None)
    assert iron is not None
    assert iron.amount == 15
    assert iron.period_seconds == 3600  # 1h


# ---------------------------------------------------------------------------
# Time parser tests
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    ("3600", 3600),
    ("1h", 3600),
    ("30m", 1800),
    ("1h 30m", 5400),
    ("90s", 90),
    ("2h 15m 30s", 8130),
    (None, None),
    ("", None),
])
def test_parse_time(value, expected):
    assert _parse_time(value) == expected