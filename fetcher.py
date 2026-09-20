#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetcher.py — фоновый поток fetch с приоритетными источниками."""

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

import feedparser

from config import (
    HISTORY_HOURS, DEFAULT_TIMEOUT, FAST_FETCH_INTERVAL,
    FAST_PRIORITY_THRESHOLD, now_utc,
)
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
    """
    Фоновый поток с двумя уровнями:
    - приоритетные источники (priority >= FAST_PRIORITY_THRESHOLD)
      опрашиваются каждые FAST_FETCH_INTERVAL секунд;
    - остальные — раз в self.interval секунд.
    """

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
        self.last_slow_fetch = 0.0

    def start(self):
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def _split_by_priority(self):
        fast, slow = [], []
        for src in self.sources:
            if not src.get("enabled", True):
                continue
            if self.health_map.get(src["id"], {}).get("status") != "healthy":
                continue
            if int(src.get("priority", 50)) >= FAST_PRIORITY_THRESHOLD:
                fast.append(src)
            else:
                slow.append(src)
        return fast, slow

    def _loop(self):
        while not self.stop_event.is_set():
            self.fetching = True
            try:
                fast, slow = self._split_by_priority()

                # ---- Быстрые источники каждые FAST_FETCH_INTERVAL секунд ----
                if fast:
                    items = fetch_news_parallel(
                        fast, self.health_map, self.seen_keys, self.stop_event
                    )
                    for item in items:
                        self.queue.put(item)

                # ---- Медленные источники раз в self.interval секунд ----
                now = time.time()
                if slow and now - self.last_slow_fetch >= self.interval:
                    items = fetch_news_parallel(
                        slow, self.health_map, self.seen_keys, self.stop_event
                    )
                    for item in items:
                        self.queue.put(item)
                    self.last_slow_fetch = now
            except Exception:
                pass
            self.fetching = False
            self.last_fetch = time.time()
            self.stop_event.wait(FAST_FETCH_INTERVAL)

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
        return max(0, int(FAST_FETCH_INTERVAL - elapsed))