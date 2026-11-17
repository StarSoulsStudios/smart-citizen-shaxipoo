"""Which source writes each mission type's text: StarStrings, Smart Citizen, or both.

Two sources can write a mission's title and description: MrKraken's
StarStrings (``starstrings`` source) and Smart Citizen's own generated text
(``enhancements`` source). The Missions tab's layer orderer gives every
mission type (``mission_types.LAYER_GROUPS``, item names included) its own
:class:`LayerChoice`: which of the two sits on top, and whether each is used
at all. Where both have a string for a key, the top one wins; where only one
has it, that one shows; where neither is used, the stock text shows.

When StarStrings wins a title and Smart Citizen is still switched on for that
type, Smart Citizen's title extras are laid over StarStrings' text: the
"Shorter titles" phrases, the pickup and drop-off route, and the FPS tag
(:func:`starstrings_title`). That is what "Smart Citizen under StarStrings"
means for a title, so the shortening a player switched on never silently
stops working because StarStrings is on top.

The route and FPS facts come from the game files, which only a generation
reads, so the generator leaves them in ``mission_index.json`` beside the
enhancement INIs (:func:`write_mission_index` / :func:`load_mission_index`).

Qt-free: the merge (``ini_parser``), the Missions tab preview and the
generator all use it.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable, Dict, Mapping, Optional, Tuple

from src.utils.mission_types import LAYER_GROUPS, is_title_key, layer_group

logger = logging.getLogger(__name__)

STARSTRINGS = "starstrings"
SMART = "smart"
LAYERS: Tuple[str, str] = (STARSTRINGS, SMART)

MISSION_INDEX_FILE = "mission_index.json"
_INDEX_VERSION = 1


@dataclass(frozen=True)
class LayerChoice:
    """One orderer row: which layer is on top, and which layers are used."""

    top: str = STARSTRINGS
    starstrings: bool = True
    smart: bool = True

    def uses(self, layer: str) -> bool:
        return self.starstrings if layer == STARSTRINGS else self.smart

    def with_top(self, layer: str) -> "LayerChoice":
        return replace(self, top=layer if layer in LAYERS else STARSTRINGS)

    def with_layer(self, layer: str, on: bool) -> "LayerChoice":
        return replace(self, **{layer: bool(on)}) if layer in LAYERS else self

    def order(self) -> Tuple[str, str]:
        """The two layers, top first."""
        return (self.top, SMART if self.top == STARSTRINGS else STARSTRINGS)

    def winner(self, has_starstrings: bool, has_smart: bool) -> Optional[str]:
        """The layer whose string shows, or None for the stock text."""
        ss = self.starstrings and has_starstrings
        sc = self.smart and has_smart
        if ss and sc:
            return self.top
        if ss:
            return STARSTRINGS
        if sc:
            return SMART
        return None


# StarStrings on top of Smart Citizen, both used: what every version before
# the orderer did, so an upgrade changes nothing until the player says so.
DEFAULT_CHOICE = LayerChoice()


def default_choices() -> Dict[str, LayerChoice]:
    return {group: DEFAULT_CHOICE for group in LAYER_GROUPS}


def choices_from_json(blob: Optional[str]) -> Dict[str, LayerChoice]:
    """Parse saved choices; every group missing or malformed gets the default."""
    choices = default_choices()
    if not blob:
        return choices
    try:
        data = json.loads(blob)
    except (TypeError, ValueError):
        logger.warning("Mission layer choices could not be read; using the defaults")
        return choices
    if not isinstance(data, dict):
        return choices
    for group, raw in data.items():
        if group not in choices or not isinstance(raw, dict):
            continue
        top = raw.get("top", STARSTRINGS)
        choices[group] = LayerChoice(
            top=top if top in LAYERS else STARSTRINGS,
            starstrings=bool(raw.get(STARSTRINGS, True)),
            smart=bool(raw.get(SMART, True)),
        )
    return choices


def choices_to_json(choices: Mapping[str, LayerChoice]) -> str:
    return json.dumps(
        {group: {"top": c.top, STARSTRINGS: c.starstrings, SMART: c.smart}
         for group, c in choices.items() if group in LAYER_GROUPS},
        sort_keys=True,
    )


# ── The merge ───────────────────────────────────────────────────────────────

TitleTransform = Callable[[str, str], str]


def apply_layers(
    enhancements: Mapping[str, str],
    starstrings: Mapping[str, str],
    choices: Mapping[str, LayerChoice],
    title_transform: Optional[TitleTransform] = None,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """The two sources as the merge should see them under *choices*.

    Returns ``(enhancements, starstrings)``, new dicts. A key no orderer row
    decides (``layer_group`` is None) passes through untouched. For one that
    a row decides: Smart Citizen's string is dropped when Smart Citizen is
    off for that row; StarStrings' string is dropped when StarStrings is off
    or loses to Smart Citizen. A StarStrings title that wins while Smart
    Citizen is on is passed through *title_transform(key, value)*.

    The merge puts ``starstrings`` above ``enhancements``, so with these two
    dicts the ordinary "later source wins" merge shows each row's winner.
    """
    out_enh: Dict[str, str] = {}
    for key, value in enhancements.items():
        group = layer_group(key)
        if group is not None and not choices.get(group, DEFAULT_CHOICE).smart:
            continue
        out_enh[key] = value
    out_ss: Dict[str, str] = {}
    for key, value in starstrings.items():
        group = layer_group(key)
        if group is None:
            out_ss[key] = value
            continue
        choice = choices.get(group, DEFAULT_CHOICE)
        if choice.winner(True, key in out_enh) != STARSTRINGS:
            continue
        if title_transform is not None and choice.smart and is_title_key(key):
            value = title_transform(key, value)
        out_ss[key] = value
    return out_enh, out_ss


# ── StarStrings titles with Smart Citizen's extras ──────────────────────────

# The tags a title ends with: StarStrings' "<EM4>[100 Rep] [BP]*</EM4>",
# Smart Citizen's own, or bare "[...]" groups.
_TRAILING_TAGS = re.compile(
    r"((?:\s*<EM(\d+)>(?:(?!</EM\2>).)*</EM\2>|\s*\[[^\]\[]*\]\*?)+)\s*$", re.DOTALL)
_SINGLE_EM_GROUP = re.compile(r"^\s*<EM(\d+)>(.*)</EM\1>\s*$", re.DOTALL)
# A title that already names a pickup or drop-off (~mission(Location|name) ...).
_ROUTE_TOKEN = re.compile(r"~mission\(\s*(?:location|pickup|destination|dropoff)", re.IGNORECASE)


@dataclass(frozen=True)
class IndexEntry:
    """What a generation learned about one title from the game files."""

    ground: str = ""      # tag_builder.GROUND_ALL / GROUND_SOME / "" (none)
    space: bool = False   # every variant fights in ships only
    route: str = ""       # rendered route core ("~mission(Location|Address) > ...")


@dataclass(frozen=True)
class TitleExtras:
    """The Smart Citizen title settings laid over a StarStrings title."""

    phrases: frozenset = frozenset()
    rank_separator: str = "dash"
    standardize_hauling: bool = False
    shorten: bool = True
    route: bool = False
    route_config: object = None      # the mission_titles TagConfig, for placement
    show_ground: bool = True
    show_space: bool = False
    ground_label: str = "fps"


def split_trailing_tags(title: str) -> Tuple[str, str]:
    """``("Title text", " <EM4>[100 Rep]</EM4>")``: the text and its end tags."""
    m = _TRAILING_TAGS.search(title or "")
    if not m or m.start() == 0:
        return (title or ""), ""
    return title[:m.start()].rstrip(), m.group(1)


def add_tag(tags: str, tag: str) -> str:
    """Put *tag* first among *tags*, inside their emphasis when they share one."""
    if not tag:
        return tags
    if not tags.strip():
        return f" <EM4>{tag}</EM4>"
    m = _SINGLE_EM_GROUP.match(tags)
    if m:
        return f" <EM{m.group(1)}>{tag} {m.group(2).strip()}</EM{m.group(1)}>"
    return f" <EM4>{tag}</EM4>{tags}"


def starstrings_title(title: str, extras: TitleExtras,
                      entry: Optional[IndexEntry] = None) -> str:
    """A StarStrings title with Smart Citizen's shortening, route and FPS tag."""
    from src.utils.tag_builder import abbreviate_title, apply_mission_title, engagement_tag

    text, tags = split_trailing_tags(title)
    if extras.shorten:
        shortened = abbreviate_title(text, extras.phrases, extras.rank_separator,
                                     extras.standardize_hauling)
        if shortened:
            text = shortened
    if (extras.route and entry is not None and entry.route
            and extras.route_config is not None and not _ROUTE_TOKEN.search(text)):
        text = apply_mission_title(text, entry.route, extras.route_config)
    if entry is not None:
        tag = engagement_tag(entry.ground, entry.space, show_ground=extras.show_ground,
                             show_space=extras.show_space, label_key=extras.ground_label)
        tags = add_tag(tags, tag)
    return f"{text}{tags}"


