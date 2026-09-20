#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stats.py — статистика по новостям.
Читает news_history/*.jsonl, считает позитивные и негативные упоминания
по ключевым словам, строит отчёт за 7 / 30 / 365 дней и за всё время.
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from config import HISTORY_DIR, BASE_DIR


REPORT_DIR = BASE_DIR / "stats"


# ============================================================
#  Ключевые слова
# ============================================================

NEGATIVE_RU = [
    "смерт", "умер", "погиб", "убийств", "убит", "убийц",
    "войн", "военн", "конфликт", "атак", "обстрел", "удар",
    "взрыв", "теракт", "катастроф", "авари",
    "пожар", "крушени", "ранени", "травм", "бедств",
    "преступл", "арест", "тюрьм", "ракет", "дрон", "бпла",
    "чп", "трагед", "кризис", "санкц", "инфляц",
    "угроз", "опасн", "риск", "потер", "ущерб",
    "напад", "грабеж", "мошен", "коррупц", "нарко",
    "эвакуац", "голод", "эпидем", "пандем",
]

NEGATIVE_EN = [
    "death", "dead", "killed", "killing", "murder",
    "war", "attack", "strike", "missile", "bombing",
    "explosion", "terror", "disaster", "crash", "fire",
    "crisis", "sanction", "inflation", "threat",
    "victim", "wounded", "injured", "damage", "loss",
    "assault", "robbery", "fraud", "corruption", "drug",
    "evacuation", "famine", "epidemic", "pandemic",
]

POSITIVE_RU = [
    "любов", "семь", "счасть", "радост",
    "успех", "побед", "достижен", "рекорд",
    "помощ", "поддержк", "спасен", "восстановлен",
    "открыт", "развит", "рост", "улучшен",
    "мир", "соглашен", "договорен", "прогресс",
    "праздник", "награ", "подар", "юбилей",
    "здоров", "благодар", "надежд", "добр",
    "выигр", "первенств", "чемпион", "запуск",
]

POSITIVE_EN = [
    "love", "family", "happiness", "joy",
    "success", "victory", "achievement", "record",
    "help", "support", "rescue", "recovery",
    "growth", "development", "improvement", "progress",
    "peace", "agreement", "deal", "breakthrough",
    "award", "celebration", "gift", "anniversary",
    "health", "gratitude", "hope", "kindness",
    "win", "won", "champion", "launch",
]


def _hits(text, keywords):
    if not text:
        return []
    low = text.lower()
    return [k for k in keywords if k in low]


# ============================================================
#  Чтение файлов
# ============================================================

def _deserialize(obj):
    try:
        obj["time"] = datetime.fromisoformat(obj["time"])
    except Exception:
        return None
    if obj["time"].tzinfo is None:
        obj["time"] = obj["time"].replace(tzinfo=timezone.utc)
    return obj


def load_all_items(folder=HISTORY_DIR):
    folder = Path(folder)
    if not folder.exists():
        return [], 0
    items = []
    seen = set()
    files_count = 0
    for path in sorted(folder.glob("news_*.jsonl")):
        files_count += 1
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        item = _deserialize(obj)
                        if item is None:
                            continue
                        k = item.get("key")
                        if k and k in seen:
                            continue
                        if k:
                            seen.add(k)
                        items.append(item)
                    except Exception:
                        continue
        except Exception:
            continue
    return items, files_count


# ============================================================
#  Анализ
# ============================================================

def analyze(items):
    neg = Counter()
    pos = Counter()
    total = 0
    neg_items = 0
    pos_items = 0
    sources = Counter()

    for item in items:
        total += 1
        title = item.get("title", "") or ""
        title_ru = item.get("title_ru") or ""
        text_ru = title_ru if title_ru else title

        nh = set(
            _hits(title, NEGATIVE_RU)
            + _hits(title, NEGATIVE_EN)
            + _hits(title_ru, NEGATIVE_RU)
        )
        ph = set(
            _hits(title, POSITIVE_RU)
            + _hits(title, POSITIVE_EN)
            + _hits(title_ru, POSITIVE_RU)
        )

        if nh:
            neg_items += 1
            for k in nh:
                neg[k] += 1
        if ph:
            pos_items += 1
            for k in ph:
                pos[k] += 1

        sources[item.get("source", "?")] += 1

    return {
        "total": total,
        "neg_items": neg_items,
        "pos_items": pos_items,
        "neutral": total - neg_items - pos_items,
        "neg_keywords": neg.most_common(15),
        "pos_keywords": pos.most_common(15),
        "top_sources": sources.most_common(10),
    }


def filter_days(items, days):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    return [x for x in items if x["time"] >= cutoff]


# ============================================================
#  Отчёт
# ============================================================

TOP = "═" * 68
SEP = "─" * 66


def _pct(part, total):
    if total <= 0:
        return "0.0%"
    return "{:.1f}%".format(part * 100.0 / total)


def _verdict(neg, pos, total):
    if total <= 0:
        return "нет данных"
    if pos == 0 and neg == 0:
        return "нейтральный поток"
    if pos == 0:
        return "ПРЕОБЛАДАЮТ НЕГАТИВНЫЕ"
    r = neg / pos
    if r >= 2.0:
        return "ПРЕОБЛАДАЮТ НЕГАТИВНЫЕ"
    if r >= 1.2:
        return "скорее негативные"
    if r <= 0.5:
        return "ПРЕОБЛАДАЮТ ПОЗИТИВНЫЕ"
    if r <= 0.8:
        return "скорее позитивные"
    return "баланс"


def format_period(title, stats):
    lines = []
    lines.append("╔" + "═" * 66 + "╗")
    lines.append("║  {:<64}║".format(title))
    lines.append("╚" + "═" * 66 + "╝")
    lines.append("")

    if stats["total"] == 0:
        lines.append("  (нет новостей за период)")
        lines.append("")
        return lines

    total = stats["total"]
    lines.append("  Items: {}".format(total))
    lines.append("")

    lines.append("  ── Sentiment ──")
    lines.append("    ⚠ NEGATIVE : {:>5}  ({})".format(
        stats["neg_items"], _pct(stats["neg_items"], total)))
    lines.append("    ☺ POSITIVE : {:>5}  ({})".format(
        stats["pos_items"], _pct(stats["pos_items"], total)))
    lines.append("    · NEUTRAL  : {:>5}  ({})".format(
        stats["neutral"], _pct(stats["neutral"], total)))
    lines.append("    → {}".format(
        _verdict(stats["neg_items"], stats["pos_items"], total)))
    lines.append("")

    lines.append("  ── Top negative keywords ──")
    if stats["neg_keywords"]:
        for kw, cnt in stats["neg_keywords"]:
            lines.append("    {:24} {:>5}".format(kw, cnt))
    else:
        lines.append("    (нет)")
    lines.append("")

    lines.append("  ── Top positive keywords ──")
    if stats["pos_keywords"]:
        for kw, cnt in stats["pos_keywords"]:
            lines.append("    {:24} {:>5}".format(kw, cnt))
    else:
        lines.append("    (нет)")
    lines.append("")

    lines.append("  ── Top sources ──")
    for src, cnt in stats["top_sources"]:
        lines.append("    {:30} {:>5}".format(str(src)[:30], cnt))
    lines.append("")
    return lines


def build_report(items, files_count):
    lines = []
    lines.append(TOP)
    lines.append("  NEWS TERMINAL :: STATISTICS REPORT")
    lines.append("  Generated: {}".format(
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    lines.append(TOP)
    lines.append("")

    if not items:
        lines.append("  No news files found in {}".format(HISTORY_DIR))
        lines.append("")
        lines.append(TOP)
        return "\n".join(lines)

    times = [x["time"] for x in items]
    start = min(times).astimezone().strftime("%Y-%m-%d")
    end = max(times).astimezone().strftime("%Y-%m-%d")

    lines.append("  Files analyzed : {}".format(files_count))
    lines.append("  Total items    : {}".format(len(items)))
    lines.append("  Period         : {} — {}".format(start, end))
    lines.append("")

    # 7 / 30 / 365
    lines.extend(format_period("LAST 7 DAYS", analyze(filter_days(items, 7))))
    lines.extend(format_period("LAST 30 DAYS", analyze(filter_days(items, 30))))
    lines.extend(format_period("LAST 365 DAYS", analyze(filter_days(items, 365))))
    lines.extend(format_period("ALL TIME", analyze(items)))

    lines.append(TOP)
    lines.append("  END OF REPORT")
    lines.append(TOP)
    return "\n".join(lines)


# ============================================================
#  CLI
# ============================================================

def run():
    parser = argparse.ArgumentParser(description="News statistics")
    parser.add_argument("--days", type=int, default=0,
                        help="Только за N последних дней (0 = все)")
    parser.add_argument("--out", default="",
                        help="Имя файла отчёта (без пути)")
    parser.add_argument("--no-save", action="store_true",
                        help="Только вывести в консоль, не сохранять")
    args = parser.parse_args()

    items, files_count = load_all_items(HISTORY_DIR)
    if args.days > 0:
        items = filter_days(items, args.days)

    report = build_report(items, files_count)
    print(report)

    if not args.no_save:
        REPORT_DIR.mkdir(parents=True, exist_ok=True)
        name = args.out or "stats_{}.txt".format(
            datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        path = REPORT_DIR / name
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(report)
            print()
            print("Report saved:", path)
        except Exception as e:
            print("Save failed:", e)

    return 0


if __name__ == "__main__":
    sys.exit(run())