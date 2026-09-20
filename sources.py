#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sources.py — диагностика RSS/Atom-источников.

Диагностика:
- выполняет настоящий HTTP timeout;
- не держит программу на зависшем RSS дольше заданного timeout;
- показывает прогресс, текущий источник, elapsed и ETA;
- отдельно помечает медленные проверки;
- невалидные источники попадают в failed и автоматически исключаются
  из активной ленты через source_health.json;
- сохраняет полный машинный отчёт для последующего анализа.
"""

import platform
import socket
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import feedparser

from config import (
    DATA_DIR, HEALTH_FILE, FAILURE_LOG, AI_REPORT, SOURCES_FILE,
    DEFAULT_TIMEOUT, save_json, now_utc,
)
from textutils import fit_text, visible_width, pad_visible
from news import parse_entry_time

USER_AGENT = "NewsTerminal/1.0 RSS reader"
MAX_FEED_BYTES = 4 * 1024 * 1024
SLOW_THRESHOLD_SECONDS = 2.0


def _http_get(url, timeout):
    """Получить RSS/Atom через urllib с реальным timeout."""
    request = Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
            "Accept-Encoding": "identity",
        },
    )
    with urlopen(request, timeout=max(1, float(timeout))) as response:
        status = getattr(response, "status", None) or response.getcode()
        final_url = response.geturl()
        content = response.read(MAX_FEED_BYTES + 1)
        if len(content) > MAX_FEED_BYTES:
            raise ValueError("FEED_TOO_LARGE")
        return status, final_url, content


def fetch_one_source(source, timeout):
    """Проверить один RSS/Atom источник."""
    started = time.monotonic()
    result = {
        "id": source["id"],
        "name": source["name"],
        "url": source["url"],
        "language": source.get("language", ""),
        "region": source.get("region", "WORLD"),
        "priority": source.get("priority", 50),
        "status": "failed",
        "http_status": None,
        "latency_ms": None,
        "items": 0,
        "latest": None,
        "error": None,
        "parser": None,
        "final_url": None,
        "warning": None,
    }

    try:
        status, final_url, content = _http_get(source["url"], timeout)
        result["http_status"] = status
        result["final_url"] = final_url

        if status >= 400:
            result["error"] = "HTTP {}".format(status)
            return result

        parsed = feedparser.parse(content)
        bozo = getattr(parsed, "bozo", 0)
        entries = list(getattr(parsed, "entries", []) or [])

        if not entries:
            result["error"] = "EMPTY_FEED"
            if bozo:
                bozo_exc = getattr(parsed, "bozo_exception", None)
                if bozo_exc:
                    result["error"] = "EMPTY_FEED: {}".format(
                        str(bozo_exc)[:150]
                    )
            return result

        valid_titles = []
        for entry in entries:
            title = str(entry.get("title", "")).strip()
            if title:
                valid_titles.append(title)

        if not valid_titles:
            result["error"] = "NO_TITLES"
            return result

        result["items"] = len(valid_titles)
        result["parser"] = "RSS/Atom"

        try:
            result["latest"] = parse_entry_time(entries[0]).isoformat()
        except Exception:
            result["latest"] = None
            result["warning"] = "LATEST_DATE_UNPARSEABLE"

        if bozo:
            result["warning"] = "BOZO_XML_BUT_USABLE"

        result["status"] = "healthy"
        return result

    except HTTPError as exc:
        result["http_status"] = getattr(exc, "code", None)
        result["error"] = "HTTP {}".format(getattr(exc, "code", "ERROR"))
        return result
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        result["error"] = "URL_ERROR: {}".format(str(reason)[:160])
        return result
    except TimeoutError:
        result["error"] = "TIMEOUT"
        return result
    except Exception as exc:
        result["error"] = "{}: {}".format(
            type(exc).__name__, str(exc)[:180]
        )
        return result
    finally:
        result["latency_ms"] = round((time.monotonic() - started) * 1000)


def write_failure(result):
    """Добавить невалидный источник в журнал отказов."""
    if result.get("status") == "healthy":
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    line = "{} | {} | {} | {} | {} ms | {}\n".format(
        now_utc().isoformat(),
        result.get("id", ""),
        result.get("name", ""),
        result.get("error", "UNKNOWN"),
        result.get("latency_ms", ""),
        result.get("url", ""),
    )
    with open(FAILURE_LOG, "a", encoding="utf-8") as f:
        f.write(line)


def _format_eta(seconds):
    if seconds is None:
        return "--:--"
    seconds = max(0, int(round(seconds)))
    minutes, secs = divmod(seconds, 60)
    return "{:02d}:{:02d}".format(minutes, secs)


def _format_elapsed(seconds):
    return _format_eta(seconds)


def _progress_line(width, done, total, current_name, elapsed, eta, result=None):
    """Сформировать одну строго фиксированную строку диагностики."""
    inner = max(20, width - 2)
    percent = int(done * 100 / max(1, total))

    if result is None:
        state = "СКАНИРОВАНИЕ"
    elif result.get("status") == "healthy":
        state = "OK"
    else:
        state = "FAIL"

    name_width = max(12, min(28, inner - 46))
    name = fit_text(current_name or "", name_width)
    left = "{}/{} {:3d}% {:<5} {:<" + str(name_width) + "}"
    left = left.format(done, total, percent, state, name)

    info = "  Время {}  Осталось {}".format(
        _format_elapsed(elapsed), _format_eta(eta)
    )

    content = left + info
    content = fit_text(content, inner)
    return "║" + pad_visible(content, inner) + "║"


def _status_lines(width, total, workers):
    inner = max(20, width - 2)
    title = "NEWS TERMINAL | DIAGNOSTICS"
    line1 = "║" + pad_visible(fit_text(title, inner), inner) + "║"
    info = "Источников: {}   Потоков: {}   Таймаут: {} сек".format(
        total, workers, DEFAULT_TIMEOUT
    )
    line2 = "║" + pad_visible(fit_text(info, inner), inner) + "║"
    return [line1, line2]


def _write_progress(width, done, total, current_name, elapsed, eta, result=None,
                    slow=False):
    """Обновить компактный статус диагностики без растягивания строки."""
    status = _progress_line(
        width, done, total, current_name, elapsed, eta, result=result
    )
    if slow:
        inner = max(20, width - 2)
        notice = "Подождите — идёт сканирование, текущий источник отвечает медленно..."
        status2 = "║" + pad_visible(fit_text(notice, inner), inner) + "║"
        sys.stdout.write("\033[2K\r" + status + "\n" + "\033[2K\r" + status2)
    else:
        sys.stdout.write("\033[2K\r" + status)
    sys.stdout.flush()


def scan_sources(sources, timeout=DEFAULT_TIMEOUT, width=80, show_progress=True):
    """Полное сканирование источников с ETA и отбраковкой невалидных."""
    total = len(sources)
    workers = min(8, max(1, total))
    results = []
    scan_started = time.monotonic()

    if show_progress:
        # Начальный экран диагностики.
        sys.stdout.write("\033[2J\033[H")
        for line in _status_lines(width, total, workers):
            sys.stdout.write(line + "\n")
        sys.stdout.write("\n")
        sys.stdout.flush()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {
            pool.submit(fetch_one_source, src, timeout): src
            for src in sources
        }
        done = 0

        for future in as_completed(future_map):
            done += 1
            src = future_map[future]
            try:
                result = future.result()
            except Exception as exc:
                result = {
                    "id": src["id"],
                    "name": src["name"],
                    "url": src["url"],
                    "language": src.get("language", ""),
                    "region": src.get("region", "WORLD"),
                    "priority": src.get("priority", 50),
                    "status": "failed",
                    "error": repr(exc),
                    "http_status": None,
                    "latency_ms": None,
                    "items": 0,
                    "latest": None,
                    "parser": None,
                }

            results.append(result)
            if result.get("status") != "healthy":
                write_failure(result)

            if show_progress:
                elapsed = time.monotonic() - scan_started
                avg = elapsed / max(1, done)
                remaining = total - done
                eta = avg * remaining
                slow = (result.get("latency_ms") or 0) >= SLOW_THRESHOLD_SECONDS * 1000
                _write_progress(
                    width,
                    done,
                    total,
                    result.get("name", ""),
                    elapsed,
                    eta,
                    result=result,
                    slow=slow,
                )

    elapsed_total = time.monotonic() - scan_started

    if show_progress:
        sys.stdout.write("\n\n")
        sys.stdout.flush()

    # Сортируем для стабильного AI-отчёта.
    results.sort(key=lambda x: x.get("id", ""))
    healthy = [r for r in results if r.get("status") == "healthy"]
    failed = [r for r in results if r.get("status") != "healthy"]

    # ВАЖНО: source_health.json становится фильтром активных источников.
    # fetcher.py использует только status == healthy.
    save_json(HEALTH_FILE, {
        "generated": now_utc().isoformat(),
        "scan_elapsed_seconds": round(elapsed_total, 2),
        "configured": len(sources),
        "healthy": len(healthy),
        "failed": len(failed),
        "results": results,
    })

    ru = sum(1 for r in healthy if r.get("region") == "RU")
    world = sum(1 for r in healthy if r.get("region") != "RU")
    slow_sources = sorted(
        [r for r in results if (r.get("latency_ms") or 0) >= SLOW_THRESHOLD_SECONDS * 1000],
        key=lambda x: x.get("latency_ms") or 0,
        reverse=True,
    )

    save_json(AI_REPORT, {
        "report_version": 2,
        "generated": now_utc().isoformat(),
        "scan": {
            "elapsed_seconds": round(elapsed_total, 2),
            "workers": workers,
            "timeout_seconds": timeout,
            "slow_threshold_seconds": SLOW_THRESHOLD_SECONDS,
        },
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
            "slow_sources": len(slow_sources),
        },
        "failed_sources": failed,
        "slow_sources": slow_sources,
        "healthy_sources": healthy,
    })

    if show_progress:
        inner = max(20, width - 2)
        summary_lines = [
            "NEWS TERMINAL | DIAGNOSTICS COMPLETE",
            "Configured : {}".format(len(sources)),
            "Healthy    : {}".format(len(healthy)),
            "Failed     : {}".format(len(failed)),
            "RU healthy : {}".format(ru),
            "WORLD      : {}".format(world),
            "Slow       : {}".format(len(slow_sources)),
            "Scan time  : {}".format(_format_elapsed(elapsed_total)),
            "AI report  : diagnostics/ai_report.json",
            "Failures   : data/source_failures.log",
        ]
        # Статический итог — каждая строка той же видимой ширины.
        sys.stdout.write("╔" + "═" * inner + "╗\n")
        for text in summary_lines:
            sys.stdout.write("║" + pad_visible(fit_text(text, inner), inner) + "║\n")
        sys.stdout.write("╚" + "═" * inner + "╝\n")
        sys.stdout.flush()

    return results
