#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Установщик NEWS TERMINAL.
Создаёт структуру проекта, пишет все модули и упаковывает в ZIP.
"""

import json
import os
import sys
import zipfile
from pathlib import Path


# ============================================================
#  Файлы проекта
# ============================================================

FILES = {}

# ---------------- requirements.txt ----------------
FILES["requirements.txt"] = """feedparser>=6.0,<7
deep-translator>=1.11
"""

# ---------------- README.md ----------------
FILES["README.md"] = """# NEWS TERMINAL

Модульный новостной терминал для Raspberry Pi Zero / Windows.

## Установка

    pip install -r requirements.txt

## Запуск

    python main.py
    python main.py --diagnostics
    python main.py --once
    python main.py --no-fresh-scan
    python main.py --source rbc

## Клавиши в live-режиме

| Клавиша | Действие |
|---|---|
| S | Меню настроек |
| D | Пересканировать источники |
| R | Мгновенный fetch |
| Q | Выход |

## Модули

| Модуль | Ответственность |
|---|---|
| config | пути, константы, Color, ANSI |
| textutils | fit/pad/box/borders |
| storage | settings, sources, history I/O |
| news | ключи, классификация, dedup |
| sources | диагностика RSS |
| fetcher | фоновый поток |
| translator | перевод EN-RU с кэшем |
| render | frame builder |
| menu | интерактивное меню |
| live | главный цикл |
| main | entry point |
"""

# ---------------- config.py ----------------
FILES["config.py"] = '''#!/usr/bin/env python3
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
FLASH_DURATION = 3.0

LANG_TOGGLE_SECONDS = 5
TRANSLATION_RATE_LIMIT = 1.2
TRANSLATION_TARGET_LANG = "ru"


class Color:
    RESET = "\\033[0m"
    BOLD = "\\033[1m"
    DIM = "\\033[2m"
    BLACK = "\\033[30m"
    WHITE = "\\033[37m"
    BRIGHT_WHITE = "\\033[97m"
    GRAY = "\\033[90m"
    BRIGHT_CYAN = "\\033[96m"
    BRIGHT_YELLOW = "\\033[93m"
    BRIGHT_GREEN = "\\033[92m"
    BG_BLUE = "\\033[44m"
    BG_CYAN = "\\033[46m"
    BG_RED = "\\033[41m"
    BG_YELLOW = "\\033[43m"
    BG_BLACK = "\\033[40m"
    BG_GREEN = "\\033[42m"
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
    sys.stdout.write("\\033[2J\\033[H\\033[?25l")
    sys.stdout.flush()


def restore_screen():
    sys.stdout.write("\\033[?25h" + Color.RESET + "\\n")
    sys.stdout.flush()


def render_diff(previous, current):
    output = []
    cur_len = len(current)
    prev_len = len(previous)
    for i in range(cur_len):
        prev_line = previous[i] if i < prev_len else None
        cur_line = current[i]
        if prev_line != cur_line:
            output.append("\\033[{};1H\\033[2K".format(i + 1))
            output.append(cur_line)
    if prev_len > cur_len:
        for i in range(cur_len, prev_len):
            output.append("\\033[{};1H\\033[2K".format(i + 1))
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
'''

# ---------------- textutils.py ----------------
FILES["textutils.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""textutils.py — работа с текстом и рамками."""

import re


ANSI_RE = re.compile(r"\\x1b\\[[0-9;?]*[ -/]*[@-~]")


def visible_width(text):
    return len(ANSI_RE.sub("", str(text)))


