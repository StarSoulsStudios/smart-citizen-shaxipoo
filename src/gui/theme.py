"""Application theme management.

Themes are applied by swapping the Qt palette on the QApplication. Widgets
that need theme-aware text colors should rely on the palette's
WindowText/Text roles (the default); dim labels mark themselves with
`setProperty("role", "secondary")` and an app-level QSS rule (installed by
`apply_theme`) recolors them when the theme changes.
"""
import logging
import sys
from pathlib import Path

from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import (
    QApplication, QFrame, QProxyStyle, QScrollArea, QStyle, QVBoxLayout, QWidget,
)

logger = logging.getLogger(__name__)


# Branded display font used on the main window title + tagline. Loaded from
# assets/fonts/ at app startup via load_application_fonts(). The family name
# is what Qt reports after registering the OTF — the Fontspring demo ships
# with a prefixed family string, which we match here.
BRAND_FONT_FAMILY = "FONTSPRING DEMO - Hyperspace Race Expanded"
_BRAND_FONT_FILE = "HyperspaceRace-ExpandedBold.otf"


def _assets_fonts_dir() -> Path:
    """Resolve the assets/fonts directory for both dev and PyInstaller builds."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base / "assets" / "fonts"


# Hangar theme typefaces (SIL OFL, licences beside them in assets/fonts):
# Goldman for headings, tab names and buttons, Poppins for body text,
# JetBrains Mono for text shown the way the game shows it (previews).
DISPLAY_FONT_FAMILY = "Goldman"
BODY_FONT_FAMILY = "Poppins"
GAME_TEXT_FONT_FAMILY = "JetBrains Mono"
_OFL_FONT_FILES = (
    "Goldman-Regular.ttf", "Goldman-Bold.ttf",
    "Poppins-Light.ttf", "Poppins-Regular.ttf", "Poppins-Medium.ttf", "Poppins-SemiBold.ttf",
    "JetBrainsMono-Variable.ttf",
)


def load_application_fonts() -> None:
    """Register bundled display fonts with Qt. Call once at startup after
    QApplication is constructed and before any widgets use the font."""
    for name in _OFL_FONT_FILES:
        path = _assets_fonts_dir() / name
        if not path.exists() or QFontDatabase.addApplicationFont(str(path)) < 0:
            logger.warning(f"Font {name} not registered; using system fallback")
    font_path = _assets_fonts_dir() / _BRAND_FONT_FILE
    if not font_path.exists():
        logger.warning(f"Brand font not found at {font_path}; using system fallback")
        return
    font_id = QFontDatabase.addApplicationFont(str(font_path))
    if font_id < 0:
        logger.warning(f"Failed to register brand font {font_path}")
        return
    families = QFontDatabase.applicationFontFamilies(font_id)
    logger.info(f"Registered brand font families: {families}")

THEME_LIGHT = "light"
THEME_DARK = "dark"
THEME_SCLE = "scle"
THEME_ODW = "odw"
THEME_HANGAR = "hangar"
AVAILABLE_THEMES = (THEME_HANGAR, THEME_LIGHT, THEME_DARK, THEME_SCLE, THEME_ODW)
DEFAULT_THEME = THEME_HANGAR

# Hangar theme tokens (styled after the StarLabels tool): charcoal-navy
# surfaces, one signal red for the actions that change the game.
HANGAR_VOID = "#14151C"      # window
HANGAR_HULL = "#1C1D28"      # panels, inputs' wells
HANGAR_PLATE = "#2A2C3D"     # raised blocks, selected rows
HANGAR_PLATE_HI = "#353850"  # hover, checked segments
HANGAR_LINE = "#2F3144"      # borders, dividers
HANGAR_TEXT = "#ECEDF3"
HANGAR_MUTED = "#9A9CB0"
HANGAR_FAINT = "#5E6075"
HANGAR_SIGNAL = "#E3161C"
HANGAR_TERMINAL = "#0D0E13"  # in-game preview panels

# Secondary/dim text color per theme. A single shade can't stay readable on
# both #C8C8C8 (light window) and #0D1826 (scle navy) — so we resolve it
# per-theme and surface it via the app-level QSS rule in `_app_stylesheet_for`.
_SECONDARY_TEXT_COLORS = {
    THEME_HANGAR: HANGAR_MUTED,
    THEME_LIGHT: "#2A2A2A",
    THEME_DARK:  "#D5D5D5",
    THEME_SCLE:  "#D5D5D5",
    THEME_ODW:   "#D4B876",
}


# Toolbar action button colors per theme. Light uses Material 500 shades;
# dark uses Material 300 so buttons read softer against the dark background.
# "needs_apply" is the attention-red used by the dirty-tracking system
# (Apply Enhancements' background when a change is pending; the text color
# on Generate Enhancements / Save Tag Changes / Apply Owned Tags when they
# light up) — kept in this per-theme palette rather than a hardcoded hex so
# it stays visually consistent with each theme's own saturation/warmth.
_BUTTON_COLORS = {
    THEME_HANGAR: {
        "load":        "#C4C6D4",
        "restore":     "#F08A4B",
        "apply":       "#3C9A6A",   # quiet green: the game already matches
        "clear":       HANGAR_MUTED,
        "open":        "#C4C6D4",
        "needs_apply": "#FF4045",   # signal red, lifted so it reads as text on dark
    },
    THEME_LIGHT: {
        "load":        "#2196F3",
        "restore":     "#FF5722",
        "apply":       "#4CAF50",
        "clear":       "#9E9E9E",
        "open":        "#2196F3",
        "needs_apply": "#F44336",
    },
    THEME_DARK: {
        "load":        "#64B5F6",
        "restore":     "#FF8A65",
        "apply":       "#81C784",
        "clear":       "#BDBDBD",
        "open":        "#64B5F6",
        "needs_apply": "#E57373",
    },
    THEME_SCLE: {
        "load":        "#4FD7E8",   # cube-glow cyan
        "restore":     "#FF8A42",   # pencil-tip orange
        "apply":       "#4ADE80",   # bright green that pops against navy
        "clear":       "#5F7A95",   # muted cyan-gray
        "open":        "#4FD7E8",
        "needs_apply": "#FF5C5C",   # hot red that still reads against navy
    },
    THEME_ODW: {
        "load":        "#D4B876",   # brighter gold (navigate)
        "restore":     "#C77A4D",   # copper (rollback)
        "apply":       "#A5B989",   # sage green (commit)
        "clear":       "#7A7D87",   # slate gray (cleanup)
        "open":        "#D4B876",
        "needs_apply": "#C0392B",   # brick red, warm enough to sit with the gold/copper palette
    },
}


def get_button_color(role: str) -> str:
    """Return the button color for the given role (load/restore/apply/clear/open/needs_apply)."""
    from src.utils.settings import AppSettings
    theme = AppSettings.get_theme()
    palette = _BUTTON_COLORS.get(theme, _BUTTON_COLORS[DEFAULT_THEME])
    return palette[role]


# How opaque a stylesheet colour is drawn on a disabled button (#483).
DISABLED_ALPHA = 110


def dimmed_color(color: str) -> str:
    """*color* as a stylesheet rgba() at DISABLED_ALPHA, for a button's
    ``:disabled`` rule. A stylesheet colour outlives setEnabled(False), so a
    button coloured by one has to dim itself to stop looking clickable."""
    c = QColor(color)
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {DISABLED_ALPHA})"


def host_in_scroll_area(tab: QWidget, content: QWidget) -> None:
    """Fill *tab* with a frameless scroll area showing *content*.

    The Config, Enhancements, Blueprint Tracker and Overlay tabs build into a
    content widget and host it this way, so each scrolls instead of squeezing
    its controls. MainWindow adds the tab widget with stretch=1, so the
    scroll area fills the tab and this does NOT reintroduce the tab-switch
    resize that got the 1.4.x Enhancements scroll-area attempt reverted
    (#65). The frame and viewport background stay clear so the themed
    background shows through rather than the scroll area painting its own
    Base colour.
    """
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.viewport().setAutoFillBackground(False)
    content.setAutoFillBackground(False)
    scroll.setWidget(content)

    outer = QVBoxLayout(tab)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.addWidget(scroll)


def needs_apply_style() -> str:
    """Stylesheet for a button the dirty-tracking system lights up: the
    needs_apply red, dimmed while the button is disabled (#483).

    A running job locks some of these buttons while their change is still
    pending (Generate Enhancements, Save Tag Changes, the Config tab's
    Extract), and a stylesheet colour outlives setEnabled(False), so a
    locked button looked ready to click. Dimmed, it still says a change is
    waiting without looking clickable, and its tooltip or the Config tab's
    lock label says why.
    """
    red = get_button_color("needs_apply")
    return (f"QPushButton {{ color: {red}; }} "
            f"QPushButton:disabled {{ color: {dimmed_color(red)}; }}")


def get_button_text_color() -> str:
    """Return the readable text color for toolbar action buttons.

    Material 500 (light theme) buttons need white text. Every other theme
    uses lighter button backgrounds — black reads better on those.
    """
    from src.utils.settings import AppSettings
    return "white" if AppSettings.get_theme() == THEME_LIGHT else "black"


# Per-theme colors for the branded title + tagline labels at the top of the
# main window. Each pair ties to the theme's signature accent so the header
# reads as "of" that theme.
_TITLE_COLORS = {
    THEME_HANGAR: "#FFFFFF",
    THEME_LIGHT: "#1565C0",   # rich blue
    THEME_DARK:  "#64B5F6",   # soft sky blue
    THEME_SCLE:  "#4FD7E8",   # cube-glow cyan
    THEME_ODW:   "#C9A961",   # Osiris gold
}

_TAGLINE_COLORS = {
    THEME_HANGAR: HANGAR_MUTED,
    THEME_LIGHT: "#555555",
    THEME_DARK:  "#A0A0A0",
    THEME_SCLE:  "#6FB5D0",   # muted cyan
    THEME_ODW:   "#A08C5A",   # muted gold
}


def get_title_color() -> str:
    from src.utils.settings import AppSettings
    return _TITLE_COLORS.get(AppSettings.get_theme(), _TITLE_COLORS[DEFAULT_THEME])


def get_tagline_color() -> str:
    from src.utils.settings import AppSettings
    return _TAGLINE_COLORS.get(AppSettings.get_theme(), _TAGLINE_COLORS[DEFAULT_THEME])


# Progress-bar colors — groove (unfilled track) and chunk (filled region).
# Applied via QSS on AnimatedProgressDialog's QProgressBar, but ONLY while
# the bar is in determinate mode. In indeterminate mode the QSS is cleared
# so Fusion's animated busy indicator keeps working.
_PROGRESS_GROOVE_COLORS = {
    THEME_HANGAR: HANGAR_PLATE,
    THEME_LIGHT: "#8A8A8A",
    THEME_DARK:  "#3C3C3F",
    THEME_SCLE:  "#152538",
    THEME_ODW:   "#242938",
}

_PROGRESS_CHUNK_COLORS = {
    THEME_HANGAR: HANGAR_SIGNAL,
    THEME_LIGHT: "#1565C0",
    THEME_DARK:  "#3B82F6",
    THEME_SCLE:  "#4FD7E8",
    THEME_ODW:   "#D4A017",
}


def get_progress_groove_color() -> str:
    from src.utils.settings import AppSettings
    return _PROGRESS_GROOVE_COLORS.get(AppSettings.get_theme(),
                                       _PROGRESS_GROOVE_COLORS[DEFAULT_THEME])


def get_progress_chunk_color() -> str:
    from src.utils.settings import AppSettings
    return _PROGRESS_CHUNK_COLORS.get(AppSettings.get_theme(),
                                      _PROGRESS_CHUNK_COLORS[DEFAULT_THEME])




def _light_palette() -> QPalette:
    """Return a palette matching the Fusion light defaults with adjusted placeholder."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(200, 200, 200))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.Base,            QColor(215, 215, 215))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(208, 208, 208))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(240, 240, 218))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.Text,            QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.Button,          QColor(200, 200, 200))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(25, 25, 25))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 0, 0))
    # Highlight pulls double duty: text-selection + Fusion's QProgressBar
    # chunk gradient. The chunk gradient widens when Highlight sits at mid
    # luminance (Fusion's lighter()/darker() factors have room to move both
    # ways), so the two scrolling tones read as distinct.
    p.setColor(QPalette.ColorRole.Highlight,       QColor(21, 101, 192))   # #1565C0
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link,            QColor(0, 102, 204))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(90, 90, 90))
    # Disabled-state overrides — darker than 150-gray so disabled text keeps
    # ~4:1 contrast against the 200-gray window (was 150, which blurred away).
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(100, 100, 100))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(100, 100, 100))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(100, 100, 100))
    return p


