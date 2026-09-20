#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""storage.py — settings, sources, history I/O с сессионной ротацией."""

import json
import shutil
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import (
    SETTINGS_FILE, SOURCES_FILE, HISTORY_DIR,
    DEFAULT_WIDTH, DEFAULT_HEIGHT, DEFAULT_REFRESH,
    RESTORE_HOURS, load_json, now_utc,
)


# ============================================================
#  Settings / sources
# ============================================================

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


# ============================================================
#  Serialization
# ============================================================

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


# ============================================================
#  HistoryWriter — сессионная ротация
# ============================================================

def _session_file_path(d):
    """Путь к файлу текущей сессии (без метки времени)."""
    return HISTORY_DIR / "news_{}.jsonl".format(d.strftime("%Y-%m-%d"))


class HistoryWriter:
    """
    Пишет items в news_history/news_YYYY-MM-DD.jsonl (текущая сессия).
    При закрытии (close) или смене даты — переименовывает файл
    в news_YYYY-MM-DD_HH-MM-SS.jsonl с меткой времени последней записи.
    """

    def __init__(self, folder=HISTORY_DIR):
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.current_date = None
        self.current_path = None
        self.file = None
        self.last_write_time = None
        self._open_for_date(datetime.now().date())

    def _open_for_date(self, d):
        # Финализируем предыдущий файл (если был)
        self._finalize_current()

        self.current_date = d
        self.current_path = _session_file_path(d)
        self.file = open(self.current_path, "a", encoding="utf-8")
        self.last_write_time = datetime.now()

    def _finalize_current(self):
        """
        Закрывает текущий файл.
        Если он непустой — переименовывает с меткой времени.
        Если пустой — удаляет.
        """
        if self.file is not None:
            try:
                self.file.close()
            except Exception:
                pass
            self.file = None

        if not self.current_path or not self.current_path.exists():
            return

        try:
            size = self.current_path.stat().st_size
        except Exception:
            return

        if size == 0:
            # Пустой файл — просто удалить
            try:
                self.current_path.unlink()
            except Exception:
                pass
            return

        # Непустой — переименовать
        ts = (self.last_write_time or datetime.now()).strftime("%Y-%m-%d_%H-%M-%S")
        target = self.folder / "news_{}.jsonl".format(ts)

        # Если такой файл уже есть — добавить суффикс
        counter = 1
        final = target
        while final.exists():
            final = self.folder / "news_{}_{}.jsonl".format(ts, counter)
            counter += 1

        try:
            self.current_path.rename(final)
        except Exception:
            pass

    def write(self, item):
        today = datetime.now().date()
        if today != self.current_date:
            # Смена даты — финализируем старый, открываем новый
            self._open_for_date(today)

        try:
            obj = serialize_item(item)
            self.file.write(json.dumps(obj, ensure_ascii=False) + "\n")
            self.file.flush()
            self.last_write_time = datetime.now()
        except Exception:
            pass

    def write_many(self, items):
        for it in items:
            self.write(it)

    def close(self):
        """Финализировать сессию — файл переименовывается с меткой времени."""
        self._finalize_current()


# ============================================================
#  Restore from all recent files
# ============================================================

def load_recent_history(folder=HISTORY_DIR, hours=RESTORE_HOURS):
    """
    Читает ВСЕ файлы news_*.jsonl из папки,
    возвращает items за последние N часов.
    Работает и с сессионными (с меткой), и с текущим (без метки).
    """
    folder = Path(folder)
    if not folder.exists():
        return []

    cutoff = now_utc() - timedelta(hours=hours)

    # Все файлы, свежие первыми
    try:
        files = sorted(
            folder.glob("news_*.jsonl"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return []

    seen_keys = set()
    items = []

    for path in files:
        # Если файл старше cutoff по mtime — дальше смысла нет
        try:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
        except Exception:
            continue

        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        item = deserialize_item(obj)
                        if item is None:
                            continue
                        if item["time"] < cutoff:
                            continue
                        k = item.get("key")
                        if k and k in seen_keys:
                            continue
                        if k:
                            seen_keys.add(k)
                        items.append(item)
                    except Exception:
                        continue
        except Exception:
            continue

    return items


# ============================================================
#  Legacy helpers (оставлены для совместимости)
# ============================================================

def history_file_for_today():
    """Путь к файлу текущей сессии (без метки времени)."""
    return _session_file_path(datetime.now().date())


def load_history_from_file(path, hours=RESTORE_HOURS):
    """Обратная совместимость: читает один файл."""
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