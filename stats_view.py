#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""stats_view.py — экран статистики внутри терминала."""

import sys
from datetime import datetime

from config import HISTORY_DIR
from textutils import box_line, top_border, mid_border, bottom_border, fit_text
from stats import load_all_items, analyze, filter_days, _verdict, _pct


def _bar(value, total, width=30):
    if total <= 0:
        return "░" * width
    filled = int(width * value / total)
    filled = max(0, min(width, filled))
    return "█" * filled + "░" * (width - filled)


def build_stats_lines(width, height):
    """Собирает кадр статистики как список строк."""
    lines = []
    lines.append(top_border(width))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines.append(box_line("NEWS TERMINAL  ::  STATISTICS   {}".format(now), width))
    lines.append(mid_border(width))

    items, files_count = load_all_items(HISTORY_DIR)

    if not items:
        lines.append(box_line("No history files found.", width))
        lines.append(box_line("", width))
        lines.append(mid_border(width))
        lines.append(box_line("Press any key to return", width))
        lines.append(bottom_border(width))
        while len(lines) < height:
            lines.append(box_line("", width))
        return lines[:height]

    lines.append(box_line(
        "Files: {}   Items: {}   Period: {} — {}".format(
            files_count,
            len(items),
            min(x["time"] for x in items).astimezone().strftime("%Y-%m-%d"),
            max(x["time"] for x in items).astimezone().strftime("%Y-%m-%d"),
        ), width))
    lines.append(mid_border(width))

    periods = [
        ("7 DAYS",    filter_days(items, 7)),
        ("30 DAYS",   filter_days(items, 30)),
        ("365 DAYS",  filter_days(items, 365)),
        ("ALL TIME",  items),
    ]

    for label, subset in periods:
        st = analyze(subset)
        if st["total"] == 0:
            lines.append(box_line("{}: no data".format(label), width))
            continue

        total = st["total"]
        neg = st["neg_items"]
        pos = st["pos_items"]
        neu = st["neutral"]

        lines.append(box_line(
            "── {}  (items: {}) ──".format(label, total), width))

        neg_line = "   ⚠ NEGATIVE  {:>5}  {:>6}  {}".format(
            neg, _pct(neg, total), _bar(neg, total))
        lines.append(box_line(neg_line, width))

        pos_line = "   ☺ POSITIVE  {:>5}  {:>6}  {}".format(
            pos, _pct(pos, total), _bar(pos, total))
        lines.append(box_line(pos_line, width))

        neu_line = "   · NEUTRAL   {:>5}  {:>6}  {}".format(
            neu, _pct(neu, total), _bar(neu, total))
        lines.append(box_line(neu_line, width))

        verdict = _verdict(neg, pos, total)
        lines.append(box_line("   → {}".format(verdict), width))
        lines.append(box_line("", width))

    # Топ-5 негативных ключевых слов за 30 дней
    st30 = analyze(filter_days(items, 30))
    if st30["neg_keywords"]:
        lines.append(box_line("── TOP NEGATIVE (30d) ──", width))
        for kw, cnt in st30["neg_keywords"][:5]:
            lines.append(box_line("   {:24} {:>5}".format(kw, cnt), width))
        lines.append(box_line("", width))

    if st30["pos_keywords"]:
        lines.append(box_line("── TOP POSITIVE (30d) ──", width))
        for kw, cnt in st30["pos_keywords"][:5]:
            lines.append(box_line("   {:24} {:>5}".format(kw, cnt), width))
        lines.append(box_line("", width))

    lines.append(mid_border(width))
    lines.append(box_line("[R] refresh   [Q]/any key — back to live", width))
    lines.append(bottom_border(width))

    while len(lines) < height:
        lines.append(box_line("", width))
    if len(lines) > height:
        lines = lines[:height]
    return lines


def show_stats_screen(width, height):
    """Показывает экран статистики, ждёт нажатия клавиши."""
    from config import render_diff, restore_screen

    restore_screen()
    sys.stdout.write("\033[2J\033[H\033[?25l")
    sys.stdout.flush()

    previous = []
    lines = build_stats_lines(width, height)
    previous = render_diff(previous, lines)

    # Ждём клавишу
    import time
    from live import read_key
    while True:
        key = read_key()
        if key is None:
            time.sleep(0.1)
            continue
        if key == "r":
            lines = build_stats_lines(width, height)
            previous = render_diff(previous, lines)
            continue
        break

    sys.stdout.write("\033[2J\033[H\033[?25l")
    sys.stdout.flush()