def _dark_palette() -> QPalette:
    """Return a dark palette inspired by the Qt-community "Fusion dark" pattern."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.WindowText,      QColor(232, 232, 232))
    p.setColor(QPalette.ColorRole.Base,            QColor(30, 30, 30))
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(45, 45, 48))
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(45, 45, 48))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(232, 232, 232))
    p.setColor(QPalette.ColorRole.Text,            QColor(232, 232, 232))
    p.setColor(QPalette.ColorRole.Button,          QColor(55, 55, 58))
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(232, 232, 232))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 80, 80))
    # Brighter mid-tone blue so Fusion's indeterminate chunk gradient has
    # a visible light/dark delta against the near-black track.
    p.setColor(QPalette.ColorRole.Highlight,       QColor(59, 130, 246))   # #3B82F6
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))
    p.setColor(QPalette.ColorRole.Link,            QColor(100, 170, 255))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(175, 175, 175))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(150, 150, 150))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(150, 150, 150))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(150, 150, 150))
    return p


def _scle_palette() -> QPalette:
    """Star Citizen Localization Editor branded palette — deep navy + cyan
    highlights inspired by the app's splash artwork."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(13, 24, 38))    # #0D1826 deep navy
    p.setColor(QPalette.ColorRole.WindowText,      QColor(216, 232, 240)) # #D8E8F0 silver-blue
    p.setColor(QPalette.ColorRole.Base,            QColor(13, 24, 38))    # match Window for tab consistency
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(21, 37, 56))    # #152538
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(21, 37, 56))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(216, 232, 240))
    p.setColor(QPalette.ColorRole.Text,            QColor(216, 232, 240))
    p.setColor(QPalette.ColorRole.Button,          QColor(26, 45, 68))    # #1A2D44 raised panel
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(216, 232, 240))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(255, 138, 66))  # #FF8A42 orange accent
    # Pulled down from near-max-brightness #00D4FF to a mid-luminance teal-
    # cyan so Fusion's QProgressBar chunk gradient has room to produce a
    # visible light/dark delta (bright-cyan Highlight capped the lighter()
    # endpoint and the bar read as a single flat color).
    p.setColor(QPalette.ColorRole.Highlight,       QColor(0, 153, 204))   # #0099CC
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(10, 18, 32))    # dark on cyan
    p.setColor(QPalette.ColorRole.Link,            QColor(79, 215, 232))  # #4FD7E8
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(111, 181, 208)) # #6FB5D0
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(88, 120, 144))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(88, 120, 144))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(88, 120, 144))
    return p


