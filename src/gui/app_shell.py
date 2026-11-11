"""The window's header and main navigation (Hangar redesign).

``AppHeader`` carries the wordmark, the channel switch, the "changes not in
the game yet" status, the one Apply to game button and a settings menu.
``ShellNav`` replaces the QTabWidget's own tab bar with four large tabs, each
with a one-line subtitle. Pages that moved off the bar (Config, Overlay,
Log, ...) open from the settings menu and show as a fifth, temporary tab.

Both only drive widgets ``MainWindow`` already owns: the channel buttons set
the Config tab's channel combo, Apply clicks the original Apply button, and
the tabs call ``QTabWidget.setCurrentIndex`` -- so every existing flow, index
and test keeps working unchanged.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton, QSizePolicy,
    QToolButton, QVBoxLayout, QWidget,
)

from src.gui.theme import (
    DISPLAY_FONT_FAMILY, HANGAR_FAINT, HANGAR_HULL, HANGAR_LINE, HANGAR_MUTED,
    HANGAR_PLATE_HI, HANGAR_SIGNAL, HANGAR_TEXT,
)
from src.utils.i18n import tr

HEADER_HEIGHT = 64
NAV_BUTTON_MIN_WIDTH = 140


def _display_font(point_size: float, weight: QFont.Weight = QFont.Weight.Bold) -> QFont:
    font = QFont(DISPLAY_FONT_FAMILY)
    font.setPointSizeF(point_size)
    font.setWeight(weight)
    return font


class AppHeader(QWidget):
    """Wordmark, channel switch, apply status, Apply to game, settings menu."""

    apply_clicked = pyqtSignal()

    def __init__(self, title_label: QLabel, tagline_label: QLabel,
                 parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("appHeader")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setFixedHeight(HEADER_HEIGHT)
        self.setStyleSheet(
            f"#appHeader {{ background: #101117; border-bottom: 1px solid {HANGAR_LINE}; }}"
        )
        self._channel_combo: Optional[QComboBox] = None

        row = QHBoxLayout(self)
        row.setContentsMargins(20, 0, 16, 0)
        row.setSpacing(18)

        mark = QVBoxLayout()
        mark.setSpacing(0)
        mark.addStretch()
        mark.addWidget(title_label)
        mark.addWidget(tagline_label)
        mark.addStretch()
        row.addLayout(mark)
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setTextFormat(Qt.TextFormat.RichText)
        # May shrink to nothing: on a narrow window the status note gives way
        # first, so the header never sets the window's minimum width.
        self.status_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.status_label.setMinimumWidth(0)
        row.addWidget(self.status_label, 2)

        self._channel_row = QHBoxLayout()
        self._channel_row.setSpacing(0)
        self._channel_group = QButtonGroup(self)
        self._channel_group.setExclusive(True)
        self._channel_group.idClicked.connect(self._on_channel_clicked)
        row.addLayout(self._channel_row)

        self.apply_button = QPushButton()
        self.apply_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.apply_button.clicked.connect(self.apply_clicked)
        row.addWidget(self.apply_button)

        self.settings_button = QToolButton()
        self.settings_button.setText("⚙")
        self.settings_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.settings_button.setFixedSize(36, 36)
        self.settings_button.setStyleSheet(
            f"QToolButton {{ color: {HANGAR_MUTED}; border: 1px solid {HANGAR_LINE}; "
            f"font-size: 17px; }} QToolButton:hover {{ color: {HANGAR_TEXT}; }}"
            "QToolButton::menu-indicator { image: none; }"
        )
        self.settings_menu = QMenu(self.settings_button)
        self.settings_button.setMenu(self.settings_menu)
        row.addWidget(self.settings_button)

        self.set_dirty(True)

    # ── Channel switch ──────────────────────────────────────────────────────

    def bind_channel_combo(self, combo: QComboBox) -> None:
        """Mirror the Config tab's channel combo as a segmented switch."""
        self._channel_combo = combo
        combo.currentIndexChanged.connect(lambda _i: self.refresh_channels())
        self.refresh_channels()

    def refresh_channels(self) -> None:
        combo = self._channel_combo
        if combo is None:
            return
        from src.utils.settings import AppSettings
        available = set(AppSettings.get_available_channels())
        if not AppSettings.get_sc_install_root():
            available = {combo.currentText()}   # no install found: just say where we are
        wanted = [i for i in range(combo.count())
                  if combo.itemText(i) in available or i == combo.currentIndex()]
        current = [self._channel_group.id(b) for b in self._channel_group.buttons()]
        if wanted != current:
            for button in self._channel_group.buttons():
                self._channel_group.removeButton(button)
                self._channel_row.removeWidget(button)
                button.setParent(None)
                button.deleteLater()
            for i in wanted:
                button = QPushButton(combo.itemText(i))
                button.setCheckable(True)
                button.setCursor(Qt.CursorShape.PointingHandCursor)
                button.setStyleSheet(
                    f"QPushButton {{ background: transparent; color: {HANGAR_MUTED};"
                    f" padding: 5px 12px; border: 1.5px solid {HANGAR_TEXT}; font-size: 11px;"
                    f" letter-spacing: 1px; font-family: '{DISPLAY_FONT_FAMILY}'; }}"
                    f"QPushButton:checked {{ background: {HANGAR_PLATE_HI}; color: {HANGAR_TEXT}; }}"
                )
                self._channel_group.addButton(button, i)
                self._channel_row.addWidget(button)
        for button in self._channel_group.buttons():
            button.setChecked(self._channel_group.id(button) == combo.currentIndex())

    def _on_channel_clicked(self, index: int) -> None:
        if self._channel_combo is not None and self._channel_combo.currentIndex() != index:
            self._channel_combo.setCurrentIndex(index)

    # ── Apply state ─────────────────────────────────────────────────────────

    def set_dirty(self, dirty: bool) -> None:
        """Red Apply button and a waiting note while the game is behind."""
        self._dirty = dirty
        self.apply_button.setEnabled(dirty)
        if dirty:
            self.apply_button.setStyleSheet(
                f"QPushButton {{ background: {HANGAR_SIGNAL}; color: white; border: none;"
                " padding: 9px 20px; font-size: 13px; letter-spacing: 1px;"
                f" font-family: '{DISPLAY_FONT_FAMILY}'; font-weight: 700; }}"
                "QPushButton:hover { background: #F2262C; }"
            )
        else:
            self.apply_button.setStyleSheet(
                f"QPushButton:disabled {{ background: transparent; color: {HANGAR_FAINT};"
                f" border: 1px solid {HANGAR_LINE}; padding: 9px 20px; font-size: 13px;"
                f" font-family: '{DISPLAY_FONT_FAMILY}'; font-weight: 700; }}"
            )
        self.retranslate_ui()

    def retranslate_ui(self) -> None:
        self.apply_button.setText(tr("shell.apply_btn"))
        self.apply_button.setToolTip(
            tr("toolbar.apply_enabled_tooltip") if self._dirty else tr("toolbar.apply_disabled_tooltip")
        )
        if self._dirty:
            self.status_label.setText(
                f"<span style='color:{HANGAR_TEXT};font-weight:500'>{tr('shell.status_dirty')}</span>"
            )
        else:
            self.status_label.setText(
                f"<span style='color:{HANGAR_MUTED}'>{tr('shell.status_clean')}</span>"
            )
        self.settings_button.setToolTip(tr("shell.settings_tooltip"))


