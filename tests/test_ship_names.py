"""Ships tab core (src/utils/ship_names.py) and its merge-source injection."""
from __future__ import annotations

import json

import pytest

from src.utils import ship_names
from src.utils.ship_names import ShipNameEntry, ShipNamesConfig

STOCK = {
    "vehicle_NameANVL_Liberator": "Anvil Liberator",
    "vehicle_NameANVL_Liberator_short": "Liberator",
    "vehicle_NameMISC_Razor": "Mirai Razor",
    "vehicle_NameMISC_Razor_short": "Razor",
    "vehicle_NameDRAK_Cutlass_Black": "Drake Cutlass Black",
    "Vehicle_NameGRIN_UTV": "Greycat UTV",
    "vehicle_NameComingSoon": "Coming Soon",
    "vehicle_NameEA_GroundRadar": "Radar Dish",
    "vehicle_DescANVL_Liberator": "A carrier.",
    "item_NameCOOL_Bracer": "Bracer",
}


def _config(*pairs, numbering=True, manufacturer=False):
    return ShipNamesConfig([ShipNameEntry(k, n) for k, n in pairs], numbering, manufacturer)


class TestOptions:
    def test_lists_ships_only(self):
        keys = {o.key for o in ship_names.ship_options(STOCK)}
        assert keys == {
            "vehicle_NameANVL_Liberator", "vehicle_NameMISC_Razor",
            "vehicle_NameDRAK_Cutlass_Black", "Vehicle_NameGRIN_UTV",
        }

    def test_sorted_by_stock_name(self):
        names = [o.stock_name for o in ship_names.ship_options(STOCK)]
        assert names == sorted(names, key=str.lower)

    def test_manufacturer_from_short_name_beats_code(self):
        by_key = {o.key: o for o in ship_names.ship_options(STOCK)}
        assert by_key["vehicle_NameMISC_Razor"].manufacturer == "Mirai"
        assert by_key["vehicle_NameANVL_Liberator"].manufacturer == "Anvil"

    def test_manufacturer_from_code_without_short(self):
        by_key = {o.key: o for o in ship_names.ship_options(STOCK)}
        assert by_key["vehicle_NameDRAK_Cutlass_Black"].manufacturer == "Drake"
        assert by_key["Vehicle_NameGRIN_UTV"].manufacturer == "Greycat"

    def test_strip_manufacturer(self):
        by_key = {o.key: o for o in ship_names.ship_options(STOCK)}
        assert ship_names.strip_manufacturer(by_key["vehicle_NameMISC_Razor"]) == "Razor"


class TestRender:
    def test_numbered_zero_padded(self):
        cfg = _config(("vehicle_NameANVL_Liberator", "Liberator"),
                      ("vehicle_NameMISC_Razor", "Razor"))
        out = ship_names.render_overrides(cfg, STOCK)
        assert out == {"vehicle_NameANVL_Liberator": "01. Liberator",
                       "vehicle_NameMISC_Razor": "02. Razor"}

    def test_width_grows_past_99(self):
        cfg = _config(*[("vehicle_NameANVL_Liberator", "x")] * 100)
        assert ship_names.render_name(cfg, 0, "") == "001. x"

    def test_sorts_lexicographically_in_list_order(self):
        cfg = _config(*[("k%d" % i, "Ship") for i in range(12)])
        names = [ship_names.render_name(cfg, i, "") for i in range(12)]
        assert names == sorted(names)

    def test_manufacturer_switch(self):
        cfg = _config(("vehicle_NameANVL_Liberator", "Liberator"),
                      numbering=False, manufacturer=True)
        out = ship_names.render_overrides(cfg, STOCK)
        assert out == {"vehicle_NameANVL_Liberator": "Anvil Liberator"}

    def test_manufacturer_not_doubled(self):
        cfg = _config(("vehicle_NameANVL_Liberator", "anvil Lib"),
                      numbering=False, manufacturer=True)
        out = ship_names.render_overrides(cfg, STOCK)
        assert out["vehicle_NameANVL_Liberator"] == "anvil Lib"

    def test_plain_name(self):
        cfg = _config(("vehicle_NameANVL_Liberator", "  Big Boy "), numbering=False)
        assert ship_names.render_overrides(cfg, STOCK) == {"vehicle_NameANVL_Liberator": "Big Boy"}

    def test_missing_key_skipped_but_keeps_its_number(self):
        cfg = _config(("vehicle_NameGONE", "Old"), ("vehicle_NameMISC_Razor", "Razor"))
        assert ship_names.render_overrides(cfg, STOCK) == {"vehicle_NameMISC_Razor": "02. Razor"}

    def test_short_key_untouched(self):
        cfg = _config(("vehicle_NameANVL_Liberator", "Lib"))
        assert "vehicle_NameANVL_Liberator_short" not in ship_names.render_overrides(cfg, STOCK)


