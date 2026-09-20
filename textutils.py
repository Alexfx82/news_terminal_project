#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""textutils.py — работа с текстом и рамками (с учётом wide-символов)."""

import re

try:
    from wcwidth import wcswidth
except ImportError:
    def wcswidth(s):
        return len(s)


ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def visible_width(text):
    """
    Видимая ширина строки без ANSI с учётом wide-символов.
    ⚡, ⚠, ❗, эмодзи занимают 2 клетки в терминале.
    """
    clean = ANSI_RE.sub("", str(text))
    w = wcswidth(clean)
    if w < 0:
        # wcswidth вернул -1 — есть непечатаемые, считаем поштучно
        w = 0
        for ch in clean:
            cw = wcswidth(ch)
            w += cw if cw > 0 else 1
    return w


def fit_text(text, width):
    """Обрезает строку до видимой ширины, без переноса."""
    text = str(text).replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    if width <= 0:
        return ""
    if visible_width(text) <= width:
        return text
    if width <= 3:
        return text[:width]

    # Обрезаем посимвольно, пока не влезет
    cut = text
    suffix = "..."
    limit = width - len(suffix)
    out = []
    acc = 0
    for ch in cut:
        cw = wcswidth(ch)
        if cw < 0:
            cw = 1
        if acc + cw > limit:
            break
        out.append(ch)
        acc += cw
    return "".join(out).rstrip() + suffix


def pad_visible(text, width, align="left"):
    """Фиксированная видимая ширина с учётом wide-символов."""
    text = str(text)
    diff = width - visible_width(text)
    if diff <= 0:
        return text
    if align == "right":
        return " " * diff + text
    if align == "center":
        left = diff // 2
        return " " * left + text + " " * (diff - left)
    return text + " " * diff


def box_line(content, width, left="║", right="║"):
    inner = width - 2
    content = fit_text(content, inner)
    return left + pad_visible(content, inner) + right


def top_border(width):
    return "╔" + "═" * (width - 2) + "╗"


def mid_border(width):
    return "╠" + "═" * (width - 2) + "╣"


def bottom_border(width):
    return "╚" + "═" * (width - 2) + "╝"