# ── mission_index.json ──────────────────────────────────────────────────────

def write_mission_index(path: Path, titles: Mapping[str, IndexEntry]) -> None:
    """Write what the generation learned per title (atomic, like every output)."""
    from src.utils.atomic_io import atomic_write_text

    data = {}
    for key, entry in sorted(titles.items()):
        item = {}
        if entry.ground:
            item["ground"] = entry.ground
        if entry.space:
            item["space"] = True
        if entry.route:
            item["route"] = entry.route
        if item:
            data[key] = item
    atomic_write_text(Path(path), json.dumps(
        {"version": _INDEX_VERSION, "titles": data}, ensure_ascii=False, indent=1))


_index_cache: Dict[str, object] = {}


def load_mission_index(path: Path) -> Dict[str, IndexEntry]:
    """Read ``mission_index.json``; {} when it is missing or unreadable.

    Cached by path and modification time, as the StarStrings file is.
    """
    path = Path(path)
    try:
        stamp = (str(path), path.stat().st_mtime_ns)
    except OSError:
        return {}
    if _index_cache.get("stamp") == stamp:
        return _index_cache["data"]  # type: ignore[return-value]
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        titles = raw.get("titles", {}) if isinstance(raw, dict) else {}
        data = {
            str(key): IndexEntry(
                ground=str(item.get("ground", "")),
                space=bool(item.get("space", False)),
                route=str(item.get("route", "")),
            )
            for key, item in titles.items() if isinstance(item, dict)
        }
    except (OSError, ValueError, AttributeError) as exc:
        logger.warning(f"{path.name} could not be read ({exc}); no FPS tags or routes "
                       f"on StarStrings titles until the next generation")
        data = {}
    _index_cache["stamp"] = stamp
    _index_cache["data"] = data
    return data
