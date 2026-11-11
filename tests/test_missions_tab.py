"""Missions tab helpers: placeholder filling, rich text, sample picking."""
from src.gui.missions_tab import SAMPLE_CONTRACTS, fill_tokens, pick_contracts, to_html


def test_tokens_filled_by_name_ignoring_detail():
    assert fill_tokens("go to ~mission(Location|Address) now") == "go to Wala's outer belt now"
    assert fill_tokens("~mission(Unknown)") == "Unknown"


def test_emphasis_and_breaks():
    out = to_html("Pay <EM4>[150 Rep]</EM4>\\nnext & <b>")
    assert "<span style='color:#F2C86B'>[150 Rep]</span>" in out
    assert "<br>" in out and "&amp;" in out and "&lt;b&gt;" in out


def test_stray_tags_dropped():
    assert "EM" not in to_html("<EM4>open only")


def test_only_contracts_with_both_strings():
    first = SAMPLE_CONTRACTS[0]
    have = {first.title_key: "t", first.desc_key: "d", SAMPLE_CONTRACTS[1].title_key: "t"}
    assert pick_contracts(have.get) == [first]
