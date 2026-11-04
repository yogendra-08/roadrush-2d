"""Shared look & feel: theme colours, fonts, gradient backgrounds and canvas widgets."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont

from PIL import Image, ImageDraw, ImageTk

VIEW_W, VIEW_H = 1000, 660

BG_TOP, BG_BOTTOM = (10, 14, 38), (48, 16, 74)
PANEL = "#1a1f40"
PANEL_LIGHT = "#272e5c"
TEXT = "#f4f6ff"
MUTED = "#98a2d6"
ACCENT = "#ff3d71"
ACCENT_DARK = "#c4244f"
GOLD = "#ffd23c"
CYAN = "#38d6ff"
GREEN = "#4cf29a"
RED = "#ff5b5b"

_family: str | None = None


def pick_font_family(root: tk.Misc) -> str:
    """Prefer a modern UI font that exists on the machine (Segoe UI on Windows)."""
    global _family
    if _family is None:
        available = set(tkfont.families(root))
        for name in ("Segoe UI", "Helvetica Neue", "Inter", "DejaVu Sans", "Arial", "Helvetica"):
            if name in available:
                _family = name
                break
        else:
            _family = "TkDefaultFont"
    return _family


def font(size: int, bold: bool = True, italic: bool = False) -> tuple:
    style = ("bold " if bold else "") + ("italic" if italic else "")
    return (_family or "Helvetica", size, style.strip() or "normal")


def gradient_image(w: int = VIEW_W, h: int = VIEW_H) -> Image.Image:
    """Vertical gradient with faint diagonal 'speed lines'."""
    img = Image.new("RGB", (w, h))
    px = ImageDraw.Draw(img)
    for y in range(h):
        t = y / (h - 1)
        px.line([(0, y), (w, y)], fill=tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)))
    over = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(over)
    for k in range(-h, w, 70):
        od.line([(k, h), (k + h * 0.55, 0)], fill=(255, 255, 255, 10), width=22)
    for k in range(-h, w, 210):
        od.line([(k + 30, h), (k + 30 + h * 0.55, 0)], fill=(255, 61, 113, 14), width=6)
    img.paste(over, (0, 0), over)
    return img


def round_rect(canvas: tk.Canvas, x1, y1, x2, y2, r=12, **kw) -> int:
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
           x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


_STYLES = {
    "primary": ("#ff3d71", "#ff6b93", "#c4244f", "#ffffff"),
    "secondary": ("#2b3370", "#3b4590", "#1c2250", "#f4f6ff"),
    "success": ("#1fbf75", "#3ee59a", "#13885a", "#06241a"),
    "danger": ("#8a2a3c", "#b53a50", "#5a1824", "#ffffff"),
    "gold": ("#ffb81c", "#ffd23c", "#b8800a", "#2a1c00"),
}


class CanvasButton:
    """A rounded, hover-aware button drawn on a canvas (works on any canvas)."""

    _counter = 0

    def __init__(self, canvas, x, y, w, h, text, command, style="secondary", size=16, sound=None, anchor="center"):
        CanvasButton._counter += 1
        self.canvas, self.command, self.style, self.sound = canvas, command, style, sound
        self.tag = f"btn{CanvasButton._counter}"
        if anchor == "center":
            x1, y1 = x - w / 2, y - h / 2
        else:
            x1, y1 = x, y
        x2, y2 = x1 + w, y1 + h
        self.enabled = True
        base, hover, shadow, fg = _STYLES[style]
        self._colors = (base, hover)
        self.shadow = round_rect(canvas, x1, y1 + 5, x2, y2 + 5, 14, fill=shadow, outline="", tags=(self.tag,))
        self.body = round_rect(canvas, x1, y1, x2, y2, 14, fill=base, outline="", tags=(self.tag,))
        self.shine = canvas.create_line(x1 + 16, y1 + 4, x2 - 16, y1 + 4, fill="#ffffff", stipple="gray25",
                                        width=2, tags=(self.tag,))
        self.label = canvas.create_text((x1 + x2) / 2, (y1 + y2) / 2, text=text, fill=fg, font=font(size),
                                        tags=(self.tag,))
        self._fg = fg
        canvas.tag_bind(self.tag, "<Enter>", self._enter)
        canvas.tag_bind(self.tag, "<Leave>", self._leave)
        canvas.tag_bind(self.tag, "<ButtonPress-1>", self._press)
        canvas.tag_bind(self.tag, "<ButtonRelease-1>", self._release)

    def _enter(self, _e):
        if self.enabled:
            self.canvas.itemconfig(self.body, fill=self._colors[1])
            self.canvas.config(cursor="hand2")

    def _leave(self, _e):
        if self.enabled:
            self.canvas.itemconfig(self.body, fill=self._colors[0])
        self.canvas.config(cursor="")

    def _press(self, _e):
        if self.enabled:
            self.canvas.move(self.tag, 0, 2)
            self._pressed = True

    def _release(self, e):
        if not self.enabled or not getattr(self, "_pressed", False):
            return
        self._pressed = False
        self.canvas.move(self.tag, 0, -2)
        x1, y1, x2, y2 = self.canvas.bbox(self.body)
        if x1 <= e.x <= x2 and y1 <= e.y <= y2 and self.command:
            if self.sound:
                self.sound("click")
            self.command()

    def set_text(self, text: str) -> None:
        self.canvas.itemconfig(self.label, text=text)

    def set_style(self, style: str) -> None:
        base, hover, shadow, fg = _STYLES[style]
        self._colors = (base, hover)
        self.canvas.itemconfig(self.body, fill=base)
        self.canvas.itemconfig(self.shadow, fill=shadow)
        self.canvas.itemconfig(self.label, fill=fg)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self.canvas.itemconfig(self.body, fill=self._colors[0] if enabled else "#3a3f5e")
        self.canvas.itemconfig(self.label, fill=self._fg if enabled else "#80869e")

    def destroy(self) -> None:
        self.canvas.delete(self.tag)


class Segmented:
    """Row of mutually exclusive buttons (e.g. difficulty)."""

    def __init__(self, canvas, x, y, options, selected, on_change, w=110, h=40, gap=10, sound=None, size=14):
        self.options, self.selected, self.on_change = options, selected, on_change
        self.buttons = {}
        total = len(options) * w + (len(options) - 1) * gap
        for i, (key, label) in enumerate(options):
            bx = x - total / 2 + i * (w + gap) + w / 2
            self.buttons[key] = CanvasButton(canvas, bx, y, w, h, label, lambda k=key: self.select(k),
                                             "primary" if key == selected else "secondary", size, sound)

    def select(self, key):
        self.selected = key
        for k, b in self.buttons.items():
            b.set_style("primary" if k == key else "secondary")
        self.on_change(key)


class Slider:
    """Horizontal 0..1 slider with drag support."""

    def __init__(self, canvas, x, y, w, value, on_change, on_release=None):
        self.canvas, self.x, self.y, self.w = canvas, x, y, w
        self.value, self.on_change, self.on_release = value, on_change, on_release
        self.tag = f"slider{id(self)}"
        canvas.create_line(x, y, x + w, y, fill="#323a78", width=10, capstyle="round", tags=(self.tag,))
        self.fill = canvas.create_line(x, y, x + w * value, y, fill=ACCENT, width=10, capstyle="round", tags=(self.tag,))
        self.knob = canvas.create_oval(0, 0, 0, 0, fill="#ffffff", outline=ACCENT, width=3, tags=(self.tag,))
        self.text = canvas.create_text(x + w + 36, y, text="", fill=TEXT, font=font(14), tags=(self.tag,))
        self._draw()
        canvas.tag_bind(self.tag, "<Button-1>", self._drag)
        canvas.tag_bind(self.tag, "<B1-Motion>", self._drag)
        canvas.tag_bind(self.tag, "<ButtonRelease-1>", lambda e: self.on_release and self.on_release())

    def _draw(self):
        kx = self.x + self.w * self.value
        self.canvas.coords(self.knob, kx - 11, self.y - 11, kx + 11, self.y + 11)
        self.canvas.coords(self.fill, self.x, self.y, kx, self.y)
        self.canvas.itemconfig(self.text, text=f"{int(round(self.value * 100))}%")

    def _drag(self, e):
        self.value = max(0.0, min(1.0, (e.x - self.x) / self.w))
        self._draw()
        self.on_change(self.value)


def draw_title(canvas, x, y, text, size=40, color=TEXT):
    canvas.create_text(x + 3, y + 4, text=text, fill="#05071a", font=font(size))
    canvas.create_text(x, y, text=text, fill=color, font=font(size))


def draw_panel(canvas, x1, y1, x2, y2, fill=PANEL, outline="#3a4390", r=18):
    return round_rect(canvas, x1, y1, x2, y2, r, fill=fill, outline=outline, width=2)


def stat_bar(canvas, x, y, w, value, color=ACCENT, h=14):
    round_rect(canvas, x, y, x + w, y + h, h / 2, fill="#101431", outline="")
    if value > 0:
        round_rect(canvas, x, y, x + max(h, w * min(1.0, value)), y + h, h / 2, fill=color, outline="")
