"""Missions tab: the mission settings that matter, beside a Contracts Manager preview.

The left column is a front for settings the Enhancements page already owns
(it stays the single source of truth, now opened from the settings menu):
each switch here drives that page's own checkbox or combo, so its handlers,
saved settings and dirty tracking run exactly as before. The one setting of
its own is the source of mission text: StarStrings or Smart Citizen.

The right side is a close mock of the in-game Contracts Manager built from the
strings currently loaded (``set_strings``): real titles and descriptions,
with ``~mission(...)`` placeholders filled from sample values. Whatever the
last change altered gets a dashed red outline.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QRect, QRectF, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QTextDocument
from PyQt6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate,
    QTextBrowser, QVBoxLayout, QWidget,
)

from src.gui.theme import (
    DISPLAY_FONT_FAMILY, GAME_TEXT_FONT_FAMILY, HANGAR_FAINT, HANGAR_HULL, HANGAR_LINE,
    HANGAR_MUTED, HANGAR_PLATE_HI, HANGAR_SIGNAL, HANGAR_TEXT, host_in_scroll_area,
)
from src.utils.i18n import tr

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
CONTROLS_WIDTH = 400


@dataclass(frozen=True)
class SampleContract:
    """A contract the preview shows: its strings and made-up card values.

    The extra fields stand in for what the generator reads from the game
    files (rep reward, blueprint chance, haul route, hostiles), so the
    preview can show each Smart Citizen setting the moment it changes.
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


# Real keys from the game's strings. Contractor, reward and type are samples.
SAMPLE_CONTRACTS: Tuple[SampleContract, ...] = (
    SampleContract("CFP_RecoverCargo_Medium_Title", "CFP_RecoverCargo_Medium_Description",
                   "Citizens for Prosperity", "48,500 aUEC", "Cargo recovery", rep=150,
                   blueprints=("P8-SC SMG", "C54 SMG", "S71 Rifle", "G-2 Helmet Woodland"),
                   hostiles="Light fighters x4", difficulty="Medium"),
    SampleContract("Covalex_Delivery_Stanton_Medium_Title_001",
                   "Covalex_Delivery_Stanton_Medium_Desc_001",
                   "Covalex Shipping", "21,750 aUEC", "Delivery", rep=100,
                   route=("Area18", "Lorville")),
    SampleContract("Adagio_Industrial_Component_Salvage_Stanton_M_Title_001",
                   "Adagio_Industrial_Component_Salvage_Stanton_M_Desc_001",
                   "Adagio Holdings", "36,000 aUEC", "Salvage", rep=100,
                   blueprints=("Bracer Cooler", "FR-76 Shield"),
                   hostiles="None expected", difficulty="Easy"),
    SampleContract("CFP_RecoverCargo_Easy_Title", "CFP_RecoverCargo_Easy_Description",
                   "Citizens for Prosperity", "27,000 aUEC", "Cargo recovery", rep=100,
                   blueprints=("C54 SMG",), hostiles="Light fighters x2", difficulty="Easy"),
    SampleContract("Covalex_Delivery_Stanton_Super_Title_001",
                   "Covalex_Delivery_Stanton_Super_Desc_001",
                   "Covalex Shipping", "64,000 aUEC", "Delivery", rep=200,
                   route=("Port Tressler", "Orison")),
)

