"""Preview for a HangarLink import into the Ships tab.

One row per owned hull: tick to add, the hull as RSI names it (with how many
you own), the game ship it was matched to (change it from the dropdown when
the guess is wrong or missing) and the name it gets in the list. Nothing is
saved here; the caller reads :attr:`picks` and :attr:`replace_list` after
``exec()`` returns Accepted.
"""
from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QCheckBox, QCompleter, QDialog, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from src.gui.combo_box import NoScrollComboBox
from src.utils import hangar_import
from src.utils.hangar_import import ImportRow
from src.utils.i18n import tr
from src.utils.ship_names import ShipOption

COL_USE, COL_HANGAR, COL_MATCH, COL_NAME = range(4)


class HangarImportDialog(QDialog):
    def __init__(self, rows: Sequence[ImportRow], options: Sequence[ShipOption],
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._rows = list(rows)
        self._options = list(options)
        self._combos: List[NoScrollComboBox] = []
        self.picks: List[Tuple[str, str]] = []
        self.replace_list = False

        self.setWindowTitle(tr("ship_names.import_dialog_title"))
        self.resize(860, 620)
        layout = QVBoxLayout(self)

        matched = sum(1 for r in self._rows if r.option is not None)
        summary = QLabel(tr("ship_names.import_summary", matched=matched, total=len(self._rows)))
        summary.setWordWrap(True)
        layout.addWidget(summary)

        self._custom_check = QCheckBox(tr("ship_names.import_use_custom"))
        self._custom_check.setVisible(any(r.ship.custom_names for r in self._rows))
        self._custom_check.toggled.connect(self._refill_names)
        layout.addWidget(self._custom_check)

        self._table = QTableWidget(len(self._rows), 4)
        self._table.setHorizontalHeaderLabels([
            tr("ship_names.import_col_use"), tr("ship_names.import_col_hangar"),
            tr("ship_names.import_col_match"), tr("ship_names.import_col_name"),
        ])
        self._table.verticalHeader().setVisible(False)
        self._table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_USE, QHeaderView.ResizeMode.ResizeToContents)
        for col in (COL_HANGAR, COL_MATCH, COL_NAME):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        for i, row in enumerate(self._rows):
            self._fill_row(i, row)
        layout.addWidget(self._table, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        cancel = QPushButton(tr("ship_names.import_cancel"))
        cancel.clicked.connect(self.reject)
        replace = QPushButton(tr("ship_names.import_replace"))
        replace.clicked.connect(lambda: self._finish(replace=True))
        append = QPushButton(tr("ship_names.import_append"))
        append.setDefault(True)
        append.clicked.connect(lambda: self._finish(replace=False))
        for btn in (cancel, replace, append):
            buttons.addWidget(btn)
        layout.addLayout(buttons)

    # ── Rows ────────────────────────────────────────────────────────────────

    def _fill_row(self, i: int, row: ImportRow) -> None:
        use = QTableWidgetItem()
        use.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        use.setCheckState(Qt.CheckState.Checked if row.option else Qt.CheckState.Unchecked)
        self._table.setItem(i, COL_USE, use)

        title = row.ship.title if row.ship.count == 1 else f"{row.ship.title}  ×{row.ship.count}"
        hangar = QTableWidgetItem(title)
        hangar.setFlags(Qt.ItemFlag.ItemIsEnabled)
        tip = [row.ship.liner] if row.ship.liner else []
        tip += [f"“{n}”" for n in row.ship.custom_names]
        hangar.setToolTip("\n".join(tip))
        self._table.setItem(i, COL_HANGAR, hangar)

        combo = NoScrollComboBox()
        combo.setEditable(True)
        combo.setInsertPolicy(NoScrollComboBox.InsertPolicy.NoInsert)
        completer = combo.completer()
        completer.setFilterMode(Qt.MatchFlag.MatchContains)
        completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        completer.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)
        combo.addItem(tr("ship_names.import_no_match"), None)
        for option in self._options:
            combo.addItem(option.stock_name, option.key)
        combo.setCurrentIndex(combo.findData(row.option.key) if row.option else 0)
        combo.currentIndexChanged.connect(lambda _i, r=i: self._on_match_changed(r))
        self._table.setCellWidget(i, COL_MATCH, combo)
        self._combos.append(combo)

        self._table.setItem(i, COL_NAME, QTableWidgetItem(self._default_name(i)))

    def _option_at(self, i: int) -> Optional[ShipOption]:
        combo = self._combos[i]
        key = combo.currentData()
        if key is None or combo.currentText() != combo.itemText(combo.currentIndex()):
            return None
        return next((o for o in self._options if o.key == key), None)

    def _default_name(self, i: int) -> str:
        return hangar_import.default_name(self._rows[i].ship, self._option_at(i),
                                          self._custom_check.isChecked())

    def _on_match_changed(self, i: int) -> None:
        option = self._option_at(i)
        self._table.item(i, COL_USE).setCheckState(
            Qt.CheckState.Checked if option else Qt.CheckState.Unchecked)
        self._table.item(i, COL_NAME).setText(self._default_name(i))

    def _refill_names(self, _on: bool) -> None:
        for i in range(len(self._rows)):
            self._table.item(i, COL_NAME).setText(self._default_name(i))

    # ── Done ────────────────────────────────────────────────────────────────

    def _finish(self, replace: bool) -> None:
        self.picks = []
        for i in range(len(self._rows)):
            if self._table.item(i, COL_USE).checkState() != Qt.CheckState.Checked:
                continue
            option = self._option_at(i)
            name = self._table.item(i, COL_NAME).text().strip()
            if option is not None and name:
                self.picks.append((option.key, name))
        self.replace_list = replace
        self.accept()
