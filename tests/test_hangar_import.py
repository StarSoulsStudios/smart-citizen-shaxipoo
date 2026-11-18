"""HangarLink CSV import (src/utils/hangar_import.py)."""
from __future__ import annotations

import pytest

from src.utils import hangar_import, ship_names
from src.utils.ship_names import ShipNameEntry, ShipNamesConfig

pytestmark = pytest.mark.unit

STOCK = {
    "vehicle_NameANVL_Liberator": "Anvil Liberator",
    "vehicle_NameANVL_Liberator_short": "Liberator",
    "vehicle_NameANVL_Hornet_F7C_Mk2": "Anvil F7C Hornet Mk II",
    "vehicle_NameDRAK_Cutlass_Black": "Drake Cutlass Black",
    "vehicle_NameDRAK_Cutlass_Blue": "Drake Cutlass Blue",
    "vehicle_NameCRUS_Starlifter_C2": "Crusader C2 Hercules Starlifter",
    "vehicle_NameMISC_Razor": "Mirai Razor",
    "vehicle_NameMISC_Razor_short": "Razor",
    "vehicle_NameRSI_Aurora_MR": "RSI Aurora MR",
}
OPTIONS = ship_names.ship_options(STOCK)
BY_KEY = {o.key: o for o in OPTIONS}

# Shaped like hangarexport.csv from the HangarLink extension (content.js
# convertToCsv): unescaped values, items packed into one quoted cell.
HANGARLINK_CSV = "\n".join([
    '"shaxipoo Type","PledgeId","Name","Value","ConfigurationValue","Date","Page",'
    '"Pagesize","Contains","AlsoContains","Items","PageUrl","BuybackUrl"',
    '"PLEDGE",111,"Package - Liberator Starter","$1,000.00 USD","","Nov 01, 2026",1,10,'
    '"Contains: Liberator and 3 items","[TITLE Lifetime Insurance]",'
    '"[KIND Ship][TITLE Liberator][LINER Anvil Aerospace][CUSTOMNAME Big Mama],'
    '[KIND Ship][TITLE Hornet F7C Mk II][LINER Anvil Aerospace],'
    '[KIND Hangar decoration][TITLE Liberator Model]",'
    '"https://robertsspaceindustries.com/account/pledges?page=1&pagesize=10",',
    '"PLEDGE",112,"Standalone Ship - Cutlass Black "Best" Deal","$110.00 USD","","Oct 01, 2026",1,10,'
    '"Contains: Cutlass Black","","[KIND Ship][TITLE Cutlass Black][LINER Drake Interplanetary]",'
    '"https://robertsspaceindustries.com/account/pledges?page=1&pagesize=10",',
    '"PLEDGE",113,"Standalone Ship - Cutlass Black","$110.00 USD","","Oct 02, 2026",1,10,'
    '"Contains: Cutlass Black","","[KIND Ship][TITLE Cutlass Black][LINER Drake Interplanetary]",'
    '"https://robertsspaceindustries.com/account/pledges?page=1&pagesize=10",',
    '"PLEDGE",114,"Standalone Ship - C2","$400.00 USD","","Oct 03, 2026",1,10,'
    '"Contains: C2","","[KIND Ship][TITLE C2 Hercules][LINER Crusader Industries]",'
    '"https://robertsspaceindustries.com/account/pledges?page=1&pagesize=10",',
    '"PLEDGE",115,"Standalone Ship - Concept","$50.00 USD","","Oct 04, 2026",1,10,'
    '"Contains: Pegasus","","[KIND Ship][TITLE Pegasus Escort][LINER Banu Souli]",'
    '"https://robertsspaceindustries.com/account/pledges?page=1&pagesize=10",',
    '"BUYBACK",116,"Standalone Ship - Aurora MR","","","Jan 01, 2026",1,100,'
    '"Contains: Aurora MR","","","https://robertsspaceindustries.com/account/buy-back-pledges?page=1&pagesize=100",',
])