def _odw_palette() -> QPalette:
    """Osiris DevWorks branded palette — navy charcoal + antique gold,
    matching the ODW logo."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window,          QColor(26, 31, 46))    # #1A1F2E navy
    p.setColor(QPalette.ColorRole.WindowText,      QColor(240, 230, 207)) # #F0E6CF cream
    p.setColor(QPalette.ColorRole.Base,            QColor(26, 31, 46))    # match Window
    p.setColor(QPalette.ColorRole.AlternateBase,   QColor(36, 41, 56))    # #242938 panel
    p.setColor(QPalette.ColorRole.ToolTipBase,     QColor(36, 41, 56))
    p.setColor(QPalette.ColorRole.ToolTipText,     QColor(240, 230, 207))
    p.setColor(QPalette.ColorRole.Text,            QColor(240, 230, 207))
    p.setColor(QPalette.ColorRole.Button,          QColor(36, 41, 56))    # raised
    p.setColor(QPalette.ColorRole.ButtonText,      QColor(240, 230, 207))
    p.setColor(QPalette.ColorRole.BrightText,      QColor(199, 122, 77))  # #C77A4D copper
    # More saturated / mid-luminance gold — the previous muted #C9A961
    # gave Fusion's chunk gradient almost no light/dark spread, so the
    # scrolling bar read as two near-identical shades of gold.
    p.setColor(QPalette.ColorRole.Highlight,       QColor(212, 160, 23))  # #D4A017
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(26, 31, 46))    # navy on gold
    p.setColor(QPalette.ColorRole.Link,            QColor(212, 184, 118)) # #D4B876 brighter gold
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(160, 140, 90))  # #A08C5A muted gold
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(100, 90, 70))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text,       QColor(100, 90, 70))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(100, 90, 70))
    return p


def _hangar_palette() -> QPalette:
    """Hangar: charcoal-navy and signal red, after the StarLabels tool."""
    p = QPalette()
    c = QColor
    p.setColor(QPalette.ColorRole.Window,          c(HANGAR_VOID))
    p.setColor(QPalette.ColorRole.WindowText,      c(HANGAR_TEXT))
    p.setColor(QPalette.ColorRole.Base,            c(HANGAR_HULL))
    p.setColor(QPalette.ColorRole.AlternateBase,   c("#202131"))
    p.setColor(QPalette.ColorRole.ToolTipBase,     c(HANGAR_PLATE))
    p.setColor(QPalette.ColorRole.ToolTipText,     c(HANGAR_TEXT))
    p.setColor(QPalette.ColorRole.Text,            c(HANGAR_TEXT))
    p.setColor(QPalette.ColorRole.Button,          c(HANGAR_PLATE))
    p.setColor(QPalette.ColorRole.ButtonText,      c(HANGAR_TEXT))
    p.setColor(QPalette.ColorRole.BrightText,      c(HANGAR_SIGNAL))
    p.setColor(QPalette.ColorRole.Highlight,       c("#B8141A"))
    p.setColor(QPalette.ColorRole.HighlightedText, c("#FFFFFF"))
    p.setColor(QPalette.ColorRole.Link,            c("#FF5A5F"))
    p.setColor(QPalette.ColorRole.PlaceholderText, c(HANGAR_FAINT))
    for role in (QPalette.ColorRole.WindowText, QPalette.ColorRole.Text,
                 QPalette.ColorRole.ButtonText):
        p.setColor(QPalette.ColorGroup.Disabled, role, c(HANGAR_FAINT))
    return p


def _hangar_stylesheet() -> str:
    """App-wide QSS for Hangar. Leaves QProgressBar alone (see below)."""
    v, h, pl, phi, ln = HANGAR_VOID, HANGAR_HULL, HANGAR_PLATE, HANGAR_PLATE_HI, HANGAR_LINE
    t, m, f, red = HANGAR_TEXT, HANGAR_MUTED, HANGAR_FAINT, HANGAR_SIGNAL
    return f"""
