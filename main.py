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


def _check_updates_on_startup():
    """Проверяет обновления при старте, выводит уведомление."""
    try:
        from update import check_for_updates
        info = check_for_updates()
        if info.get("ok") and info.get("available"):
            print()
            print("╔══════════════════════════════════════════════════════════╗")
            print("║  ДОСТУПНО ОБНОВЛЕНИЕ                                     ║")
            print("╚══════════════════════════════════════════════════════════╝")
            print("  Локально: {} {}".format(info["local_sha"], info["local_msg"][:50]))
            print("  На GitHub: {} {}".format(info["remote_sha"], info["remote_msg"][:50]))
            print()
            print("  Обновить можно через меню [S] → пункт 9")
            print()
    except Exception:
        pass


def run():
    enable_windows_ansi()

    parser = argparse.ArgumentParser(description="News Terminal")
    parser.add_argument("--diagnostics", action="store_true")
    parser.add_argument("--source", default="")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-fresh-scan", action="store_true")
    parser.add_argument("--check-updates", action="store_true",
                        help="Проверить обновления и выйти")
    args = parser.parse_args()

    # === Проверка обновлений, если запрошено ===
    if args.check_updates:
        from update import check_for_updates
        info = check_for_updates()
        if info["ok"]:
            if info["available"]:
                print("Обновление доступно:")
                print("  Локально:  {} {}".format(info["local_sha"], info["local_msg"]))
                print("  На GitHub: {} {}".format(info["remote_sha"], info["remote_msg"]))
            else:
                print("Обновлений нет. Текущая версия:", info["local_sha"])
        else:
            print("Ошибка:", info["error"])
        return 0

    # === Проверка при обычном старте ===
    if not args.no_fresh_scan:
        _check_updates_on_startup()

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