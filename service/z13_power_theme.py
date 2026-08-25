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

from PyQt6.QtCore import (
    QObject, QPoint, QPointF, QRectF, Qt, QFileSystemWatcher, pyqtSignal,
)
from PyQt6.QtGui import (
    QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen,
)
from PyQt6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QStyle, QStyleOption, QVBoxLayout, QWidget,
)

def is_omarchy():
    """True when this user has an Omarchy config — not KDE/Cachy-without-it."""
    return os.path.isdir(os.path.expanduser("~/.config/omarchy"))


CURRENT_DIR = os.path.expanduser("~/.local/state/omarchy/current")
THEME_DIR = os.path.join(CURRENT_DIR, "theme")
THEME_NAME = os.path.join(CURRENT_DIR, "theme.name")
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

# Omarchy colors.toml / shell.toml use unquoted hex (`accent = #faa968`) as
# well as quoted strings. A naive split-on-# would eat every color.
_KV = re.compile(
    r'^([A-Za-z0-9_.-]+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|(\S.*?))\s*$'
)
_COMMENT = re.compile(r"\s+#(?![0-9A-Fa-f]{3,8}\b).*$")


def _parse_simple(path):
    """Parse the subset of TOML Omarchy ships (flat keys, quoted or bare)."""
    out = {}
    section = ""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError:
        return out
    for raw in lines:
        line = _COMMENT.sub("", raw).strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            continue
        m = _KV.match(line)
        if not m:
            continue
        value = m.group(2) if m.group(2) is not None else (
            m.group(3) if m.group(3) is not None else m.group(4))
        key = f"{section}.{m.group(1)}" if section else m.group(1)
        out[key] = value
    return out


def _hex(value, fallback):
    text = str(value or "").strip().strip("\"'")
    if text.startswith("#") and len(text) in (4, 7, 9):
        return text
    return fallback


def _token_hex(raw, shell, colors, fallback):
    """Resolve a shell.toml color: hex, palette role, or hyprland.* alias."""
    text = str(raw or "").strip().strip("\"'")
    if not text:
        return fallback
    if text.startswith("#"):
        return _hex(text, fallback)
    role = text.lower()
    if role in ("foreground", "text"):
        return _hex(colors.get("foreground"), fallback)
    if role == "accent":
        return _hex(colors.get("accent") or colors.get("blue"), fallback)
    if role == "background":
        return _hex(colors.get("background"), fallback)
    if role == "muted":
        return _hex(colors.get("muted") or colors.get("dark_foreground"), fallback)
    if text.startswith("hyprland."):
        return _token_hex(shell.get(text), shell, colors, fallback)
    return fallback


def _alpha(hex_color, alpha):
    color = QColor(hex_color)
    color.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return color.name(QColor.NameFormat.HexArgb)


_font_cache = None
_radius_cache = None


def detect_font():
    """Same source `omarchy font current` uses: fontconfig monospace."""
    global _font_cache
    if _font_cache:
        return _font_cache
    try:
        out = subprocess.check_output(
            ["fc-match", "monospace", "-f", "%{family}\\n"],
            text=True, timeout=2)
        name = out.splitlines()[0].split(",")[0].strip()
        if name:
            _font_cache = name
            return name
    except (OSError, subprocess.SubprocessError):
        pass
    _font_cache = "JetBrainsMono Nerd Font"
    return _font_cache


