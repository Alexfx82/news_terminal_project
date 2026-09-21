#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg_bot.py — Telegram-бот для NEWS TERMINAL.

Роли:
- OWNER (владелец, config.owner_id) — все команды + admin
- USER (в allowed_chat_ids) — только чтение
- ОСТАЛЬНЫЕ — отказ
"""

import json
import sys
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
#  Пути
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
CONFIG_DIR = BASE_DIR / "config"
DATA_DIR = BASE_DIR / "data"
HISTORY_DIR = BASE_DIR / "news_history"
TELEGRAM_CONFIG = CONFIG_DIR / "telegram.json"
HEALTH_FILE = DATA_DIR / "source_health.json"
BOT_LOG = DATA_DIR / "tg_bot.log"


# ============================================================
#  Логирование
# ============================================================

def _log(msg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(BOT_LOG, "a", encoding="utf-8") as f:
            f.write("{} | {}\n".format(
                datetime.now(timezone.utc).isoformat(), msg))
    except Exception:
        pass


# ============================================================
#  Конфиг
# ============================================================

def _normalize_ids(value):
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, str):
        out = []
        for x in value.split(","):
            x = x.strip()
            if x.lstrip("-").isdigit():
                out.append(int(x))
        return out
    if isinstance(value, list):
        return [int(x) for x in value if str(x).lstrip("-").isdigit()]
    return []


def load_telegram_config():
    if not TELEGRAM_CONFIG.exists():
        TELEGRAM_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        template = {
            "bot_token": "",
            "owner_id": 0,
            "allowed_chat_ids": [],
            "enabled": True,
            "daily_digest": False,
            "daily_digest_hour": 9,
        }
        with open(TELEGRAM_CONFIG, "w", encoding="utf-8") as f:
            json.dump(template, f, ensure_ascii=False, indent=2)
        print("Создан шаблон:", TELEGRAM_CONFIG)
        sys.exit(1)

    try:
        with open(TELEGRAM_CONFIG, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        print("Ошибка чтения telegram.json:", e)
        sys.exit(1)

    if not data.get("bot_token"):
        print("bot_token пуст:", TELEGRAM_CONFIG)
        sys.exit(1)

    data["allowed_chat_ids"] = _normalize_ids(data.get("allowed_chat_ids"))

    owner = data.get("owner_id")
    if isinstance(owner, int) and owner != 0:
        pass
    elif data["allowed_chat_ids"]:
        data["owner_id"] = data["allowed_chat_ids"][0]
        save_telegram_config(data)
    else:
        data["owner_id"] = 0

    return data


def save_telegram_config(data):
    tmp = TELEGRAM_CONFIG.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(TELEGRAM_CONFIG)


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
                headers={"Content-Type": "application/json"})
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
#  РЕЕСТР КОМАНД
# ============================================================

USER_COMMANDS = {
    "/help":     "❓ Справка",
    "/menu":     "📋 Показать меню",
    "/latest":   "🆕 Последние 10 новостей",
    "/breaking": "⚡ Активные BREAKING",
    "/stats":    "📊 Статистика за 24 часа",
    "/search":   "🔍 Поиск: /search <слово>",
    "/sources":  "📡 Состояние источников",
}

ADMIN_COMMANDS = {
    "/admin":       "👑 Меню администратора",
    "/users":       "👥 Список пользователей",
    "/adduser":     "➕ Добавить: /adduser <id>",
    "/removeuser":  "➖ Удалить: /removeuser <id>",
    "/stats_admin": "📊 Расширенная статистика",
    "/log":         "📜 Последние логи",
}


# ============================================================
#  Команды
# ============================================================

def cmd_start(api, chat_id, is_owner=False):
    lines = ["📰 <b>NEWS TERMINAL Bot</b>", ""]
    lines.append("<b>Доступные команды:</b>")
    for cmd, desc in USER_COMMANDS.items():
        lines.append("  {} — {}".format(cmd, desc))
    if is_owner:
        lines.append("")
        lines.append("👑 <b>Вы владелец бота.</b>")
        lines.append("Используйте /admin для управления.")
    api.send_message(chat_id, "\n".join(lines))


def cmd_menu(api, chat_id, is_owner=False):
    if is_owner:
        cmd_admin(api, chat_id)
    else:
        cmd_start(api, chat_id, is_owner=False)


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
    neg = sum(1 for it in items if any(
        w in (it.get("title_ru") or it.get("title", "")).lower()
        for w in neg_words))
    pos = sum(1 for it in items if any(
        w in (it.get("title_ru") or it.get("title", "")).lower()
        for w in pos_words))
    total = len(items)
    lines = [
        "<b>📊 Статистика за 24 часа</b>", "",
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
        "<b>📡 Источники</b>", "",
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


# ---------- Администраторские ----------

def cmd_admin(api, chat_id):
    lines = ["👑 <b>Администратор</b>", ""]
    lines.append("<b>Управление пользователями:</b>")
    for cmd in ("/users", "/adduser", "/removeuser"):
        lines.append("  {} — {}".format(cmd, ADMIN_COMMANDS[cmd]))
    lines.append("")
    lines.append("<b>Управление ботом:</b>")
    for cmd in ("/stats_admin", "/log"):
        lines.append("  {} — {}".format(cmd, ADMIN_COMMANDS[cmd]))
    api.send_message(chat_id, "\n".join(lines))


def cmd_users(api, chat_id, config):
    ids = config["allowed_chat_ids"]
    owner = config.get("owner_id", 0)
    lines = ["<b>👥 Пользователи бота</b>", ""]
    for i, uid in enumerate(ids, 1):
        mark = " 👑" if uid == owner else ""
        lines.append("{}. <code>{}</code>{}".format(i, uid, mark))
    lines.append("")
    lines.append("Всего: {}".format(len(ids)))
    api.send_message(chat_id, "\n".join(lines))


def cmd_adduser(api, chat_id, config, arg):
    if not arg or not arg.strip().lstrip("-").isdigit():
        api.send_message(chat_id,
                         "Используйте: /adduser &lt;id&gt;\n"
                         "Пример: <code>/adduser 123456789</code>")
        return
    new_id = int(arg.strip())
    if new_id in config["allowed_chat_ids"]:
        api.send_message(chat_id,
                         "⚠️ Пользователь <code>{}</code> уже в списке.".format(new_id))
        return
    config["allowed_chat_ids"].append(new_id)
    save_telegram_config(config)
    _log("OWNER {} added user {}".format(chat_id, new_id))
    api.send_message(
        chat_id,
        "✅ Пользователь <code>{}</code> добавлен.\n\n"
        "Теперь в whitelist: {}.".format(
            new_id, len(config["allowed_chat_ids"])))


def cmd_removeuser(api, chat_id, config, arg):
    if not arg or not arg.strip().lstrip("-").isdigit():
        api.send_message(chat_id, "Используйте: /removeuser &lt;id&gt;")
        return
    new_id = int(arg.strip())
    owner = config.get("owner_id", 0)
    if new_id == owner:
        api.send_message(chat_id, "❌ Нельзя удалить владельца.")
        return
    if new_id not in config["allowed_chat_ids"]:
        api.send_message(chat_id,
                         "⚠️ Пользователь <code>{}</code> не найден.".format(new_id))
        return
    config["allowed_chat_ids"].remove(new_id)
    save_telegram_config(config)
    _log("OWNER {} removed user {}".format(chat_id, new_id))
    api.send_message(
        chat_id,
        "✅ Пользователь <code>{}</code> удалён.\n\n"
        "Осталось: {}.".format(
            new_id, len(config["allowed_chat_ids"])))


def cmd_admin_stats(api, chat_id):
    items = load_recent_items(24)
    health = load_health()
    results = health.get("results", [])
    healthy = sum(1 for r in results if r.get("status") == "healthy")
    failed = len(results) - healthy
    breaking = sum(1 for x in items if x.get("level") == "BREAKING")
    alert = sum(1 for x in items if x.get("level") == "ALERT")
    lines = [
        "📊 <b>Статистика администратора</b>", "",
        "<b>Новости (24ч):</b>",
        "  Всего: {}".format(len(items)),
        "  ⚡ BREAKING: {}".format(breaking),
        "  ⚠ ALERT: {}".format(alert),
        "",
        "<b>Источники:</b>",
        "  Всего: {}".format(len(results)),
        "  ✅ Работают: {}".format(healthy),
        "  ❌ Не работают: {}".format(failed),
    ]
    api.send_message(chat_id, "\n".join(lines))


def cmd_admin_log(api, chat_id, lines_count=20):
    if not BOT_LOG.exists():
        api.send_message(chat_id, "Лог пуст.")
        return
    try:
        with open(BOT_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()[-lines_count:]
        text = "".join(lines)
        api.send_message(chat_id,
                         "<b>Последние {} строк:</b>\n\n<pre>{}</pre>".format(
                             len(lines), text[:3500]))
    except Exception as e:
        api.send_message(chat_id, "Ошибка чтения лога: {}".format(e))


# ============================================================
#  Обработчик
# ============================================================

def handle_update(api, update, config):
    msg = update.get("message")
    if not msg:
        return

    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()

    if not chat_id:
        return

    allowed = config["allowed_chat_ids"]
    owner_id = config.get("owner_id", 0)
    is_owner = (chat_id == owner_id)

    if allowed and chat_id not in allowed:
        api.send_message(chat_id, "⛔ Доступ запрещён.")
        _log("ACCESS DENIED for {}".format(chat_id))
        return

    if not text:
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # ADMIN-команды — только владелец
    if cmd in ADMIN_COMMANDS:
        if not is_owner:
            api.send_message(chat_id,
                             "⛔ Эта команда доступна только владельцу.")
            _log("OWNER-CMD DENIED: user {} tried {}".format(chat_id, cmd))
            return
        if cmd == "/admin":
            cmd_admin(api, chat_id)
        elif cmd == "/users":
            cmd_users(api, chat_id, config)
        elif cmd == "/adduser":
            cmd_adduser(api, chat_id, config, arg)
        elif cmd == "/removeuser":
            cmd_removeuser(api, chat_id, config, arg)
        elif cmd == "/stats_admin":
            cmd_admin_stats(api, chat_id)
        elif cmd == "/log":
            cmd_admin_log(api, chat_id)
        return

    # Обычные команды
    if cmd == "/start":
        cmd_start(api, chat_id, is_owner=is_owner)
    elif cmd in ("/help", "/menu"):
        cmd_menu(api, chat_id, is_owner=is_owner)
    elif cmd == "/latest":
        cmd_latest(api, chat_id)
    elif cmd == "/breaking":
        cmd_breaking(api, chat_id)
    elif cmd == "/stats":
        cmd_stats(api, chat_id)
    elif cmd == "/search":
        cmd_search(api, chat_id, arg)
    elif cmd == "/sources":
        cmd_sources(api, chat_id)
    else:
        api.send_message(chat_id, "Неизвестная команда. /help")


# ============================================================
#  Точка входа
# ============================================================

def main():
    print("NEWS TERMINAL Bot — запуск")
    config = load_telegram_config()
    api = TelegramAPI(config["bot_token"])
    owner_id = config.get("owner_id", 0)
    allowed = config["allowed_chat_ids"]

    print("Owner ID: {}".format(owner_id))
    print("Allowed users: {}".format(len(allowed)))
    for uid in allowed:
        mark = " 👑" if uid == owner_id else ""
        print("  • {}{}".format(uid, mark))

    print("Бот запущен. Ctrl+C для выхода.")
    _log("Bot started. owner={} users={}".format(owner_id, len(allowed)))

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
                    handle_update(api, update, config)
                except Exception as e:
                    print("Ошибка обработки:", e)
                    _log("handle_update error: {}".format(e))
        except KeyboardInterrupt:
            print("\nОстановлено.")
            return 0
        except Exception as e:
            print("Ошибка polling:", e)
            _log("polling error: {}".format(e))
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())