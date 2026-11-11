"""Items tab: rename components, armor, FPS weapons and tools, and other items.

The four sub-tabs are in place so the navigation is final; each shows what
it will hold until its editor lands (it reuses the Ships tab's pattern:
pick an item, name it or pick a preset, live preview beside it).
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QFrame, QLabel, QTabWidget, QVBoxLayout, QWidget

from src.gui.theme import DISPLAY_FONT_FAMILY, HANGAR_LINE
from src.utils.i18n import tr

# (sub-tab key, tr key of its tab name, tr key of what it will hold)
SUB_TABS: Tuple[Tuple[str, str, str], ...] = (
    ("components", "items.components", "items.components_desc"),
    ("armor", "items.armor", "items.armor_desc"),
    ("fps", "items.fps", "items.fps_desc"),
    ("misc", "items.misc", "items.misc_desc"),
)


class _ComingPage(QWidget):
    """One sub-tab's placeholder: its title and what it will hold."""

    def __init__(self, title_key: str, desc_key: str) -> None:
        super().__init__()
        self._title_key, self._desc_key = title_key, desc_key
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 16, 0, 0)
        box = QFrame()
        box.setObjectName("comingBox")
        box.setStyleSheet(f"#comingBox {{ border: 1.5px dashed {HANGAR_LINE}; }}")
        col = QVBoxLayout(box)
        col.setContentsMargins(28, 24, 28, 24)
        col.setSpacing(8)
        self.title = QLabel()
        font = QFont(DISPLAY_FONT_FAMILY)
        font.setPointSizeF(15)
        font.setWeight(QFont.Weight.Bold)
        self.title.setFont(font)
        self.desc = QLabel()
        self.desc.setWordWrap(True)
        self.note = QLabel()
        self.note.setProperty("role", "secondary")
        self.note.setWordWrap(True)
        for w in (self.title, self.desc, self.note):
            col.addWidget(w)
        outer.addWidget(box)
        outer.addStretch(1)

    def retranslate_ui(self) -> None:
        self.title.setText(tr(self._title_key))
        self.desc.setText(tr(self._desc_key))
        self.note.setText(tr("items.coming_note"))


class ItemsTab(QWidget):
    """The Items tab and its four sub-tabs."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        self.sub_tabs = QTabWidget()
        self.sub_tabs.setDocumentMode(True)
        self._pages: List[Tuple[str, _ComingPage]] = []
        for _key, title_key, desc_key in SUB_TABS:
            page = _ComingPage(title_key, desc_key)
            self.sub_tabs.addTab(page, "")
            self._pages.append((title_key, page))
        layout.addWidget(self.sub_tabs, 1)
        self.sub_tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        for i, (title_key, page) in enumerate(self._pages):
            self.sub_tabs.setTabText(i, tr(title_key).replace("&", "&&"))
            page.retranslate_ui()
