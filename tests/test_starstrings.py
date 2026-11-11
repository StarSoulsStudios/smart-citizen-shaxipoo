"""StarStrings source (src/utils/starstrings.py) and its merge injection."""
from __future__ import annotations

import io
import json
import zipfile

import pytest

from src.utils import starstrings
from src.utils.starstrings import Release

STOCK = {
    "Battaglia_RPT_MissCrew_01_title": "Missing Crew",
    "Battaglia_RPT_MissCrew_01_desc": "Find them.",
    "item_NameCOOL_Bracer": "Bracer",
    "item_DescCOOL_Bracer": "A cooler.",
    "vehicle_NameANVL_Liberator": "Anvil Liberator",
    "ui_MainMenu_Play": "Play",
    "Unchanged_title": "Same",
}
KRAKEN = {
    "Battaglia_RPT_MissCrew_01_title": "Missing Crew [BP]",
    "Battaglia_RPT_MissCrew_01_desc": "Find them. Rep: 500",
    "item_NameCOOL_Bracer": "Mil/1/C Bracer",
    "item_DescCOOL_Bracer": "Grade C cooler.",
    "vehicle_NameANVL_Liberator": "Liberator",
    "ui_MainMenu_Play": "PLAY NOW",
    "Unchanged_title": "Same",
    "NotInThisBuild_title": "Ghost",
}
PAYLOAD = {
    "tag_name": "latest",
    "name": "SC LIVE Build (release-2026-10-09-292e6be)",
    "published_at": "2026-10-09T14:31:00Z",
    "assets": [{"name": "StarStrings-LIVE.zip",
                "browser_download_url": "https://example.test/StarStrings-LIVE.zip"}],
}


def _zip(files):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, text in files.items():
            z.writestr(name, text)
    return buf.getvalue()


class TestOverlay:
    def test_keeps_mission_text_and_item_names_only(self):
        assert starstrings.overlay(STOCK, KRAKEN) == {
            "Battaglia_RPT_MissCrew_01_title": "Missing Crew [BP]",
            "Battaglia_RPT_MissCrew_01_desc": "Find them. Rep: 500",
            "item_NameCOOL_Bracer": "Mil/1/C Bracer",
        }

    def test_ship_names_left_to_ships_tab(self):
        assert "vehicle_NameANVL_Liberator" not in starstrings.overlay(STOCK, KRAKEN)

    def test_item_descriptions_and_ui_left_alone(self):
        out = starstrings.overlay(STOCK, KRAKEN)
        assert "item_DescCOOL_Bracer" not in out and "ui_MainMenu_Play" not in out

    def test_keys_missing_from_stock_dropped(self):
        assert "NotInThisBuild_title" not in starstrings.overlay(STOCK, KRAKEN)


class TestRelease:
    def test_from_payload(self):
        r = starstrings.release_from_payload("latest", PAYLOAD)
        assert r.zip_url.endswith("StarStrings-LIVE.zip")
        assert r.build_label() == "release-2026-10-09-292e6be"

    def test_no_zip_asset(self):
        r = starstrings.release_from_payload("latest", {**PAYLOAD, "assets": []})
        assert r.zip_url == ""

    @pytest.mark.parametrize("channel,tag", [("LIVE", "latest"), ("HOTFIX", "latest"),
                                             ("PTU", "latest-ptu"), ("EPTU", "latest-ptu"),
                                             ("TECH-PREVIEW", "latest-ptu")])
    def test_channel_tags(self, channel, tag):
        assert starstrings.tag_for_channel(channel) == tag

    def test_needs_update(self):
        r = starstrings.release_from_payload("latest", PAYLOAD)
        older = Release("latest", "SC LIVE Build (release-2026-09-01-aaaaaaa)", "", "")
        assert starstrings.needs_update(None, r)
        assert starstrings.needs_update(older, r)
        assert not starstrings.needs_update(r, r)