QMainWindow, QDialog {{ background: {v}; }}
QToolTip {{ background: {pl}; color: {t}; border: 1px solid {ln}; padding: 6px; }}
QPushButton {{ background: {pl}; color: {t}; border: 1px solid {ln}; padding: 4px 10px;
    font-weight: 500; }}
QPushButton:hover {{ background: {phi}; }}
QPushButton:pressed {{ background: {h}; }}
QPushButton:disabled {{ color: {f}; background: {h}; }}
QPushButton:default {{ border: 1px solid {red}; }}
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{ background: {v}; color: {t};
    border: none; border-bottom: 2px solid {f}; padding: 6px 8px;
    selection-background-color: #B8141A; }}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border-bottom-color: {red}; }}
QComboBox QAbstractItemView {{ background: {h}; border: 1px solid {ln}; selection-background-color: {pl}; }}
QGroupBox {{ border: 1px solid {ln}; margin-top: 22px; padding: 14px 12px 10px 12px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 0px; top: 0px; padding: 0 2px;
    color: {t}; font-family: "{DISPLAY_FONT_FAMILY}"; font-weight: 700; font-size: 14px; }}
QTabWidget::pane {{ border: 1px solid {ln}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {m}; padding: 8px 16px; border: none;
    border-bottom: 2px solid {ln}; font-weight: 500; }}
QTabBar::tab:selected {{ color: {t}; background: {h}; border-bottom: 3px solid {red}; }}
QTabBar::tab:hover:!selected {{ color: {t}; }}
QTableView, QTreeView, QListView, QListWidget {{ background: {h}; alternate-background-color: #202131;
    border: 1px solid {ln}; gridline-color: {ln}; selection-background-color: {pl}; selection-color: {t}; }}
QHeaderView::section {{ background: {v}; color: {m}; border: none; border-bottom: 1px solid {ln};
    padding: 6px 8px; font-weight: 500; }}
QCheckBox, QRadioButton {{ spacing: 8px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; border: 1.5px solid {m}; background: {v}; }}
QRadioButton::indicator {{ border-radius: 8px; }}
QCheckBox::indicator:checked, QRadioButton::indicator:checked {{ background: {red}; border-color: {red}; }}
QScrollBar:vertical {{ background: {v}; width: 10px; margin: 0; }}
QScrollBar:horizontal {{ background: {v}; height: 10px; margin: 0; }}
QScrollBar::handle {{ background: {pl}; min-height: 24px; min-width: 24px; }}
QScrollBar::handle:hover {{ background: {phi}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QMenu {{ background: {h}; border: 1px solid {ln}; padding: 4px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; }}
QMenu::item:selected {{ background: {pl}; }}
QMenu::separator {{ height: 1px; background: {ln}; margin: 4px 8px; }}
QStatusBar {{ background: #101117; color: {f}; border-top: 1px solid {ln}; }}
QDockWidget::title {{ background: {h}; padding: 6px; }}
QSplitter::handle {{ background: {ln}; }}
QLabel[role="secondary"] {{ color: {m}; }}
"""


def _palette_for(theme: str) -> QPalette:
    if theme == THEME_HANGAR:
        return _hangar_palette()
    if theme == THEME_DARK:
        return _dark_palette()
    if theme == THEME_SCLE:
        return _scle_palette()
    if theme == THEME_ODW:
        return _odw_palette()
    return _light_palette()


def _app_stylesheet_for(theme: str) -> str:
    """QSS applied at the QApplication level. Used for widget-role rules that
    need to re-color on live theme swap without walking every tracked label.

    Intentionally does not touch QProgressBar — any QSS on the chunk switches
    Fusion to a styled render path that stops animating the indeterminate
    busy indicator. Per-theme progress-bar contrast is handled via the
    palette's Highlight role in the theme palettes below.
    """
    if theme == THEME_HANGAR:
        return _hangar_stylesheet()
    secondary = _SECONDARY_TEXT_COLORS.get(theme, _SECONDARY_TEXT_COLORS[DEFAULT_THEME])
    return f'QLabel[role="secondary"] {{ color: {secondary}; }}'


# Qt default tooltip wake-up delay is ~700ms, which feels twitchy on densely
# labeled toolbars — the tip pops up while the cursor is just passing over a
# button on its way somewhere else. We bump the cold delay so the tooltip
# only appears on a deliberate hover, and we zero out the "fall asleep"
# window so every tooltip is a cold wake-up rather than Qt's default where
# the *second* tooltip (and any shown within ~2s of the last) pops instantly.
_TOOLTIP_WAKE_UP_DELAY_MS = 800
_TOOLTIP_FALL_ASLEEP_DELAY_MS = 0


class _SmartCitizenProxyStyle(QProxyStyle):
    """Fusion style with a longer, consistent tooltip wake-up delay.

    Qt exposes tooltip timing only via the :class:`QStyle` ``SH_ToolTip_*``
    style hints — there's no per-widget setter and no QSS knob — so the only
    clean way to shift it app-wide is to wrap the base style and override
    ``styleHint`` for those values. Overrides both ``SH_ToolTip_WakeUpDelay``
    (cold hover delay) and ``SH_ToolTip_FallAsleepDelay`` (duration of the
    "awake" window during which subsequent tooltips would otherwise pop
    instantly). Zeroing the fall-asleep delay collapses the awake window so
    every tooltip always waits the full cold delay — matching the "give me
    a moment to pause before popping" intent of a longer wake-up.
    """

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        if hint == QStyle.StyleHint.SH_ToolTip_WakeUpDelay:
            return _TOOLTIP_WAKE_UP_DELAY_MS
        if hint == QStyle.StyleHint.SH_ToolTip_FallAsleepDelay:
            return _TOOLTIP_FALL_ASLEEP_DELAY_MS
        return super().styleHint(hint, option, widget, returnData)


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply the named theme to the application.

    Forces Fusion style (wrapped in a proxy that lengthens the tooltip
    wake-up delay) on the first call so palette changes render consistently
    regardless of the OS theme. Re-calling setStyle on a live app can crash
    Qt 6 during widget re-polish, so subsequent calls only swap the palette.
    """
    if theme not in AVAILABLE_THEMES:
        logger.warning(f"Unknown theme {theme!r}; using {DEFAULT_THEME}")
        theme = DEFAULT_THEME

    # "Already applied?" check: PyQt slices QProxyStyle back to QCommonStyle
    # when you call app.style(), so isinstance() can't see our subclass.
    # But the style hint value itself survives the slicing, so we probe it
    # directly — our proxy overrides SH_ToolTip_WakeUpDelay to our chosen
    # constant, and no stock style produces exactly that number.
    current_delay = app.style().styleHint(QStyle.StyleHint.SH_ToolTip_WakeUpDelay)
    if current_delay != _TOOLTIP_WAKE_UP_DELAY_MS:
        # QProxyStyle(str) resolves the base style by name, so this still
        # gives us the Fusion look — just with our tooltip-delay override.
        app.setStyle(_SmartCitizenProxyStyle("Fusion"))
    app.setPalette(_palette_for(theme))
    # Body text font. Set on the app rather than in QSS: a QSS font-family
    # rule would override every widget's own setFont (headings, previews).
    if theme == THEME_HANGAR:
        body = QFont(BODY_FONT_FAMILY)
        body.setPointSizeF(9)
        app.setFont(body)
    app.setStyleSheet(_app_stylesheet_for(theme))
    logger.info(f"Applied theme: {theme}")