class TestConfig:
    def test_upsert_renames_in_place(self):
        cfg = _config(("a", "A"), ("b", "B"))
        assert cfg.upsert("a", "A2") == 0
        assert [(e.key, e.name) for e in cfg.entries] == [("a", "A2"), ("b", "B")]
        assert cfg.upsert("c", "C") == 2

    def test_reorder_keeps_unknown_at_end(self):
        cfg = _config(("a", "A"), ("b", "B"), ("c", "C"))
        cfg.reorder(["c", "a", "zzz"])
        assert [e.key for e in cfg.entries] == ["c", "a", "b"]

    def test_round_trip(self, tmp_path):
        path = tmp_path / "LIVE" / ship_names.SHIP_NAMES_FILENAME
        cfg = _config(("vehicle_NameANVL_Liberator", "Liberator ✓"),
                      numbering=False, manufacturer=True)
        ship_names.save_config(path, cfg)
        assert ship_names.load_config(path) == cfg

    def test_missing_file_is_empty(self, tmp_path):
        assert ship_names.load_config(tmp_path / "nope.json") == ShipNamesConfig()

    def test_bad_file_is_empty(self, tmp_path):
        path = tmp_path / "bad.json"
        path.write_text("{not json", encoding="utf-8")
        assert ship_names.load_config(path) == ShipNamesConfig()


class TestInjection:
    @pytest.fixture
    def saved(self, tmp_path, monkeypatch):
        path = tmp_path / ship_names.SHIP_NAMES_FILENAME
        monkeypatch.setattr(ship_names, "config_path", lambda: path)
        return path

    def test_injected_below_user(self, saved):
        from src.parser.ini_parser import _inject_ship_names
        ship_names.save_config(saved, _config(("vehicle_NameANVL_Liberator", "Liberator")))
        sources = {"global": dict(STOCK)}
        hierarchy = _inject_ship_names(sources, ["global", "enhancements", "user"])
        assert hierarchy == ["global", "enhancements", "ship_names", "user"]
        assert sources["ship_names"] == {"vehicle_NameANVL_Liberator": "01. Liberator"}

    def test_nothing_injected_for_empty_list(self, saved):
        from src.parser.ini_parser import _inject_ship_names
        sources = {"global": dict(STOCK)}
        assert _inject_ship_names(sources, ["global", "user"]) == ["global", "user"]
        assert "ship_names" not in sources

    def test_user_override_wins(self, saved):
        from src.merger.ini_merger import merge_sources_by_hierarchy
        from src.parser.ini_parser import _inject_ship_names
        ship_names.save_config(saved, _config(("vehicle_NameANVL_Liberator", "Liberator")))
        sources = {"global": dict(STOCK)}
        hierarchy = _inject_ship_names(sources, ["global", "user"])
        mine = {"vehicle_NameANVL_Liberator": "Mine"}
        merged = merge_sources_by_hierarchy(sources, hierarchy, mine)
        assert merged["vehicle_NameANVL_Liberator"] == "Mine"
        merged = merge_sources_by_hierarchy(sources, hierarchy, {})
        assert merged["vehicle_NameANVL_Liberator"] == "01. Liberator"


def test_saved_json_is_readable(tmp_path):
    path = tmp_path / "s.json"
    ship_names.save_config(path, _config(("k", "N")))
    assert json.loads(path.read_text(encoding="utf-8"))["entries"] == [{"key": "k", "name": "N"}]