class TestZip:
    def test_prefers_english_global_ini(self):
        data = _zip({"StarCitizen/LIVE/user.cfg": "g_language = english",
                     "StarCitizen/LIVE/data/Localization/german/global.ini": "a=de",
                     "StarCitizen/LIVE/data/Localization/english/global.ini": "a=en"})
        assert starstrings.extract_global_ini(data) == b"a=en"

    def test_no_global_ini(self):
        with pytest.raises(ValueError):
            starstrings.extract_global_ini(_zip({"readme.txt": "hi"}))

    def test_install_and_read_back(self, tmp_path, monkeypatch):
        body = _zip({"data/Localization/english/global.ini": "﻿a=1\n"})

        class _Resp(io.BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

        monkeypatch.setattr(starstrings.urllib.request, "urlopen",
                            lambda req, timeout: _Resp(body))
        r = starstrings.release_from_payload("latest", PAYLOAD)
        target = starstrings.install(r, "test", tmp_path / "starstrings")
        assert target.read_text(encoding="utf-8") == "a=1\n"
        assert starstrings.read_installed(tmp_path / "starstrings") == r

    def test_read_installed_needs_the_file(self, tmp_path):
        (tmp_path / starstrings.RELEASE_FILE_NAME).write_text(json.dumps(
            {"tag": "latest", "name": "x"}), encoding="utf-8")
        assert starstrings.read_installed(tmp_path) is None


class TestInjection:
    @pytest.fixture
    def installed(self, tmp_path, monkeypatch):
        from src.utils.settings import AppSettings
        folder = tmp_path / "starstrings"
        folder.mkdir()
        (folder / starstrings.GLOBAL_INI_NAME).write_text(
            "\n".join(f"{k}={v}" for k, v in KRAKEN.items()), encoding="utf-8")
        monkeypatch.setattr(AppSettings, "get_starstrings_dir", staticmethod(lambda: folder))
        monkeypatch.setattr(AppSettings, "get_starstrings_enabled", staticmethod(lambda: True))
        monkeypatch.setattr(AppSettings, "get_selected_language",
                            staticmethod(lambda: "english"))
        return folder

    def test_goes_above_enhancements(self, installed):
        from src.parser.ini_parser import _inject_starstrings
        sources = {"global": dict(STOCK)}
        out = _inject_starstrings(sources, ["global", "enhancements", "user"])
        assert out == ["global", "enhancements", "starstrings", "user"]
        assert set(sources["starstrings"]) == {
            "Battaglia_RPT_MissCrew_01_title", "Battaglia_RPT_MissCrew_01_desc",
            "item_NameCOOL_Bracer"}

    def test_goes_above_global_without_enhancements(self, installed):
        from src.parser.ini_parser import _inject_starstrings
        assert _inject_starstrings({"global": dict(STOCK)}, ["global", "user"]) == [
            "global", "starstrings", "user"]

    def test_off_or_other_language_adds_nothing(self, installed, monkeypatch):
        from src.parser.ini_parser import _inject_starstrings
        from src.utils.settings import AppSettings
        monkeypatch.setattr(AppSettings, "get_selected_language", staticmethod(lambda: "german"))
        assert _inject_starstrings({"global": dict(STOCK)}, ["global"]) == ["global"]
        monkeypatch.setattr(AppSettings, "get_selected_language",
                            staticmethod(lambda: "english"))
        monkeypatch.setattr(AppSettings, "get_starstrings_enabled", staticmethod(lambda: False))
        assert _inject_starstrings({"global": dict(STOCK)}, ["global"]) == ["global"]

    def test_not_downloaded_adds_nothing(self, tmp_path, monkeypatch):
        from src.parser.ini_parser import _inject_starstrings
        from src.utils.settings import AppSettings
        monkeypatch.setattr(AppSettings, "get_starstrings_dir",
                            staticmethod(lambda: tmp_path / "none"))
        monkeypatch.setattr(AppSettings, "get_starstrings_enabled", staticmethod(lambda: True))
        monkeypatch.setattr(AppSettings, "get_selected_language",
                            staticmethod(lambda: "english"))
        assert _inject_starstrings({"global": dict(STOCK)}, ["global"]) == ["global"]
