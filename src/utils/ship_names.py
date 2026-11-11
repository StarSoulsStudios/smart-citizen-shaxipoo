"""Ship Names: the user's numbered, ordered list of renamed ships.

The Ships tab edits a list of ``(loc key, custom name)`` pairs plus two
list-wide switches: numbering (``01. ``, ``02. ``...) and the manufacturer
before the name. The list is saved per channel as ``ship_names.json`` and
rendered into ``vehicle_Name*`` overrides by :func:`render_overrides`, which
``load_sources_from_settings()`` injects as the synthetic ``ship_names``
source just below ``user`` (so a hand edit in the String Editor still wins).

Numbers are zero-padded so ASOP's lexicographic sort keeps ``02.`` above
``10.`` (the same reason as ``ship_sort_prefix``, #142). Only the full
``vehicle_Name<X>`` key is written: it is the name ASOP lists, and the table
already leaves the ``_short`` keys out.

Qt-free so it can be unit-tested without a QApplication.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from src.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

SHIP_NAMES_FILENAME = "ship_names.json"
SHIP_NAME_KEY_PREFIX = "vehicle_name"   # compared lower-case; CIG mixes the case
SHORT_SUFFIX = "_short"
NUMBER_SEPARATOR = ". "
MIN_NUMBER_WIDTH = 2

# Keys under vehicle_Name that are not ships a player owns or calls in ASOP.
_IGNORED_KEY_STARTS = ("comingsoon", "ea_", "probe_")

# Manufacturer code (the loc key's first segment) -> the name CIG uses.
# Only a fallback: a ship with a ``_short`` key gets its manufacturer from
# the difference between its full and short names, which also covers MISC
# keys that are really Mirai ships (``MISC_Razor`` = "Mirai Razor").
MANUFACTURERS = {
    "AEGS": "Aegis", "AGES": "Aegis", "ANVL": "Anvil", "ARGO": "Argo",
    "BANU": "Banu", "CNOU": "C.O.", "CRUS": "Crusader", "DRAK": "Drake",
    "ESPR": "Esperia", "GAMA": "Gatac", "GLSN": "Gallenson", "GRIN": "Greycat",
    "KRIG": "Kruger", "MISC": "MISC", "MRAI": "Mirai", "ORIG": "Origin",
    "RSI": "RSI", "TMBL": "Tumbril", "VNCL": "Vanduul", "XIAN": "Aopoa",
    "XNAA": "Aopoa",
}


@dataclass(frozen=True)
class ShipOption:
    """One ship the dropdown offers."""

    key: str            # e.g. "vehicle_NameANVL_Liberator"
    stock_name: str     # e.g. "Anvil Liberator"
    manufacturer: str   # e.g. "Anvil" ("" when unknown)


@dataclass
class ShipNameEntry:
    key: str
    name: str


@dataclass
class ShipNamesConfig:
    entries: List[ShipNameEntry] = field(default_factory=list)
    numbering: bool = True
    manufacturer: bool = False

    def index_of(self, key: str) -> int:
        for i, entry in enumerate(self.entries):
            if entry.key == key:
                return i
        return -1

    def upsert(self, key: str, name: str) -> int:
        """Add *key* at the end, or rename it where it is. Returns its index."""
        i = self.index_of(key)
        if i >= 0:
            self.entries[i].name = name
            return i
        self.entries.append(ShipNameEntry(key, name))
        return len(self.entries) - 1

    def remove(self, key: str) -> None:
        self.entries = [e for e in self.entries if e.key != key]

    def reorder(self, keys: Iterable[str]) -> None:
        """Put the entries in the order of *keys* (unknown keys ignored)."""
        by_key = {e.key: e for e in self.entries}
        ordered = [by_key.pop(k) for k in keys if k in by_key]
        self.entries = ordered + list(by_key.values())


# ── Options ─────────────────────────────────────────────────────────────────

def is_ship_name_key(key: str) -> bool:
    low = key.lower()
    if not low.startswith(SHIP_NAME_KEY_PREFIX) or low.endswith(SHORT_SUFFIX):
        return False
    rest = low[len(SHIP_NAME_KEY_PREFIX):]
    return bool(rest) and not rest.startswith(_IGNORED_KEY_STARTS)


def _short_lookup(stock: Dict[str, str]) -> Dict[str, str]:
    """Lower-case full key -> its ``_short`` value."""
    out = {}
    for key, value in stock.items():
        low = key.lower()
        if low.startswith(SHIP_NAME_KEY_PREFIX) and low.endswith(SHORT_SUFFIX):
            out[low[: -len(SHORT_SUFFIX)]] = value
    return out


def manufacturer_for(key: str, stock_name: str, short_name: Optional[str]) -> str:
    """The manufacturer at the front of *stock_name*, or ""."""
    if short_name and stock_name.endswith(short_name) and len(stock_name) > len(short_name):
        head = stock_name[: -len(short_name)].strip()
        if head and len(head.split()) <= 2:
            return head
    code = key[len(SHIP_NAME_KEY_PREFIX):].split("_", 1)[0].upper()
    name = MANUFACTURERS.get(code, "")
    return name if name and stock_name.startswith(name + " ") else ""


def ship_options(stock: Dict[str, str]) -> List[ShipOption]:
    """Every renameable ship in *stock* (the stock base.ini), sorted by name."""
    shorts = _short_lookup(stock)
    options = []
    for key, value in stock.items():
        if not value or not is_ship_name_key(key):
            continue
        mfr = manufacturer_for(key, value, shorts.get(key.lower()))
        options.append(ShipOption(key, value, mfr))
    options.sort(key=lambda o: (o.stock_name.lower(), o.key.lower()))
    return options


def strip_manufacturer(option: ShipOption) -> str:
    """The stock name without its manufacturer, a starting point for a rename."""
    if option.manufacturer and option.stock_name.startswith(option.manufacturer + " "):
        return option.stock_name[len(option.manufacturer) + 1:]
    return option.stock_name


# ── Rendering ───────────────────────────────────────────────────────────────

def number_width(count: int) -> int:
    return max(MIN_NUMBER_WIDTH, len(str(count)))


def render_name(config: ShipNamesConfig, index: int, manufacturer: str) -> str:
    """The in-game name for ``config.entries[index]``."""
    entry = config.entries[index]
    name = entry.name.strip()
    has_it = name.lower().startswith(manufacturer.lower() + " ")
    if config.manufacturer and manufacturer and not has_it:
        name = f"{manufacturer} {name}"
    if config.numbering:
        width = number_width(len(config.entries))
        name = f"{index + 1:0{width}d}{NUMBER_SEPARATOR}{name}"
    return name


def render_overrides(config: ShipNamesConfig, stock: Dict[str, str]) -> Dict[str, str]:
    """``{loc key: in-game name}`` for every listed ship that is in *stock*.

    A key the current build no longer has is skipped (and kept in the list),
    so a patch that renames a ship never writes a dead key into global.ini.
    """
    if not config.entries:
        return {}
    shorts = _short_lookup(stock)
    out = {}
    for i, entry in enumerate(config.entries):
        stock_name = stock.get(entry.key)
        if stock_name is None or not entry.name.strip():
            continue
        mfr = manufacturer_for(entry.key, stock_name, shorts.get(entry.key.lower()))
        out[entry.key] = render_name(config, i, mfr)
    return out


# ── Persistence ─────────────────────────────────────────────────────────────

def load_config(path: Path) -> ShipNamesConfig:
    """Read *path*; a missing or unreadable file gives an empty list."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return ShipNamesConfig()
    except (OSError, ValueError) as exc:
        logger.warning(f"Could not read {path}: {exc}; starting with an empty ship list")
        return ShipNamesConfig()
    entries = [
        ShipNameEntry(str(e["key"]), str(e.get("name", "")))
        for e in data.get("entries", [])
        if isinstance(e, dict) and e.get("key")
    ]
    return ShipNamesConfig(
        entries=entries,
        numbering=bool(data.get("numbering", True)),
        manufacturer=bool(data.get("manufacturer", False)),
    )


def save_config(path: Path, config: ShipNamesConfig) -> None:
    data = {
        "numbering": config.numbering,
        "manufacturer": config.manufacturer,
        "entries": [{"key": e.key, "name": e.name} for e in config.entries],
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def config_path() -> Path:
    """This channel's ``ship_names.json``."""
    from src.utils.settings import AppSettings
    return AppSettings.get_channel_data_dir() / SHIP_NAMES_FILENAME
