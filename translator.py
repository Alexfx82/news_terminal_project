#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""translator.py — перевод с fallback, cooldown и отладкой."""

import hashlib
import queue
import threading
import time
from pathlib import Path

from config import (
    TRANSLATION_CACHE_FILE, TRANSLATION_RATE_LIMIT, YANDEX_API_KEY,
    TRANSLATION_FAIL_THRESHOLD, TRANSLATION_COOLDOWN_SECONDS,
    DATA_DIR, load_json, save_json, now_utc,
)


DEBUG_LOG = DATA_DIR / "translation_debug.log"


def _log(msg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write("{} | {}\n".format(now_utc().isoformat(), msg))
    except Exception:
        pass


class TranslatorSlot:
    """Обёртка над одним переводчиком с учётом 429 и cooldown."""

    def __init__(self, name, translator, handles_langs):
        self.name = name
        self.translator = translator
        self.handles_langs = handles_langs   # set, например {"en"}
        self.fail_streak = 0
        self.banned_until = 0.0
        self.stats = {"ok": 0, "fail": 0, "skip": 0, "empty": 0}

    def available_for(self, lang):
        if lang not in self.handles_langs:
            return False
        if time.time() < self.banned_until:
            return False
        return True

    def is_banned(self):
        return time.time() < self.banned_until

    def ban_seconds_left(self):
        return max(0, int(self.banned_until - time.time()))

    def translate(self, text):
        # Обрезка для MyMemory
        payload = text[:4500] if self.name != "mymemory" else text[:500]
        translated = self.translator.translate(payload)
        if translated and translated.strip():
            self.fail_streak = 0
            self.stats["ok"] += 1
            return translated
        self.stats["empty"] += 1
        return None

    def on_fail(self):
        self.fail_streak += 1
        self.stats["fail"] += 1
        if self.fail_streak >= TRANSLATION_FAIL_THRESHOLD:
            self.banned_until = time.time() + TRANSLATION_COOLDOWN_SECONDS
            _log("{} BANNED for {}s after {} fails".format(
                self.name, TRANSLATION_COOLDOWN_SECONDS, self.fail_streak))

    def on_skip(self):
        self.stats["skip"] += 1


class TranslationService:
    """
    Асинхронный переводчик с цепочкой fallback и автоматическим cooldown.
    Если Google отдаёт 429 — переключаемся на MyMemory на 10 минут.
    """

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
        self._slots = self._build_slots()
        _log("TranslationService init; slots = {}".format(
            [s.name for s in self._slots]))

    # ============================================================
    #  Chain
    # ============================================================

    def _build_slots(self):
        slots = []

        # Google — умеет всё (auto)
        try:
            from deep_translator import GoogleTranslator
            slots.append(TranslatorSlot(
                "google",
                GoogleTranslator(source="auto", target="ru"),
                {"en", "zh", "de", "fr", "es"},
            ))
            _log("slot: google OK")
        except Exception as e:
            _log("slot: google FAIL: {}".format(e))

        # Yandex — если ключ
        if YANDEX_API_KEY:
            try:
                from deep_translator import YandexTranslator
                slots.append(TranslatorSlot(
                    "yandex",
                    YandexTranslator(api_key=YANDEX_API_KEY,
                                     source="auto", target="ru"),
                    {"en", "zh", "de", "fr", "es"},
                ))
                _log("slot: yandex OK")
            except Exception as e:
                _log("slot: yandex FAIL: {}".format(e))

        # MyMemory — только EN→RU, но стабильный
        try:
            from deep_translator import MyMemoryTranslator
            slots.append(TranslatorSlot(
                "mymemory",
                MyMemoryTranslator(source="en-US", target="ru-RU"),
                {"en"},
            ))
            _log("slot: mymemory OK")
        except Exception as e:
            _log("slot: mymemory FAIL: {}".format(e))

        return slots

    # ============================================================
    #  Cache
    # ============================================================

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

    # ============================================================
    #  Lifecycle
    # ============================================================

    def start(self):
        if self.thread is not None:
            return
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self._save(force=True)

    # ============================================================
    #  Translation loop
    # ============================================================

    @staticmethod
    def _detect_lang(text):
        if any("\u4e00" <= c <= "\u9fff" for c in text):
            return "zh"
        if any("\u0400" <= c <= "\u04ff" for c in text):
            return "ru"
        if any(c.isalpha() for c in text):
            return "en"
        return "en"

    def _try_translate(self, text, lang):
        """Проходит по слотам, возвращает (translated, slot_name) или (None, None)."""
        for slot in self._slots:
            if not slot.available_for(lang):
                if slot.is_banned():
                    slot.on_skip()
                continue
            try:
                result = slot.translate(text)
                if result:
                    _log("OK {} [{}] | {} -> {}".format(
                        slot.name, lang, text[:40], result[:40]))
                    return result, slot.name
            except Exception as e:
                ename = type(e).__name__
                msg = str(e)[:100]
                _log("FAIL {} [{}] {} | {}".format(
                    slot.name, lang, ename, msg))
                slot.on_fail()
                continue
        return None, None

    def _loop(self):
        if not self._slots:
            _log("No translators available, loop exiting")
            return

        while not self.stop_event.is_set():
            try:
                key, text = self.queue.get(timeout=0.5)
            except queue.Empty:
                self._save()
                continue

            lang = self._detect_lang(text)
            if lang == "ru":
                with self.lock:
                    self._pending.discard(key)
                continue

            translated, source = self._try_translate(text, lang)
            if translated:
                with self.lock:
                    self.cache[key] = translated
                    self._dirty = True
            with self.lock:
                self._pending.discard(key)

            self.stop_event.wait(self.rate_limit)

    # ============================================================
    #  Persistence
    # ============================================================

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

    # ============================================================
    #  Diagnostics
    # ============================================================

    def chain_status(self):
        if not self._slots:
            return "TRANSLATORS: NONE"
        parts = []
        for slot in self._slots:
            tag = slot.name
            if slot.is_banned():
                tag += "(BANNED {}s)".format(slot.ban_seconds_left())
            parts.append("{}: ok={} fail={} skip={} empty={}".format(
                tag, slot.stats["ok"], slot.stats["fail"],
                slot.stats["skip"], slot.stats["empty"]))
        return "TRANSLATORS: " + " | ".join(parts)