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

from PyQt6.QtCore import QRect, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen, QTextDocument
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QListWidget, QListWidgetItem, QPushButton, QSizePolicy, QStyle, QStyledItemDelegate,
    QTextBrowser, QVBoxLayout, QWidget,
)

from src.gui.theme import (
    DISPLAY_FONT_FAMILY, GAME_TEXT_FONT_FAMILY, HANGAR_HULL, HANGAR_LINE, HANGAR_SIGNAL,
    host_in_scroll_area,
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

KEY_ROLE = Qt.ItemDataRole.UserRole
HTML_ROLE = Qt.ItemDataRole.UserRole + 1
CHANGED_ROLE = Qt.ItemDataRole.UserRole + 2
CONTROLS_WIDTH = 400


@dataclass(frozen=True)
class SampleContract:
    """A contract the preview shows: its strings and made-up card values."""

    title_key: str
    desc_key: str
    contractor: str
    reward: str
    kind: str


# Real keys from the game's strings. Contractor, reward and type are samples.
SAMPLE_CONTRACTS: Tuple[SampleContract, ...] = (
    SampleContract("CFP_RecoverCargo_Medium_Title", "CFP_RecoverCargo_Medium_Description",
                   "Citizens for Prosperity", "48,500 aUEC", "Cargo recovery"),
    SampleContract("Covalex_Delivery_Stanton_Medium_Title_001",
                   "Covalex_Delivery_Stanton_Medium_Desc_001",
                   "Covalex Shipping", "21,750 aUEC", "Delivery"),
    SampleContract("Adagio_Industrial_Component_Salvage_Stanton_M_Title_001",
                   "Adagio_Industrial_Component_Salvage_Stanton_M_Desc_001",
                   "Adagio Holdings", "36,000 aUEC", "Salvage"),
    SampleContract("CFP_RecoverCargo_Easy_Title", "CFP_RecoverCargo_Easy_Description",
                   "Citizens for Prosperity", "27,000 aUEC", "Cargo recovery"),
    SampleContract("Covalex_Delivery_Stanton_Super_Title_001",
                   "Covalex_Delivery_Stanton_Super_Desc_001",
                   "Covalex Shipping", "64,000 aUEC", "Delivery"),
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
        self.setFixedHeight(72)
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
    """A labelled switch row with an optional hint line."""

    def __init__(self) -> None:
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)


class MissionsTab(QWidget):
    """Mission text settings and the Contracts Manager preview."""

    source_changed = pyqtSignal(bool)   # True: StarStrings writes mission text

    def __init__(self, enhancements_tab, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._enh = enhancements_tab
        self._mt = enhancements_tab._tag_builder_pages["mission_titles"]
        self._contracts: List[SampleContract] = []
        self._titles: Dict[str, str] = {}
        self._descs: Dict[str, str] = {}
        self._rebuild_pending = False
        self.setup_ui()
        self.retranslate_ui()

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

    def _build_controls(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("missionControls")
        panel.setStyleSheet(f"#missionControls {{ border: 1px solid {HANGAR_LINE}; }}")
        panel.setFixedWidth(CONTROLS_WIDTH)
        col = QVBoxLayout(panel)
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(10)

        self._title = self._heading()
        col.addWidget(self._title)
        self._lede = self._secondary()
        col.addWidget(self._lede)

        # Who writes mission text
        self._source_heading = self._heading(11.5)
        col.addWidget(self._source_heading)
        cards = QHBoxLayout()
        cards.setSpacing(8)
        self._source_buttons: Dict[bool, _SourceCard] = {}
        for starstrings in (True, False):
            button = _SourceCard()
            button.clicked.connect(lambda _c, s=starstrings: self._choose_source(s))
            self._source_buttons[starstrings] = button
            cards.addWidget(button)
        col.addLayout(cards)

        # Titles: Smart Citizen's tags, through the Enhancements page's widgets
        self._titles_heading = self._heading(11.5)
        col.addWidget(self._titles_heading)
        self._titles_note = self._secondary()
        col.addWidget(self._titles_note)
        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(6)
        self._route = self._bind_check(self._mt._mt_enable)
        self._route_pos = QComboBox()
        self._route_pos.setModel(self._mt._mt_placement.model())
        self._route_pos.setCurrentIndex(self._mt._mt_placement.currentIndex())
        self._route_pos.currentIndexChanged.connect(self._mt._mt_placement.setCurrentIndex)
        self._mt._mt_placement.currentIndexChanged.connect(self._sync_route_pos)
        self._route_pos.currentIndexChanged.connect(self._mark_rebuild)
        self._rep = self._bind_check(self._mt._title_tag_checkboxes["rep"])
        self._bp = self._bind_check(self._mt._title_tag_checkboxes["blueprint"])
        self._shorten = self._bind_check(self._mt._mt_shorten_titles)
        grid.addWidget(self._route, 0, 0)
        grid.addWidget(self._route_pos, 0, 1)
        for row, check in enumerate((self._rep, self._bp, self._shorten), start=1):
            grid.addWidget(check, row, 0, 1, 2)
        col.addLayout(grid)

        # Description fields
        self._desc_heading = self._heading(11.5)
        col.addWidget(self._desc_heading)
        fields = self._enh._mission_field_checkboxes
        self._f_rep = self._bind_check(fields["reputation"])
        self._f_bp = self._bind_check(fields["blueprints"])
        self._f_hostiles = self._bind_check(fields["spawns"], extra=[fields["difficulty"]])
        for check in (self._f_rep, self._f_bp, self._f_hostiles):
            col.addWidget(check)

        rebuild = QHBoxLayout()
        self._rebuild_note = self._secondary()
        rebuild.addWidget(self._rebuild_note, 1)
        self._rebuild_btn = QPushButton()
        self._rebuild_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._rebuild_btn.clicked.connect(self._on_rebuild)
        rebuild.addWidget(self._rebuild_btn)
        col.addLayout(rebuild)

        col.addStretch(1)
        self._moved_note = self._secondary()
        self._moved_note.setStyleSheet(f"border-top: 1px solid {HANGAR_LINE}; padding-top: 8px;")
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
        self.source_changed.emit(starstrings)

    def _refresh_source_state(self) -> None:
        starstrings = getattr(self, "_starstrings", True)
        self._titles_note.setText(
            tr("missions.titles_note_starstrings") if starstrings
            else tr("missions.titles_note_smart"))
        self._rebuild_note.setText(
            tr("missions.rebuild_pending") if self._rebuild_pending
            else tr("missions.rebuild_note"))
        self._rebuild_btn.setStyleSheet(
            f"QPushButton {{ background: {HANGAR_SIGNAL}; color: white; border: none; }}"
            if self._rebuild_pending else ""
        )

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

    def set_strings(self, lookup: Callable[[str], Optional[str]]) -> None:
        """Refill the preview from the loaded strings; outline what changed."""
        old_titles, old_descs = self._titles, self._descs
        self._contracts = pick_contracts(lookup)
        self._titles = {c.title_key: lookup(c.title_key) or "" for c in self._contracts}
        self._descs = {c.desc_key: lookup(c.desc_key) or "" for c in self._contracts}
        current = self._list.currentRow()
        self._list.blockSignals(True)
        self._list.clear()
        for c in self._contracts:
            item = QListWidgetItem()
            item.setData(KEY_ROLE, c.title_key)
            item.setData(HTML_ROLE, to_html(self._titles[c.title_key]) +
                         f"<br><span style='color:{HOLO_DIM};font-size:9pt'>"
                         f"{html.escape(c.contractor)}</span>")
            item.setData(CHANGED_ROLE, bool(old_titles) and
                         old_titles.get(c.title_key) not in (None, self._titles[c.title_key]))
            self._list.addItem(item)
        self._list.setCurrentRow(current if 0 <= current < self._list.count() else 0)
        self._list.blockSignals(False)
        self._desc_changed = {
            k for k, v in self._descs.items() if old_descs and old_descs.get(k) not in (None, v)
        }
        if not self._contracts:
            self._detail.setHtml(
                f"<p style='color:{HOLO_DIM}'>{html.escape(tr('missions.preview_empty'))}</p>")
        else:
            self._render_detail()

    def _render_detail(self) -> None:
        row = self._list.currentRow()
        if not (0 <= row < len(self._contracts)):
            return
        c = self._contracts[row]
        changed = c.desc_key in getattr(self, "_desc_changed", set())
        border = f"border:1.5px dashed {HANGAR_SIGNAL};" if changed else ""
        meta = "".join(
            f"<td style='padding-right:26px'><span style='color:{HOLO_DIM};font-size:8pt;"
            f"letter-spacing:1px'>{html.escape(label)}</span><br>"
            f"<span style='color:{HOLO_BRIGHT};font-weight:600'>{html.escape(value)}</span></td>"
            for label, value in ((tr("missions.card_contractor"), c.contractor),
                                 (tr("missions.card_reward"), c.reward),
                                 (tr("missions.card_type"), c.kind))
        )
        self._detail.setHtml(
            f"<div style='color:{HOLO_BRIGHT};font-size:14pt;font-weight:700'>"
            f"{to_html(self._titles.get(c.title_key, ''))}</div>"
            f"<table style='margin:10px 0'><tr>{meta}</tr></table>"
            f"<div style='color:{HOLO_TEXT};line-height:150%;{border}'>"
            f"{to_html(self._descs.get(c.desc_key, ''))}</div>"
        )
