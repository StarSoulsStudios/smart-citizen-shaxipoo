"""Missions tab: which source writes each mission type, beside a Contracts Manager preview.

The left column opens on the layer orderer: for every mission type (and for
item names) a small stack of two layers, StarStrings and Smart Citizen. The
one in front wins where both have a string; click the one behind to bring it
forward, or its dot to switch it off (src/utils/mission_layers.py has the
rules, shared with the merge). The rest of the column is a front for
settings the Enhancements page owns (it stays the single source of truth,
opened from the settings menu): each switch here drives that page's own
checkbox or combo, so its handlers, saved settings and dirty tracking run
exactly as before.

The right side is a close mock of the in-game Contracts Manager built from the
strings currently loaded (``set_strings``): real titles and descriptions, put
through the same layer choice the merge makes, with ``~mission(...)``
placeholders filled from sample values. Whatever the last change altered gets
a dashed red outline.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Mapping, Optional, Tuple

from PyQt6.QtCore import (
    QEasingCurve, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen, QTextDocument
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate,
    QTextBrowser, QVBoxLayout, QWidget,
)

from src.gui.theme import (
    DISPLAY_FONT_FAMILY, GAME_TEXT_FONT_FAMILY, HANGAR_FAINT, HANGAR_HULL, HANGAR_LINE,
    HANGAR_MUTED, HANGAR_PLATE, HANGAR_PLATE_HI, HANGAR_SIGNAL, HANGAR_TEXT, host_in_scroll_area,
)
from src.utils import mission_categories, mission_types
from src.utils.i18n import tr
from src.utils.mission_layers import (
    DEFAULT_CHOICE, SMART, STARSTRINGS, IndexEntry, LayerChoice, TitleExtras, starstrings_title,
)
from src.utils.tag_builder import DEFAULT_GROUND_TAG_LABEL, engagement_tag

# The preview's own palette: a cool holo screen inside the app.
GLASS = "#08131A"
HOLO = "#7FD8E6"
HOLO_DIM = "#3E7684"
HOLO_LINE = "#16303A"
HOLO_TEXT = "#A9DDE6"
HOLO_BRIGHT = "#D6F3F8"
EMPHASIS = "#F2C86B"

CHANGED_BG = "#4A1A1E"       # what the last change altered, for a moment
MARK_SECONDS = 2.5
KEY_ROLE = Qt.ItemDataRole.UserRole
HTML_ROLE = Qt.ItemDataRole.UserRole + 1
CHANGED_ROLE = Qt.ItemDataRole.UserRole + 2
CONTROLS_WIDTH = 450
# A layer change reaches the table (and so Apply) with a reload, once the
# player stops clicking; the preview shows it at once.
LAYER_RELOAD_MS = 700

# Each layer's colour, everywhere it is drawn.
LAYER_COLORS = {STARSTRINGS: HOLO, SMART: HANGAR_SIGNAL}
STOCK = "stock"


@dataclass(frozen=True)
class SampleContract:
    """A contract the preview shows: its strings and made-up card values.

    The extra fields stand in for what the generator reads from the game
    files (rep reward, blueprint chance, haul route, hostiles, whether it
    needs FPS gear), so the preview can show each setting the moment it
    changes.
    """

    title_key: str
    desc_key: str
    contractor: str
    reward: str
    kind: str
    rep: int = 0
    blueprints: Tuple[str, ...] = ()
    route: Optional[Tuple[str, str]] = None
    hostiles: str = ""
    difficulty: str = ""
    ground: str = ""          # tag_builder GROUND_ALL / GROUND_SOME / ""
    space: bool = False       # ship combat only

    @property
    def mission_type(self) -> str:
        return mission_types.mission_type(self.title_key)


# Real keys from the game's strings, one or more per common mission type.
# Contractor, reward and type are samples.
SAMPLE_CONTRACTS: Tuple[SampleContract, ...] = (
    SampleContract("CFP_RecoverCargo_Medium_Title", "CFP_RecoverCargo_Medium_Description",
                   "Citizens for Prosperity", "48,500 aUEC", "Cargo recovery", rep=150,
                   blueprints=("P8-SC SMG", "C54 SMG", "S71 Rifle", "G-2 Helmet Woodland"),
                   hostiles="Light fighters x4", difficulty="Medium", space=True),
    SampleContract("Covalex_Delivery_Stanton_Medium_Title_001",
                   "Covalex_Delivery_Stanton_Medium_Desc_001",
                   "Covalex Shipping", "21,750 aUEC", "Delivery", rep=100,
                   route=("Area18", "Lorville")),
    SampleContract("vaughn_assassination_FPS_UGF_legal_title_001",
                   "vaughn_assassination_FPS_UGF_legal_desc_001",
                   "Vaughn", "62,000 aUEC", "Assassination", rep=250,
                   blueprints=("Arrowhead Sniper Rifle",),
                   hostiles="Guards x6, Boss x1", difficulty="Hard", ground="all"),
    SampleContract("Foxwell_SecurityPatrol_H_Title_001", "Foxwell_SecurityPatrol_H_Desc_001",
                   "Foxwell Enforcement", "54,000 aUEC", "Security patrol", rep=200,
                   blueprints=("FR-76 Shield",), hostiles="Medium fighters x3",
                   difficulty="Hard", space=True),
    SampleContract("Covalex_HaulCargo_AToB_title", "Covalex_HaulCargo_AToB_Scrap",
                   "Covalex Shipping", "34,000 aUEC", "Hauling", rep=100,
                   route=("Port Tressler", "Orison")),
    SampleContract("dusters_basesweep_title_003", "dusters_basesweep_desc_003",
                   "Dusters", "40,500 aUEC", "Base sweep", rep=150,
                   hostiles="Soldiers x8", difficulty="Medium", ground="all"),
    SampleContract("Shubin_Industrial_HandMining_Stanton_E_Local_Title_001",
                   "Shubin_Industrial_HandMining_Stanton_E_Local_Desc_001",
                   "Shubin Interstellar", "18,000 aUEC", "Hand mining", rep=100,
                   blueprints=("Pyro RYT Multi-Tool",), ground="all"),
    SampleContract("Adagio_Industrial_Component_Salvage_Stanton_M_Title_001",
                   "Adagio_Industrial_Component_Salvage_Stanton_M_Desc_001",
                   "Adagio Holdings", "36,000 aUEC", "Salvage", rep=100,
                   blueprints=("Bracer Cooler", "FR-76 Shield"),
                   hostiles="None expected", difficulty="Easy"),
    SampleContract("Hockcrow_SearchBody_Easy_Title_001", "Hockcrow_SearchBody_Easy_Description_001",
                   "Hockrow Agency", "12,500 aUEC", "Missing person", rep=100),
)

# Sample values for ~mission(...) placeholders, by name (lower case).
SAMPLE_TOKENS: Dict[str, str] = {
    "location": "Wala's outer belt", "destination": "Area18", "system": "Stanton",
    "missionmaxscusize": "8 SCU", "targetname": "Vesper Kade", "item": "medical supplies",
    "client": "Lima Endicott", "contractor": "Lima Endicott", "ship": "Cutlass Black",
    "danger": "moderate", "timed": "45 minutes", "scripamount": "12",
    "approvalcode": "7741", "rush": "", "trouble": "outlaws",
    "reputationrank": "Senior", "cargogradetoken": "Medium", "cargoroutetoken": "Direct",
}
_TOKEN = re.compile(r"~mission\(([^)|]+)(?:\|[^)]*)?\)")
_EMPHASIS = re.compile(r"<EM\d+>(.*?)</EM\d+>", re.DOTALL)
_ANY_TAG = re.compile(r"</?EM\d+>")


def fill_tokens(text: str) -> str:
    """Replace ``~mission(Name|Detail)`` with a sample value for Name."""
    return _TOKEN.sub(lambda m: SAMPLE_TOKENS.get(m.group(1).lower(), m.group(1)), text)


def to_html(text: str) -> str:
    """Game string -> rich text: escaped, \\n as breaks, <EMn> as emphasis."""
    text = fill_tokens(text).replace("\\n", "\n")
    parts, last = [], 0
    for m in _EMPHASIS.finditer(text):
        parts.append(html.escape(text[last:m.start()]))
        parts.append(f"<span style='color:{EMPHASIS}'>{html.escape(m.group(1))}</span>")
        last = m.end()
    parts.append(html.escape(_ANY_TAG.sub("", text[last:])))
    return "".join(parts).replace("\n", "<br>")


def pick_contracts(lookup: Callable[[str], Optional[str]]) -> List[SampleContract]:
    """The sample contracts whose title and description are both loaded."""
    return [c for c in SAMPLE_CONTRACTS if lookup(c.title_key) and lookup(c.desc_key)]


@dataclass
class PreviewOptions:
    """The mission settings, as the preview applies them."""

    route: bool = True
    placement: str = "append"
    route_arrow: str = "gt"
    title_separator: str = "dash"
    shorten_phrases: frozenset = frozenset()
    rank_separator: str = "dash"
    standardize_hauling: bool = False
    rep_tag: bool = True
    bp_tag: bool = True
    ground_tag: bool = True
    space_tag: bool = False
    ground_label: str = DEFAULT_GROUND_TAG_LABEL
    field_rep: bool = True
    field_bp: bool = True
    field_hostiles: bool = False
    starstrings_extras: bool = True


# Tags a title already carries ("[150 Rep] [BP]*", with or without <EMn>), and
# the detail blocks a description already ends with. Stripped first so the
# preview starts from the plain text whichever tool tagged it.
_TITLE_TAGS = re.compile(r"(\s*(<EM\d+>)?\s*\[[^\]]*\]\*?\s*(</EM\d+>)?)+\s*$")
_DESC_TAIL = re.compile(
    r"(\\n|\n)+\s*(<EM\d+>)?\s*(Reputation Awarded|Potential Blueprints|Hostiles|"
    r"Difficulty|Blueprints)", re.IGNORECASE)


def plain_title(text: str) -> str:
    return _TITLE_TAGS.sub("", text or "").strip()


def plain_desc(text: str) -> str:
    m = _DESC_TAIL.search(text or "")
    return (text[:m.start()] if m else text or "").rstrip()


def _route_text(contract: SampleContract, opts: PreviewOptions) -> str:
    from src.utils.tag_builder import render_route
    if not contract.route:
        return ""
    return render_route(contract.route[0], contract.route[1], opts.route_arrow)


def simulate(contract: SampleContract, title: str, desc: str,
             opts: PreviewOptions) -> Tuple[str, List[Tuple[str, str]]]:
    """The title and description blocks Smart Citizen would write for *contract*.

    Mirrors the generator's order (scripts/generate_enhancements_ini.py):
    shorten, then the route placed per the setting, then the FPS / SHIP tag,
    [BP] and the rep tag. Description blocks are ``(block id, game text)``.
    """
    from types import SimpleNamespace
    from src.utils.tag_builder import abbreviate_title, apply_mission_title

    out = abbreviate_title(plain_title(title), opts.shorten_phrases, opts.rank_separator,
                           opts.standardize_hauling) or plain_title(title)
    if opts.route and contract.route:
        cfg = SimpleNamespace(placement=opts.placement, title_separator=opts.title_separator)
        out = apply_mission_title(out, _route_text(contract, opts), cfg)
    tag = engagement_tag(contract.ground, contract.space, show_ground=opts.ground_tag,
                         show_space=opts.space_tag, label_key=opts.ground_label)
    if tag:
        out += f" <EM4>{tag}</EM4>"
    if opts.bp_tag and contract.blueprints:
        out += " <EM4>[BP]</EM4>"
    if opts.rep_tag and contract.rep:
        out += f" <EM4>[{contract.rep:,} Rep]</EM4>"
    blocks = [("body", plain_desc(desc))]
    if opts.field_rep and contract.rep:
        blocks.append(("rep", f"<EM4>Reputation Awarded:</EM4> {contract.rep:,}"))
    if opts.field_bp and contract.blueprints:
        blocks.append(("bp", "<EM4>Potential Blueprints</EM4>\n" +
                       "\n".join(f"- {b}" for b in contract.blueprints)))
    if opts.field_hostiles and (contract.hostiles or contract.difficulty):
        blocks.append(("hostiles", f"<EM4>Hostiles:</EM4> {contract.hostiles}\n"
                                   f"<EM4>Difficulty:</EM4> {contract.difficulty}"))
    return out, blocks


def compose(contract: SampleContract, stock_title: str, stock_desc: str,
            ss_title: Optional[str], ss_desc: Optional[str], choice: LayerChoice,
            opts: PreviewOptions) -> Tuple[str, List[Tuple[str, str]], str]:
    """What the game shows for *contract* under *choice*: (title, blocks, source).

    The same decision the merge makes (mission_layers.apply_layers): the
    layer on top wins where both have the string, a layer switched off never
    shows, and a StarStrings title that wins while Smart Citizen is on gets
    Smart Citizen's title extras. *ss_title* / *ss_desc* are None where
    StarStrings has nothing for the key (or is unavailable). Smart Citizen
    always has a string for a sample: the preview simulates it.
    """
    sc_title, sc_blocks = simulate(contract, stock_title, stock_desc, opts)
    title_source = choice.winner(ss_title is not None, True)
    desc_source = choice.winner(ss_desc is not None, True)

    if title_source == STARSTRINGS:
        title = ss_title or ""
        if choice.smart and opts.starstrings_extras:
            extras = TitleExtras(
                phrases=opts.shorten_phrases, rank_separator=opts.rank_separator,
                standardize_hauling=opts.standardize_hauling,
                shorten=bool(opts.shorten_phrases) or opts.standardize_hauling,
                route=opts.route,
                route_config=_PlacementConfig(opts.placement, opts.title_separator),
                show_ground=opts.ground_tag, show_space=opts.space_tag,
                ground_label=opts.ground_label)
            entry = IndexEntry(ground=contract.ground, space=contract.space,
                               route=_route_text(contract, opts))
            title = starstrings_title(title, extras, entry)
    elif title_source == SMART:
        title = sc_title
    else:
        title = stock_title

    if desc_source == STARSTRINGS:
        blocks = [("body", ss_desc or "")]
    elif desc_source == SMART:
        blocks = sc_blocks
    else:
        blocks = [("body", stock_desc)]
    return title, blocks, title_source or STOCK


@dataclass(frozen=True)
class _PlacementConfig:
    """The two route fields apply_mission_title reads."""

    placement: str
    title_separator: str


# ── The layer orderer ───────────────────────────────────────────────────────

class LayerStack(QWidget):
    """Two overlapping layer chips; the one in front (left) is on top.

    Click the chip behind to bring it forward (or drag it across), click a
    chip's dot to switch that layer on or off. Space swaps, 1 and 2 switch the
    front and back layer. Emits ``changed`` with the new LayerChoice.
    """

    changed = pyqtSignal(object)

    CHIP_W, CHIP_H, OVERLAP, DOT_R = 112, 24, 16, 4.5
    DOT_ZONE = 17

    def __init__(self, choice: LayerChoice = DEFAULT_CHOICE, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._choice = choice
        self._mixed = False
        self._unavailable = {STARSTRINGS: "", SMART: ""}   # layer -> reason, "" = available
        self._hover: Optional[str] = None
        self._press: Optional[Tuple[str, QPointF]] = None
        self._drag_dx = 0.0
        self._swap_t = 1.0          # 0 -> 1 while the chips change places
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(170)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._labels = {STARSTRINGS: "StarStrings", SMART: "Smart Citizen"}
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    # ── state ──
    def choice(self) -> LayerChoice:
        return self._choice

    def set_choice(self, choice: LayerChoice, mixed: bool = False) -> None:
        animate = choice.top != self._choice.top and self.isVisible()
        self._choice = choice
        self._mixed = mixed
        if animate:
            self._anim.stop()
            self._anim.setStartValue(0.0)
            self._anim.setEndValue(1.0)
            self._anim.start()
        self._refresh_tooltip()
        self.update()

    def set_labels(self, starstrings: str, smart: str) -> None:
        self._labels = {STARSTRINGS: starstrings, SMART: smart}
        self._refresh_tooltip()
        self.update()

    def set_unavailable(self, layer: str, reason: str) -> None:
        self._unavailable[layer] = reason or ""
        self._refresh_tooltip()
        self.update()

    def _refresh_tooltip(self) -> None:
        top, back = self._choice.order()
        tip = tr("missions.stack_tip", top=self._labels[top], back=self._labels[back])
        reason = self._unavailable.get(STARSTRINGS)
        if reason:
            tip += "\n" + reason
        self.setToolTip(tip)
        self.setAccessibleName(tip)

    # ── geometry ──
    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return QSize(2 * self.CHIP_W - self.OVERLAP + 4, self.CHIP_H + 6)

    def _slot_x(self, slot: int) -> float:
        return 1.0 + slot * (self.CHIP_W - self.OVERLAP)

    def _chip_rect(self, layer: str) -> QRectF:
        top = self._choice.top
        slot = 0 if layer == top else 1
        x = self._slot_x(slot)
        if self._swap_t < 1.0:
            # Coming from the other slot.
            x = self._slot_x(1 - slot) + (x - self._slot_x(1 - slot)) * self._swap_t
        if self._press and self._press[0] == layer and self._drag_dx:
            x = max(self._slot_x(0), min(self._slot_x(1), x + self._drag_dx))
        return QRectF(x, 2.0, self.CHIP_W, self.CHIP_H)

    def _chip_at(self, pos: QPointF) -> Optional[str]:
        top, back = self._choice.order()
        for layer in (top, back):        # front first
            if self._chip_rect(layer).contains(pos):
                return layer
        return None

    def _on_dot(self, layer: str, pos: QPointF) -> bool:
        r = self._chip_rect(layer)
        return pos.x() >= r.right() - self.DOT_ZONE

    # ── painting ──
    def _on_anim(self, value) -> None:
        self._swap_t = float(value)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        top, back = self._choice.order()
        if self._press and self._press[0] == back and self._drag_dx:
            top, back = back, top           # the dragged chip rides in front
        for layer, front in ((back, False), (top, True)):
            self._paint_chip(p, layer, front)
        if self.hasFocus():
            pen = QPen(QColor(HANGAR_MUTED))
            pen.setStyle(Qt.PenStyle.DotLine)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)
        p.end()

    def _paint_chip(self, p: QPainter, layer: str, front: bool) -> None:
        r = self._chip_rect(layer)
        on = self._choice.uses(layer)
        unavailable = bool(self._unavailable.get(layer))
        live = on and not unavailable
        accent = QColor(LAYER_COLORS[layer])
        dim = 0.55 if self._mixed else 1.0
        if front and live:
            shadow = QColor(0, 0, 0, 110)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(shadow)
            p.drawRoundedRect(r.translated(2, 2), 4, 4)
        fill = QColor(HANGAR_PLATE if front else HANGAR_HULL)
        if live:
            tint = QColor(accent)
            tint.setAlphaF((0.26 if front else 0.10) * dim)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(fill)
            p.drawRoundedRect(r, 4, 4)
            p.setBrush(tint)
            p.drawRoundedRect(r, 4, 4)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(HANGAR_HULL))
            p.drawRoundedRect(r, 4, 4)
        border = QColor(accent if live else HANGAR_FAINT)
        if not front and live:
            border.setAlphaF(0.55)
        if self._hover == layer and live:
            border = border.lighter(130)
        pen = QPen(border)
        pen.setWidthF(1.6 if front and live else 1.0)
        if not live:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 4, 4)

        # Label: the back chip's left edge is under the front one.
        left_pad = 8 if front else self.OVERLAP + 6
        text_rect = QRectF(r.left() + left_pad, r.top(), r.width() - left_pad - self.DOT_ZONE,
                           r.height())
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.0))
        font.setWeight(QFont.Weight.DemiBold if front else QFont.Weight.Normal)
        font.setStrikeOut(not live)
        p.setFont(font)
        color = QColor(HANGAR_TEXT if (front and live) else HANGAR_MUTED if live else HANGAR_FAINT)
        if self._mixed:
            color.setAlphaF(0.7)
        p.setPen(color)
        text = QFontMetrics(font).elidedText(self._labels[layer], Qt.TextElideMode.ElideRight,
                                             int(text_rect.width()))
        p.drawText(text_rect, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                   text)

        # The on/off dot.
        c = QPointF(r.right() - self.DOT_ZONE / 2, r.center().y())
        dot_pen = QPen(QColor(accent if live else HANGAR_FAINT))
        dot_pen.setWidthF(1.3)
        p.setPen(dot_pen)
        p.setBrush(QColor(accent) if live else Qt.BrushStyle.NoBrush)
        p.drawEllipse(c, self.DOT_R, self.DOT_R)

    # ── input ──
    def mouseMoveEvent(self, event) -> None:  # noqa: N802 (Qt name)
        pos = event.position()
        if self._press is not None:
            dx = pos.x() - self._press[1].x()
            if abs(dx) > 5 or self._drag_dx:
                self._drag_dx = dx
                self.update()
            return
        hover = self._chip_at(pos)
        if hover != self._hover:
            self._hover = hover
            self.update()

    def leaveEvent(self, _event) -> None:  # noqa: N802 (Qt name)
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        layer = self._chip_at(event.position())
        if layer is not None:
            self._press = (layer, event.position())
            self._drag_dx = 0.0

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 (Qt name)
        press, self._press = self._press, None
        dragged, self._drag_dx = self._drag_dx, 0.0
        if press is None:
            return
        layer, start = press
        if dragged:
            # Dropped past the middle of the other slot: the chips swap.
            moved_to_front = layer != self._choice.top and dragged < -self.CHIP_W / 3
            moved_to_back = layer == self._choice.top and dragged > self.CHIP_W / 3
            if moved_to_front:
                self._emit(self._choice.with_top(layer))
            elif moved_to_back:
                self._emit(self._choice.with_top(self._choice.order()[1]))
            else:
                self.update()
            return
        if self._on_dot(layer, start):
            if self._unavailable.get(layer):
                return
            self._emit(self._choice.with_layer(layer, not self._choice.uses(layer)))
        elif layer != self._choice.top:
            self._emit(self._choice.with_top(layer))

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        key = event.key()
        top, back = self._choice.order()
        if key in (Qt.Key.Key_Space, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._emit(self._choice.with_top(back))
        elif key == Qt.Key.Key_1 and not self._unavailable.get(top):
            self._emit(self._choice.with_layer(top, not self._choice.uses(top)))
        elif key == Qt.Key.Key_2 and not self._unavailable.get(back):
            self._emit(self._choice.with_layer(back, not self._choice.uses(back)))
        else:
            super().keyPressEvent(event)

    def _emit(self, choice: LayerChoice) -> None:
        if choice == self._choice and not self._mixed:
            self.update()
            return
        self.set_choice(choice)
        self.changed.emit(choice)


class _LayerRow(QWidget):
    """One orderer row: a mission type's name and title count, and its stack."""

    picked = pyqtSignal(str)

    def __init__(self, group: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.group = group
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 1, 0, 1)
        row.setSpacing(6)
        self.name = QLabel()
        self.name.setCursor(Qt.CursorShape.PointingHandCursor)
        self.count = QLabel()
        self.count.setStyleSheet(f"color: {HANGAR_FAINT};")
        row.addWidget(self.name)
        row.addWidget(self.count)
        row.addStretch(1)
        self.stack = LayerStack()
        row.addWidget(self.stack)

    def mousePressEvent(self, event) -> None:  # noqa: N802 (Qt name)
        if event.button() == Qt.MouseButton.LeftButton:
            self.picked.emit(self.group)
        super().mousePressEvent(event)