def detect_radius():
    """Hyprland `decoration:rounding` — 0 on sharp Omarchy themes."""
    global _radius_cache
    if _radius_cache is not None:
        return _radius_cache
    try:
        import json
        out = subprocess.check_output(
            ["hyprctl", "-j", "getoption", "decoration:rounding"],
            text=True, timeout=1)
        value = int(json.loads(out).get("int", 0))
        _radius_cache = max(0, value)
        return _radius_cache
    except (OSError, subprocess.SubprocessError, ValueError, TypeError):
        _radius_cache = 12
        return _radius_cache


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

    menu_bg = _token_hex(shell.get("menu.background"), shell, colors, bg)
    menu_fg = _token_hex(shell.get("menu.text"), shell, colors, fg)
    menu_border = _token_hex(shell.get("menu.border"), shell, colors, fg)
    menu_sel_bg = _token_hex(shell.get("menu.selected-background"),
                             shell, colors, fg)
    try:
        sel_a = float(shell.get("menu.selected-background-alpha", "0.08"))
    except ValueError:
        sel_a = 0.08
    try:
        border_a = float(shell.get("menu.border-alpha", "1.0"))
    except ValueError:
        border_a = 1.0
    menu_sel_text = _token_hex(shell.get("menu.selected-text"), shell, colors,
                               accent)

    try:
        base = int(float(shell.get("font.base-size", "12")))
    except ValueError:
        base = 12

    def _shell_float(key, default):
        try:
            return float(shell.get(key, default))
        except (TypeError, ValueError):
            return float(default)

    fill_a = _shell_float("controls.normal-fill-alpha", 0.04)
    hover_a = _shell_float("controls.hover-cursor-fill-alpha", 0.08)
    selected_a = _shell_float("controls.selected-fill-alpha", 0.18)
    border_fill_a = _shell_float("controls.normal-border-alpha", 0.4)
    hover_border_a = _shell_float("controls.hover-cursor-border-alpha", 0.25)

    popup_bg = _token_hex(shell.get("popups.background"), shell, colors, bg)
    popup_fg = _token_hex(shell.get("popups.text"), shell, colors, fg)

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
        "popup_bg": popup_bg,
        "popup_fg": popup_fg,
        "control_fill": _alpha(fg, fill_a),
        "control_fill_hover": _alpha(fg, hover_a),
        "control_fill_selected": _alpha(fg, selected_a),
        "control_border": _alpha(fg, border_fill_a),
        "control_border_hover": _alpha(fg, hover_border_a),
        "font": detect_font(),
        "font_size": max(10, base),
        "caption_size": max(9, base - 2),
        "title_size": max(12, base + 2),
        "display_size": max(18, base * 2),
        "radius": detect_radius(),
    }


