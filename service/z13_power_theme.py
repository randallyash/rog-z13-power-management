#!/usr/bin/env python3
"""Omarchy theme tokens for z13-power Qt surfaces.

Reads the live theme from ~/.local/state/omarchy/current/ (colors.toml,
shell.toml) and the current monospace font. Falls back to a Nord-like
palette when Omarchy is not installed, so the same code works on KDE.

Used by z13-power-service (tray menu, diagnose dialog) and
z13-power-settings.
"""

from __future__ import annotations

import os
import re
import subprocess

from PyQt6.QtCore import QObject, QPoint, Qt, QFileSystemWatcher, pyqtSignal
from PyQt6.QtGui import (
    QColor, QCursor, QFont, QGuiApplication, QPainter, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QStyle, QStyleOption,
    QVBoxLayout, QWidget,
)

THEME_DIR = os.path.expanduser("~/.local/state/omarchy/current/theme")
THEME_NAME = os.path.expanduser("~/.local/state/omarchy/current/theme.name")
COLORS_PATH = os.path.join(THEME_DIR, "colors.toml")
SHELL_PATH = os.path.join(THEME_DIR, "shell.toml")

# Matches Omarchy's Nord default so a missing theme still looks like the
# shell, not like stock Qt.
FALLBACK = {
    "mode": "dark",
    "accent": "#81a1c1",
    "selection": "#434c5e",
    "muted": "#4c566a",
    "background": "#2e3440",
    "dark_background": "#222730",
    "lighter_background": "#3b4252",
    "foreground": "#d8dee9",
    "dark_foreground": "#667080",
    "light_foreground": "#adb5c4",
    "red": "#bf616a",
    "yellow": "#ebcb8b",
    "orange": "#d5967a",
    "green": "#a3be8c",
    "cyan": "#88c0d0",
    "blue": "#81a1c1",
}

MODE_GLYPHS = {
    "max": "\uf0e7",           # bolt
    "performance": "\U000f04c5",  # nf-md-speedometer
    "balanced": "\U000f04ba",     # nf-md-scale-balance
    "silent": "\U000f075f",       # nf-md-volume-off
    "lowpower": "\U000f0331",     # nf-md-leaf
}

_KV = re.compile(r'^([A-Za-z0-9_.-]+)\s*=\s*"([^"]*)"\s*$')
_NUM = re.compile(r"^([A-Za-z0-9_.-]+)\s*=\s*([0-9.]+)\s*$")


def _parse_simple(path):
    """Parse the subset of TOML Omarchy ships (flat keys, quoted strings)."""
    out = {}
    section = ""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return out
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        m = _KV.match(line) or _NUM.match(line)
        if not m:
            continue
        key = f"{section}.{m.group(1)}" if section else m.group(1)
        out[key] = m.group(2)
    return out


def _hex(value, fallback):
    text = str(value or "").strip()
    if text.startswith("#") and len(text) in (4, 7, 9):
        return text
    return fallback


def _alpha(hex_color, alpha):
    color = QColor(hex_color)
    color.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return color.name(QColor.NameFormat.HexArgb)


def detect_font():
    """Same source `omarchy font current` uses: fontconfig monospace."""
    try:
        out = subprocess.check_output(
            ["fc-match", "monospace", "-f", "%{family}\\n"],
            text=True, timeout=2)
        name = out.splitlines()[0].split(",")[0].strip()
        if name:
            return name
    except (OSError, subprocess.SubprocessError):
        pass
    return "JetBrainsMono Nerd Font"


