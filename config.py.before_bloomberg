#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""config.py — пути, константы, цвета, ANSI, JSON-хелперы."""

import ctypes
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
DIAG_DIR = BASE_DIR / "diagnostics"
HISTORY_DIR = BASE_DIR / "news_history"

SOURCES_FILE = CONFIG_DIR / "sources.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
HEALTH_FILE = DATA_DIR / "source_health.json"
FAILURE_LOG = DATA_DIR / "source_failures.log"
AI_REPORT = DIAG_DIR / "ai_report.json"
TRANSLATION_CACHE_FILE = DATA_DIR / "translation_cache.json"

DEFAULT_WIDTH = 80
DEFAULT_HEIGHT = 30
DEFAULT_TIMEOUT = 8
DEFAULT_REFRESH = 60
HISTORY_HOURS = 12
RECLASSIFY_HOURS = 2
RESTORE_HOURS = 4

RENDER_FPS = 1.0
FETCH_INTERVAL = 60
FAST_FETCH_INTERVAL = 15
FAST_PRIORITY_THRESHOLD = 95
FLASH_DURATION = 3.0

# ------------------------------------------------------------
# BREAKING NEWS board
# ------------------------------------------------------------
# Максимальное количество одновременно живых горячих тем.
HOT_TOPIC_MAX = 4
# Если по теме нет нового сообщения столько времени — слот освобождается.
HOT_TOPIC_TTL_SECONDS = 20 * 60
# Абсолютный максимум жизни одной hot-темы, даже если старые сообщения ещё есть.
HOT_TOPIC_HARD_TTL_SECONDS = 45 * 60
# Минимальная похожесть заголовков, чтобы считать их продолжением одной темы.
HOT_TOPIC_MIN_SIMILARITY = 0.60
# Сколько секунд новая/обновлённая тема визуально мигает.
HOT_NEW_FLASH_SECONDS = 8
# После этого возраста не обновлявшаяся тема визуально приглушается.
HOT_FADE_AFTER_SECONDS = 12 * 60

LANG_TOGGLE_SECONDS = 3
TRANSLATION_RATE_LIMIT = 3.0        # пауза между запросами (было 1.2)
TRANSLATION_TARGET_LANG = "ru"

# Сколько 429-х подряд считаются «сервис заблокирован»
TRANSLATION_FAIL_THRESHOLD = 3
# Сколько секунд держать сервис в «бане» после блокировки
TRANSLATION_COOLDOWN_SECONDS = 600   # 10 минут

# Языки источников, которые нужно переводить на русский
TRANSLATION_SOURCE_LANGS = ["en", "zh", "de", "fr", "es"]

# Пометки языков источников (для отображения в ленте)
LANG_TAGS = {
    "zh": "CH",
    "de": "DE",
    "fr": "FR",
    "es": "ES",
    "en": "EN",
}

# Yandex Translate API key.
# Оставьте пустым, если не хотите использовать Yandex.
YANDEX_API_KEY = ""

# Индивидуальные цвета источников (в стиле Bloomberg)
USE_SOURCE_COLORS = True


class Color:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    BLACK = "\033[30m"
    WHITE = "\033[37m"
    BRIGHT_WHITE = "\033[97m"
    GRAY = "\033[90m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_GREEN = "\033[92m"
    BG_BLUE = "\033[44m"
    BG_CYAN = "\033[46m"
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"
    BG_BLACK = "\033[40m"
    BG_GREEN = "\033[42m"
    RU_SOURCE = BG_BLUE + BRIGHT_WHITE
    WORLD_SOURCE = BG_CYAN + BLACK
    ALERT = BG_YELLOW + BLACK
    BREAKING = BG_RED + BRIGHT_WHITE


def enable_windows_ansi():
    if os.name != "nt":
        return
    try:
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


def setup_screen():
    sys.stdout.write("\033[2J\033[H\033[?25l")
    sys.stdout.flush()


def restore_screen():
    sys.stdout.write("\033[?25h" + Color.RESET + "\n")
    sys.stdout.flush()


def render_diff(previous, current):
    output = []
    cur_len = len(current)
    prev_len = len(previous)
    for i in range(cur_len):
        prev_line = previous[i] if i < prev_len else None
        cur_line = current[i]
        if prev_line != cur_line:
            output.append("\033[{};1H\033[2K".format(i + 1))
            output.append(cur_line)
    if prev_len > cur_len:
        for i in range(cur_len, prev_len):
            output.append("\033[{};1H\033[2K".format(i + 1))
    if output:
        sys.stdout.write("".join(output))
        sys.stdout.flush()
    return current


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(str(tmp), str(path))


def now_utc():
    return datetime.now(timezone.utc)