# Sample values for ~mission(...) placeholders, by name (lower case).
SAMPLE_TOKENS: Dict[str, str] = {
    "location": "Wala's outer belt", "destination": "Area18", "system": "Stanton",
    "missionmaxscusize": "8 SCU", "targetname": "Vesper Kade", "item": "medical supplies",
    "client": "Lima Endicott", "contractor": "Lima Endicott", "ship": "Cutlass Black",
    "danger": "moderate", "timed": "45 minutes", "scripamount": "12",
    "approvalcode": "7741", "rush": "", "trouble": "outlaws",
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
    """The Smart Citizen mission settings, as the preview applies them."""

    route: bool = True
    placement: str = "append"
    route_arrow: str = "gt"
    title_separator: str = "dash"
    shorten_phrases: frozenset = frozenset()
    rank_separator: str = "dash"
    rep_tag: bool = True
    bp_tag: bool = True
    field_rep: bool = True
    field_bp: bool = True
    field_hostiles: bool = False


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


def simulate(contract: SampleContract, title: str, desc: str,
             opts: PreviewOptions) -> Tuple[str, List[Tuple[str, str]]]:
    """The title and description blocks Smart Citizen would write for *contract*.

    Mirrors the generator's order (scripts/generate_enhancements_ini.py):
    shorten, then the route placed per the setting, then [BP] and the rep tag.
    Description blocks are ``(block id, game text)``.
    """
    from types import SimpleNamespace
    from src.utils.tag_builder import abbreviate_title, apply_mission_title, render_route

    out = abbreviate_title(plain_title(title), opts.shorten_phrases, opts.rank_separator)
    if opts.route and contract.route:
        route = render_route(contract.route[0], contract.route[1], opts.route_arrow)
        cfg = SimpleNamespace(placement=opts.placement, title_separator=opts.title_separator)
        out = apply_mission_title(out, route, cfg)
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


class _SourceCard(QPushButton):
    """A checkable card: a bold name and a wrapped one-line description."""

    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(68)
        self.setStyleSheet(
            f"QPushButton {{ background: {HANGAR_HULL}; border: 1.5px solid transparent; }}"
            f"QPushButton:checked {{ border-color: {HANGAR_SIGNAL}; background: #231A20; }}"
        )
        inner = QVBoxLayout(self)
        inner.setContentsMargins(10, 8, 10, 8)
        inner.setSpacing(2)
        self.name = QLabel()
        font = QFont(DISPLAY_FONT_FAMILY)
        font.setPointSizeF(10.5)
        font.setWeight(QFont.Weight.Bold)
        self.name.setFont(font)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.desc.setProperty("role", "secondary")
        for label in (self.name, self.desc):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            label.setStyleSheet("background: transparent;")
            inner.addWidget(label)
        inner.addStretch(1)


class _Switch(QCheckBox):
    """A full-width settings row: label (and an optional hint) left, a toggle right.

    Still a QCheckBox, so ``toggled`` / ``isChecked`` and the bindings to the
    Enhancements page are unchanged; only how it draws is.
    """

    PILL_W, PILL_H = 30, 16

    def __init__(self) -> None:
        super().__init__()
        self._hint = ""
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def setHint(self, hint: str) -> None:  # noqa: N802 (Qt-style name)
        self._hint = hint
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return QSize(240, 42 if self._hint else 30)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 (Qt name)
        return QSize(160, self.sizeHint().height())

    def hitButton(self, pos) -> bool:  # noqa: N802 (Qt name): the whole row toggles
        return self.rect().contains(pos)

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt name)
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect()
        on, enabled = self.isChecked(), self.isEnabled()
        p.setPen(QColor(HANGAR_LINE))
        p.drawLine(r.left(), r.bottom(), r.right(), r.bottom())
        text_w = r.width() - self.PILL_W - 16
        label_font = QFont(self.font())
        label_font.setWeight(QFont.Weight.Normal)
        p.setFont(label_font)
        p.setPen(QColor(HANGAR_TEXT if enabled else HANGAR_FAINT))
        top = 3 if self._hint else 0
        label_h = 20 if self._hint else r.height()
        p.drawText(QRect(0, top, text_w, label_h),
                   Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self.text())
        if self._hint:
            hint_font = QFont(self.font())
            hint_font.setPointSizeF(max(7.5, hint_font.pointSizeF() - 1.5))
            p.setFont(hint_font)
            p.setPen(QColor(HANGAR_MUTED if enabled else HANGAR_FAINT))
            p.drawText(QRect(0, 21, text_w, 17),
                       Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._hint)
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
    """Mission text settings and the Contracts Manager preview."""

    source_changed = pyqtSignal(bool)   # True: StarStrings writes mission text

    def __init__(self, enhancements_tab, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._enh = enhancements_tab
        self._mt = enhancements_tab._tag_builder_pages["mission_titles"]
        self._contracts: List[SampleContract] = []
        self._rebuild_pending = False
        self._changed: Dict[str, set] = {}
        self._clear_marks = QTimer(self)
        self._clear_marks.setSingleShot(True)
        self._clear_marks.setInterval(int(MARK_SECONDS * 1000))
        self._clear_marks.timeout.connect(self._unmark)
        self.setup_ui()
        self.retranslate_ui()
        # Every setting redraws the preview at once.
        for switch in (self._route, self._rep, self._bp, self._shorten,
                       self._f_rep, self._f_bp, self._f_hostiles):
            switch.toggled.connect(lambda _c: self._render_all())
        self._route_pos.currentIndexChanged.connect(lambda _i: self._render_all())
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

        # Who writes mission text
        self._source_heading = self._section(col)
        cards = QHBoxLayout()
        cards.setSpacing(8)
        cards.setContentsMargins(0, 4, 0, 0)
        self._source_buttons: Dict[bool, _SourceCard] = {}
        for starstrings in (True, False):
            button = _SourceCard()
            button.clicked.connect(lambda _c, s=starstrings: self._choose_source(s))
            self._source_buttons[starstrings] = button
            cards.addWidget(button)
        col.addLayout(cards)

        # Everything below is Smart Citizen's own tagging; StarStrings mode
        # disables it as one block, with the reason on top.
        self._titles_note = QLabel()
        self._titles_note.setWordWrap(True)
        self._titles_note.setStyleSheet(
            f"background: {HANGAR_HULL}; color: {HANGAR_MUTED}; padding: 8px 10px;"
            f" border-left: 2px solid {HANGAR_MUTED};"
        )
        col.addSpacing(8)
        col.addWidget(self._titles_note)

        self._titles_heading = self._section(col)
        self._route = self._bind_check(self._mt._mt_enable)
        col.addWidget(self._route)
        # The Enhancements page's placement combo stays the one source of truth;
        # a hidden mirror keeps this tab's wiring, the segments show it.
        self._route_pos = QComboBox(panel)
        self._route_pos.setModel(self._mt._mt_placement.model())
        self._route_pos.setCurrentIndex(self._mt._mt_placement.currentIndex())
        self._route_pos.currentIndexChanged.connect(self._mt._mt_placement.setCurrentIndex)
        self._mt._mt_placement.currentIndexChanged.connect(self._sync_route_pos)
        self._route_pos.currentIndexChanged.connect(self._mark_rebuild)
        self._route_pos.hide()
        pos_row = QHBoxLayout()
        pos_row.setContentsMargins(0, 6, 0, 6)
        self._route_pos_label = QLabel()
        self._route_pos_label.setStyleSheet(
            f"QLabel {{ color: {HANGAR_MUTED}; }} QLabel:disabled {{ color: {HANGAR_FAINT}; }}")
        pos_row.addWidget(self._route_pos_label)
        self._route_seg = _Segmented(self._route_pos)
        pos_row.addWidget(self._route_seg, 1)
        col.addLayout(pos_row)
        self._route.toggled.connect(self._route_seg.setEnabled)
        self._route_seg.setEnabled(self._route.isChecked())
        self._rep = self._bind_check(self._mt._title_tag_checkboxes["rep"])
        self._bp = self._bind_check(self._mt._title_tag_checkboxes["blueprint"])
        self._shorten = self._bind_check(self._mt._mt_shorten_titles)
        for check in (self._rep, self._bp, self._shorten):
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

        col.addStretch(1)
        self._moved_note = self._secondary()
        self._moved_note.setStyleSheet(f"border-top: 1px solid {HANGAR_LINE}; padding-top: 10px;")
        col.addWidget(self._moved_note)
        return panel

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

        switch.toggled.connect(push)
        target.toggled.connect(pull)
        return switch

    def _sync_route_pos(self, index: int) -> None:
        if self._route_pos.currentIndex() != index:
            self._route_pos.blockSignals(True)
            self._route_pos.setCurrentIndex(index)
            self._route_pos.blockSignals(False)

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
        self._source_heading.setText(tr("missions.source_heading"))
        for starstrings, button in self._source_buttons.items():
            key = "missions.source_starstrings" if starstrings else "missions.source_smart"
            button.name.setText(tr(key))
            button.desc.setText(tr(key + "_desc"))
        self._titles_heading.setText(tr("missions.titles_heading"))
        self._route.setText(tr("missions.route"))
        self._route.setHint(tr("missions.route_hint"))
        self._route_pos_label.setText(tr("missions.route_position"))
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
        self._refresh_source_state()
        if hasattr(self, "_rendered"):
            self._render_detail()

    # ── Source ──────────────────────────────────────────────────────────────

    def set_source(self, starstrings: bool) -> None:
        """Show which source is chosen (MainWindow, from the setting)."""
        for value, button in self._source_buttons.items():
            button.setChecked(value == starstrings)
        self._starstrings = starstrings
        self._refresh_source_state()

    def _choose_source(self, starstrings: bool) -> None:
        self.set_source(starstrings)
        self._render_all()
        self.source_changed.emit(starstrings)

    def _refresh_source_state(self) -> None:
        starstrings = getattr(self, "_starstrings", True)
        for widget in (self._route, self._route_pos, self._rep, self._bp, self._shorten,
                       self._f_rep, self._f_bp, self._f_hostiles, self._rebuild_btn,
                       self._route_pos_label):
            widget.setEnabled(not starstrings)
        self._route_seg.setEnabled(not starstrings and self._route.isChecked())
        self._titles_note.setText(
            tr("missions.titles_note_starstrings") if starstrings
            else tr("missions.titles_note_smart"))
        self._rebuild_note.setText(
            tr("missions.rebuild_pending") if self._rebuild_pending
            else tr("missions.rebuild_note"))
        self._titles_note.setVisible(starstrings)
        # Nothing to rebuild while StarStrings writes the mission text.
        self._rebuild_strip.setVisible(not starstrings)
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
                    stock: Optional[Callable[[str], Optional[str]]] = None) -> None:
        """New strings loaded: *lookup* gives what Apply writes, *stock* the base."""
        self._lookup = lookup
        self._stock = stock or lookup
        self._contracts = pick_contracts(lookup)
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
            rep_tag=self._rep.isChecked(),
            bp_tag=self._bp.isChecked(),
            field_rep=self._f_rep.isChecked(),
            field_bp=self._f_bp.isChecked(),
            field_hostiles=self._f_hostiles.isChecked(),
        )

    def _render_all(self, mark_changes: bool = True) -> None:
        """Rebuild every contract's text from the current settings, at once.

        StarStrings mode shows the text Apply writes. Smart Citizen mode shows
        what the settings produce, so a switch changes the preview instantly;
        Rebuild mission text then makes it real. Parts that changed are lit.
        """
        if not hasattr(self, "_lookup"):
            return
        old = getattr(self, "_rendered", {})
        opts = self._options()
        rendered = {}
        for c in self._contracts:
            if getattr(self, "_starstrings", True):
                title = self._lookup(c.title_key) or ""
                blocks = [("body", self._lookup(c.desc_key) or "")]
            else:
                title, blocks = simulate(c, self._stock(c.title_key) or "",
                                         self._stock(c.desc_key) or "", opts)
            rendered[c.title_key] = (title, blocks)
        # Keep marks still on screen: one click can redraw twice (a switch here
        # and the Enhancements page it drives), and the second sees no change.
        previous = self._changed if self._clear_marks.isActive() else {}
        self._changed = {k: set(v) for k, v in previous.items()}
        if mark_changes and old:
            for key, (title, blocks) in rendered.items():
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

    def _fill_list(self) -> None:
        current = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for c in self._contracts:
            title = self._rendered[c.title_key][0]
            item = QListWidgetItem()
            item.setData(KEY_ROLE, c.title_key)
            item.setData(HTML_ROLE, to_html(title) +
                         f"<br><span style='color:{HOLO_DIM};font-size:9pt'>"
                         f"{html.escape(c.contractor)}</span>")
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
        self._render_detail()

    def _render_detail(self) -> None:
        row = self._list.currentRow()
        if not (0 <= row < len(self._contracts)):
            return
        c = self._contracts[row]
        title, blocks = self._rendered[c.title_key]
        lit = self._changed.get(c.title_key, set())

        def mark(fragment: str, block_id: str) -> str:
            if block_id not in lit:
                return fragment
            return f"<span style='background-color:{CHANGED_BG}'>{fragment}</span>"

        meta = "".join(
            f"<td style='padding-right:26px'><span style='color:{HOLO_DIM};font-size:8pt;"
            f"letter-spacing:1px'>{html.escape(label)}</span><br>"
            f"<span style='color:{HOLO_BRIGHT};font-weight:600'>{html.escape(value)}</span></td>"
            for label, value in ((tr("missions.card_contractor"), c.contractor),
                                 (tr("missions.card_reward"), c.reward),
                                 (tr("missions.card_type"), c.kind))
        )
        body = "<br><br>".join(mark(to_html(text), bid) for bid, text in blocks if text)
        self._detail.setHtml(
            f"<div style='color:{HOLO_BRIGHT};font-size:14pt;font-weight:700'>"
            f"{mark(to_html(title), 'title')}</div>"
            f"<table style='margin:10px 0'><tr>{meta}</tr></table>"
            f"<div style='color:{HOLO_TEXT};line-height:150%'>{body}</div>"
        )