def load_theme():
    colors = dict(FALLBACK)
    colors.update(_parse_simple(COLORS_PATH))
    shell = _parse_simple(SHELL_PATH)

    bg = _hex(colors.get("background"), FALLBACK["background"])
    fg = _hex(colors.get("foreground"), FALLBACK["foreground"])
    accent = _hex(colors.get("accent") or colors.get("blue"), FALLBACK["accent"])
    muted = _hex(colors.get("muted") or colors.get("dark_foreground"),
                 FALLBACK["muted"])
    hover_bg = _hex(colors.get("selection") or colors.get("lighter_background"),
                    FALLBACK["selection"])

    menu_bg = _hex(shell.get("menu.background"), bg)
    menu_fg = _hex(shell.get("menu.text"), fg)
    menu_border = _hex(shell.get("menu.border")
                       if str(shell.get("menu.border", "")).startswith("#")
                       else None, fg)
    menu_sel_bg = _hex(
        shell.get("menu.selected-background")
        if str(shell.get("menu.selected-background", "")).startswith("#")
        else None, fg)
    try:
        sel_a = float(shell.get("menu.selected-background-alpha", "0.08"))
    except ValueError:
        sel_a = 0.08
    try:
        border_a = float(shell.get("menu.border-alpha", "1.0"))
    except ValueError:
        border_a = 1.0
    menu_sel_text = _hex(shell.get("menu.selected-text"), accent)

    try:
        base = int(float(shell.get("font.base-size", "12")))
    except ValueError:
        base = 12

    return {
        "mode": colors.get("mode", "dark"),
        "background": bg,
        "foreground": fg,
        "accent": accent,
        "muted": muted,
        "hover": hover_bg,
        "red": _hex(colors.get("red"), FALLBACK["red"]),
        "yellow": _hex(colors.get("yellow"), FALLBACK["yellow"]),
        "orange": _hex(colors.get("orange"), FALLBACK["orange"]),
        "green": _hex(colors.get("green"), FALLBACK["green"]),
        "cyan": _hex(colors.get("cyan"), FALLBACK["cyan"]),
        "blue": _hex(colors.get("blue"), FALLBACK["blue"]),
        "dark_background": _hex(colors.get("dark_background"),
                                FALLBACK["dark_background"]),
        "lighter_background": _hex(colors.get("lighter_background"),
                                   FALLBACK["lighter_background"]),
        "menu_bg": menu_bg,
        "menu_fg": menu_fg,
        "menu_border": _alpha(menu_border, border_a),
        "menu_sel_bg": _alpha(menu_sel_bg, sel_a),
        "menu_sel_text": menu_sel_text,
        "font": detect_font(),
        "font_size": max(10, base),
        "radius": 12,
    }


def mode_colors(theme=None):
    """Profile tints drawn from the current theme, not hardcoded neon."""
    t = theme or load_theme()
    return {
        "performance": t["red"],
        "balanced": t["cyan"],
        "silent": t["green"],
        "max": t["orange"],
        "lowpower": t["yellow"],
    }


def stylesheet(theme=None):
    t = theme or load_theme()
    font = t["font"]
    size = t["font_size"]
    return f"""
    * {{
        font-family: "{font}";
        font-size: {size}px;
        color: {t["menu_fg"]};
    }}
    QWidget {{
        background-color: {t["menu_bg"]};
        color: {t["menu_fg"]};
        selection-background-color: {t["menu_sel_bg"]};
        selection-color: {t["menu_sel_text"]};
    }}
    QMainWindow, QDialog, QMessageBox {{
        background-color: {t["background"]};
        color: {t["foreground"]};
    }}
    QTabWidget::pane {{
        border: 1px solid {t["muted"]};
        background: {t["background"]};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {t["dark_background"]};
        color: {t["menu_fg"]};
        padding: 7px 14px;
        border: 1px solid {t["muted"]};
        border-bottom: none;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {t["background"]};
        color: {t["accent"]};
    }}
    QTabBar::tab:hover {{
        color: {t["accent"]};
    }}
    QPushButton {{
        background: {t["lighter_background"]};
        color: {t["foreground"]};
        border: 1px solid {t["muted"]};
        border-radius: 6px;
        padding: 6px 12px;
    }}
    QPushButton:hover {{
        background: {t["hover"]};
        color: {t["accent"]};
        border-color: {t["accent"]};
    }}
    QPushButton:pressed {{
        background: {t["hover"]};
    }}
    QPushButton:checked {{
        background: {t["hover"]};
        color: {t["accent"]};
        border-color: {t["accent"]};
    }}
    QComboBox, QSpinBox, QLineEdit {{
        background: {t["dark_background"]};
        color: {t["foreground"]};
        border: 1px solid {t["muted"]};
        border-radius: 6px;
        padding: 4px 8px;
    }}
    QComboBox:hover, QSpinBox:hover, QLineEdit:hover {{
        border-color: {t["accent"]};
    }}
    QComboBox QAbstractItemView {{
        background: {t["menu_bg"]};
        color: {t["menu_fg"]};
        selection-background-color: {t["menu_sel_bg"]};
        selection-color: {t["menu_sel_text"]};
        border: 1px solid {t["muted"]};
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {t["lighter_background"]};
        border-radius: 3px;
    }}
    QSlider::handle:horizontal {{
        background: {t["accent"]};
        width: 14px;
        margin: -5px 0;
        border-radius: 7px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {t["muted"]};
        border-radius: 3px;
        background: {t["dark_background"]};
    }}
    QCheckBox::indicator:checked {{
        background: {t["accent"]};
        border-color: {t["accent"]};
    }}
    QLabel {{
        background: transparent;
    }}
    QMenu {{
        background: {t["menu_bg"]};
        color: {t["menu_fg"]};
        border: 1px solid {t["menu_border"]};
        border-radius: 8px;
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 18px 6px 12px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {t["menu_sel_bg"]};
        color: {t["menu_sel_text"]};
    }}
    QMenu::separator {{
        height: 1px;
        background: {t["muted"]};
        margin: 6px 10px;
    }}
    QMenu::indicator {{
        width: 14px;
        height: 14px;
        margin-left: 6px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 4px 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {t["muted"]};
        border-radius: 4px;
        min-height: 24px;
    }}
    QMessageBox {{
        background: {t["background"]};
    }}
    QMessageBox QLabel {{
        color: {t["foreground"]};
    }}
    """