@dataclass
class NavPage:
    """One page the nav can show: the widget in the QTabWidget, its texts."""

    widget: QWidget
    title_key: str
    subtitle_key: str


class _NavButton(QPushButton):
    """A tab with a title and a one-line subtitle."""

    def __init__(self) -> None:
        super().__init__()
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumWidth(NAV_BUTTON_MIN_WIDTH)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            "QPushButton { background: transparent; border: none;"
            f" border-bottom: 2px solid {HANGAR_LINE}; padding: 0; text-align: left; }}"
            f"QPushButton:checked {{ background: {HANGAR_HULL}; border-bottom: 3px solid {HANGAR_SIGNAL}; }}"
            f"QPushButton:hover:!checked {{ background: #181922; }}"
        )
        inner = QVBoxLayout(self)
        inner.setContentsMargins(16, 10, 16, 10)
        inner.setSpacing(0)
        self.title = QLabel()
        self.title.setFont(_display_font(13))
        self.title.setStyleSheet(f"color: {HANGAR_TEXT}; background: transparent;")
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet(f"color: {HANGAR_MUTED}; font-size: 12px; background: transparent;")
        for label in (self.title, self.subtitle):
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            inner.addWidget(label)
        self.setFixedHeight(62)


class ShellNav(QWidget):
    """The four main tabs, plus a temporary one for a page opened from settings."""

    def __init__(self, tabs, pages: List[NavPage], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._tabs = tabs
        self._pages = pages
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 6, 20, 0)
        row.setSpacing(0)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: List[_NavButton] = []
        for i, _page in enumerate(pages):
            button = _NavButton()
            self._group.addButton(button, i)
            self._buttons.append(button)
            row.addWidget(button)
        self._extra_button = _NavButton()
        self._extra_button.hide()
        row.addWidget(self._extra_button)
        self._group.idClicked.connect(self._on_clicked)
        tabs.currentChanged.connect(lambda _i: self.sync())
        tabs.tabBar().hide()
        self.retranslate_ui()

    def _on_clicked(self, index: int) -> None:
        if 0 <= index < len(self._pages):
            self._tabs.setCurrentWidget(self._pages[index].widget)

    def open_page(self, widget: QWidget) -> None:
        """Show a page that is not one of the four tabs (from the settings menu)."""
        self._tabs.setCurrentWidget(widget)
        self.sync()

    def sync(self) -> None:
        """Check the current page's tab; show the temporary tab for any other page."""
        current = self._tabs.currentWidget()
        for page, button in zip(self._pages, self._buttons):
            if page.widget is current:
                button.setChecked(True)
                self._extra_button.hide()
                return
        index = self._tabs.indexOf(current)
        self._extra_button.title.setText(self._tabs.tabText(index) if index >= 0 else "")
        self._extra_button.subtitle.setText(tr("shell.from_settings"))
        self._group.setExclusive(False)
        for button in self._buttons:
            button.setChecked(False)
        self._group.setExclusive(True)
        self._extra_button.setChecked(True)
        self._extra_button.show()

    def retranslate_ui(self) -> None:
        for page, button in zip(self._pages, self._buttons):
            button.title.setText(tr(page.title_key))
            button.subtitle.setText(tr(page.subtitle_key))
        self.sync()


