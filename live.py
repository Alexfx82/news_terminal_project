#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""live.py — главный цикл."""

import os
import sys
import time
from collections import deque
from datetime import datetime

from config import (
    RENDER_FPS, DEFAULT_TIMEOUT, HEALTH_FILE, LANG_TOGGLE_SECONDS,
    RESTORE_HOURS, HISTORY_DIR, TRANSLATION_ENABLED,
    setup_screen, restore_screen, render_diff, load_json,
)
from storage import load_recent_history
from news import reclassify_recent, RECLASSIFY_HOURS
from fetcher import Fetcher
from render import build_frame_lines, trim_history
from menu import settings_menu
from sources import scan_sources
from stats_view import show_stats_screen


def read_key():
    """Неблокирующее чтение одной клавиши."""
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


def _make_translator():
    """
    Создаёт TranslationService только если перевод разрешён.
    При TRANSLATION_ENABLED=False возвращает None — код работает без переводов.
    """
    if not TRANSLATION_ENABLED:
        return None
    try:
        from translator import TranslationService
        t = TranslationService()
        t.start()
        return t
    except Exception as e:
        print("Переводчик недоступен:", e, flush=True)
        return None


def _translator_get(translator, text):
    """Безопасно получить перевод из кэша."""
    if translator is None or not text:
        return None
    try:
        return translator.get(text)
    except Exception:
        return None


def _translator_request(translator, text):
    """Безопасно поставить текст в очередь на перевод."""
    if translator is None or not text:
        return
    try:
        translator.request(text)
    except Exception:
        pass


def run_live(sources, health_map, width, height, settings,
             history_writer, once=False):
    history = deque(maxlen=2000)
    ticker_offset = 0
    last_update = "--:--:--"
    reclassify_tick = 0

    # ===== Восстановление из всех файлов за RESTORE_HOURS =====
    restored = load_recent_history(HISTORY_DIR, RESTORE_HOURS)
    for item in restored:
        history.append(item)
    if restored:
        reclassify_recent(history, RECLASSIFY_HOURS)

    interval = int(settings.get("refresh", 60))
    fetcher = Fetcher(sources, health_map, interval)

    # Засеиваем seen_keys
    for item in restored:
        k = item.get("key")
        if k:
            fetcher.seen_keys.add(k)

    # ===== Переводчик =====
    translator = _make_translator()
    if translator is None:
        print("Перевод: ОТКЛЮЧЁН", flush=True)
    else:
        print("Перевод: включён", flush=True)
        # Подхватить переводы для восстановленных
        for item in restored:
            lang = item.get("language", "")
            if lang and lang != "ru":
                cached = _translator_get(translator, item["title"])
                if cached:
                    item["title_ru"] = cached

    fetcher.start()
    setup_screen()
    previous = []

    try:
        while True:
            # ===== 1. Дренаж очереди =====
            new_items = fetcher.drain()
            if new_items:
                existing_keys = {x.get("key") for x in history if x.get("key")}
                filtered = []
                for item in new_items:
                    k = item.get("key")
                    if k and k in existing_keys:
                        continue
                    lang = item.get("language", "")
                    if lang and lang != "ru":
                        cached = _translator_get(translator, item["title"])
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

            # ===== 2. Пересчёт level =====
            reclassify_tick += 1
            if reclassify_tick % 3 == 0:
                reclassify_recent(history, RECLASSIFY_HOURS)

            # ===== 3. Запрос переводов (только если включён) =====
            if translator is not None:
                for item in history:
                    lang = item.get("language", "")
                    if not lang or lang == "ru":
                        continue
                    if item.get("title_ru"):
                        continue
                    cached = _translator_get(translator, item["title"])
                    if cached:
                        item["title_ru"] = cached
                    else:
                        _translator_request(translator, item["title"])

            # ===== 4. Toggle EN/RU =====
            show_translation = int(time.time() / LANG_TOGGLE_SECONDS) % 2 == 1

            # ===== 5. Рендер =====
            frame = build_frame_lines(
                history, width, height, health_map,
                last_update, ticker_offset,
                fetcher.seconds_until_next(),
                fetcher.fetching,
                show_translation=show_translation,
            )
            previous = render_diff(previous, frame)
            ticker_offset += 4

            if once:
                time.sleep(2)
                break

            # ===== 6. Клавиши =====
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
            elif key == "t":
                show_stats_screen(width, height)
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
        if translator is not None:
            try:
                translator.stop()
            except Exception:
                pass
        restore_screen()

    return "ok"