class _ContractDelegate(QStyledItemDelegate):
    """A contract row: rich-text title, contractor under it, change marker."""

    PAD = 14

    def _doc(self, index, width: int) -> QTextDocument:
        doc = QTextDocument()
        doc.setDefaultFont(QFont(GAME_TEXT_FONT_FAMILY, 10))
        doc.setDefaultStyleSheet(f"body {{ color: {HOLO}; }}")
        doc.setHtml(index.data(HTML_ROLE) or "")
        doc.setTextWidth(max(80, width - 2 * self.PAD))
        return doc

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt name)
        doc = self._doc(index, option.rect.width() or 300)
        return QSize(option.rect.width(), int(doc.size().height()) + 18)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        rect = option.rect
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(rect, QColor(127, 216, 230, 26))
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor(HOLO))
        painter.setPen(QColor(HOLO_LINE))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        doc = self._doc(index, rect.width())
        painter.translate(rect.left() + self.PAD, rect.top() + 8)
        doc.drawContents(painter)
        painter.restore()
        if index.data(CHANGED_ROLE):
            painter.save()
            pen = QPen(QColor(HANGAR_SIGNAL))
            pen.setStyle(Qt.PenStyle.DashLine)
            pen.setWidthF(1.5)
            painter.setPen(pen)
            painter.drawRect(QRectF(rect.adjusted(4, 3, -5, -4)))
            painter.restore()