class UpdateBanner(QWidget):
    """A slim bar under the header offering one update, with one button.

    Hidden until ``show_offer``. The owner decides what the button does
    (``action_clicked``); the × hides the bar for this session.
    """

    action_clicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("updateBanner")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#updateBanner {{ background: #2A1214; border-bottom: 1px solid {HANGAR_SIGNAL}; }}"
        )
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 6, 16, 6)
        row.setSpacing(12)
        mark = QLabel("●")
        mark.setStyleSheet(f"color: {HANGAR_SIGNAL}; background: transparent;")
        row.addWidget(mark)
        self.message = QLabel()
        self.message.setStyleSheet(f"color: {HANGAR_TEXT}; background: transparent;")
        self.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        row.addWidget(self.message, 1)
        self.button = QPushButton()
        self.button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.button.setStyleSheet(
            f"QPushButton {{ background: {HANGAR_SIGNAL}; color: white; border: none;"
            f" padding: 5px 16px; font-family: '{DISPLAY_FONT_FAMILY}'; font-weight: 700; }}"
            f"QPushButton:disabled {{ background: #5A2326; color: {HANGAR_MUTED}; }}"
        )
        self.button.clicked.connect(self.action_clicked)
        row.addWidget(self.button)
        self.close_button = QToolButton()
        self.close_button.setText("✕")
        self.close_button.setStyleSheet(
            f"QToolButton {{ color: {HANGAR_MUTED}; border: none; background: transparent; }}"
            f"QToolButton:hover {{ color: {HANGAR_TEXT}; }}"
        )
        self.close_button.clicked.connect(self.hide)
        row.addWidget(self.close_button)
        self.hide()

    def show_offer(self, message: str, button_text: str, busy: bool = False) -> None:
        self.message.setText(message)
        self.button.setText(button_text)
        self.button.setEnabled(not busy)
        self.close_button.setEnabled(not busy)
        self.show()
