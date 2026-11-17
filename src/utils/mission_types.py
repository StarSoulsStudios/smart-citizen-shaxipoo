"""Mission types: which kind of contract a mission string belongs to.

The Missions tab lets the player choose, per mission type, which source writes
the text (StarStrings or Smart Citizen) and which one sits on top. That needs
one answer to "what type is this key?" shared by the merge (``ini_parser``),
the Missions tab and its preview, so it lives here, Qt-free.

The type comes from CIG's own key naming. Title and description keys share
their stem (``Covalex_HaulCargo_AToB_title`` / ``..._desc``), so a mission's
title and description always land in the same type. The groups follow the
Contracts Manager's tabs closely enough to be recognisable, folding the rare
ones together (Refueling into Repair & Refuel, the three mining kinds into
Mining). A key no rule names is ``other``.

``ITEMS`` is not a mission type: it is the item-name layer (StarStrings'
``Mil/1/C Bracer`` against Smart Citizen's component tags), which the same
orderer controls, so it shares the vocabulary.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Optional

HAULING = "hauling"
DELIVERY = "delivery"
MERCENARY = "mercenary"
BOUNTY = "bounty"
INVESTIGATION = "investigation"
SALVAGE = "salvage"
MINING = "mining"
REPAIR = "repair"
COLLECTION = "collection"
WIKELO = "wikelo"
OTHER = "other"
ITEMS = "items"

# Display order on the Missions tab. Every id has a ``missions.type_<id>``
# label in languages/*/ui.json.
MISSION_TYPES: tuple[str, ...] = (
    HAULING, DELIVERY, MERCENARY, BOUNTY, INVESTIGATION, SALVAGE,
    MINING, REPAIR, COLLECTION, WIKELO, OTHER,
)
# Everything the layer orderer has a row for.
LAYER_GROUPS: tuple[str, ...] = MISSION_TYPES + (ITEMS,)

# (type, lower-case substrings of the key). The first rule with a match wins,
# so the specific ones come first: CFP_RecoverCargo is a Mercenary contract in
# game even though it "recovers", and RedWind_HaulCargo_* is hauling even
# though some of them "deliver".
_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (WIKELO, ("thecollector",)),
    (MERCENARY, ("recovercargo",)),
    (MINING, ("mining", "fpsmine", "groundvehicle", "miningclaim", "rockcracker")),
    (SALVAGE, ("salvage",)),
    (HAULING, ("haulcargo", "hauling", "spacecargo", "collectcargo", "cargohaul",
               "regionlink", "recoverstolen")),
    (DELIVERY, ("delivery", "deliver", "courier", "package")),
    (BOUNTY, ("bounty", "bhg_", "eliminatespecific", "killship", "confirmkill",
              "assassin", "wantedlevel", "murderspree", "capture")),
    (REPAIR, ("maintenance", "repair", "refuel", "commarray", "comm_array",
              "commsarray", "oxygenkiosk")),
    (INVESTIGATION, ("searchbody", "searchcrew", "investigat", "blackbox",
                     "recoveritem", "recovery_", "facilitydelve", "findbody",
                     "misscrew", "missingcrew", "missingperson", "retrieve",
                     "recoverstash", "stealevidence", "datapad", "search",
                     "recover")),
    (COLLECTION, ("collect", "resourcegather", "construct", "ors_", "gather",
                  "supply")),
    (MERCENARY, ("eliminate", "patrol", "defend", "destroy", "sabotage", "sweep",
                 "ambush", "bombing", "combatassist", "escort", "siege",
                 "security", "attack", "kill", "raid", "heist", "assault",
                 "protect", "clear", "retake", "prisonerbreak", "distraction",
                 "deploy", "guard", "fight", "showdown", "xenothreat",
                 "lockdown", "penetrator", "hack", "breach", "ugf", "wave",
                 "defense", "defence", "hunt", "cull", "boss", "rescue",
                 "steal", "theft", "boarders")),
)

# A key that is a mission title or description: ``..._title``, ``..._Title_001``,
# ``..._desc_01``, ``..._Description``, ``Tutorial01_MissionTitle``.
_TEXT_KEY = re.compile(r"(?:title|desc|description)(?:_?\d+)?$", re.IGNORECASE)
_TITLE_KEY = re.compile(r"title(?:_?\d+)?$", re.IGNORECASE)
_ITEM_NAME_PREFIX = "item_name"


@lru_cache(maxsize=None)
def mission_type(key: str) -> str:
    """The mission type of *key* (a title or description key)."""
    low = (key or "").lower()
    for kind, tokens in _RULES:
        if any(token in low for token in tokens):
            return kind
    return OTHER


def is_mission_text_key(key: str) -> bool:
    """True for a key that names a mission title or description."""
    return bool(key) and _TEXT_KEY.search(key) is not None \
        and not key.lower().startswith(("item_", "vehicle_"))


def is_title_key(key: str) -> bool:
    """True for a mission title key (``..._title``, ``..._Title_001``)."""
    return bool(key) and _TITLE_KEY.search(key) is not None \
        and not key.lower().startswith(("item_", "vehicle_"))


def layer_group(key: str) -> Optional[str]:
    """The orderer row that decides *key*, or None when no row does.

    Item names belong to ``items``; mission titles and descriptions to their
    mission type. Everything else (UI text, cargo-size words, ore names) is
    not on the orderer and keeps the ordinary merge order.
    """
    if not key:
        return None
    if key.lower().startswith(_ITEM_NAME_PREFIX):
        return ITEMS
    if is_mission_text_key(key):
        return mission_type(key)
    return None