class TestParse:
    def test_reads_ship_items_from_pledges_only(self):
        titles = {s.title for s in hangar_import.parse_hangar_text(HANGARLINK_CSV)}
        assert titles == {"Liberator", "Hornet F7C Mk II", "Cutlass Black",
                          "C2 Hercules", "Pegasus Escort"}

    def test_copies_collapse_with_a_count(self):
        ships = {s.title: s for s in hangar_import.parse_hangar_text(HANGARLINK_CSV)}
        assert ships["Cutlass Black"].count == 2
        assert ships["Liberator"].count == 1

    def test_keeps_rsi_custom_names(self):
        ships = {s.title: s for s in hangar_import.parse_hangar_text(HANGARLINK_CSV)}
        assert ships["Liberator"].custom_names == ["Big Mama"]
        assert ships["Liberator"].manufacturer == "Anvil"

    def test_plain_csv_fallback(self):
        text = "Manufacturer,Ship\nDrake,Cutlass Black\nAnvil,Liberator\n"
        ships = hangar_import.parse_hangar_text(text)
        assert [(s.title, s.manufacturer) for s in ships] == [
            ("Cutlass Black", "Drake"), ("Liberator", "Anvil")]

    def test_unrelated_csv_gives_nothing(self):
        assert hangar_import.parse_hangar_text("a,b\n1,2\n") == []

    def test_reads_bom_file(self, tmp_path):
        path = tmp_path / "hangarexport.csv"
        path.write_bytes(b"\xef\xbb\xbf" + HANGARLINK_CSV.encode("utf-8"))
        assert len(hangar_import.parse_hangar_csv(path)) == 5


class TestMatch:
    def _rows(self):
        ships = hangar_import.parse_hangar_text(HANGARLINK_CSV)
        return {r.ship.title: r for r in hangar_import.match_ships(ships, OPTIONS)}

    def test_exact_after_manufacturer(self):
        assert self._rows()["Liberator"].option.key == "vehicle_NameANVL_Liberator"

    def test_word_order_and_mk(self):
        assert self._rows()["Hornet F7C Mk II"].option.key == "vehicle_NameANVL_Hornet_F7C_Mk2"

    def test_black_not_blue(self):
        assert self._rows()["Cutlass Black"].option.key == "vehicle_NameDRAK_Cutlass_Black"

    def test_short_title_in_longer_stock_name(self):
        assert self._rows()["C2 Hercules"].option.key == "vehicle_NameCRUS_Starlifter_C2"

    def test_ship_not_in_build_is_unmatched(self):
        assert self._rows()["Pegasus Escort"].option is None

    def test_unmatched_rows_sort_last(self):
        ships = hangar_import.parse_hangar_text(HANGARLINK_CSV)
        rows = hangar_import.match_ships(ships, OPTIONS)
        assert rows[-1].option is None
        names = [r.option.stock_name for r in rows if r.option]
        assert names == sorted(names, key=str.lower)

    def test_manufacturer_mismatch_is_penalised(self):
        ship = hangar_import.HangarShip("Razor", "Drake Interplanetary")
        razor = BY_KEY["vehicle_NameMISC_Razor"]
        assert hangar_import.score(ship, razor) < hangar_import.MATCH_THRESHOLD


class TestApply:
    def test_default_names(self):
        lib = BY_KEY["vehicle_NameANVL_Liberator"]
        ship = hangar_import.HangarShip("Liberator", "Anvil Aerospace", 1, ["Big Mama"])
        assert hangar_import.default_name(ship, lib, use_custom=False) == "Liberator"
        assert hangar_import.default_name(ship, lib, use_custom=True) == "Big Mama"

    def test_append_keeps_existing_entries(self):
        cfg = ShipNamesConfig([ShipNameEntry("vehicle_NameANVL_Liberator", "Home")])
        added = hangar_import.apply_import(cfg, [
            ("vehicle_NameANVL_Liberator", "Liberator"),
            ("vehicle_NameDRAK_Cutlass_Black", "Cutlass"),
            ("vehicle_NameDRAK_Cutlass_Black", "Dupe"),
            ("vehicle_NameRSI_Aurora_MR", "  "),
        ])
        assert added == 1
        assert [(e.key, e.name) for e in cfg.entries] == [
            ("vehicle_NameANVL_Liberator", "Home"),
            ("vehicle_NameDRAK_Cutlass_Black", "Cutlass"),
        ]

    def test_replace_starts_over(self):
        cfg = ShipNamesConfig([ShipNameEntry("vehicle_NameANVL_Liberator", "Home")])
        hangar_import.apply_import(cfg, [("vehicle_NameMISC_Razor", "Razor")], replace=True)
        assert [e.key for e in cfg.entries] == ["vehicle_NameMISC_Razor"]