class _Switch(QCheckBox):
    """A full-width settings row: label (and an optional hint) left, a toggle right.

    Still a QCheckBox, so ``toggled`` / ``isChecked`` and the bindings to the
    Enhancements page are unchanged; only how it draws is. The hint wraps
    (translations run long), so the row's height follows its width.
    """

    PILL_W, PILL_H = 30, 16
    LABEL_H = 20

    def __init__(self) -> None:
        super().__init__()
        self._hint = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        policy = QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def setHint(self, hint: str) -> None:  # noqa: N802 (Qt-style name)
        self._hint = hint
        self.updateGeometry()
        self.update()

    def _hint_font(self) -> QFont:
        font = QFont(self.font())
        font.setPointSizeF(max(7.5, font.pointSizeF() - 1.5))
        return font

    def _text_width(self, width: int) -> int:
        return max(80, width - self.PILL_W - 16)

    def _hint_height(self, width: int) -> int:
        if not self._hint:
            return 0
        rect = QFontMetrics(self._hint_font()).boundingRect(
            QRect(0, 0, self._text_width(width), 1000),
            int(Qt.TextFlag.TextWordWrap), self._hint)
        return rect.height()

    def hasHeightForWidth(self) -> bool:  # noqa: N802 (Qt name)
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802 (Qt name)
        if not self._hint:
            return 30
        return 3 + self.LABEL_H + self._hint_height(width) + 6

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        width = self.width() if self.width() > 100 else 360
        return QSize(240, self.heightForWidth(width))

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return QSize(160, self.sizeHint().height())

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().resizeEvent(event)
        if self._hint and self.height() != self.heightForWidth(self.width()):
            self.updateGeometry()

    def hitButton(self, pos) -> bool:  # noqa: N802 (Qt name): the whole row toggles
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        on, enabled = self.isChecked(), self.isEnabled()
        p.setPen(QColor(HANGAR_LINE))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        text_w = self._text_width(r.width())
        label_font = QFont(self.font())
        label_font.setWeight(QFont.Weight.Normal)
        p.setFont(label_font)
        p.setPen(QColor(HANGAR_TEXT if enabled else HANGAR_FAINT))
        top = 3 if self._hint else 0
        label_h = self.LABEL_H if self._hint else r.height()
        p.drawText(QRect(0, top, text_w, label_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        if self._hint:
            p.setFont(self._hint_font())
            p.setPen(QColor(HANGAR_MUTED if enabled else HANGAR_FAINT))
            p.drawText(QRect(0, top + self.LABEL_H, text_w, r.height() - top - self.LABEL_H),
                       int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
                           | Qt.TextFlag.TextWordWrap), self._hint)
        pill = QRectF(r.right() - self.PILL_W, (r.height() - self.PILL_H) / 2,
                      self.PILL_W, self.PILL_H)
        track = QColor(HANGAR_SIGNAL if on else HANGAR_PLATE_HI)
        if not enabled:
            track.setAlpha(90)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(track)
        p.drawRoundedRect(pill, self.PILL_H / 2, self.PILL_H / 2)
        knob = QColor("#FFFFFF" if on else HANGAR_MUTED)
        if not enabled:
            knob.setAlpha(120)
        p.setBrush(knob)
        d = self.PILL_H - 4
        x = pill.right() - d - 2 if on else pill.left() + 2
        p.drawEllipse(QRectF(x, pill.top() + 2, d, d))
        if self.hasFocus():
            pen = QPen(QColor(HANGAR_SIGNAL))
            pen.setWidthF(1.0)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(pill.adjusted(-2, -2, 2, 2), self.PILL_H / 2 + 2, self.PILL_H / 2 + 2)
        p.end()


class _Segmented(QWidget):
    """A segmented control mirroring a QComboBox's items and current index."""

    def __init__(self, combo: QComboBox) -> None:
        super().__init__()
        self._combo = combo
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i in range(combo.count()):
            b = QPushButton(combo.itemText(i))
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet(
                f"QPushButton {{ background: transparent; color: {HANGAR_MUTED};"
                f" border: 1px solid {HANGAR_LINE}; padding: 4px 10px; font-weight: 400; }}"
                f"QPushButton:checked {{ background: {HANGAR_PLATE_HI}; color: {HANGAR_TEXT};"
                f" border-color: {HANGAR_MUTED}; }}"
                f"QPushButton:disabled {{ color: {HANGAR_FAINT}; }}"
                f"QPushButton:checked:disabled {{ background: {HANGAR_HULL}; }}"
            )
            self._group.addButton(b, i)
            row.addWidget(b)
        row.addStretch(1)
        self._group.idClicked.connect(combo.setCurrentIndex)
        combo.currentIndexChanged.connect(self.sync)
        self.sync()

    def sync(self, *_args) -> None:
        button = self._group.button(self._combo.currentIndex())
        if button is not None:
            button.setChecked(True)


class MissionsTab(QWidget):
    """Mission text layers, mission settings and the Contracts Manager preview."""

    source_changed = pyqtSignal(bool)   # the "Use StarStrings" switch
    layers_changed = pyqtSignal()       # a layer choice settled: reload the strings

    def __init__(self, enhancements_tab, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._enh = enhancements_tab
        self._mt = enhancements_tab._tag_builder_pages["mission_titles"]
        self._contracts: List[SampleContract] = []
        self._rebuild_pending = False
        self._changed: Dict[str, set] = {}
        self._starstrings_on = True
        self._starstrings_reason = ""        # why StarStrings cannot be used, "" if it can
        self._starstrings_values: Dict[str, str] = {}
        self._type_counts: Dict[str, int] = {}
        from src.utils.settings import AppSettings
        self._choices: Dict[str, LayerChoice] = AppSettings.get_mission_layer_choices()
        self._clear_marks = QTimer(self)
        self._clear_marks.setSingleShot(True)
        self._clear_marks.setInterval(int(MARK_SECONDS * 1000))
        self._clear_marks.timeout.connect(self._unmark)
        self._layer_timer = QTimer(self)
        self._layer_timer.setSingleShot(True)
        self._layer_timer.setInterval(LAYER_RELOAD_MS)
        self._layer_timer.timeout.connect(self.layers_changed.emit)
        self.setup_ui()
        self.retranslate_ui()
        # Every setting redraws the preview at once.
        for switch in (self._route, self._rep, self._bp, self._shorten, self._ground,
                       self._space, self._f_rep, self._f_bp, self._f_hostiles):
            switch.toggled.connect(lambda _c: self._render_all())
        self._route_pos.currentIndexChanged.connect(lambda _i: self._render_all())
        self._ground_word.currentIndexChanged.connect(lambda _i: self._render_all())
        self._mt.config_changed.connect(self._render_all)

    # ── Build ───────────────────────────────────────────────────────────────

    def setup_ui(self) -> None:
        content = QWidget()
        outer = QHBoxLayout(content)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(20)
        outer.addWidget(self._build_controls())
        outer.addWidget(self._build_preview(), 1)
        host_in_scroll_area(self, content)

    def _heading(self, size: float = 15) -> QLabel:
        label = QLabel()
        font = QFont(DISPLAY_FONT_FAMILY)
        font.setPointSizeF(size)
        font.setWeight(QFont.Weight.Bold)
        label.setFont(font)
        return label

    def _secondary(self) -> QLabel:
        label = QLabel()
        label.setProperty("role", "secondary")
        label.setWordWrap(True)
        return label

    def _section(self, col: QVBoxLayout) -> QLabel:
        col.addSpacing(8)
        heading = self._heading(11.5)
        col.addWidget(heading)
        return heading

    def _rule(self, col: QVBoxLayout) -> None:
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {HANGAR_LINE};")
        col.addSpacing(3)
        col.addWidget(line)
        col.addSpacing(3)

    def _build_controls(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("missionControls")
        panel.setStyleSheet(f"#missionControls {{ border: 1px solid {HANGAR_LINE}; }}")
        panel.setFixedWidth(CONTROLS_WIDTH)
        col = QVBoxLayout(panel)
        col.setContentsMargins(20, 6, 20, 14)
        col.setSpacing(2)

        # The nav tab already says "Missions" and what it is for, so the panel
        # opens straight on the first choice. (Both labels kept, hidden, for
        # retranslate_ui.)
        self._title = self._heading()
        self._title.hide()
        self._lede = self._secondary()
        self._lede.hide()

        # ── Who writes mission text: the layer orderer ──
        self._layers_heading = self._section(col)
        self._layers_lede = self._secondary()
        col.addWidget(self._layers_lede)
        self._use_starstrings = _Switch()
        self._use_starstrings.setChecked(True)
        self._use_starstrings.toggled.connect(self._on_use_starstrings)
        col.addWidget(self._use_starstrings)

        legend = QHBoxLayout()
        legend.setContentsMargins(0, 6, 0, 2)
        self._legend_front = QLabel()
        self._legend_front.setStyleSheet(f"color: {HANGAR_FAINT}; font-size: 10px;")
        legend.addWidget(self._legend_front)
        legend.addStretch(1)
        col.addLayout(legend)

        self._rows: Dict[str, _LayerRow] = {}
        self._all_row = _LayerRow("all")
        bold = QFont(self._all_row.name.font())
        bold.setWeight(QFont.Weight.DemiBold)
        self._all_row.name.setFont(bold)
        self._all_row.stack.changed.connect(self._on_all_changed)
        col.addWidget(self._all_row)
        self._rule(col)
        for group in mission_types.MISSION_TYPES:
            self._add_row(col, group)
        self._rule(col)
        self._add_row(col, mission_types.ITEMS)

        self._ss_extras = _Switch()
        self._ss_extras.toggled.connect(self._on_ss_extras)
        col.addSpacing(4)
        col.addWidget(self._ss_extras)

        # ── Titles ──
        self._titles_heading = self._section(col)
        self._route = self._bind_check(self._mt._mt_enable)
        col.addWidget(self._route)
        # The Enhancements page's placement combo stays the one source of truth;
        # a hidden mirror keeps this tab's wiring, the segments show it.
        self._route_pos = self._mirror_combo(panel, self._mt._mt_placement)
        self._route_pos_label, self._route_seg = self._segment_row(col, self._route_pos)
        self._route.toggled.connect(self._route_seg.setEnabled)
        self._route_seg.setEnabled(self._route.isChecked())

        tags = self._mt._title_tag_checkboxes
        self._ground = self._bind_check(tags["ground"])
        col.addWidget(self._ground)
        self._ground_word = self._mirror_combo(panel, self._mt._mt_ground_label)
        self._ground_word_label, self._ground_seg = self._segment_row(col, self._ground_word)
        self._ground.toggled.connect(self._ground_seg.setEnabled)
        self._ground_seg.setEnabled(self._ground.isChecked())
        self._space = self._bind_check(tags["space"])
        self._rep = self._bind_check(tags["rep"])
        self._bp = self._bind_check(tags["blueprint"])
        self._shorten = self._bind_check(self._mt._mt_shorten_titles)
        for check in (self._space, self._rep, self._bp, self._shorten):
            col.addWidget(check)

        self._desc_heading = self._section(col)
        fields = self._enh._mission_field_checkboxes
        self._f_rep = self._bind_check(fields["reputation"])
        self._f_bp = self._bind_check(fields["blueprints"])
        self._f_hostiles = self._bind_check(fields["spawns"], extra=[fields["difficulty"]])
        for check in (self._f_rep, self._f_bp, self._f_hostiles):
            col.addWidget(check)

        # Rebuild: quiet until a setting is waiting, then it lights up.
        col.addSpacing(10)
        strip = QFrame()
        self._rebuild_strip = strip
        strip.setObjectName("rebuildStrip")
        strip.setStyleSheet(f"#rebuildStrip {{ background: {HANGAR_HULL}; }}")
        srow = QHBoxLayout(strip)
        srow.setContentsMargins(12, 8, 8, 8)
        srow.setSpacing(10)
        self._rebuild_note = self._secondary()
        srow.addWidget(self._rebuild_note, 1)
        self._rebuild_btn = QPushButton()
        self._rebuild_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rebuild_btn.clicked.connect(self._on_rebuild)
        srow.addWidget(self._rebuild_btn)
        col.addWidget(strip)

        self._build_category_names(col)

        col.addStretch(1)
        self._moved_note = self._secondary()
        self._moved_note.setStyleSheet(f"border-top: 1px solid {HANGAR_LINE}; padding-top: 10px;")
        col.addWidget(self._moved_note)
        self._sync_layer_rows()
        return panel

    def _build_category_names(self, col: QVBoxLayout) -> None:
        """The Contracts Manager's category names, each renamable.

        Folded by default (there are many); a row shows only when the loaded
        game strings have its key. A rename reaches the table with the same
        settled reload as a layer change.
        """
        from src.utils.settings import AppSettings
        self._category_names: Dict[str, str] = AppSettings.get_mission_category_names()
        col.addSpacing(8)
        head = QHBoxLayout()
        self._cat_heading = self._heading(11.5)
        head.addWidget(self._cat_heading)
        head.addStretch(1)
        self._cat_toggle = QPushButton()
        self._cat_toggle.setCheckable(True)
        self._cat_toggle.setCursor(Qt.CursorShape.PointingHandCursor)
        self._cat_toggle.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {HANGAR_MUTED}; border: none;"
            f" padding: 2px 4px; }} QPushButton:hover {{ color: {HANGAR_TEXT}; }}")
        self._cat_toggle.toggled.connect(self._on_category_toggle)
        head.addWidget(self._cat_toggle)
        col.addLayout(head)
        self._cat_hint = self._secondary()
        col.addWidget(self._cat_hint)
        self._cat_box = QWidget()
        grid = QGridLayout(self._cat_box)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(3)
        grid.setColumnStretch(1, 1)
        self._cat_rows: Dict[str, Tuple[QLabel, QLineEdit, QPushButton]] = {}
        for i, key in enumerate(mission_categories.CATEGORY_KEYS):
            stock = QLabel()
            stock.setStyleSheet(f"color: {HANGAR_MUTED};")
            stock.setFixedWidth(150)
            edit = QLineEdit(self._category_names.get(key, ""))
            edit.setToolTip(key)
            edit.textEdited.connect(lambda text, k=key: self._on_category_edited(k, text))
            reset = QPushButton("\u21BA")
            reset.setFixedWidth(26)
            reset.setCursor(Qt.CursorShape.PointingHandCursor)
            reset.clicked.connect(lambda _c, k=key: self._reset_category(k))
            reset.setVisible(bool(self._category_names.get(key)))
            for c, w in enumerate((stock, edit, reset)):
                grid.addWidget(w, i, c)
            self._cat_rows[key] = (stock, edit, reset)
        self._cat_box.setVisible(False)
        col.addWidget(self._cat_box)

    def _on_category_toggle(self, open_: bool) -> None:
        self._cat_box.setVisible(open_)
        self._refresh_category_header()

    def _refresh_category_header(self) -> None:
        renamed = sum(1 for v in self._category_names.values() if v)
        arrow = "\u25BE" if self._cat_toggle.isChecked() else "\u25B8"
        label = tr("missions.cat_renamed", count=renamed) if renamed else tr("missions.cat_show")
        self._cat_toggle.setText(f"{label} {arrow}")

    def _on_category_edited(self, key: str, text: str) -> None:
        name = text.strip()
        if name:
            self._category_names[key] = name
        else:
            self._category_names.pop(key, None)
        self._cat_rows[key][2].setVisible(bool(name))
        self._save_category_names()

    def _reset_category(self, key: str) -> None:
        self._category_names.pop(key, None)
        _stock, edit, reset = self._cat_rows[key]
        edit.clear()
        reset.setVisible(False)
        self._save_category_names()

    def _save_category_names(self) -> None:
        from src.utils.settings import AppSettings
        AppSettings.set_mission_category_names(self._category_names)
        self._refresh_category_header()
        self._layer_timer.start()

    def _refresh_category_rows(self) -> None:
        """Show each category the loaded strings have, with its game name."""
        lookup = getattr(self, "_stock", None)
        for key, (stock, edit, reset) in self._cat_rows.items():
            game = lookup(key) if lookup else None
            visible = bool(game)
            for w in (stock, edit):
                w.setVisible(visible)
            reset.setVisible(visible and bool(self._category_names.get(key)))
            if game:
                stock.setText(game)
                stock.setToolTip(game)
                edit.setPlaceholderText(game)

    def _add_row(self, col: QVBoxLayout, group: str) -> None:
        row = _LayerRow(group)
        row.stack.changed.connect(lambda choice, g=group: self._on_layer_changed(g, choice))
        row.picked.connect(self._focus_type)
        self._rows[group] = row
        col.addWidget(row)

    def _mirror_combo(self, parent: QWidget, source: QComboBox) -> QComboBox:
        """A hidden combo sharing *source*'s model and kept in step both ways."""
        combo = QComboBox(parent)
        combo.setModel(source.model())
        combo.setCurrentIndex(source.currentIndex())
        combo.currentIndexChanged.connect(source.setCurrentIndex)

        def pull(index: int) -> None:
            if combo.currentIndex() != index:
                combo.blockSignals(True)
                combo.setCurrentIndex(index)
                combo.blockSignals(False)
                self._render_all()
        source.currentIndexChanged.connect(pull)
        combo.currentIndexChanged.connect(self._mark_rebuild)
        combo.hide()
        return combo

    def _segment_row(self, col: QVBoxLayout, combo: QComboBox) -> Tuple[QLabel, "_Segmented"]:
        row = QHBoxLayout()
        row.setContentsMargins(0, 6, 0, 6)
        label = QLabel()
        label.setStyleSheet(
            f"QLabel {{ color: {HANGAR_MUTED}; }} QLabel:disabled {{ color: {HANGAR_FAINT}; }}")
        row.addWidget(label)
        seg = _Segmented(combo)
        row.addWidget(seg, 1)
        col.addLayout(row)
        return label, seg

    def _bind_check(self, target: QCheckBox, extra: Optional[List[QCheckBox]] = None) -> _Switch:
        """A switch here that drives *target* (and *extra*) on the Enhancements page."""
        switch = _Switch()
        switch.setChecked(target.isChecked())

        def push(checked: bool) -> None:
            for widget in [target] + (extra or []):
                if widget.isChecked() != checked:
                    widget.setChecked(checked)
            self._mark_rebuild()

        def pull(checked: bool) -> None:
            if switch.isChecked() != checked:
                switch.blockSignals(True)
                switch.setChecked(checked)
                switch.blockSignals(False)
                self._render_all()

        switch.toggled.connect(push)
        target.toggled.connect(pull)
        return switch

    def _build_preview(self) -> QWidget:
        wrap = QWidget()
        col = QVBoxLayout(wrap)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(8)
        head = QHBoxLayout()
        self._preview_title = self._heading()
        head.addWidget(self._preview_title)
        head.addStretch(1)
        self._preview_where = self._secondary()
        self._preview_where.setWordWrap(False)
        head.addWidget(self._preview_where)
        col.addLayout(head)

        screen = QFrame()
        screen.setObjectName("contractsScreen")
        screen.setStyleSheet(
            f"#contractsScreen {{ background: qradialgradient(cx:0.7, cy:0, radius:1.1,"
            f" fx:0.7, fy:0, stop:0 #10303B, stop:0.55 {GLASS}, stop:1 {GLASS});"
            f" border: 1px solid #1D3D48; }}"
        )
        grid = QGridLayout(screen)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)
        self._app_bar = QLabel()
        self._app_bar.setTextFormat(Qt.TextFormat.RichText)
        self._app_bar.setStyleSheet(
            f"background: transparent; color: {HOLO_DIM}; padding: 10px 16px;"
            f" border-bottom: 1px solid {HOLO_LINE}; font-family: '{GAME_TEXT_FONT_FAMILY}';"
            " font-size: 11px; letter-spacing: 2px;"
        )
        grid.addWidget(self._app_bar, 0, 0, 1, 2)

        self._list = QListWidget()
        self._list.setItemDelegate(_ContractDelegate(self._list))
        self._list.setFixedWidth(320)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self._list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: none;"
            f" border-right: 1px solid {HOLO_LINE}; }}"
        )
        self._list.currentRowChanged.connect(lambda _r: self._render_detail())
        grid.addWidget(self._list, 1, 0)

        self._detail = QTextBrowser()
        self._detail.setOpenLinks(False)
        self._detail.setFrameShape(QFrame.Shape.NoFrame)
        self._detail.setStyleSheet(
            f"QTextBrowser {{ background: transparent; color: {HOLO_TEXT}; border: none;"
            f" padding: 12px 18px; font-family: '{GAME_TEXT_FONT_FAMILY}'; font-size: 12px; }}"
        )
        grid.addWidget(self._detail, 1, 1)
        grid.setRowStretch(1, 1)
        grid.setColumnStretch(1, 1)
        col.addWidget(screen, 1)

        self._caption = self._secondary()
        col.addWidget(self._caption)
        return wrap

    # ── Text ────────────────────────────────────────────────────────────────

    def retranslate_ui(self) -> None:
        self._title.setText(tr("missions.title"))
        self._lede.setText(tr("missions.lede"))
        self._layers_heading.setText(tr("missions.layers_heading"))
        self._layers_lede.setText(tr("missions.layers_lede"))
        self._use_starstrings.setText(tr("missions.use_starstrings"))
        self._legend_front.setText(tr("missions.layers_legend"))
        self._all_row.name.setText(tr("missions.type_all"))
        for group, row in self._rows.items():
            row.name.setText(tr(f"missions.type_{group}"))
        for row in [self._all_row, *self._rows.values()]:
            row.stack.set_labels(tr("missions.layer_starstrings"), tr("missions.layer_smart"))
        self._ss_extras.setText(tr("missions.ss_extras"))
        self._ss_extras.setHint(tr("missions.ss_extras_hint"))
        self._titles_heading.setText(tr("missions.titles_heading"))
        self._route.setText(tr("missions.route"))
        self._route.setHint(tr("missions.route_hint"))
        self._route_pos_label.setText(tr("missions.route_position"))
        self._ground.setText(tr("missions.ground_tag"))
        self._ground.setHint(tr("missions.ground_hint"))
        self._ground_word_label.setText(tr("missions.ground_word"))
        self._space.setText(tr("missions.space_tag"))
        self._space.setHint(tr("missions.space_hint"))
        self._rep.setHint(tr("missions.rep_hint"))
        self._bp.setHint(tr("missions.bp_hint"))
        self._shorten.setHint(tr("missions.shorten_hint"))
        self._rep.setText(tr("missions.rep_tag"))
        self._bp.setText(tr("missions.bp_tag"))
        self._shorten.setText(tr("missions.shorten"))
        self._desc_heading.setText(tr("missions.desc_heading"))
        self._f_rep.setText(tr("missions.field_rep"))
        self._f_bp.setText(tr("missions.field_bp"))
        self._f_hostiles.setText(tr("missions.field_hostiles"))
        self._rebuild_btn.setText(tr("missions.rebuild_btn"))
        self._cat_heading.setText(tr("missions.cat_heading"))
        self._cat_hint.setText(tr("missions.cat_hint"))
        self._refresh_category_header()
        self._moved_note.setText(tr("missions.moved_note"))
        self._preview_title.setText(tr("missions.preview_title"))
        self._preview_where.setText(tr("missions.preview_where"))
        self._caption.setText(tr("missions.caption"))
        self._app_bar.setText(
            f"<b style='color:{HOLO};letter-spacing:3px'>{html.escape(tr('missions.app_contracts'))}"
            f"</b>&nbsp;&nbsp;&nbsp;&nbsp;<span style='color:{HOLO}'>"
            f"{html.escape(tr('missions.app_offers'))}</span>&nbsp;&nbsp;&nbsp;"
            f"{html.escape(tr('missions.app_accepted'))}&nbsp;&nbsp;&nbsp;"
            f"{html.escape(tr('missions.app_history'))}"
        )
        self._refresh_counts()
        self._refresh_source_state()
        self._sync_layer_rows()
        if hasattr(self, "_rendered"):
            self._fill_list()
            self._render_detail()

    # ── StarStrings and the layers ──────────────────────────────────────────

    def set_source(self, starstrings: bool) -> None:
        """Show whether StarStrings is switched on (MainWindow, from the setting)."""
        self._starstrings_on = bool(starstrings)
        if self._use_starstrings.isChecked() != self._starstrings_on:
            self._use_starstrings.blockSignals(True)
            self._use_starstrings.setChecked(self._starstrings_on)
            self._use_starstrings.blockSignals(False)
        self._refresh_source_state()
        self._render_all()

    def set_starstrings_status(self, reason: str, status: str) -> None:
        """Why StarStrings cannot be used ("" when it can), and a one-line status."""
        self._starstrings_reason = reason or ""
        self._starstrings_status = status or ""
        self._refresh_source_state()
        self._render_all()

    def _on_use_starstrings(self, on: bool) -> None:
        self._starstrings_on = on
        self._refresh_source_state()
        self._render_all()
        self.source_changed.emit(on)

    def _on_ss_extras(self, on: bool) -> None:
        from src.utils.settings import AppSettings
        if AppSettings.get_starstrings_title_extras() != on:
            AppSettings.set_starstrings_title_extras(on)
            self._layer_timer.start()
        self._render_all()

    def _starstrings_unavailable(self) -> str:
        """Why StarStrings cannot show here right now, or ""."""
        if not self._starstrings_on:
            return tr("missions.ss_status_off")
        return self._starstrings_reason

    def _refresh_source_state(self) -> None:
        reason = self._starstrings_unavailable()
        status = reason or getattr(self, "_starstrings_status", "")
        self._use_starstrings.setHint(status)
        for row in [self._all_row, *self._rows.values()]:
            row.stack.set_unavailable(STARSTRINGS, reason)
        from src.utils.settings import AppSettings
        extras_on = AppSettings.get_starstrings_title_extras()
        if self._ss_extras.isChecked() != extras_on:
            self._ss_extras.blockSignals(True)
            self._ss_extras.setChecked(extras_on)
            self._ss_extras.blockSignals(False)
        self._ss_extras.setEnabled(not reason)
        self._rebuild_note.setText(
            tr("missions.rebuild_pending") if self._rebuild_pending
            else tr("missions.rebuild_note"))
        if self._rebuild_pending:
            style = (f"QPushButton {{ background: {HANGAR_SIGNAL}; color: white; border: none;"
                     f" padding: 7px; font-family: '{DISPLAY_FONT_FAMILY}'; font-weight: 700; }}"
                     "QPushButton:hover { background: #F2262C; }")
        else:
            style = (f"QPushButton {{ background: transparent; color: {HANGAR_TEXT};"
                     f" border: 1px solid {HANGAR_MUTED}; padding: 7px;"
                     f" font-family: '{DISPLAY_FONT_FAMILY}'; font-weight: 700; }}"
                     f"QPushButton:disabled {{ color: {HANGAR_FAINT}; border-color: {HANGAR_LINE}; }}")
        self._rebuild_btn.setStyleSheet(style)

    def layer_choices(self) -> Dict[str, LayerChoice]:
        return dict(self._choices)

    def _on_layer_changed(self, group: str, choice: LayerChoice) -> None:
        self._choices[group] = choice
        self._save_layers()

    def _on_all_changed(self, choice: LayerChoice) -> None:
        for group in mission_types.MISSION_TYPES:
            self._choices[group] = choice
        self._save_layers()

    def _save_layers(self) -> None:
        from src.utils.settings import AppSettings
        AppSettings.set_mission_layer_choices(self._choices)
        self._sync_layer_rows()
        self._render_all()
        self._layer_timer.start()

    def _sync_layer_rows(self) -> None:
        for group, row in self._rows.items():
            choice = self._choices.get(group, DEFAULT_CHOICE)
            if row.stack.choice() != choice:
                row.stack.set_choice(choice)
        mission_choices = [self._choices.get(g, DEFAULT_CHOICE) for g in mission_types.MISSION_TYPES]
        common = max(set(mission_choices), key=mission_choices.count)
        mixed = len(set(mission_choices)) > 1
        self._all_row.stack.set_choice(common, mixed=mixed)
        self._all_row.count.setText(tr("missions.type_mixed") if mixed else "")

    def set_type_counts(self, counts: Mapping[str, int]) -> None:
        """How many titles of each type the loaded strings hold (MainWindow)."""
        self._type_counts = dict(counts)
        self._refresh_counts()

    def _refresh_counts(self) -> None:
        for group, row in self._rows.items():
            n = self._type_counts.get(group)
            row.count.setText(f"{n:,}" if n else "")

    def _focus_type(self, group: str) -> None:
        """A row's name was clicked: show that type's first sample contract."""
        for i, c in enumerate(self._contracts):
            if c.mission_type == group:
                self._list.setCurrentRow(i)
                return

    def _mark_rebuild(self, *_args) -> None:
        self._rebuild_pending = True
        self._refresh_source_state()

    def _on_rebuild(self) -> None:
        """Save the mission settings and rebuild the generated mission text."""
        self._rebuild_pending = False
        self._refresh_source_state()
        self._enh._on_generate_enhancements_clicked()

    # ── Preview ─────────────────────────────────────────────────────────────

    @staticmethod
    def preview_keys() -> set:
        """Every key the preview may show (MainWindow looks only these up)."""
        return {k for c in SAMPLE_CONTRACTS for k in (c.title_key, c.desc_key)}

    def set_strings(self, lookup: Callable[[str], Optional[str]],
                    stock: Optional[Callable[[str], Optional[str]]] = None,
                    starstrings: Optional[Mapping[str, str]] = None) -> None:
        """New strings loaded.

        *lookup* gives what Apply writes, *stock* the base, *starstrings*
        StarStrings' own strings before the layer choices (empty when it is
        off or missing). The preview works every layer choice out from the
        last two, so a choice shows before the reload that applies it.
        """
        self._lookup = lookup
        self._stock = stock or lookup
        self._starstrings_values = dict(starstrings or {})
        self._contracts = pick_contracts(self._stock)
        self._refresh_category_rows()
        # Marked too: a setting can reach the preview through a reload first.
        self._render_all()

    def _options(self) -> PreviewOptions:
        cfg = self._mt.config
        return PreviewOptions(
            route=self._route.isChecked(),
            placement=self._mt._mt_placement.currentData() or cfg.placement,
            route_arrow=getattr(cfg, "route_arrow", "gt"),
            title_separator=getattr(cfg, "title_separator", "dash"),
            shorten_phrases=frozenset(getattr(cfg, "abbreviated_phrases", frozenset())),
            rank_separator=getattr(cfg, "rank_separator", "dash"),
            standardize_hauling=bool(getattr(cfg, "standardize_hauling_names", False)),
            rep_tag=self._rep.isChecked(),
            bp_tag=self._bp.isChecked(),
            ground_tag=self._ground.isChecked(),
            space_tag=self._space.isChecked(),
            ground_label=self._mt._mt_ground_label.currentData() or DEFAULT_GROUND_TAG_LABEL,
            field_rep=self._f_rep.isChecked(),
            field_bp=self._f_bp.isChecked(),
            field_hostiles=self._f_hostiles.isChecked(),
            starstrings_extras=self._ss_extras.isChecked(),
        )

    def _starstrings_for(self, key: str) -> Optional[str]:
        if self._starstrings_unavailable():
            return None
        return self._starstrings_values.get(key)

    def _render_all(self, mark_changes: bool = True) -> None:
        """Rebuild every contract's text from the current settings, at once.

        Each contract goes through its type's layer choice exactly as the
        merge would (compose), so the preview shows the effect of a switch
        or a layer click immediately; Rebuild mission text or the reload
        that follows a layer click makes it real. Parts that changed are lit.
        """
        if not hasattr(self, "_lookup"):
            return
        old = getattr(self, "_rendered", {})
        opts = self._options()
        rendered = {}
        for c in self._contracts:
            choice = self._choices.get(c.mission_type, DEFAULT_CHOICE)
            rendered[c.title_key] = compose(
                c, self._stock(c.title_key) or "", self._stock(c.desc_key) or "",
                self._starstrings_for(c.title_key), self._starstrings_for(c.desc_key),
                choice, opts)
        # Keep marks still on screen: one click can redraw twice (a switch here
        # and the Enhancements page it drives), and the second sees no change.
        previous = self._changed if self._clear_marks.isActive() else {}
        self._changed = {k: set(v) for k, v in previous.items()}
        if mark_changes and old:
            for key, (title, blocks, _source) in rendered.items():
                before = old.get(key)
                if before is None:
                    continue
                old_blocks = dict(before[1])
                lit = {bid for bid, text in blocks if old_blocks.get(bid) != text}
                if before[0] != title:
                    lit.add("title")
                if lit:
                    self._changed.setdefault(key, set()).update(lit)
        self._rendered = rendered
        self._fill_list()
        self._render_detail()
        if self._changed and self._changed != previous:
            self._clear_marks.start()

    def _source_badge(self, source: str) -> str:
        color = LAYER_COLORS.get(source, HOLO_DIM)
        label = tr(f"missions.layer_{source}") if source in LAYER_COLORS else tr("missions.layer_stock")
        return f"<span style='color:{color}'>&#9679;</span> {html.escape(label)}"

    def _fill_list(self) -> None:
        current = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for c in self._contracts:
            title, _blocks, source = self._rendered[c.title_key]
            item = QListWidgetItem()
            item.setData(KEY_ROLE, c.title_key)
            item.setData(HTML_ROLE, to_html(title) +
                         f"<br><span style='color:{HOLO_DIM};font-size:9pt'>"
                         f"{html.escape(c.contractor)} &middot; "
                         f"{html.escape(tr(f'missions.type_{c.mission_type}'))} &middot; "
                         f"{self._source_badge(source)}</span>")
            item.setData(CHANGED_ROLE, "title" in self._changed.get(c.title_key, ()))
            self._list.addItem(item)
        self._list.setCurrentRow(current if 0 <= current < self._list.count() else 0)
        self._list.blockSignals(False)
        if not self._contracts:
            self._detail.setHtml(
                f"<p style='color:{HOLO_DIM}'>{html.escape(tr('missions.preview_empty'))}</p>")

    def _unmark(self) -> None:
        self._changed = {}
        for i in range(self._list.count()):
            self._list.item(i).setData(CHANGED_ROLE, False)
        self._list.viewport().update()
        self._render_detail()

    def _render_detail(self) -> None:
        row = self._list.currentRow()
        if not (0 <= row < len(self._contracts)):
            return
        c = self._contracts[row]
        title, blocks, source = self._rendered[c.title_key]
        lit = self._changed.get(c.title_key, set())

        def mark(fragment: str, block_id: str) -> str:
            if block_id not in lit:
                return fragment
            return f"<span style='background-color:{CHANGED_BG}'>{fragment}</span>"

        cells = [(tr("missions.card_contractor"), html.escape(c.contractor)),
                 (tr("missions.card_reward"), html.escape(c.reward)),
                 (tr("missions.card_type"), html.escape(c.kind)),
                 (tr("missions.card_source"), self._source_badge(source))]
        meta = "".join(
            f"<td style='padding-right:26px'><span style='color:{HOLO_DIM};font-size:8pt;"
            f"letter-spacing:1px'>{html.escape(label)}</span><br>"
            f"<span style='color:{HOLO_BRIGHT};font-weight:600'>{value}</span></td>"
            for label, value in cells
        )
        body = "<br><br>".join(mark(to_html(text), bid) for bid, text in blocks if text)
        self._detail.setHtml(
            f"<div style='color:{HOLO_BRIGHT};font-size:14pt;font-weight:700'>"
            f"{mark(to_html(title), 'title')}</div>"
            f"<table style='margin:10px 0'><tr>{meta}</tr></table>"
            f"<div style='color:{HOLO_TEXT};line-height:150%'>{body}</div>"
        )
