"""Renamed Contracts Manager categories: the tab and dropdown names in mobiGlas.

The Contracts Manager labels its categories with ordinary global.ini strings
(``mobiglas_ui_Mercenary`` = "Mercenary", ``mobiGlas_ui_MissionType_Hauling_Solar``
= "Hauling - Stellar", ...). The Missions tab lets the player rename them; the
names are kept apart from user.ini (like the Ships tab's renames) and reach
the merge as the synthetic ``category_names`` source, so a game patch that
changes the stock text never loses them. Qt-free.
"""
from __future__ import annotations

import json
from typing import Dict, Mapping, Optional, Tuple

# Display order on the Missions tab: the top-level categories first, then the
# Contracts Manager's sub-tabs. Only keys the loaded game strings hold are
# shown, so a key CIG retires simply drops off the list.
CATEGORY_KEYS: Tuple[str, ...] = (
    "mobiglas_ui_Mercenary",
    "mobiglas_ui_BountyHunter",
    "mobiGlas_ui_MissionType_Hauling",
    "mobiGlas_ui_MissionType_Hauling_Local",
    "mobiGlas_ui_MissionType_Hauling_Planetary",
    "mobiGlas_ui_MissionType_Hauling_Solar",
    "mobiGlas_ui_MissionType_Hauling_Interstellar",
    "mobiGlas_ui_MissionType_Delivery",
    "mobiGlas_ui_MissionType_DeliveryPilot",
    "mobiGlas_ui_MissionType_Courier",
    "mobiglas_ui_Investigation",
    "mobiglas_ui_Salvage",
    "mobiglas_ui_Mining",
    "mobiglas_ui_ShipMining",
    "mobiglas_ui_FPSMining",
    "mobiglas_ui_GroundMining",
    "mobiglas_ui_Maintenance",
    "mobiGlas_ui_MissionType_Collection",
    "mobiglas_ui_Priority",
    "mobiglas_ui_Priority_ArcCorp",
    "mobiglas_ui_Priority_Crusader",
    "mobiglas_ui_Priority_Hurston",
    "mobiglas_ui_Priority_MicroTech",
    "mobiglas_ui_Race",
    "mobiglas_ui_PVPMissions",
    "mobiglas_ui_ECN",
    "mobiGlas_ui_MissionType_ServiceBeacon",
    "mobiGlas_ui_MissionType_Battaglia",
    "mobiGlas_ui_MissionType_Defend",
    "mobiGlas_ui_MissionType_Escort",
    "mobiGlas_ui_MissionType_Rescue",
    "mobiGlas_ui_MissionType_Investigate",
    "mobiGlas_ui_MissionType_Search",
    "mobiGlas_ui_MissionType_Research",
    "mobiGlas_ui_MissionType_Survival",
    "mobiGlas_ui_MissionType_Job",
    "ContractManager_TempTab_Vehicles",
    "ContractManager_TempTab_Small_Items",
)
_KNOWN = frozenset(CATEGORY_KEYS)


def names_from_json(blob: Optional[str]) -> Dict[str, str]:
    """Saved renames, {key: name}; unknown keys and blank names dropped."""
    if not blob:
        return {}
    try:
        data = json.loads(blob)
    except (TypeError, ValueError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items()
            if k in _KNOWN and isinstance(v, str) and v.strip()}


def names_to_json(names: Mapping[str, str]) -> str:
    return json.dumps({k: v.strip() for k, v in names.items()
                       if k in _KNOWN and v and v.strip()}, sort_keys=True, ensure_ascii=False)


def render_overrides(names: Mapping[str, str], stock: Mapping[str, str]) -> Dict[str, str]:
    """The strings the merge gets: a rename for every key the stock base has.

    A name equal to the stock text is left out (nothing to change), and so
    is a key the game no longer has.
    """
    out = {}
    for key, name in names.items():
        name = (name or "").strip()
        if key in _KNOWN and name and key in stock and stock[key] != name:
            out[key] = name
    return out
