"""Ships tab: rename ships and set the order they appear in the ASOP.

Pick a ship, type the name it should have in game, add it to the list. The
list is numbered and drag-sortable; two list-wide switches put a zero-padded
number (``01. ``) and the manufacturer before each name. Every change saves
``ship_names.json`` at once (``src/utils/ship_names.py``) and emits
``names_changed``; ``MainWindow`` reloads so the table and Apply to Game pick
the names up through the synthetic ``ship_names`` source.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QCompleter, QDialog, QFileDialog, QFrame, QGroupBox,
    QHBoxLayout, QLabel,
    QStyle, QStyledItemDelegate, QStyleOptionViewItem,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
    QWidget,
)

from src.gui.combo_box import NoScrollComboBox
from src.gui.hangar_import_dialog import HangarImportDialog
from src.gui.theme import (
    BODY_FONT_FAMILY, DISPLAY_FONT_FAMILY, GAME_TEXT_FONT_FAMILY, HANGAR_FAINT, HANGAR_LINE,
    HANGAR_MUTED, HANGAR_PLATE, HANGAR_PLATE_HI, HANGAR_SIGNAL, HANGAR_TERMINAL, HANGAR_TEXT,
    host_in_scroll_area,
)
from src.utils import hangar_import, ship_names
from src.utils.i18n import tr
from src.utils.ship_names import ShipNamesConfig, ShipOption

logger = logging.getLogger(__name__)

KEY_ROLE = Qt.ItemDataRole.UserRole
NUMBER_ROLE = Qt.ItemDataRole.UserRole + 1   # "01" badge text ("" when numbering is off)
NAME_ROLE = Qt.ItemDataRole.UserRole + 2     # the name, without the number
STOCK_ROLE = Qt.ItemDataRole.UserRole + 3    # stock name, or the not-in-build note
MISSING_ROLE = Qt.ItemDataRole.UserRole + 4
ROW_HEIGHT = 52
BADGE_WIDTH = 40
PREVIEW_ROWS = 60   # enough to show your list plus the top of everything else


def _heading_font() -> QFont:
    font = QFont(DISPLAY_FONT_FAMILY)
    font.setPointSizeF(15)
    font.setWeight(QFont.Weight.Bold)
    return font


class _ShipRowDelegate(QStyledItemDelegate):
    """A list row: drag grip, number badge, name, stock name under it."""

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 (Qt name)
        return QSize(option.rect.width(), ROW_HEIGHT)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        painter.save()
        rect = option.rect
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected:
            painter.fillRect(rect, QColor(HANGAR_PLATE))
            painter.fillRect(QRect(rect.left(), rect.top(), 3, rect.height()), QColor(HANGAR_SIGNAL))
        painter.setPen(QColor(HANGAR_LINE))
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        x = rect.left() + 10
        painter.setPen(QColor(HANGAR_FAINT))
        painter.setFont(QFont(BODY_FONT_FAMILY, 13))
        painter.drawText(QRect(x, rect.top(), 16, rect.height()), Qt.AlignmentFlag.AlignCenter, "⠿")
        x += 24

        number = index.data(NUMBER_ROLE) or ""
        if number:
            badge = QRect(x, rect.top() + (rect.height() - 26) // 2, BADGE_WIDTH, 26)
            painter.fillRect(badge, QColor(HANGAR_SIGNAL if selected else HANGAR_PLATE_HI))
            font = QFont(DISPLAY_FONT_FAMILY)
            font.setPointSizeF(11)
            font.setWeight(QFont.Weight.Bold)
            painter.setFont(font)
            painter.setPen(QColor("#FFFFFF" if selected else HANGAR_MUTED))
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, number)
            x += BADGE_WIDTH + 12

        missing = bool(index.data(MISSING_ROLE))
        name_font = QFont(BODY_FONT_FAMILY)
        name_font.setPointSizeF(12.5)
        name_font.setWeight(QFont.Weight.Medium)
        painter.setFont(name_font)
        painter.setPen(QColor(HANGAR_FAINT if missing else HANGAR_TEXT))
        text_rect = QRect(x, rect.top() + 7, rect.right() - x - 8, 22)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         index.data(NAME_ROLE) or "")
        painter.setFont(QFont(BODY_FONT_FAMILY, 10))
        painter.setPen(QColor(HANGAR_SIGNAL if missing else HANGAR_MUTED))
        sub_rect = QRect(x, rect.top() + 28, rect.right() - x - 8, 18)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         index.data(STOCK_ROLE) or "")
        painter.restore()


SHIP_COMBO_MIN_WIDTH = 200
SIDE_BUTTON_WIDTH = 104


class _ShipList(QListWidget):
    """A list whose drag-and-drop reorder is reported as one signal."""

    reordered = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setStyleSheet("QListWidget { border: none; background: transparent; }")

    def dropEvent(self, event) -> None:  # noqa: N802 (Qt name)
        super().dropEvent(event)
        self.reordered.emit()


class ShipNamesTab(QWidget):
    """The Ships tab."""

    names_changed = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._options: List[ShipOption] = []
        self._by_key: Dict[str, ShipOption] = {}
        self._config: ShipNamesConfig = ship_names.load_config(ship_names.config_path())
        self.setup_ui()
        self.retranslate_ui()
        self._render_list()

    # ── Build ───────────────────────────────────────────────────────────────

    def setup_ui(self) -> None:
        # Hosted in a scroll area so a narrow window scrolls this tab, not the
        # whole window (the app's per-tab overflow rule).
        content = QWidget()
        outer = QHBoxLayout(content)
        outer.setContentsMargins(20, 18, 20, 16)
        outer.setSpacing(20)
        editor = QFrame()
        editor.setObjectName("shipEditor")
        editor.setStyleSheet(f"#shipEditor {{ border: 1px solid {HANGAR_LINE}; }}")
        outer.addWidget(editor, 11)
        layout = QVBoxLayout(editor)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        self._title_label = QLabel()
        self._title_label.setFont(_heading_font())
        layout.addWidget(self._title_label)
        self._desc_label = QLabel()
        self._desc_label.setProperty("role", "secondary")
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)

        # Rename a ship
        self._add_group = QGroupBox()
        add_layout = QVBoxLayout(self._add_group)
        row = QHBoxLayout()
        self._ship_label = QLabel()
        row.addWidget(self._ship_label)
        self._ship_combo = NoScrollComboBox()
        self._ship_combo.setEditable(True)
        self._ship_combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        self._ship_combo.setMinimumWidth(SHIP_COMBO_MIN_WIDTH)
        self._ship_combo.setMaxVisibleItems(20)
        completer = self._ship_combo.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        self._ship_combo.currentIndexChanged.connect(self._on_ship_picked)
        self._ship_combo.lineEdit().textEdited.connect(lambda _t: self._refresh_buttons())
        row.addWidget(self._ship_combo, 2)
        self._name_label = QLabel()
        row.addWidget(self._name_label)
        self._name_edit = QLineEdit()
        self._name_edit.textChanged.connect(lambda _t: self._refresh_buttons())
        self._name_edit.returnPressed.connect(self._on_add)
        row.addWidget(self._name_edit, 2)
        self._add_btn = QPushButton()
        self._add_btn.clicked.connect(self._on_add)
        row.addWidget(self._add_btn)
        add_layout.addLayout(row)
        hint_row = QHBoxLayout()
        self._add_hint = QLabel()
        self._add_hint.setProperty("role", "secondary")
        self._add_hint.setWordWrap(True)
        hint_row.addWidget(self._add_hint, 1)
        self._import_btn = QPushButton()
        self._import_btn.clicked.connect(self._on_import)
        hint_row.addWidget(self._import_btn, 0, Qt.AlignmentFlag.AlignTop)
        add_layout.addLayout(hint_row)
        layout.addWidget(self._add_group)

        # The list
        self._list_group = QGroupBox()
        list_layout = QVBoxLayout(self._list_group)
        options = QHBoxLayout()
        self._numbering_check = QCheckBox()
        self._numbering_check.setChecked(self._config.numbering)
        self._numbering_check.toggled.connect(self._on_numbering_toggled)
        options.addWidget(self._numbering_check)
        self._manufacturer_check = QCheckBox()
        self._manufacturer_check.setChecked(self._config.manufacturer)
        self._manufacturer_check.toggled.connect(self._on_manufacturer_toggled)
        options.addWidget(self._manufacturer_check)
        options.addStretch()
        self._count_label = QLabel()
        self._count_label.setProperty("role", "secondary")
        options.addWidget(self._count_label)
        list_layout.addLayout(options)

        body = QHBoxLayout()
        self._list = _ShipList()
        self._list.setItemDelegate(_ShipRowDelegate(self._list))
        self._list.reordered.connect(self._on_reordered)
        self._list.currentItemChanged.connect(lambda *_: self._on_row_selected())
        body.addWidget(self._list, 1)
        side = QVBoxLayout()
        self._up_btn = QPushButton()
        self._up_btn.clicked.connect(lambda: self._move_selected(-1))
        self._down_btn = QPushButton()
        self._down_btn.clicked.connect(lambda: self._move_selected(1))
        self._remove_btn = QPushButton()
        self._remove_btn.clicked.connect(self._remove_selected)
        self._clear_btn = QPushButton()
        self._clear_btn.clicked.connect(self._clear_all)
        for btn in (self._up_btn, self._down_btn, self._remove_btn):
            btn.setFixedWidth(SIDE_BUTTON_WIDTH)
            side.addWidget(btn)
        side.addStretch()
        self._clear_btn.setFixedWidth(SIDE_BUTTON_WIDTH)
        side.addWidget(self._clear_btn)
        body.addLayout(side)
        list_layout.addLayout(body, 1)
        self._list_hint = QLabel()
        self._list_hint.setProperty("role", "secondary")
        self._list_hint.setWordWrap(True)
        list_layout.addWidget(self._list_hint)
        layout.addWidget(self._list_group, 1)

        outer.addWidget(self._build_preview(), 9)
        host_in_scroll_area(self, content)

        QShortcut(QKeySequence(Qt.Key.Key_Delete), self._list, activated=self._remove_selected)
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self._list, activated=self._remove_selected)

    def _build_preview(self) -> QWidget:
        """The ASOP preview: every ship's final name, sorted as the game sorts."""
        panel = QFrame()
        panel.setObjectName("shipPreview")
        panel.setStyleSheet(f"#shipPreview {{ border: 1px solid {HANGAR_LINE}; }}")
        col = QVBoxLayout(panel)
        col.setContentsMargins(20, 16, 20, 16)
        col.setSpacing(8)
        self._preview_title = QLabel()
        self._preview_title.setFont(_heading_font())
        col.addWidget(self._preview_title)
        self._preview_desc = QLabel()
        self._preview_desc.setProperty("role", "secondary")
        self._preview_desc.setWordWrap(True)
        col.addWidget(self._preview_desc)
        self._preview = QListWidget()
        self._preview.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self._preview.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._preview.setFont(QFont(GAME_TEXT_FONT_FAMILY, 11))
        self._preview.setStyleSheet(
            f"QListWidget {{ background: {HANGAR_TERMINAL}; border: none;"
            f" border-left: 3px solid {HANGAR_SIGNAL}; padding: 4px 0; }}"
            f"QListWidget::item {{ padding: 7px 14px; border-bottom: 1px solid #1A1B24; }}"
        )
        col.addWidget(self._preview, 1)
        return panel

    def _render_preview(self) -> None:
        """Fill the preview with every ship's in-game name, A to Z."""
        if not hasattr(self, "_preview"):
            return
        renamed = {}
        for i, entry in enumerate(self._config.entries):
            if entry.key in self._by_key and entry.name.strip():
                renamed[entry.key] = ship_names.render_name(
                    self._config, i, self._manufacturer(entry.key))
        names = [(renamed.get(o.key, o.stock_name), o.key in renamed) for o in self._options]
        names.sort(key=lambda pair: pair[0].casefold())
        self._preview.clear()
        for text, mine in names[:PREVIEW_ROWS]:
            item = QListWidgetItem(text)
            item.setForeground(QColor("#FFFFFF" if mine else "#7D7F93"))
            self._preview.addItem(item)

    def retranslate_ui(self) -> None:
        self._preview_title.setText(tr("ship_names.preview_title"))
        self._preview_desc.setText(tr("ship_names.preview_desc"))
        self._title_label.setText(tr("ship_names.title"))
        self._desc_label.setText(tr("ship_names.desc"))
        self._add_group.setTitle(tr("ship_names.add_group"))
        self._ship_label.setText(tr("ship_names.ship_label"))
        self._ship_combo.lineEdit().setPlaceholderText(tr("ship_names.ship_placeholder"))
        self._name_label.setText(tr("ship_names.name_label"))
        self._name_edit.setPlaceholderText(tr("ship_names.name_placeholder"))
        self._add_hint.setText(tr("ship_names.add_hint"))
        self._import_btn.setText(tr("ship_names.import_btn"))
        self._import_btn.setToolTip(tr("ship_names.import_tooltip"))
        self._list_group.setTitle(tr("ship_names.list_group"))
        self._numbering_check.setText(tr("ship_names.numbering"))
        self._manufacturer_check.setText(tr("ship_names.manufacturer"))
        self._up_btn.setText(tr("ship_names.move_up"))
        self._down_btn.setText(tr("ship_names.move_down"))
        self._remove_btn.setText(tr("ship_names.remove"))
        self._clear_btn.setText(tr("ship_names.clear"))
        self._list_hint.setText(tr("ship_names.list_hint"))
        self._refresh_buttons()
        self._render_list()

    # ── Data in ─────────────────────────────────────────────────────────────

    def set_stock_names(self, stock: Dict[str, str]) -> None:
        """Fill the dropdown from the stock base.ini (MainWindow, after each load)."""
        options = ship_names.ship_options(stock or {})
        if [o.key for o in options] == [o.key for o in self._options]:
            return
        self._options = options
        self._by_key = {o.key: o for o in options}
        counts: Dict[str, int] = {}
        for o in options:
            counts[o.stock_name] = counts.get(o.stock_name, 0) + 1
        picked = self._picked_key()
        self._ship_combo.blockSignals(True)
        self._ship_combo.clear()
        for o in options:
            label = o.stock_name
            if counts[o.stock_name] > 1:
                label = f"{label}  ({o.key[len(ship_names.SHIP_NAME_KEY_PREFIX):]})"
            self._ship_combo.addItem(label, o.key)
        self._ship_combo.setCurrentIndex(self._ship_combo.findData(picked) if picked else -1)
        self._ship_combo.blockSignals(False)
        self._render_list()

    def reload_config(self) -> None:
        """Re-read this channel's list (after a channel or data-folder change)."""
        self._config = ship_names.load_config(ship_names.config_path())
        for check, value in ((self._numbering_check, self._config.numbering),
                             (self._manufacturer_check, self._config.manufacturer)):
            check.blockSignals(True)
            check.setChecked(value)
            check.blockSignals(False)
        self._render_list()

    # ── Helpers ─────────────────────────────────────────────────────────────

    def _picked_key(self) -> Optional[str]:
        """The ship the dropdown shows, only when its text names one exactly."""
        i = self._ship_combo.currentIndex()
        if i < 0 or self._ship_combo.currentText() != self._ship_combo.itemText(i):
            return None
        return self._ship_combo.itemData(i)

    def _manufacturer(self, key: str) -> str:
        option = self._by_key.get(key)
        return option.manufacturer if option else ""

    def _render_list(self) -> None:
        selected = self._selected_key()
        self._list.blockSignals(True)
        self._list.clear()
        for i, entry in enumerate(self._config.entries):
            option = self._by_key.get(entry.key)
            text = ship_names.render_name(self._config, i, self._manufacturer(entry.key))
            item = QListWidgetItem(text)
            item.setData(KEY_ROLE, entry.key)
            number, name = "", text
            if self._config.numbering:
                number, _sep, name = text.partition(ship_names.NUMBER_SEPARATOR)
            item.setData(NUMBER_ROLE, number)
            item.setData(NAME_ROLE, name)
            if option:
                item.setData(STOCK_ROLE, option.stock_name)
                item.setToolTip(
                    tr("ship_names.stock_tooltip", name=option.stock_name, key=entry.key)
                )
            elif self._options:
                item.setText(f"{text}   {tr('ship_names.missing_suffix')}")
                item.setData(STOCK_ROLE, tr("ship_names.missing_suffix"))
                item.setData(MISSING_ROLE, True)
                item.setToolTip(tr("ship_names.missing_tooltip", key=entry.key))
            self._list.addItem(item)
            if entry.key == selected:
                self._list.setCurrentItem(item)
        self._list.blockSignals(False)
        self._count_label.setText(tr("ship_names.count", count=len(self._config.entries)))
        self._refresh_buttons()
        self._render_preview()

    def _selected_key(self) -> Optional[str]:
        item = self._list.currentItem()
        return item.data(KEY_ROLE) if item else None

    def _refresh_buttons(self) -> None:
        key = self._picked_key()
        has_name = bool(self._name_edit.text().strip())
        in_list = key is not None and self._config.index_of(key) >= 0
        self._add_btn.setEnabled(key is not None and has_name)
        self._add_btn.setText(tr("ship_names.update_btn") if in_list else tr("ship_names.add_btn"))
        row = self._list.currentRow()
        count = len(self._config.entries)
        self._up_btn.setEnabled(row > 0)
        self._down_btn.setEnabled(0 <= row < count - 1)
        self._remove_btn.setEnabled(row >= 0)
        self._clear_btn.setEnabled(count > 0)

    def _save(self) -> None:
        try:
            ship_names.save_config(ship_names.config_path(), self._config)
        except OSError as exc:
            logger.warning(f"Could not save ship names: {exc}")
            return
        self.names_changed.emit()

    # ── Slots ───────────────────────────────────────────────────────────────

    def _on_ship_picked(self, _index: int) -> None:
        key = self._picked_key()
        if key is None:
            self._refresh_buttons()
            return
        i = self._config.index_of(key)
        if i >= 0:
            self._name_edit.setText(self._config.entries[i].name)
        elif key in self._by_key:
            self._name_edit.setText(ship_names.strip_manufacturer(self._by_key[key]))
        self._name_edit.setFocus()
        self._name_edit.selectAll()
        self._refresh_buttons()

    def _on_add(self) -> None:
        key = self._picked_key()
        name = self._name_edit.text().strip()
        if key is None or not name:
            return
        index = self._config.upsert(key, name)
        self._render_list()
        self._list.setCurrentRow(index)
        self._save()
        self._ship_combo.setCurrentIndex(-1)
        self._ship_combo.clearEditText()
        self._name_edit.clear()
        self._ship_combo.setFocus()
        self._refresh_buttons()

    def _on_row_selected(self) -> None:
        key = self._selected_key()
        if key is not None:
            i = self._ship_combo.findData(key)
            self._ship_combo.blockSignals(True)
            self._ship_combo.setCurrentIndex(i)
            if i < 0:
                self._ship_combo.setEditText(key)
            self._ship_combo.blockSignals(False)
            self._name_edit.setText(self._config.entries[self._config.index_of(key)].name)
        self._refresh_buttons()

    def _on_reordered(self) -> None:
        keys = [self._list.item(i).data(KEY_ROLE) for i in range(self._list.count())]
        self._config.reorder(keys)
        self._render_list()
        self._save()

    def _move_selected(self, step: int) -> None:
        row = self._list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < len(self._config.entries):
            return
        entries = self._config.entries
        entries[row], entries[target] = entries[target], entries[row]
        self._render_list()
        self._list.setCurrentRow(target)
        self._save()

    def _remove_selected(self) -> None:
        key = self._selected_key()
        if key is None:
            return
        row = self._list.currentRow()
        self._config.remove(key)
        self._render_list()
        if self._config.entries:
            self._list.setCurrentRow(min(row, len(self._config.entries) - 1))
        self._save()

    def _clear_all(self) -> None:
        if not self._config.entries:
            return
        buttons = QMessageBox.StandardButton
        answer = QMessageBox.question(
            self, tr("ship_names.clear_title"),
            tr("ship_names.clear_body", count=len(self._config.entries)),
            buttons.Yes | buttons.No, buttons.No,
        )
        if answer != buttons.Yes:
            return
        self._config.entries = []
        self._render_list()
        self._save()

    def _on_import(self) -> None:
        """Add owned ships from a HangarLink Hangar Export CSV."""
        if not self._options:
            QMessageBox.information(self, tr("ship_names.import_dialog_title"),
                                    tr("ship_names.import_no_strings"))
            return
        start = Path.home() / "Downloads"
        path, _ = QFileDialog.getOpenFileName(
            self, tr("ship_names.import_dialog_title"),
            str(start if start.is_dir() else Path.home()), tr("ship_names.import_file_filter"),
        )
        if not path:
            return
        try:
            ships = hangar_import.parse_hangar_csv(Path(path))
        except OSError as exc:
            QMessageBox.warning(self, tr("ship_names.import_error_title"),
                                tr("ship_names.import_error_body", path=path, error=exc))
            return
        if not ships:
            QMessageBox.warning(self, tr("ship_names.import_error_title"),
                                tr("ship_names.import_empty_body", path=path))
            return
        rows = hangar_import.match_ships(ships, self._options)
        dialog = HangarImportDialog(rows, self._options, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        if not dialog.picks and not dialog.replace_list:
            return
        hangar_import.apply_import(self._config, dialog.picks, replace=dialog.replace_list)
        self._render_list()
        self._save()

    def _on_numbering_toggled(self, on: bool) -> None:
        self._config.numbering = on
        self._render_list()
        self._save()

    def _on_manufacturer_toggled(self, on: bool) -> None:
        self._config.manufacturer = on
        self._render_list()
        self._save()
