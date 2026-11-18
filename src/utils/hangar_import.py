"""HangarLink import: the ships a player owns, from a Hangar Export CSV.

The HangarLink "Hangar Export" browser extension
(https://github.com/hangarlink/hangarexport) saves ``hangarexport.csv`` from
the RSI pledges page. Its first header is ``"<handle> Type"`` and each row is
a ``PLEDGE`` or a ``BUYBACK``. A pledge's ``Items`` cell packs every item in
it as tokens, items joined with commas::

    [KIND Ship][TITLE Cutlass Black][LINER Drake Interplanetary][CUSTOMNAME Rusty]

The extension does not escape quotes inside values, so instead of trusting
the CSV quoting this module reads the item tokens straight out of each
PLEDGE line (buyback rows never carry items, so they drop out on their own).
A plain CSV with a ``Ship`` / ``Name`` / ``Model`` column (and optionally a
``Manufacturer`` column) is accepted as a fallback.

:func:`match_ships` pairs each owned hull with a :class:`ShipOption` from the
stock base.ini. One loc key names every copy of a hull in ASOP, so copies of
the same ship collapse into one :class:`HangarShip` with a count.

Qt-free so it can be unit-tested without a QApplication.
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from src.utils import ship_names
from src.utils.ship_names import ShipNameEntry, ShipNamesConfig, ShipOption

# A match must score at least this to be preselected in the import dialog.
MATCH_THRESHOLD = 0.72

_ITEM_RE = re.compile(
    r"\[KIND (?P<kind>[^\]]*)\]"
    r"(?:\[TITLE (?P<title>[^\]]*)\])?"
    r"(?:\[LINER (?P<liner>[^\]]*)\])?"
    r"(?:\[CUSTOMNAME (?P<custom>[^\]]*)\])?"
)
_SHIP_KINDS = ("ship", "vehicle")
_FALLBACK_NAME_HEADERS = ("ship", "ship name", "model", "vehicle", "name", "title")
_FALLBACK_MFR_HEADERS = ("manufacturer", "mfr", "maker", "liner")

# First word of RSI's manufacturer line ("Drake Interplanetary") -> the
# manufacturer name ship_names uses.
_LINER_MANUFACTURERS = {
    "aegis": "Aegis", "anvil": "Anvil", "aopoa": "Aopoa", "argo": "Argo",
    "banu": "Banu", "consolidated": "C.O.", "c.o.": "C.O.", "crusader": "Crusader",
    "drake": "Drake", "esperia": "Esperia", "gallenson": "Gallenson",
    "gatac": "Gatac", "greycat": "Greycat", "kruger": "Kruger", "misc": "MISC",
    "musashi": "MISC", "mirai": "Mirai", "origin": "Origin", "roberts": "RSI",
    "rsi": "RSI", "tumbril": "Tumbril", "vanduul": "Vanduul",
}


@dataclass
class HangarShip:
    """One hull the player owns (every copy of it)."""

    title: str                  # RSI's name for it, e.g. "Cutlass Black"
    liner: str = ""             # RSI's manufacturer line, e.g. "Drake Interplanetary"
    count: int = 1
    custom_names: List[str] = field(default_factory=list)   # names given on the RSI site

    @property
    def manufacturer(self) -> str:
        return liner_manufacturer(self.liner)


@dataclass
class ImportRow:
    ship: HangarShip
    option: Optional[ShipOption]   # best match, or None when nothing scored high enough
    score: float


# ── Parsing ─────────────────────────────────────────────────────────────────

def liner_manufacturer(liner: str) -> str:
    words = liner.strip().lower().split()
    return _LINER_MANUFACTURERS.get(words[0], "") if words else ""


def read_text(path: Path) -> str:
    raw = Path(path).read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _collapse(found: Iterable[Tuple[str, str, str]]) -> List[HangarShip]:
    """``(title, liner, custom name)`` triples -> one HangarShip per hull."""
    by_hull: Dict[Tuple[str, str], HangarShip] = {}
    for title, liner, custom in found:
        title, liner, custom = title.strip(), liner.strip(), custom.strip()
        if not title:
            continue
        hull = (" ".join(_tokens(title)), liner_manufacturer(liner) or liner.lower())
        ship = by_hull.get(hull)
        if ship is None:
            by_hull[hull] = ship = HangarShip(title, liner, 0)
        ship.count += 1
        if custom and custom not in ship.custom_names:
            ship.custom_names.append(custom)
    return list(by_hull.values())


def _hangarlink_items(text: str) -> List[Tuple[str, str, str]]:
    found = []
    for line in text.splitlines():
        if not line.lstrip().strip('"').upper().startswith("PLEDGE"):
            continue
        for m in _ITEM_RE.finditer(line):
            kind = (m.group("kind") or "").strip().lower()
            if not any(k in kind for k in _SHIP_KINDS):
                continue
            found.append((m.group("title") or "", m.group("liner") or "",
                          m.group("custom") or ""))
    return found


def _plain_csv_items(text: str) -> List[Tuple[str, str, str]]:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def column(names: Sequence[str]) -> int:
        for name in names:
            if name in header:
                return header.index(name)
        return -1

    name_col = column(_FALLBACK_NAME_HEADERS)
    if name_col < 0:
        return []
    mfr_col = column(_FALLBACK_MFR_HEADERS)
    found = []
    for row in rows[1:]:
        if name_col >= len(row):
            continue
        liner = row[mfr_col] if 0 <= mfr_col < len(row) else ""
        found.append((row[name_col], liner, ""))
    return found


def parse_hangar_text(text: str) -> List[HangarShip]:
    """The owned ships in a Hangar Export CSV (or a plain ship-list CSV)."""
    found = _hangarlink_items(text)
    if not found and "[KIND " not in text:
        found = _plain_csv_items(text)
    return _collapse(found)


def parse_hangar_csv(path: Path) -> List[HangarShip]:
    return parse_hangar_text(read_text(path))


# ── Matching ────────────────────────────────────────────────────────────────

def _tokens(text: str) -> List[str]:
    s = text.lower().replace("&", " and ")
    s = re.sub(r"\bmk\.?\s*", "mk", s)          # "Mk II" / "Mk. II" -> "mkii"
    return re.findall(r"[a-z0-9]+", s)


def _similarity(a: List[str], b: List[str]) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa, sb = set(a), set(b)
    if sa == sb:
        return 0.97                               # same words, other order
    small, big = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
    if small < big:
        # "C2 Hercules" in "C2 Hercules Starlifter"
        return 0.75 + 0.2 * len(small) / len(big)
    seq = SequenceMatcher(None, " ".join(a), " ".join(b)).ratio()
    jaccard = len(sa & sb) / len(sa | sb)
    return 0.5 * seq + 0.5 * jaccard


def score(ship: HangarShip, option: ShipOption) -> float:
    title = _tokens(ship.title)
    best = max(_similarity(title, _tokens(ship_names.strip_manufacturer(option))),
               _similarity(title, _tokens(option.stock_name)))
    mfr = ship.manufacturer
    if mfr and option.manufacturer:
        if mfr.lower() == option.manufacturer.lower():
            best = min(1.0, best + 0.05)
        else:
            best *= 0.6
    return best


def best_match(ship: HangarShip, options: Sequence[ShipOption]) -> Tuple[Optional[ShipOption], float]:
    best: Optional[ShipOption] = None
    best_score = 0.0
    for option in options:
        s = score(ship, option)
        # Ties go to the shorter key: the plain hull over an AI/event variant.
        if s > best_score or (s == best_score and best and len(option.key) < len(best.key)):
            best, best_score = option, s
    if best_score < MATCH_THRESHOLD:
        return None, best_score
    return best, best_score


def match_ships(ships: Sequence[HangarShip], options: Sequence[ShipOption]) -> List[ImportRow]:
    """One row per owned hull: matched ones A to Z by game name, then the rest."""
    rows = [ImportRow(ship, *best_match(ship, options)) for ship in ships]
    rows.sort(key=lambda r: (r.option is None,
                             (r.option.stock_name if r.option else r.ship.title).lower()))
    return rows


# ── Into the list ───────────────────────────────────────────────────────────

def default_name(ship: HangarShip, option: Optional[ShipOption], use_custom: bool) -> str:
    if use_custom and ship.custom_names:
        return ship.custom_names[0]
    if option is not None:
        return ship_names.strip_manufacturer(option)
    return ship.title


def apply_import(config: ShipNamesConfig, picks: Iterable[Tuple[str, str]],
                 replace: bool = False) -> int:
    """Add ``(key, name)`` picks to *config*. Returns how many were added.

    Appending leaves ships already in the list (and their names) where they
    are; replacing starts the list over. A key picked twice keeps the first.
    """
    if replace:
        config.entries = []
    added = 0
    for key, name in picks:
        name = name.strip()
        if not key or not name or config.index_of(key) >= 0:
            continue
        config.entries.append(ShipNameEntry(key, name))
        added += 1
    return added
