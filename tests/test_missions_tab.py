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


# ── Live preview simulation ─────────────────────────────────────────────────

from src.gui.missions_tab import PreviewOptions, plain_desc, plain_title, simulate  # noqa: E402

HAUL = SAMPLE_CONTRACTS[1]          # has a route, rep 100, no blueprints
RECOVER = SAMPLE_CONTRACTS[0]       # rep 150, blueprints, hostiles


def test_plain_title_strips_any_tool_tags():
    assert plain_title("Run <EM4>[100 Rep]</EM4> [BP]*") == "Run"
    assert plain_title("Plain") == "Plain"


def test_plain_desc_cuts_appended_blocks():
    assert plain_desc("Body.\\n\\n<EM4>Reputation Awarded:</EM4> 5") == "Body."
    assert plain_desc("Body.\n\nPotential Blueprints\n- x") == "Body."


def test_route_placement_and_tags():
    title, _ = simulate(HAUL, "Delivery <EM4>[1 Rep]</EM4>", "Body", PreviewOptions())
    assert title == "Delivery - Area18 > Lorville <EM4>[100 Rep]</EM4>"
    title, _ = simulate(HAUL, "Delivery", "Body", PreviewOptions(placement="prepend"))
    assert title.startswith("Area18 > Lorville - Delivery")


def test_switches_remove_their_parts():
    off = PreviewOptions(route=False, rep_tag=False, bp_tag=False,
                         field_rep=False, field_bp=False, field_hostiles=False)
    title, blocks = simulate(RECOVER, "Recover", "Body", off)
    assert title == "Recover" and [b for b, _ in blocks] == ["body"]


def test_description_blocks_in_order():
    _, blocks = simulate(RECOVER, "Recover", "Body", PreviewOptions(field_hostiles=True))
    assert [b for b, _ in blocks] == ["body", "rep", "bp", "hostiles"]