def theme_rgb_pair(theme=None):
    """Accent + cyan from the live Omarchy theme, as 6-digit hex (no #)."""
    t = theme or load_theme()

    def strip(c):
        s = str(c or "").strip().lstrip("#")
        if len(s) == 3 and all(ch in "0123456789abcdefABCDEF" for ch in s):
            s = "".join(ch * 2 for ch in s)
        if len(s) >= 6 and all(ch in "0123456789abcdefABCDEF" for ch in s[:6]):
            return s[:6].upper()
        return None

    c1 = strip(t.get("accent")) or "81A1C1"
    c2 = strip(t.get("cyan")) or strip(t.get("blue")) or c1
    return c1, c2


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
    radius = min(int(t["radius"]), 8)
    knob = 7 if t["radius"] > 0 else 0
    groove = 3 if t["radius"] > 0 else 0
    return f"""
    * {{
        font-family: "{font}";
        font-size: {size}px;
        color: {t["popup_fg"]};
    }}
    QMainWindow, QDialog, QMessageBox, QStackedWidget, QScrollArea {{
        background-color: {t["popup_bg"]};
        color: {t["popup_fg"]};
    }}
    QWidget {{
        color: {t["popup_fg"]};
        selection-background-color: {t["menu_sel_bg"]};
        selection-color: {t["menu_sel_text"]};
    }}
    QTabWidget::pane {{
        border: 1px solid {t["control_border"]};
        background: {t["popup_bg"]};
        top: -1px;
    }}
    QTabBar::tab {{
        background: {t["control_fill"]};
        color: {t["popup_fg"]};
        padding: 7px 14px;
        border: 1px solid {t["control_border"]};
        border-bottom: none;
        margin-right: 2px;
    }}
    QTabBar::tab:selected {{
        background: {t["control_fill_selected"]};
        color: {t["accent"]};
    }}
    QTabBar::tab:hover {{
        background: {t["control_fill_hover"]};
        color: {t["accent"]};
    }}
    QPushButton {{
        background: {t["control_fill"]};
        color: {t["foreground"]};
        border: 1px solid {t["control_border"]};
        border-radius: {radius}px;
        padding: 6px 12px;
        min-height: 28px;
    }}
    QPushButton:hover {{
        background: {t["control_fill_hover"]};
        border-color: {t["control_border_hover"]};
    }}
    QPushButton:pressed {{
        background: {t["control_fill_selected"]};
    }}
    QPushButton:checked {{
        background: {t["control_fill_selected"]};
        color: {t["accent"]};
        border-color: {t["control_border_hover"]};
    }}
    QComboBox, QSpinBox, QAbstractSpinBox, QLineEdit {{
        background: {t["control_fill"]};
        color: {t["foreground"]};
        border: 1px solid {t["control_border"]};
        border-radius: {radius}px;
        padding: 4px 8px;
        min-height: 28px;
    }}
    QComboBox:hover, QSpinBox:hover, QAbstractSpinBox:hover, QLineEdit:hover {{
        background: {t["control_fill_hover"]};
        border-color: {t["control_border_hover"]};
    }}
    QComboBox QAbstractItemView {{
        background: {t["menu_bg"]};
        color: {t["menu_fg"]};
        selection-background-color: {t["menu_sel_bg"]};
        selection-color: {t["menu_sel_text"]};
        border: 1px solid {t["menu_border"]};
        outline: none;
    }}
    QSlider::groove:horizontal {{
        height: 6px;
        background: {t["control_fill_selected"]};
        border-radius: {groove}px;
    }}
    QSlider::sub-page:horizontal {{
        background: {t["foreground"]};
        border-radius: {groove}px;
    }}
    QSlider::handle:horizontal {{
        background: {t["foreground"]};
        width: 14px;
        margin: -5px 0;
        border-radius: {knob}px;
    }}
    QCheckBox::indicator {{
        width: 14px;
        height: 14px;
        border: 1px solid {t["control_border"]};
        border-radius: {min(radius, 3)}px;
        background: {t["control_fill"]};
    }}
    QCheckBox::indicator:checked {{
        background: {t["accent"]};
        border-color: {t["accent"]};
    }}
    QLabel {{
        background: transparent;
    }}
    QToolTip {{
        background: {t["popup_bg"]};
        color: {t["popup_fg"]};
        border: 1px solid {t["menu_border"]};
        padding: 4px 8px;
    }}
    QMenu {{
        background: {t["menu_bg"]};
        color: {t["menu_fg"]};
        border: 1px solid {t["menu_border"]};
        border-radius: {min(int(t["radius"]), 8)}px;
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
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QMessageBox {{
        background: {t["popup_bg"]};
    }}
    QMessageBox QLabel {{
        color: {t["foreground"]};
    }}
    QColorDialog {{
        background: {t["popup_bg"]};
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


def apply_to_tray(app=None, theme=None):
    """Fusion + font for the windowless tray. Skip the settings QSS."""
    application = app or QApplication.instance()
    t = theme or load_theme()
    if application is None:
        return t
    application.setStyle("Fusion")
    application.setStyleSheet("")
    application.setFont(QFont(t["font"], t["font_size"]))
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
        # omarchy-theme-set rm -rf's `theme/` and mv's a new tree in. Watch
        # the parent `current/` dir so the swap always produces an event,
        # then re-arm file watches after the new tree exists.
        paths = [CURRENT_DIR, THEME_DIR, THEME_NAME, COLORS_PATH, SHELL_PATH]
        existing = [p for p in paths if os.path.exists(p)]
        current = set(self._watcher.files()) | set(self._watcher.directories())
        for stale in current - set(existing):
            self._watcher.removePath(stale)
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
        self._timer.start(250)


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


def _apply_children(widget, theme):
    for child in widget.findChildren(QWidget):
        apply = getattr(child, "apply_theme", None)
        if callable(apply):
            apply(theme)


class SectionHeader(QLabel):
    """Small-caps section label matching Omarchy PanelSectionHeader."""

    def __init__(self, text, theme, parent=None):
        super().__init__(text, parent)
        self._theme = theme
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self._theme = theme
        color = QColor(theme["foreground"]).darker(140).name()
        self.setStyleSheet(
            f"color: {color}; background: transparent;"
            f" font-size: {theme['caption_size']}px; font-weight: 700;"
            f" letter-spacing: 1px; padding-top: 2px;"
        )


class Note(QLabel):
    def __init__(self, text, theme, parent=None):
        super().__init__(text, parent)
        self.setWordWrap(True)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        color = QColor(theme["foreground"]).darker(150).name()
        self.setStyleSheet(
            f"color: {color}; background: transparent;"
            f" font-size: {theme['caption_size']}px;"
        )


class StatusLine(QLabel):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self.setWordWrap(True)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self._theme = theme
        self.setStyleSheet(
            f"color: {theme['foreground']}; background: transparent;"
        )

    def set_info(self, text):
        self.setStyleSheet(
            f"color: {self._theme['foreground']}; background: transparent;"
        )
        self.setText(text)

    def set_result(self, ok, text):
        color = self._theme["green"] if ok else self._theme["red"]
        self.setStyleSheet(f"color: {color}; background: transparent;")
        self.setText(text)


class HLine(QFrame):
    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFixedHeight(1)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self.setStyleSheet(f"background: {theme['control_border']};")


class Hero(QWidget):
    """Bolt + title + uppercase meta, same shape as the tray flyout hero."""

    def __init__(self, glyph, title, meta, theme, parent=None):
        super().__init__(parent)
        self._glyph = QLabel(glyph)
        self._title = QLabel(title)
        self._meta = QLabel(meta.upper())
        self._detail = QLabel("")
        labels = QVBoxLayout()
        labels.setContentsMargins(0, 0, 0, 0)
        labels.setSpacing(2)
        labels.addWidget(self._title)
        labels.addWidget(self._meta)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        row.addWidget(self._glyph)
        row.addLayout(labels, 1)
        row.addWidget(self._detail, 0, Qt.AlignmentFlag.AlignVCenter)
        self.apply_theme(theme)

    def set_meta(self, text):
        self._meta.setText(str(text or "").upper())

    def set_detail(self, text):
        self._detail.setText(str(text or ""))
        self._detail.setVisible(bool(text))

    def apply_theme(self, theme):
        muted = QColor(theme["foreground"]).darker(140).name()
        self._glyph.setStyleSheet(
            f"color: {theme['foreground']}; background: transparent;"
            f" font-size: {theme['display_size']}px;"
        )
        self._title.setStyleSheet(
            f"color: {theme['foreground']}; background: transparent;"
            f" font-size: {theme['title_size']}px; font-weight: 700;"
        )
        self._meta.setStyleSheet(
            f"color: {muted}; background: transparent;"
            f" font-size: {theme['caption_size']}px; font-weight: 700;"
            f" letter-spacing: 1px;"
        )
        self._detail.setStyleSheet(
            f"color: {theme['foreground']}; background: transparent;"
            f" font-size: {theme['display_size']}px; font-weight: 700;"
        )


class Pill(QPushButton):
    """Bordered control matching Omarchy Button { bordered: true }."""

    def __init__(self, text, theme, parent=None, glyph=""):
        super().__init__(parent)
        self._plain = text
        self._glyph = glyph
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)
        self.setAutoExclusive(False)
        self.setText((glyph + "  " if glyph else "") + text)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        radius = min(int(theme["radius"]), 8)
        self.setStyleSheet(
            f"QPushButton {{"
            f" background: {theme['control_fill']};"
            f" color: {theme['foreground']};"
            f" border: 1px solid {theme['control_border']};"
            f" border-radius: {radius}px;"
            f" padding: 6px 10px;"
            f" min-height: 28px;"
            f"}}"
            f"QPushButton:hover {{"
            f" background: {theme['control_fill_hover']};"
            f" border-color: {theme['control_border_hover']};"
            f"}}"
            f"QPushButton:checked {{"
            f" background: {theme['control_fill_selected']};"
            f" color: {theme['accent']};"
            f" border-color: {theme['control_border_hover']};"
            f" font-weight: 700;"
            f"}}"
        )


class PillRow(QWidget):
    """Exclusive row of pills. options is [value] or [(value, label, glyph?)]."""

    changed = pyqtSignal(str)

    def __init__(self, options, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._pills = {}
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        for option in options:
            if isinstance(option, (tuple, list)):
                value = option[0]
                label = option[1] if len(option) > 1 else value
                glyph = option[2] if len(option) > 2 else ""
            else:
                value, label, glyph = option, option, ""
            pill = Pill(label, theme, self, glyph=glyph)
            pill.clicked.connect(lambda _c=False, v=value: self.changed.emit(v))
            self._group.addButton(pill)
            self._pills[value] = pill
            row.addWidget(pill, 1)

    def value(self):
        for value, pill in self._pills.items():
            if pill.isChecked():
                return value
        return next(iter(self._pills), "")

    def set_value(self, value):
        if value in self._pills:
            self._pills[value].setChecked(True)

    def apply_theme(self, theme):
        self._theme = theme
        for pill in self._pills.values():
            pill.apply_theme(theme)


class ColorPill(QPushButton):
    def __init__(self, hexval, theme, parent=None):
        super().__init__(parent)
        self.hexval = hexval.lstrip("#")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(26, 26)
        self.apply_theme(theme)

    def set_hex(self, hexval):
        self.hexval = hexval.lstrip("#")
        self.apply_theme(self._theme)

    def apply_theme(self, theme):
        self._theme = theme
        radius = min(int(theme["radius"]), 6)
        color = f"#{self.hexval}"
        self.setStyleSheet(
            f"QPushButton {{"
            f" background: {color};"
            f" border: 2px solid {theme['control_border']};"
            f" border-radius: {radius}px;"
            f" padding: 0;"
            f" min-width: 26px; max-width: 26px;"
            f" min-height: 26px; max-height: 26px;"
            f"}}"
            f"QPushButton:checked {{"
            f" border: 2px solid {theme['accent']};"
            f"}}"
        )


class ToggleRow(QWidget):
    """Labeled row + painted switch, matching Omarchy Toggle."""

    clicked = pyqtSignal()

    def __init__(self, label, description, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._label = label
        self._description = description
        self._checked = False
        self._hot = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(54)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def isChecked(self):
        return self._checked

    def setChecked(self, checked):
        self._checked = bool(checked)
        self.update()

    def apply_theme(self, theme):
        self._theme = theme
        self.update()

    def enterEvent(self, event):
        self._hot = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hot = False
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        t = self._theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = min(int(t["radius"]), 8)
        fill = t["control_fill_hover"] if self._hot else t["control_fill"]
        border = t["control_border_hover"] if self._hot else t["control_border"]
        painter.setPen(QPen(QColor(border), 1))
        painter.setBrush(QColor(fill))
        painter.drawRoundedRect(rect, radius, radius)

        track_h = 20
        track_w = 38
        pad = 12
        track = QRectF(self.width() - pad - track_w,
                       (self.height() - track_h) / 2, track_w, track_h)
        track_radius = track_h / 2 if t["radius"] > 0 else 0
        if self._checked:
            painter.setBrush(QColor(t["control_fill_selected"]))
            painter.setPen(QPen(QColor(t["control_border_hover"]), 1))
        else:
            painter.setBrush(QColor(t["control_fill"]))
            painter.setPen(QPen(QColor(t["control_border"]), 1))
        painter.drawRoundedRect(track, track_radius, track_radius)

        knob = 14
        inset = (track_h - knob) / 2
        kx = track.right() - inset - knob if self._checked else track.left() + inset
        knob_rect = QRectF(kx, track.top() + inset, knob, knob)
        knob_r = knob / 2 if t["radius"] > 0 else 0
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["accent"] if self._checked else t["muted"]))
        painter.drawRoundedRect(knob_rect, knob_r, knob_r)

        text_right = int(track.left() - 12)
        title_font = QFont(t["font"], t["title_size"] - 1)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(QColor(t["foreground"]))
        painter.drawText(QRectF(pad, 8, text_right - pad, 20),
                         Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                         self._label)
        if self._description:
            cap = QFont(t["font"], t["caption_size"])
            painter.setFont(cap)
            painter.setPen(QColor(t["foreground"]).darker(150))
            painter.drawText(QRectF(pad, 28, text_right - pad, 18),
                             Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                             self._description)
        painter.end()


class NavItem(QPushButton):
    def __init__(self, glyph, label, theme, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setAutoExclusive(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setText(f"{glyph}   {label}")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        radius = min(int(theme["radius"]), 8)
        self.setStyleSheet(
            f"QPushButton {{"
            f" background: transparent;"
            f" color: {theme['foreground']};"
            f" border: 1px solid transparent;"
            f" border-radius: {radius}px;"
            f" padding: 8px 12px;"
            f" text-align: left;"
            f" min-height: 32px;"
            f"}}"
            f"QPushButton:hover {{"
            f" background: {theme['control_fill_hover']};"
            f"}}"
            f"QPushButton:checked {{"
            f" background: {theme['control_fill_selected']};"
            f" color: {theme['accent']};"
            f" font-weight: 700;"
            f"}}"
        )


class InfoRow(QWidget):
    def __init__(self, label, value, theme, parent=None):
        super().__init__(parent)
        self._label = QLabel(label)
        self._value = QLabel(value)
        self._value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 2, 0, 2)
        row.setSpacing(8)
        row.addWidget(self._label)
        row.addWidget(self._value, 1)
        self.apply_theme(theme)

    def set_value(self, value):
        self._value.setText(value)

    def apply_theme(self, theme):
        muted = QColor(theme["foreground"])
        muted.setAlphaF(0.6)
        self._label.setStyleSheet(
            f"color: {muted.name(QColor.NameFormat.HexArgb)}; background: transparent;"
        )
        self._value.setStyleSheet(
            f"color: {theme['foreground']}; background: transparent;"
        )


class FanCurveGraph(QWidget):
    """Eight firmware curve points. Drag to edit. X = °C, Y = fan %."""

    changed = pyqtSignal()
    TEMP_MIN, TEMP_MAX = 30, 100

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._points = [(40 + i * 7, min(255, 24 + i * 28)) for i in range(8)]
        self._hover = -1
        self._drag = -1
        self._live_temp = None
        self._min_pwm = 0
        self.setMouseTracking(True)
        self.setMinimumHeight(260)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.apply_theme(theme)

    def apply_theme(self, theme):
        self._theme = theme
        self.update()

    def set_points(self, points):
        if len(points) != 8:
            return
        self._points = [(int(t), int(p)) for t, p in points]
        self.update()
        self.changed.emit()

    def points(self):
        return list(self._points)

    def set_live_temp(self, temp):
        try:
            self._live_temp = int(temp)
        except (TypeError, ValueError):
            self._live_temp = None
        self.update()

    def set_min_pwm(self, pwm):
        try:
            self._min_pwm = max(0, min(255, int(pwm)))
        except (TypeError, ValueError):
            self._min_pwm = 0
        self.update()

    def selected_label(self):
        i = self._drag if self._drag >= 0 else self._hover
        if i < 0:
            return ""
        temp, pwm = self._points[i]
        return "Point %d  ·  %d°C  ·  %d%%" % (i + 1, temp, round(pwm * 100 / 255))

    def _plot(self):
        return QRectF(42, 14, max(48, self.width() - 56), max(48, self.height() - 40))

    def _xy(self, temp, pwm):
        plot = self._plot()
        tx = (temp - self.TEMP_MIN) / float(self.TEMP_MAX - self.TEMP_MIN)
        py = pwm / 255.0
        return plot.left() + tx * plot.width(), plot.bottom() - py * plot.height()

    def _from_xy(self, x, y):
        plot = self._plot()
        tx = 0.0 if plot.width() <= 0 else (x - plot.left()) / plot.width()
        py = 0.0 if plot.height() <= 0 else (plot.bottom() - y) / plot.height()
        temp = round(self.TEMP_MIN + tx * (self.TEMP_MAX - self.TEMP_MIN))
        pwm = round(py * 255)
        return temp, pwm

    def _hit(self, pos):
        best, dist = -1, 18.0
        for i, (temp, pwm) in enumerate(self._points):
            x, y = self._xy(temp, pwm)
            d = ((pos.x() - x) ** 2 + (pos.y() - y) ** 2) ** 0.5
            if d < dist:
                best, dist = i, d
        return best

    def paintEvent(self, _event):
        t = self._theme
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        plot = self._plot()
        radius = float(t.get("radius", 8))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(t["control_fill"]))
        painter.drawRoundedRect(
            QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        muted = QColor(t["foreground"])
        muted.setAlphaF(0.45)
        painter.setFont(QFont(t["font"], t["caption_size"]))

        for pct in (0, 25, 50, 75, 100):
            _x, y = self._xy(self.TEMP_MIN, round(pct * 255 / 100.0))
            painter.setPen(QPen(QColor(t["control_border"])))
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))
            painter.setPen(QPen(muted))
            painter.drawText(
                QRectF(2, y - 9, plot.left() - 8, 18),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                "%d%%" % pct)

        for temp in (30, 50, 70, 90, 100):
            x, _y = self._xy(temp, 0)
            painter.setPen(QPen(QColor(t["control_border"])))
            painter.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))
            painter.setPen(QPen(muted))
            painter.drawText(
                QRectF(x - 20, plot.bottom() + 2, 40, 18),
                Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop,
                "%d°" % temp)

        if self._min_pwm > 0:
            _x, y = self._xy(self.TEMP_MIN, self._min_pwm)
            dash = QPen(QColor(t.get("yellow") or t["accent"]))
            dash.setStyle(Qt.PenStyle.DashLine)
            painter.setPen(dash)
            painter.drawLine(int(plot.left()), int(y), int(plot.right()), int(y))

        path = QPainterPath()
        x0, y0 = self._xy(self._points[0][0], self._points[0][1])
        path.moveTo(x0, plot.bottom())
        path.lineTo(x0, y0)
        for temp, pwm in self._points[1:]:
            x, y = self._xy(temp, pwm)
            path.lineTo(x, y)
        x_end, _y_end = self._xy(self._points[-1][0], self._points[-1][1])
        path.lineTo(x_end, plot.bottom())
        path.closeSubpath()
        fill = QColor(t["accent"])
        fill.setAlphaF(0.18)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(fill)
        painter.drawPath(path)

        line = QPen(QColor(t["accent"]))
        line.setWidthF(2.2)
        painter.setPen(line)
        for i in range(len(self._points) - 1):
            x1, y1 = self._xy(self._points[i][0], self._points[i][1])
            x2, y2 = self._xy(self._points[i + 1][0], self._points[i + 1][1])
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        if self._live_temp is not None:
            temp = max(self.TEMP_MIN, min(self.TEMP_MAX, self._live_temp))
            x, _y = self._xy(temp, 0)
            live = QPen(QColor(t["foreground"]))
            live.setStyle(Qt.PenStyle.DashLine)
            live.setWidthF(1.2)
            painter.setPen(live)
            painter.drawLine(int(x), int(plot.top()), int(x), int(plot.bottom()))

        for i, (temp, pwm) in enumerate(self._points):
            x, y = self._xy(temp, pwm)
            r = 7.0 if i in (self._hover, self._drag) else 5.0
            painter.setPen(QPen(QColor(t["accent"]), 2))
            painter.setBrush(QColor(t["popup_bg"]))
            painter.drawEllipse(QPointF(x, y), r, r)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._drag = self._hit(event.position())
        if self._drag >= 0:
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
            self.changed.emit()

    def mouseMoveEvent(self, event):
        pos = event.position()
        if self._drag < 0:
            hover = self._hit(pos)
            if hover != self._hover:
                self._hover = hover
                self.update()
                self.changed.emit()
            return
        i = self._drag
        temp, pwm = self._from_xy(pos.x(), pos.y())
        lo_t = self.TEMP_MIN if i == 0 else self._points[i - 1][0] + 1
        hi_t = self.TEMP_MAX if i == 7 else self._points[i + 1][0] - 1
        lo_p = self._min_pwm if i == 0 else max(self._min_pwm, self._points[i - 1][1])
        hi_p = 255 if i == 7 else self._points[i + 1][1]
        self._points[i] = (max(lo_t, min(hi_t, temp)), max(lo_p, min(hi_p, pwm)))
        self.update()
        self.changed.emit()

    def mouseReleaseEvent(self, _event):
        self._drag = -1
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()
        self.changed.emit()

    def leaveEvent(self, event):
        if self._drag < 0 and self._hover != -1:
            self._hover = -1
            self.update()
            self.changed.emit()
        super().leaveEvent(event)
