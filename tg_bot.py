#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg_bot.py — Telegram-бот для NEWS TERMINAL.
Читает данные из news_history/ и data/.
Не зависит от внутренностей live.py, render.py и т.д.
"""

import json
import sys
import time
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
#  Пути (используем только то, что стабильно)
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = BASE_DIR / "news_history"
TELEGRAM_CONFIG = CONFIG_DIR / "telegram.json"
HEALTH_FILE = DATA_DIR / "source_health.json"


# ============================================================
#  Конфиг
# ============================================================

def load_telegram_config():
    """Читает config/telegram.json. Если нет — создаёт шаблон."""
    if not TELEGRAM_CONFIG.exists():
        TELEGRAM_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        template = {
            "bot_token": "",
            "allowed_chat_ids": [],
            "enabled": True,
            "daily_digest": False,
            "daily_digest_hour": 9,
        }
        with open(TELEGRAM_CONFIG, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        print("Создан шаблон:", TELEGRAM_CONFIG)
        print("Впишите bot_token и allowed_chat_ids, затем перезапустите.")
        sys.exit(1)

    try:
        with open(TELEGRAM_CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("Ошибка чтения telegram.json:", e)
        sys.exit(1)

    if not data.get("bot_token"):
        print("bot_token пуст. Заполните", TELEGRAM_CONFIG)
        sys.exit(1)

    return data


# ============================================================
#  Telegram API
# ============================================================

class TelegramAPI:
    def __init__(self, token):
        self.token = token
        self.base = "https://api.telegram.org/bot{}".format(token)

    def _call(self, method, params=None, timeout=35):
        url = "{}/{}".format(self.base, method)
        if params:
            data = json.dumps(params).encode("utf-8")
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"}
            )
        else:
            req = urllib.request.Request(url)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def get_updates(self, offset=0, timeout=30):
        return self._call("getUpdates", {
            "offset": offset, "timeout": timeout,
        }, timeout=timeout + 5)

    def send_message(self, chat_id, text, parse_mode="HTML",
                     disable_preview=True):
        # Telegram лимит 4096 символов
        chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
        for chunk in chunks:
            self._call("sendMessage", {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": disable_preview,
            })


# ============================================================
#  Чтение данных
# ============================================================

def load_recent_items(hours=24):
    """Читает все news_*.jsonl из news_history/, возвращает items за N часов."""
    if not HISTORY_DIR.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
    files = sorted(HISTORY_DIR.glob("news_*.jsonl"),
                   key=lambda p: p.stat().st_mtime, reverse=True)

    seen = set()
    items = []
    for path in files:
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        t = datetime.fromisoformat(obj["time"])
                        if t.tzinfo is None:
                            t = t.replace(tzinfo=timezone.utc)
                        if t < cutoff:
                            continue
                        k = obj.get("key")
                        if k and k in seen:
                            continue
                        if k:
                            seen.add(k)
                        obj["time"] = t
                        items.append(obj)
                    except Exception:
                        continue
        except Exception:
            continue
    return items


def load_health():
    if not HEALTH_FILE.exists():
        return {}
    try:
        with open(HEALTH_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ============================================================
#  Команды бота
# ============================================================

def cmd_start(api, chat_id):
    text = (
        "📰 <b>NEWS TERMINAL Bot</b>\n\n"
        "Команды:\n"
        "/latest — последние 10 новостей\n"
        "/breaking — текущие BREAKING\n"
        "/stats — статистика за 24 часа\n"
        "/search &lt;слово&gt; — поиск по заголовкам\n"
        "/sources — состояние источников\n"
        "/help — эта справка"
    )
    api.send_message(chat_id, text)


def cmd_latest(api, chat_id, hours=24, limit=10):
    items = load_recent_items(hours)
    if not items:
        api.send_message(chat_id, "Нет новостей за последние {} ч.".format(hours))
        return
    items.sort(key=lambda x: x["time"], reverse=True)

    lines = ["<b>📰 Последние новости</b>", ""]
    for it in items[:limit]:
        title = it.get("title_ru") or it.get("title", "")
        src = it.get("source", "?")
        ts = it["time"].astimezone().strftime("%H:%M")
        lines.append("• <b>{}</b> [{}] {}".format(ts, src, title[:180]))
    api.send_message(chat_id, "\n".join(lines))


def cmd_breaking(api, chat_id):
    items = load_recent_items(48)
    breaking = [x for x in items if x.get("level") == "BREAKING"]
    if not breaking:
        api.send_message(chat_id, "Активных BREAKING нет.")
        return

    breaking.sort(key=lambda x: x["time"], reverse=True)
    lines = ["<b>⚡ BREAKING</b>", ""]
    for it in breaking[:10]:
        title = it.get("title_ru") or it.get("title", "")
        src = it.get("source", "?")
        ts = it["time"].astimezone().strftime("%H:%M")
        lines.append("⚡ [{}] {} — {}".format(ts, src, title[:180]))
    api.send_message(chat_id, "\n".join(lines))


def cmd_stats(api, chat_id):
    items = load_recent_items(24)
    if not items:
        api.send_message(chat_id, "Нет данных за 24 часа.")
        return

    neg_words = ["смерт", "умер", "погиб", "убийств", "войн", "атак",
                 "взрыв", "теракт", "катастроф", "пожар", "крушени",
                 "ракет", "дрон", "бпла", "чп", "кризис", "угроз"]
    pos_words = ["любов", "семь", "счасть", "радост", "успех", "побед",
                 "достижен", "рекорд", "помощ", "поддержк", "спасен",
                 "открыт", "развит", "рост", "мир", "соглашен"]

    neg = 0
    pos = 0
    for it in items:
        t = (it.get("title_ru") or it.get("title", "")).lower()
        if any(w in t for w in neg_words):
            neg += 1
        if any(w in t for w in pos_words):
            pos += 1

    total = len(items)
    lines = [
        "<b>📊 Статистика за 24 часа</b>",
        "",
        "Всего: {}".format(total),
        "⚠ Негативных: {} ({:.1f}%)".format(neg, 100.0 * neg / max(1, total)),
        "☺ Позитивных: {} ({:.1f}%)".format(pos, 100.0 * pos / max(1, total)),
        "",
    ]
    if neg > pos * 1.5:
        lines.append("→ ПРЕОБЛАДАЮТ НЕГАТИВНЫЕ")
    elif pos > neg * 1.5:
        lines.append("→ ПРЕОБЛАДАЮТ ПОЗИТИВНЫЕ")
    else:
        lines.append("→ БАЛАНС")
    api.send_message(chat_id, "\n".join(lines))


def cmd_search(api, chat_id, query):
    if not query:
        api.send_message(chat_id, "Используйте: /search &lt;слово&gt;")
        return
    q = query.lower()
    items = load_recent_items(24 * 7)
    found = [x for x in items
             if q in (x.get("title_ru") or x.get("title", "")).lower()]
    if not found:
        api.send_message(chat_id, "Ничего не найдено: <b>{}</b>".format(query))
        return
    found.sort(key=lambda x: x["time"], reverse=True)
    lines = ["<b>🔍 Поиск: {}</b> (найдено {})".format(query, len(found)), ""]
    for it in found[:10]:
        title = it.get("title_ru") or it.get("title", "")
        src = it.get("source", "?")
        ts = it["time"].astimezone().strftime("%m-%d %H:%M")
        lines.append("• <b>{}</b> [{}] {}".format(ts, src, title[:180]))
    api.send_message(chat_id, "\n".join(lines))


def cmd_sources(api, chat_id):
    health = load_health()
    results = health.get("results", [])
    if not results:
        api.send_message(chat_id, "Нет данных о состоянии источников.")
        return
    healthy = [r for r in results if r.get("status") == "healthy"]
    failed = [r for r in results if r.get("status") != "healthy"]
    lines = [
        "<b>📡 Источники</b>",
        "",
        "Всего: {}".format(len(results)),
        "✅ Работают: {}".format(len(healthy)),
        "❌ Не работают: {}".format(len(failed)),
        "",
    ]
    if failed:
        lines.append("<b>Проблемные:</b>")
        for r in failed[:15]:
            lines.append("• {} — {}".format(r.get("name", "?"),
                                             r.get("error", "?")))
    api.send_message(chat_id, "\n".join(lines))


def cmd_help(api, chat_id):
    cmd_start(api, chat_id)


# ============================================================
#  Обработчик команд
# ============================================================

HANDLERS = {
    "/start": cmd_start,
    "/help": cmd_help,
    "/latest": cmd_latest,
    "/breaking": cmd_breaking,
    "/stats": cmd_stats,
    "/sources": cmd_sources,
}


def handle_update(api, update, allowed_chat_ids):
    msg = update.get("message")
    if not msg:
        return
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id:
        return

    # Whitelist: если список не пуст — пускать только своих
    if allowed_chat_ids and chat_id not in allowed_chat_ids:
        api.send_message(chat_id, "⛔ Доступ запрещён.")
        return

    if not text:
        return

    if text.startswith("/search"):
        query = text[7:].strip()
        cmd_search(api, chat_id, query)
        return

    handler = HANDLERS.get(text.split()[0])
    if handler:
        handler(api, chat_id)
    else:
        api.send_message(chat_id, "Неизвестная команда. /help")


# ============================================================
#  Точка входа
# ============================================================

def main():
    print("NEWS TERMINAL Bot — запуск")
    cfg = load_telegram_config()
    api = TelegramAPI(cfg["bot_token"])
    allowed = cfg.get("allowed_chat_ids") or []

    print("Бот запущен. Ctrl+C для выхода.")
    if allowed:
        print("Whitelist chat_id:", allowed)
    else:
        print("Whitelist пуст — отвечает всем.")

    offset = 0
    while True:
        try:
            result = api.get_updates(offset=offset, timeout=30)
            if not result.get("ok"):
                time.sleep(5)
                continue
            for update in result.get("result", []):
                offset = update["update_id"] + 1
                try:
                    handle_update(api, update, allowed)
                except Exception as e:
                    print("Ошибка обработки:", e)
        except KeyboardInterrupt:
            print("\nОстановлено.")
            return 0
        except Exception as e:
            print("Ошибка polling:", e)
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())