def apply_to_app(app=None, theme=None):
    """Force Fusion so QSS wins over the gtk3 platform theme."""
    application = app or QApplication.instance()
    if application is None:
        return load_theme() if theme is None else theme
    t = theme or load_theme()
    application.setStyle("Fusion")
    application.setStyleSheet(stylesheet(t))
    font = QFont(t["font"], t["font_size"])
    application.setFont(font)
    return t


class ThemeWatcher(QObject):
    """Re-emits when the Omarchy theme files change."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._watcher = QFileSystemWatcher(self)
        self._timer = None
        self._watch()
        self._watcher.fileChanged.connect(self._on_change)
        self._watcher.directoryChanged.connect(self._on_change)

    def _watch(self):
        paths = [THEME_DIR, THEME_NAME, COLORS_PATH, SHELL_PATH]
        existing = [p for p in paths if os.path.exists(p)]
        current = set(self._watcher.files()) | set(self._watcher.directories())
        for path in existing:
            if path not in current:
                self._watcher.addPath(path)

    def _on_change(self, _path=""):
        # Theme-set replaces files atomically; re-arm watches then debounce.
        from PyQt6.QtCore import QTimer
        self._watch()
        if self._timer is None:
            self._timer = QTimer(self)
            self._timer.setSingleShot(True)
            self._timer.timeout.connect(self.changed.emit)
        self._timer.start(120)


class _MenuRow(QWidget):
    def __init__(self, item, theme, parent=None):
        super().__init__(parent)
        self.item = item
        self.theme = theme
        self.hovered = False
        self.setCursor(Qt.CursorShape.PointingHandCursor if item.get("enabled", True)
                       else Qt.CursorShape.ArrowCursor)
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)
        layout.setSpacing(8)

        mark = QLabel(self._mark())
        mark.setFixedWidth(18)
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._mark_label = mark
        layout.addWidget(mark)

        glyph = item.get("glyph") or ""
        if glyph:
            g = QLabel(glyph)
            g.setFixedWidth(18)
            g.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._glyph = g
            layout.addWidget(g)
        else:
            self._glyph = None

        text = QLabel(item.get("label", ""))
        self._text = text
        layout.addWidget(text, 1)
        self._paint()

    def _mark(self):
        if self.item.get("kind") == "separator":
            return ""
        if self.item.get("checked"):
            return "\uf00c"
        return ""

    def _paint(self):
        enabled = self.item.get("enabled", True)
        active = self.hovered and enabled
        checked = bool(self.item.get("checked"))
        fg = self.theme["menu_sel_text"] if (active or checked) else self.theme["menu_fg"]
        if not enabled:
            fg = self.theme["muted"]
        for lab in (self._mark_label, self._glyph, self._text):
            if lab is None:
                continue
            lab.setStyleSheet(f"color: {fg}; background: transparent; font-size: {self.theme['font_size']}px;")
        self._mark_label.setText(self._mark())
        self.update()

    def enterEvent(self, _event):
        self.hovered = True
        self._paint()

    def leaveEvent(self, _event):
        self.hovered = False
        self._paint()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.item.get("enabled", True):
            callback = self.item.get("callback")
            popup = self.window()
            if popup is not None:
                popup.hide()
            if callable(callback):
                callback()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        if self.hovered and self.item.get("enabled", True):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self.theme["menu_sel_bg"]))
            painter.drawRoundedRect(self.rect().adjusted(4, 2, -4, -2), 6, 6)
            painter.end()
        super().paintEvent(event)


class _Separator(QWidget):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.theme = theme
        self.setFixedHeight(11)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(QColor(self.theme["muted"]), 1))
        y = self.height() // 2
        painter.drawLine(14, y, self.width() - 14, y)
        painter.end()


class ThemedMenu(QWidget):
    """Frameless popup that follows Omarchy [menu] tokens.

    Used instead of QMenu so Fusion + our own paint path win over the
    gtk3 platform theme, which would otherwise draw an Adwaita menu.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.theme = load_theme()
        self.setObjectName("z13ThemedMenu")
        self.setWindowTitle("z13-power-menu")
        self.setWindowFlags(
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._body = QFrame(self)
        self._body.setObjectName("menuCard")
        self._layout = QVBoxLayout(self._body)
        self._layout.setContentsMargins(8, 8, 8, 8)
        self._layout.setSpacing(0)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self._body)
        self._apply_card()

    def _apply_card(self):
        t = self.theme
        self._body.setStyleSheet(
            f"#menuCard {{"
            f" background: {t['menu_bg']};"
            f" border: 1px solid {t['menu_border']};"
            f" border-radius: {t['radius']}px;"
            f"}}"
        )
        self.setFont(QFont(t["font"], t["font_size"]))

    def set_theme(self, theme):
        self.theme = theme
        self._apply_card()

    def set_items(self, items):
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for entry in items:
            if entry.get("kind") == "separator":
                self._layout.addWidget(_Separator(self.theme, self._body))
            elif entry.get("kind") == "header":
                lab = QLabel(entry.get("label", ""))
                lab.setStyleSheet(
                    f"color: {self.theme['muted']}; background: transparent;"
                    f" font-size: {max(9, self.theme['font_size'] - 2)}px;"
                    f" letter-spacing: 1px; padding: 6px 12px 4px 12px;"
                )
                self._layout.addWidget(lab)
            else:
                self._layout.addWidget(_MenuRow(entry, self.theme, self._body))
        self.adjustSize()

    def popup(self, pos=None):
        if pos is None:
            pos = QCursor.pos()
        self.adjustSize()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        geo = screen.availableGeometry() if screen else None
        x, y = pos.x(), pos.y()
        if geo is not None:
            x = min(x, geo.right() - self.width() - 8)
            y = min(y, geo.bottom() - self.height() - 8)
            x = max(geo.left() + 8, x)
            y = max(geo.top() + 8, y)
        self.move(QPoint(x, y))
        self.show()
        self.raise_()

    def leaveEvent(self, event):
        # Dismiss when the pointer leaves the card, matching Omarchy popups
        # that close on an outside hover/click.
        super().leaveEvent(event)

    def hideEvent(self, event):
        super().hideEvent(event)

    def paintEvent(self, event):
        # Keep the card clipped to the rounded path so the translucent
        # window corners don't show a square drop-shadow hole.
        opt = QStyleOption()
        opt.initFrom(self)
        painter = QPainter(self)
        self.style().drawPrimitive(QStyle.PrimitiveElement.PE_Widget, opt, painter, self)
        painter.end()
        super().paintEvent(event)


def install_click_away(menu, app=None):
    """Hide the themed menu when the user clicks anywhere else."""

    class _Filter(QObject):
        def eventFilter(self, obj, event):
            if menu.isVisible() and event.type() == event.Type.MouseButtonPress:
                if not menu.geometry().contains(event.globalPosition().toPoint()):
                    menu.hide()
            return False

    application = app or QApplication.instance()
    filt = _Filter(menu)
    if application is not None:
        application.installEventFilter(filt)
    menu._click_away = filt
    return filt