def fit_text(text, width):
    text = str(text).replace("\\r", " ").replace("\\n", " ")
    text = " ".join(text.split())
    if width <= 0:
        return ""
    if visible_width(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    cut = text[:width - 3].rstrip()
    if " " in cut:
        candidate = cut.rsplit(" ", 1)[0]
        if len(candidate) >= max(1, width // 2):
            cut = candidate
    return cut + "..."


def pad_visible(text, width, align="left"):
    text = str(text)
    diff = width - visible_width(text)
    if diff <= 0:
        return text[:width]
    if align == "right":
        return " " * diff + text
    if align == "center":
        left = diff // 2
        return " " * left + text + " " * (diff - left)
    return text + " " * diff


def box_line(content, width, left="\\u2551", right="\\u2551"):
    inner = width - 2
    content = fit_text(content, inner)
    return left + pad_visible(content, inner) + right


def top_border(width):
    return "\\u2554" + "\\u2550" * (width - 2) + "\\u2557"


def mid_border(width):
    return "\\u2560" + "\\u2550" * (width - 2) + "\\u2563"


def bottom_border(width):
    return "\\u255a" + "\\u2550" * (width - 2) + "\\u255d"
'''

# ---------------- storage.py ----------------
FILES["storage.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""storage.py — settings, sources, history I/O."""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import (
    SETTINGS_FILE, SOURCES_FILE, HISTORY_DIR,
    DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_REFRESH,
    RESTORE_HOURS, load_json, now_utc,
)


def load_settings():
    data = load_json(SETTINGS_FILE, {})
    display = data.get("display", {})
    return {
        "width": int(display.get("width", DEFAULT_WIDTH)),
        "auto_detect": bool(display.get("auto_detect_terminal_size", True)),
        "refresh": int(data.get("app", {}).get("refresh_seconds", DEFAULT_REFRESH)),
    }


def get_terminal_size(settings):
    try:
        size = shutil.get_terminal_size((DEFAULT_WIDTH, DEFAULT_HEIGHT))
        cols, lines = size.columns, size.lines
    except Exception:
        cols, lines = DEFAULT_WIDTH, DEFAULT_HEIGHT
    if settings.get("auto_detect", True) and cols >= 50:
        width = min(cols, 160)
    else:
        width = max(50, settings.get("width", DEFAULT_WIDTH))
    height = max(20, lines - 1)
    return width, height


def load_sources():
    data = load_json(SOURCES_FILE, {"sources": []})
    return data.get("sources", [])


def _history_file_for_date(d):
    return HISTORY_DIR / "news_{}.jsonl".format(d.strftime("%Y-%m-%d"))


def serialize_item(item):
    return {
        "time": item["time"].isoformat(),
        "source_id": item["source_id"],
        "source": item["source"],
        "title": item["title"],
        "title_ru": item.get("title_ru"),
        "region": item["region"],
        "language": item["language"],
        "priority": item["priority"],
        "level": item["level"],
        "topic_key": item["topic_key"],
        "key": item["key"],
    }


def deserialize_item(obj):
    try:
        obj["time"] = datetime.fromisoformat(obj["time"])
    except Exception:
        return None
    if obj["time"].tzinfo is None:
        obj["time"] = obj["time"].replace(tzinfo=timezone.utc)
    obj["flash_until"] = 0.0
    obj.setdefault("title_ru", None)
    return obj


class HistoryWriter:
    def __init__(self, folder=HISTORY_DIR):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.current_date = None
        self.file = None
        self._open_for_date(datetime.now().date())

    def _open_for_date(self, d):
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass
        self.current_date = d
        self.file = open(_history_file_for_date(d), "a", encoding="utf-8")

    def write(self, item):
        today = datetime.now().date()
        if today != self.current_date:
            self._open_for_date(today)
        try:
            obj = serialize_item(item)
            self.file.write(json.dumps(obj, ensure_ascii=False) + "\\n")
            self.file.flush()
        except Exception:
            pass

    def write_many(self, items):
        for it in items:
            self.write(it)

    def close(self):
        if self.file:
            try:
                self.file.close()
            except Exception:
                pass
            self.file = None


def load_history_from_file(path, hours=RESTORE_HOURS):
    path = Path(path)
    if not path.exists():
        return []
    cutoff = now_utc() - timedelta(hours=hours)
    items = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    item = deserialize_item(obj)
                    if item is None or item["time"] < cutoff:
                        continue
                    items.append(item)
                except Exception:
                    continue
    except Exception:
        return []
    seen = set()
    unique = []
    for it in items:
        k = it.get("key")
        if not k or k in seen:
            continue
        seen.add(k)
        unique.append(it)
    return unique


def history_file_for_today():
    return _history_file_for_date(datetime.now().date())
'''

# ---------------- news.py ----------------
FILES["news.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""news.py — ключи, классификация, dedup."""

import hashlib
import re
import time
from datetime import datetime, timezone, timedelta

import feedparser

from config import RECLASSIFY_HOURS, FLASH_DURATION, now_utc


def parse_entry_time(entry):
    value = entry.get("published_parsed") or entry.get("updated_parsed")
    if value:
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if raw:
            try:
                parsed = feedparser._parse_date(raw)
                if parsed:
                    return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return now_utc()


def normalize_title(title):
    title = title.lower()
    title = re.sub(r"https?://\\S+", " ", title)
    title = re.sub(r"[^\\w\\sа-яё]", " ", title, flags=re.UNICODE)
    words = [w for w in title.split() if len(w) > 2]
    return " ".join(words[:18])


def source_news_key(source_id, title):
    normalized = normalize_title(title)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return source_id + ":" + digest


def topic_key(title):
    normalized = normalize_title(title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


STRONG_MARKERS = (
    "СРОЧНО", "МОЛНИЯ", "BREAKING", "URGENT NEWS",
    "FLASH", "JUST IN", "ЭКСТРЕННО",
    "ВЗРЫВ", "ТЕРАКТ", "ПОЖАР", "ЗЕМЛЕТРЯСЕНИ", "ЦУНАМИ",
    "ЯДЕРН", "РАДИАЦИ", "ХИМАТАК", "ЭВАКУАЦ",
    "EARTHQUAKE", "TSUNAMI", "EXPLOSION", "MISSILE",
    "NUCLEAR", "CHEMICAL ATTACK", "EVACUATION",
    "ATTACK", "STRIKE", "WAR", "INVASION",
    "УБИЙСТВО", "ПОКУШЕНИ", "СМЕРТЬ", "ПОГИБ",
    "АВАРИЯ", "КАТАСТРОФ", "КРУШЕНИ",
)

ALERT_MARKERS = (
    "ВНИМАНИЕ", "ALERT", "WARNING", "EMERGENCY",
    "ОПАСНОСТ", "УГРОЗА", "КРИЗИС", "САНКЦИ",
    "ЗАПРЕТ", "ОГРАНИЧЕН", "ПРЕДУПРЕЖД",
)

EMOJI_BREAKING = ("⚡", "❗", "🚨")
EMOJI_ALERT = ("⚠", "🔥")


def classify_item(item, source_count_for_topic, now):
    title = item["title"]
    upper = title.upper()
    score = 0
    if any(k in upper for k in STRONG_MARKERS):
        score += 100
    if any(k in upper for k in ALERT_MARKERS):
        score += 50
    if any(e in title for e in EMOJI_BREAKING):
        score += 80
    if any(e in title for e in EMOJI_ALERT):
        score += 40
    letters = [c for c in title if c.isalpha()]
    if len(letters) > 15:
        ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if ratio > 0.6:
            score += 30
    score += item.get("priority", 50) // 10
    age = (now - item["time"]).total_seconds()
    if age < 300:
        score += 50
    elif age < 900:
        score += 30
    elif age < 3600:
        score += 10
    if source_count_for_topic >= 5:
        score += 80
    elif source_count_for_topic >= 3:
        score += 50
    elif source_count_for_topic >= 2:
        score += 20
    if score >= 120:
        return "BREAKING"
    if score >= 60:
        return "ALERT"
    return "NORMAL"


def reclassify_recent(history, hours=RECLASSIFY_HOURS):
    now = now_utc()
    cutoff = now - timedelta(hours=hours)
    topic_sources = {}
    for item in history:
        if item["time"] < cutoff:
            continue
        tk = item["topic_key"]
        topic_sources.setdefault(tk, set()).add(item["source_id"])
    for item in history:
        if item["time"] < cutoff:
            continue
        count = len(topic_sources.get(item["topic_key"], set()))
        new_level = classify_item(item, count, now)
        if new_level != item["level"]:
            item["level"] = new_level
            if new_level == "BREAKING":
                item["flash_until"] = time.time() + FLASH_DURATION


def dedup_by_topic(items):
    by_topic = {}
    for item in items:
        tk = item["topic_key"]
        existing = by_topic.get(tk)
        if existing is None:
            copy = dict(item)
            copy["sources"] = [item["source"]]
            by_topic[tk] = copy
        else:
            if item["source"] not in existing["sources"]:
                existing["sources"].append(item["source"])
            if (item["priority"] > existing["priority"] or
                    (item["priority"] == existing["priority"] and
                     item["time"] > existing["time"])):
                sources_backup = existing["sources"]
                new_copy = dict(item)
                new_copy["sources"] = sources_backup
                by_topic[tk] = new_copy
    return list(by_topic.values())
'''

# ---------------- sources.py ----------------
FILES["sources.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sources.py — диагностика RSS-источников."""

import platform
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import feedparser

from config import (
    DATA_DIR, HEALTH_FILE, FAILURE_LOG, AI_REPORT, SOURCES_FILE,
    DEFAULT_TIMEOUT, save_json, now_utc,
)
from textutils import fit_text
from news import parse_entry_time


def fetch_one_source(source, timeout):
    started = time.monotonic()
    result = {
        "id": source["id"], "name": source["name"], "url": source["url"],
        "language": source.get("language", ""),
        "region": source.get("region", "WORLD"),
        "priority": source.get("priority", 50),
        "status": "failed", "http_status": None, "latency_ms": None,
        "items": 0, "latest": None, "error": None, "parser": None,
    }
    try:
        parsed = feedparser.parse(source["url"], request_headers={
            "User-Agent": "NewsTerminal/1.0 RSS reader"
        })
        result["latency_ms"] = round((time.monotonic() - started) * 1000)
        status = getattr(parsed, "status", None)
        result["http_status"] = status
        bozo = getattr(parsed, "bozo", 0)
        entries = list(getattr(parsed, "entries", []) or [])
        if status is not None and status >= 400:
            result["error"] = "HTTP {}".format(status)
            return result
        if not entries:
            result["error"] = "EMPTY_FEED"
            return result
        valid = [e.get("title", "").strip() for e in entries if e.get("title")]
        if not valid:
            result["error"] = "NO_TITLES"
            return result
        result["items"] = len(valid)
        result["parser"] = "RSS/Atom"
        result["latest"] = parse_entry_time(entries[0]).isoformat()
        if bozo:
            result["warning"] = "BOZO_XML_BUT_USABLE"
        result["status"] = "healthy"
        return result
    except Exception as exc:
        result["latency_ms"] = round((time.monotonic() - started) * 1000)
        result["error"] = "{}: {}".format(type(exc).__name__, str(exc)[:180])
        return result


def write_failure(result):
    if result.get("status") == "healthy":
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = "{} | {} | {} | {} | {} ms | {}\\n".format(
        now_utc().isoformat(),
        result.get("id", ""), result.get("name", ""),
        result.get("error", "UNKNOWN"), result.get("latency_ms", ""),
        result.get("url", "")
    )
    with open(FAILURE_LOG, "a", encoding="utf-8") as f:
        f.write(line)


def scan_sources(sources, timeout=DEFAULT_TIMEOUT, width=80, show_progress=True):
    total = len(sources)
    workers = min(8, max(1, total))
    results = []
    if show_progress:
        sys.stdout.write(
            "NEWS TERMINAL :: diagnostics\\n"
            "Testing {} sources with {} workers...\\n".format(total, workers)
        )
        sys.stdout.flush()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(fetch_one_source, src, timeout): src for src in sources
        }
        done = 0
        for future in as_completed(future_map):
            done += 1
            src = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "id": src["id"], "name": src["name"], "url": src["url"],
                    "language": src.get("language", ""),
                    "region": src.get("region", "WORLD"),
                    "priority": src.get("priority", 50),
                    "status": "failed", "error": repr(exc),
                    "http_status": None, "latency_ms": None,
                    "items": 0, "latest": None,
                }
            results.append(result)
            if result.get("status") != "healthy":
                write_failure(result)
            if show_progress:
                percent = int(done * 100 / max(1, total))
                bar_w = max(10, width - 46)
                filled = int(bar_w * percent / 100)
                bar = "█" * filled + "░" * (bar_w - filled)
                tag = "OK  " if result.get("status") == "healthy" else "FAIL"
                name = fit_text(result.get("name", ""), 28)
                sys.stdout.write("\\r\\033[K{} {:3d}%  {}  {}".format(
                    bar, percent, tag, name))
                sys.stdout.flush()
    if show_progress:
        sys.stdout.write("\\n")
        sys.stdout.flush()
    results.sort(key=lambda x: x.get("id", ""))
    healthy = [r for r in results if r.get("status") == "healthy"]
    failed = [r for r in results if r.get("status") != "healthy"]
    save_json(HEALTH_FILE, {
        "generated": now_utc().isoformat(),
        "configured": len(sources),
        "healthy": len(healthy),
        "failed": len(failed),
        "results": results,
    })
    ru = sum(1 for r in healthy if r.get("region") == "RU")
    world = sum(1 for r in healthy if r.get("region") != "RU")
    save_json(AI_REPORT, {
        "report_version": 1,
        "generated": now_utc().isoformat(),
        "device": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "hostname": socket.gethostname(),
        },
        "configuration": {
            "source_database": str(SOURCES_FILE),
            "configured": len(sources),
            "timeout_seconds": timeout,
        },
        "summary": {
            "healthy": len(healthy),
            "failed": len(failed),
            "ru_healthy": ru,
            "world_healthy": world,
        },
        "failed_sources": failed,
        "healthy_sources": healthy,
    })
    if show_progress:
        print()
        print("DIAGNOSTICS COMPLETE")
        print("  Configured : {}".format(len(sources)))
        print("  Healthy    : {}".format(len(healthy)))
        print("  Failed     : {}".format(len(failed)))
        print("  RU healthy : {}".format(ru))
        print("  WORLD      : {}".format(world))
        print("  AI report  : diagnostics/ai_report.json")
        print("  Failures   : data/source_failures.log")
        print()
        time.sleep(2)
    return results
'''

# ---------------- fetcher.py ----------------
FILES["fetcher.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetcher.py — фоновый поток fetch."""

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import feedparser

from config import HISTORY_HOURS, DEFAULT_TIMEOUT, now_utc
from news import parse_entry_time, source_news_key, topic_key


def fetch_source_news(source, cutoff, timeout=DEFAULT_TIMEOUT):
    items = []
    try:
        parsed = feedparser.parse(
            source["url"],
            request_headers={"User-Agent": "NewsTerminal/1.0 RSS reader"}
        )
        for entry in list(parsed.entries)[:10]:
            title = " ".join(str(entry.get("title", "")).split())
            if not title:
                continue
            published = parse_entry_time(entry)
            if published < cutoff:
                continue
            items.append({
                "source_id": source["id"],
                "source": source["name"],
                "title": title,
                "title_ru": None,
                "time": published,
                "region": source.get("region", "WORLD"),
                "language": source.get("language", "en"),
                "priority": int(source.get("priority", 50)),
                "level": "NORMAL",
                "flash_until": 0.0,
                "topic_key": topic_key(title),
            })
    except Exception:
        pass
    return items


def fetch_news_parallel(sources, health_map, seen_keys, stop_event=None):
    cutoff = now_utc() - timedelta(hours=HISTORY_HOURS)
    active = [
        s for s in sources
        if s.get("enabled", True) and
        health_map.get(s["id"], {}).get("status") == "healthy"
    ]
    if not active:
        return []
    all_items = []
    workers = min(8, max(1, len(active)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(fetch_source_news, src, cutoff): src for src in active
        }
        for future in as_completed(future_map):
            if stop_event is not None and stop_event.is_set():
                break
            try:
                all_items.extend(future.result())
            except Exception:
                pass
    new_items = []
    for item in all_items:
        key = source_news_key(item["source_id"], item["title"])
        if key in seen_keys:
            continue
        seen_keys.add(key)
        item["key"] = key
        new_items.append(item)
    return new_items


class Fetcher:
    def __init__(self, sources, health_map, interval):
        self.sources = sources
        self.health_map = health_map
        self.interval = interval
        self.queue = queue.Queue()
        self.seen_keys = set()
        self.stop_event = threading.Event()
        self.thread = None
        self.fetching = False
        self.last_fetch = 0.0

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _loop(self):
        while not self.stop_event.is_set():
            self.fetching = True
            try:
                items = fetch_news_parallel(
                    self.sources, self.health_map,
                    self.seen_keys, self.stop_event
                )
                for item in items:
                    self.queue.put(item)
            except Exception:
                pass
            self.fetching = False
            self.last_fetch = time.time()
            self.stop_event.wait(self.interval)

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.queue.get_nowait())
            except queue.Empty:
                break
        return out

    def seconds_until_next(self):
        if self.fetching:
            return 0
        elapsed = time.time() - self.last_fetch
        return max(0, int(self.interval - elapsed))
'''

# ---------------- translator.py ----------------
FILES["translator.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translator.py — асинхронный перевод EN-RU с кэшем."""

import hashlib
import queue
import threading
import time
from pathlib import Path

from config import (
    TRANSLATION_CACHE_FILE, TRANSLATION_RATE_LIMIT, TRANSLATION_TARGET_LANG,
    load_json, save_json,
)


class TranslationService:
    def __init__(self, cache_file=TRANSLATION_CACHE_FILE,
                 rate_limit=TRANSLATION_RATE_LIMIT):
        self.cache_file = Path(cache_file)
        self.rate_limit = rate_limit
        self.cache = load_json(self.cache_file, {})
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.thread = None
        self._pending = set()
        self._dirty = False
        self._last_save = 0.0
        self._translator = None

    def _get_translator(self):
        if self._translator is None:
            try:
                from deep_translator import GoogleTranslator
                self._translator = GoogleTranslator(
                    source="en", target=TRANSLATION_TARGET_LANG
                )
            except Exception:
                self._translator = False
        return self._translator

    @staticmethod
    def _key(text):
        return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]

    def get(self, text):
        if not text:
            return None
        with self.lock:
            return self.cache.get(self._key(text))

    def request(self, text):
        if not text:
            return
        key = self._key(text)
        with self.lock:
            if key in self.cache or key in self._pending:
                return
            self._pending.add(key)
        self.queue.put((key, text))

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self._save(force=True)

    def _loop(self):
        translator = self._get_translator()
        if translator is False:
            return
        while not self.stop_event.is_set():
            try:
                key, text = self.queue.get(timeout=0.5)
            except queue.Empty:
                self._save()
                continue
            try:
                translated = translator.translate(text[:4500])
                if translated:
                    with self.lock:
                        self.cache[key] = translated
                        self._dirty = True
            except Exception:
                pass
            finally:
                with self.lock:
                    self._pending.discard(key)
            self.stop_event.wait(self.rate_limit)

    def _save(self, force=False):
        now = time.time()
        if not force and (not self._dirty or now - self._last_save < 30):
            return
        with self.lock:
            data = dict(self.cache)
            self._dirty = False
            self._last_save = now
        try:
            save_json(self.cache_file, data)
        except Exception:
            pass
'''

# ---------------- render.py ----------------
FILES["render.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py — сборка кадра и формат строк."""

import time
from datetime import datetime, timedelta

from config import Color, HISTORY_HOURS, now_utc
from textutils import box_line, top_border, mid_border, bottom_border, \\
    fit_text, pad_visible, visible_width
from news import dedup_by_topic


def pick_title(item, show_translation):
    if show_translation and item.get("title_ru"):
        return item["title_ru"]
    return item["title"]


def format_breaking_line(item, width, show_translation=False):
    sources = item.get("sources", [item["source"]])
    if len(sources) == 1:
        src_tag = "[{}]".format(fit_text(sources[0].upper(), 12))
    else:
        first = fit_text(sources[0].upper(), 8)
        src_tag = "[{}+{}]".format(first, len(sources) - 1)
    title = pick_title(item, show_translation)
    title = fit_text(title, max(10, width - 18 - len(src_tag)))
    text = "⚡ BREAKING {} {}".format(src_tag, title)
    return box_line(text, width)


def format_news_line(item, width, show_translation=False):
    inner = width - 2
    ts = item["time"].astimezone().strftime("%H:%M")
    source = fit_text(item["source"].upper(), 12)
    title = fit_text(pick_title(item, show_translation), max(10, inner - 22))
    prefix = "{}  ".format(ts)
    if item["level"] == "BREAKING":
        return Color.BREAKING + box_line("⚡ BREAKING  " + title, width) + Color.RESET
    if item["level"] == "ALERT":
        return Color.ALERT + box_line(
            "⚠ ALERT     {}  {}".format(source, title), width) + Color.RESET
    source_text = fit_text("[{}]".format(source), 14)
    base = prefix + source_text + " " + title
    base = fit_text(base, inner)
    colored_source = (
        Color.RU_SOURCE if item["region"] == "RU" else Color.WORLD_SOURCE
    ) + pad_visible(source_text, 14) + Color.RESET
    line = "║" + pad_visible(prefix, 8) + colored_source + " " + pad_visible(
        fit_text(title, max(1, inner - 8 - 15)), max(1, inner - 8 - 15)
    ) + "║"
    if visible_width(line) != width:
        return box_line(base, width)
    return line


def render_ticker(unique_items, width, offset, show_translation=False):
    breaking = [x for x in unique_items if x["level"] == "BREAKING"]
    if not breaking:
        alert_items = [x for x in unique_items if x["level"] == "ALERT"]
        if not alert_items:
            return box_line("", width)
        text = "     ⚠     ".join(
            pick_title(x, show_translation) for x in alert_items[:6])
    else:
        text = "     ⚡     ".join(
            pick_title(x, show_translation) for x in breaking[:6])
    text = text + "     " + text
    inner = width - 2
    segment = text[offset % max(1, len(text)):][:inner]
    return box_line(segment, width)


def trim_history(history):
    cutoff = now_utc() - timedelta(hours=HISTORY_HOURS)
    while history and history[-1]["time"] < cutoff:
        history.pop()
    return history


def build_frame_lines(history, width, height, source_health,
                      last_update, ticker_offset, fetch_countdown,
                      fetching, show_translation=False):
    lines = []
    lines.append(top_border(width))
    now = datetime.now().strftime("%d %b %Y  %H:%M:%S")
    live_dot = "● LIVE" if int(time.time()) % 2 == 0 else "○ LIVE"
    lang_tag = "RU" if show_translation else "EN"
    lines.append(box_line(
        "NEWS TERMINAL   {}   {}   LANG:{}".format(now, live_dot, lang_tag),
        width))
    unique_items = dedup_by_topic(list(history))
    total = len(unique_items)
    breaking = sum(1 for x in unique_items if x["level"] == "BREAKING")
    alert = sum(1 for x in unique_items if x["level"] == "ALERT")
    ru = sum(1 for x in unique_items if x["region"] == "RU")
    world = total - ru
    healthy = sum(1 for x in source_health.values()
                  if x.get("status") == "healthy")
    stats = "SRC {}/{}  TOTAL {}  ⚡ {}  ⚠ {}  RU {}  WORLD {}".format(
        healthy, len(source_health), total, breaking, alert, ru, world)
    lines.append(box_line(stats, width))
    lines.append(mid_border(width))
    breaking_items = sorted(
        [x for x in unique_items if x["level"] == "BREAKING"],
        key=lambda x: x["time"], reverse=True)[:3]
    for item in breaking_items:
        flash = item.get("flash_until", 0) > time.time()
        if flash:
            blink = int(time.time() * 2) % 2 == 0
            color = Color.BREAKING if blink else Color.ALERT
        else:
            color = Color.BREAKING
        lines.append(color + format_breaking_line(
            item, width, show_translation) + Color.RESET)
    if breaking_items:
        lines.append(mid_border(width))
    used_top = len(lines)
    reserved_bottom = 6
    news_slots = max(0, height - used_top - reserved_bottom)
    breaking_keys = {x["key"] for x in breaking_items}
    stream = [x for x in unique_items if x["key"] not in breaking_keys]
    stream.sort(key=lambda x: x["time"], reverse=True)
    for item in stream[:news_slots]:
        lines.append(format_news_line(item, width, show_translation))
    used = min(news_slots, len(stream))
    while used < news_slots:
        lines.append(box_line("", width))
        used += 1
    lines.append(mid_border(width))
    lines.append(render_ticker(unique_items, width, ticker_offset,
                                show_translation=show_translation))
    lines.append(mid_border(width))
    if fetching:
        footer = "FETCHING...   LAST {}   [S]ETTINGS  [R]EFRESH  [Q]UIT".format(last_update)
    else:
        footer = "LAST {}   NEXT {}s   [S]ETTINGS  [D]IAG  [R]EFRESH  [Q]UIT".format(
            last_update, fetch_countdown)
    lines.append(box_line(footer, width))
    lines.append(bottom_border(width))
    while len(lines) < height:
        lines.append(box_line("", width))
    if len(lines) > height:
        lines = lines[:height]
    return lines
'''

# ---------------- menu.py ----------------
FILES["menu.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""menu.py — интерактивное меню настроек."""

import os
import shutil
import subprocess
import sys

from config import HEALTH_FILE, load_json
from textutils import box_line, top_border, mid_border, bottom_border


def clear_and_show_cursor():
    sys.stdout.write("\\033[2J\\033[H\\033[?25h")
    sys.stdout.flush()


def draw_menu_screen(title, lines, width):
    out = []
    out.append(top_border(width))
    out.append(box_line("NEWS TERMINAL  ::  " + title, width))
    out.append(mid_border(width))
    for line in lines:
        out.append(box_line(line, width))
    out.append(bottom_border(width))
    sys.stdout.write("\\n".join(out))
    sys.stdout.flush()


def draw_wifi_status(width):
    if os.name == "nt":
        print("Windows test mode: Wi-Fi не изменяется.")
        print("На Raspberry Pi используется nmcli.")
        return
    nmcli = shutil.which("nmcli")
    if not nmcli:
        print("nmcli not found.")
        return
    try:
        subprocess.call([nmcli, "dev", "status"])
        print()
        subprocess.call([nmcli, "-g", "IP4.ADDRESS", "device", "show", "wlan0"])
    except Exception as exc:
        print("Wi-Fi error:", exc)


def draw_wifi_scan(width):
    if os.name == "nt":
        print("Windows test mode: scan недоступен.")
        return
    nmcli = shutil.which("nmcli")
    if not nmcli:
        print("nmcli not found.")
        return
    try:
        subprocess.call([nmcli, "dev", "wifi", "list"])
    except Exception as exc:
        print("Wi-Fi error:", exc)


def show_source_health(width):
    health = load_json(HEALTH_FILE, {})
    results = health.get("results", [])
    if not results:
        print("Health file empty:", HEALTH_FILE)
        return
    healthy = [r for r in results if r.get("status") == "healthy"]
    failed = [r for r in results if r.get("status") != "healthy"]
    print("HEALTHY: {}   FAILED: {}   TOTAL: {}".format(
        len(healthy), len(failed), len(results)))
    print()
    print("--- FAILED ---")
    for r in failed[:40]:
        print("  {:24} {:14} {}".format(
            r.get("id", "")[:24],
            r.get("error", "")[:14],
            r.get("name", "")[:30]))


def settings_menu(width, height, sources, health_map):
    while True:
        clear_and_show_cursor()
        lines = [
            "1. Wi-Fi status / IP",
            "2. Wi-Fi scan networks",
            "3. Diagnostics: re-scan sources",
            "4. Show source health",
            "5. Clear news buffer (только экран)",
            "6. Back to live",
            "7. Quit program",
        ]
        draw_menu_screen("SETTINGS", lines, width)
        print()
        try:
            choice = input("Select (1-7): ").strip()
        except (KeyboardInterrupt, EOFError):
            return "back"
        if choice == "1":
            clear_and_show_cursor()
            draw_menu_screen("WIFI STATUS", [], width)
            print()
            draw_wifi_status(width)
            print()
            input("Press Enter to return...")
        elif choice == "2":
            clear_and_show_cursor()
            draw_menu_screen("WIFI SCAN", [], width)
            print()
            draw_wifi_scan(width)
            print()
            input("Press Enter to return...")
        elif choice == "3":
            return "rescan"
        elif choice == "4":
            clear_and_show_cursor()
            draw_menu_screen("SOURCE HEALTH", [], width)
            print()
            show_source_health(width)
            print()
            input("Press Enter to return...")
        elif choice == "5":
            return "clear_buffer"
        elif choice == "6":
            return "back"
        elif choice == "7":
            return "quit"
        else:
            continue
'''

# ---------------- live.py ----------------
FILES["live.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""live.py — главный цикл."""

import os
import sys
import time
from collections import deque
from datetime import datetime

from config import (
    RENDER_FPS, DEFAULT_TIMEOUT, HEALTH_FILE, LANG_TOGGLE_SECONDS,
    setup_screen, restore_screen, render_diff, load_json,
)
from storage import history_file_for_today, load_history_from_file
from news import reclassify_recent, RECLASSIFY_HOURS
from fetcher import Fetcher
from translator import TranslationService
from render import build_frame_lines, trim_history
from menu import settings_menu
from sources import scan_sources


def read_key():
    try:
        if os.name == "nt":
            import msvcrt
            if msvcrt.kbhit():
                ch = msvcrt.getch()
                try:
                    return ch.decode("utf-8", errors="ignore").lower()
                except Exception:
                    return None
            return None
        else:
            import select
            if select.select([sys.stdin], [], [], 0)[0]:
                ch = sys.stdin.read(1)
                if ch:
                    return ch.lower()
            return None
    except Exception:
        return None


def run_live(sources, health_map, width, height, settings,
             history_writer, once=False):
    history = deque(maxlen=2000)
    ticker_offset = 0
    last_update = "--:--:--"
    reclassify_tick = 0

    today_file = history_file_for_today()
    restored = load_history_from_file(today_file)
    for item in restored:
        history.append(item)
    if restored:
        reclassify_recent(history, RECLASSIFY_HOURS)

    interval = int(settings.get("refresh", 60))
    fetcher = Fetcher(sources, health_map, interval)

    for item in restored:
        k = item.get("key")
        if k:
            fetcher.seen_keys.add(k)

    translator = TranslationService()
    translator.start()
    for item in restored:
        if item.get("language") == "en":
            cached = translator.get(item["title"])
            if cached:
                item["title_ru"] = cached

    fetcher.start()
    setup_screen()
    previous = []

    try:
        while True:
            new_items = fetcher.drain()
            if new_items:
                existing_keys = {x.get("key") for x in history if x.get("key")}
                filtered = []
                for item in new_items:
                    k = item.get("key")
                    if k and k in existing_keys:
                        continue
                    if item.get("language") == "en":
                        cached = translator.get(item["title"])
                        if cached:
                            item["title_ru"] = cached
                    history.append(item)
                    if k:
                        existing_keys.add(k)
                    filtered.append(item)
                trim_history(history)
                if filtered:
                    history_writer.write_many(filtered)
                    last_update = datetime.now().strftime("%H:%M:%S")

            reclassify_tick += 1
            if reclassify_tick % 3 == 0:
                reclassify_recent(history, RECLASSIFY_HOURS)

            for item in history:
                if item.get("language") == "en" and not item.get("title_ru"):
                    cached = translator.get(item["title"])
                    if cached:
                        item["title_ru"] = cached
                    else:
                        translator.request(item["title"])

            show_translation = int(time.time() / LANG_TOGGLE_SECONDS) % 2 == 1

            frame = build_frame_lines(
                history, width, height, health_map,
                last_update, ticker_offset,
                fetcher.seconds_until_next(),
                fetcher.fetching,
                show_translation=show_translation,
            )
            previous = render_diff(previous, frame)
            ticker_offset += 2

            if once:
                time.sleep(2)
                break

            key = read_key()
            if key == "q":
                break
            elif key == "s":
                restore_screen()
                action = settings_menu(width, height, sources, health_map)
                if action == "quit":
                    return "quit"
                elif action == "rescan":
                    scan_sources(sources, DEFAULT_TIMEOUT, width, show_progress=True)
                    health_data = load_json(HEALTH_FILE, {})
                    health_map = {r["id"]: r for r in health_data.get("results", [])}
                    fetcher.health_map = health_map
                elif action == "clear_buffer":
                    history.clear()
                setup_screen()
                previous = []
            elif key == "d":
                restore_screen()
                scan_sources(sources, DEFAULT_TIMEOUT, width, show_progress=True)
                health_data = load_json(HEALTH_FILE, {})
                health_map = {r["id"]: r for r in health_data.get("results", [])}
                fetcher.health_map = health_map
                setup_screen()
                previous = []
            elif key == "r":
                fetcher.last_fetch = 0.0
                fetcher.stop_event.clear()

            time.sleep(1.0 / max(0.5, RENDER_FPS))
    except KeyboardInterrupt:
        pass
    finally:
        fetcher.stop()
        translator.stop()
        restore_screen()

    return "ok"
'''

# ---------------- main.py ----------------
FILES["main.py"] = '''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""main.py — entry point."""

import argparse
import json
import sys

from config import (
    DEFAULT_TIMEOUT, HEALTH_FILE, SOURCES_FILE,
    enable_windows_ansi, load_json,
)
from storage import load_settings, get_terminal_size, load_sources, HistoryWriter
from sources import scan_sources, fetch_one_source
from live import run_live


def run():
    enable_windows_ansi()

    parser = argparse.ArgumentParser(description="News Terminal")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--source", default="")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-fresh-scan", action="store_true")
    args = parser.parse_args()

    settings = load_settings()
    width, height = get_terminal_size(settings)
    sources = load_sources()

    if not sources:
        print("No sources configured:", SOURCES_FILE)
        return 2

    if args.diagnostics:
        scan_sources(sources, DEFAULT_TIMEOUT, width, show_progress=True)
        return 0

    if args.source:
        source = next((s for s in sources if s["id"] == args.source), None)
        if not source:
            print("Source not found:", args.source)
            return 1
        print(json.dumps(fetch_one_source(source, DEFAULT_TIMEOUT),
                         ensure_ascii=False, indent=2))
        return 0

    if not args.no_fresh_scan:
        scan_sources(sources, DEFAULT_TIMEOUT, width, show_progress=True)

    health_data = load_json(HEALTH_FILE, {})
    health_map = {r["id"]: r for r in health_data.get("results", [])}

    if not health_map:
        scan_sources(sources, DEFAULT_TIMEOUT, width, show_progress=True)
        health_data = load_json(HEALTH_FILE, {})
        health_map = {r["id"]: r for r in health_data.get("results", [])}

    history_writer = HistoryWriter()
    try:
        result = run_live(sources, health_map, width, height, settings,
                          history_writer, once=args.once)
    finally:
        history_writer.close()
    return 0


if __name__ == "__main__":
    sys.exit(run())
'''


# ============================================================
#  Installer
# ============================================================

def build():
    print("NEWS TERMINAL :: installer")
    print()

    target = Path("news_terminal_project")
    target.mkdir(exist_ok=True)

    # config files
    (target / "config").mkdir(exist_ok=True)
    (target / "data").mkdir(exist_ok=True)
    (target / "diagnostics").mkdir(exist_ok=True)
    (target / "news_history").mkdir(exist_ok=True)

    # default settings.json
    (target / "config" / "settings.json").write_text(
        '{\n'
        '  "version": 1,\n'
        '  "display": {\n'
        '    "width": 80,\n'
        '    "auto_detect_terminal_size": true,\n'
        '    "title": "NEWS TERMINAL",\n'
        '    "language": "ru"\n'
        '  },\n'
        '  "wifi": {\n'
        '    "interface": "wlan0"\n'
        '  },\n'
        '  "app": {\n'
        '    "refresh_seconds": 60\n'
        '  }\n'
        '}\n',
        encoding="utf-8"
    )

    # placeholder sources.json
    sources_example = {
        "version": 1,
        "defaults": {
            "refresh_seconds": 60,
            "startup_scan_timeout": 8,
            "feed_timeout": 8,
            "history_hours": 12,
        },
        "sources": [
            {"id": "ria", "name": "РИА Новости",
             "url": "https://ria.ru/export/rss2/archive/index.xml",
             "language": "ru", "region": "RU", "priority": 100,
             "enabled": True},
            {"id": "lenta", "name": "Лента.ру",
             "url": "https://lenta.ru/rss",
             "language": "ru", "region": "RU", "priority": 100,
             "enabled": True},
            {"id": "rbc", "name": "РБК",
             "url": "https://rssexport.rbc.ru/rbcnews/news/30/full.rss",
             "language": "ru", "region": "RU", "priority": 100,
             "enabled": True},
            {"id": "kommersant", "name": "Коммерсантъ",
             "url": "https://www.kommersant.ru/RSS/news.xml",
             "language": "ru", "region": "RU", "priority": 100,
             "enabled": True},
            {"id": "interfax", "name": "Интерфакс",
             "url": "https://www.interfax.ru/rss.asp",
             "language": "ru", "region": "RU", "priority": 100,
             "enabled": True},
            {"id": "tass_en", "name": "ТАСС EN",
             "url": "https://tass.com/rss/v2.xml",
             "language": "en", "region": "WORLD", "priority": 55,
             "enabled": True},
            {"id": "bbc_world", "name": "BBC WORLD",
             "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
             "language": "en", "region": "WORLD", "priority": 50,
             "enabled": True},
            {"id": "dw_all", "name": "DEUTSCHE WELLE",
             "url": "https://rss.dw.com/rdf/rss-en-all",
             "language": "en", "region": "EUROPE", "priority": 55,
             "enabled": True},
        ]
    }
    (target / "config" / "sources.json").write_text(
        json.dumps(sources_example, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # write all modules
    for name, content in FILES.items():
        path = target / name
        path.write_text(content, encoding="utf-8")
        print("  +", name)

    # build zip
    zip_name = "news_terminal.zip"
    with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in target.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(target.parent))

    print()
    print("Project folder : {}".format(target.resolve()))
    print("Archive        : {}".format(Path(zip_name).resolve()))
    print()
    print("Next steps:")
    print("  cd {}".format(target))
    print("  pip install -r requirements.txt")
    print("  python main.py --diagnostics")
    print("  python main.py")


if __name__ == "__main__":
    build()