#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""menu.py — интерактивное меню настроек."""

import os
import shutil
import subprocess
import sys

from config import HEALTH_FILE, load_json
from textutils import box_line, top_border, mid_border, bottom_border


def clear_and_show_cursor():
    sys.stdout.write("\033[2J\033[H\033[?25h")
    sys.stdout.flush()


def draw_menu_screen(title, lines, width):
    out = []
    out.append(top_border(width))
    out.append(box_line("NEWS TERMINAL  ::  " + title, width))
    out.append(mid_border(width))
    for line in lines:
        out.append(box_line(line, width))
    out.append(bottom_border(width))
    sys.stdout.write("\n".join(out))
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
