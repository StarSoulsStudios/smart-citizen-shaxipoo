"""MrKraken's StarStrings as a merge source: missions and item names only.

StarStrings (https://github.com/MrKraken/StarStrings) publishes a full
``global.ini`` per game channel as a rolling GitHub release: tag ``latest``
for LIVE, ``latest-ptu`` for PTU builds. The release *name* changes with each
build (``SC LIVE Build (release-2026-10-09-292e6be)``), so it is what this
module stores and compares to tell whether the copy on disk is current.

The downloaded file is kept per channel at
``{channel}/cache/starstrings/global.ini`` with ``release.json`` beside it.
At load time :func:`overlay` keeps only what StarStrings changes in mission
titles and descriptions and in item names, against the stock base, so every
other string stays Smart Citizen's. ``load_sources_from_settings`` injects
the result as the ``starstrings`` source above ``enhancements``.

Qt-free; the network calls run in ``StarStringsCheckWorker`` /
``StarStringsDownloadWorker`` (``src/gui/workers.py``).
"""
from __future__ import annotations

import io
import json
import logging
import urllib.request
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, Optional

from src.utils.atomic_io import atomic_write_text

logger = logging.getLogger(__name__)

REPO = "MrKraken/StarStrings"
API_URL = "https://api.github.com/repos/" + REPO + "/releases/tags/{tag}"
RELEASES_PAGE = "https://github.com/" + REPO + "/releases"
REQUEST_TIMEOUT_SECONDS = 10
DOWNLOAD_TIMEOUT_SECONDS = 60

LIVE_TAG = "latest"
PTU_TAG = "latest-ptu"
CHANNEL_TAGS = {
    "LIVE": LIVE_TAG, "HOTFIX": LIVE_TAG,
    "PTU": PTU_TAG, "EPTU": PTU_TAG, "TECH-PREVIEW": PTU_TAG,
}
# StarStrings is English only; another language keeps its own strings.
SUPPORTED_LANGUAGE = "english"

FOLDER_NAME = "starstrings"
GLOBAL_INI_NAME = "global.ini"
RELEASE_FILE_NAME = "release.json"

_ITEM_NAME_PREFIX = "item_name"
_MISSION_TEXT_SUFFIXES = ("_title", "_desc", "_description")
_NEVER_PREFIXES = ("vehicle_",)   # ship names belong to the Ships tab


@dataclass(frozen=True)
class Release:
    tag: str
    name: str            # changes with every build; what we compare
    published_at: str    # ISO 8601, for display
    zip_url: str         # the release's .zip asset ("" when it has none)

    def build_label(self) -> str:
        """``release-2026-10-09-292e6be`` from the release name, else the name."""
        if "(" in self.name and self.name.endswith(")"):
            return self.name[self.name.rindex("(") + 1:-1]
        return self.name


def tag_for_channel(channel: str) -> str:
    return CHANNEL_TAGS.get(channel.upper(), LIVE_TAG)


# ── Which strings StarStrings may change ────────────────────────────────────

def is_layer_key(key: str, category: str) -> bool:
    """True for mission text and item names: the part of StarStrings we use.

    *category* is ``StringEntry.extract_category(key)``. Mission keys that the
    category rules don't catch still end in ``_title`` / ``_desc``.
    """
    low = key.lower()
    if low.startswith(_NEVER_PREFIXES):
        return False
    if low.startswith(_ITEM_NAME_PREFIX):
        return True
    if category == "Missions":
        return True
    return low.endswith(_MISSION_TEXT_SUFFIXES) and not low.startswith("item_")


def overlay(stock: Dict[str, str], starstrings: Dict[str, str]) -> Dict[str, str]:
    """StarStrings' changes to mission text and item names, against *stock*.

    Keys the stock base lacks are left out, so a file for another build can
    never add a key the game doesn't have.
    """
    from src.models.string_model import StringEntry

    out = {}
    for key, value in starstrings.items():
        base = stock.get(key)
        if base is None or base == value:
            continue
        if is_layer_key(key, StringEntry.extract_category(key)):
            out[key] = value
    return out


# ── Files on disk ───────────────────────────────────────────────────────────

def folder_for(channel_cache_dir: Path) -> Path:
    return Path(channel_cache_dir) / FOLDER_NAME


def read_installed(folder: Path) -> Optional[Release]:
    """The release the file in *folder* came from, or None."""
    try:
        data = json.loads((Path(folder) / RELEASE_FILE_NAME).read_text(encoding="utf-8"))
        if not (Path(folder) / GLOBAL_INI_NAME).is_file():
            return None
        return Release(data["tag"], data["name"], data.get("published_at", ""),
                       data.get("zip_url", ""))
    except (OSError, ValueError, KeyError, TypeError):
        return None


def needs_update(installed: Optional[Release], latest: Release) -> bool:
    return installed is None or installed.name != latest.name


# ── Network (call from a worker thread) ─────────────────────────────────────

def _request(url: str, user_agent: str, accept: str) -> urllib.request.Request:
    return urllib.request.Request(url, headers={"Accept": accept, "User-Agent": user_agent})


def fetch_release(tag: str, user_agent: str) -> Release:
    """The current release for *tag* from the GitHub API. Raises on failure."""
    req = _request(API_URL.format(tag=tag), user_agent, "application/vnd.github+json")
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
        payload = json.load(resp)
    return release_from_payload(tag, payload)


def release_from_payload(tag: str, payload: dict) -> Release:
    zips = [a for a in payload.get("assets", [])
            if str(a.get("name", "")).lower().endswith(".zip")]
    return Release(
        tag=tag,
        name=str(payload.get("name") or payload.get("tag_name") or tag),
        published_at=str(payload.get("published_at") or ""),
        zip_url=str(zips[0].get("browser_download_url", "")) if zips else "",
    )


def extract_global_ini(zip_bytes: bytes) -> bytes:
    """The English ``global.ini`` inside a StarStrings release zip."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as archive:
        names = [n for n in archive.namelist() if n.lower().endswith("/" + GLOBAL_INI_NAME)
                 or n.lower() == GLOBAL_INI_NAME]
        if not names:
            raise ValueError("the release zip has no global.ini")
        english = [n for n in names if "/english/" in n.lower()]
        return archive.read((english or names)[0])


def install(release: Release, user_agent: str, folder: Path) -> Path:
    """Download *release* and store its global.ini in *folder*. Returns the file."""
    if not release.zip_url:
        raise ValueError(f"release {release.name!r} has no .zip asset")
    req = _request(release.zip_url, user_agent, "application/octet-stream")
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SECONDS) as resp:
        data = resp.read()
    text = extract_global_ini(data).decode("utf-8-sig")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / GLOBAL_INI_NAME
    atomic_write_text(target, text)
    atomic_write_text(folder / RELEASE_FILE_NAME, json.dumps(asdict(release), indent=2) + "\n")
    logger.info(f"StarStrings {release.build_label()} installed to {target}")
    return target
