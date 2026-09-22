#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tg_bot.py — Telegram-бот для NEWS TERMINAL.

Роли:
- OWNER (owner_id) — все команды + admin + push
- USER (allowed_chat_ids) — только чтение
- ОСТАЛЬНЫЕ — отказ

Функции:
- команды чтения (/latest, /breaking, /stats, /search, /sources)
- admin (/admin, /users, /adduser, /removeuser, /stats_admin, /log)
- push при BREAKING в отдельном потоке
- автодайджест раз в день (опционально)
"""

import json
import os
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ============================================================
#  Часовой пояс
# ============================================================

TIMEZONE_OFFSET_HOURS = 3
LOCAL_TZ = timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS))


# ============================================================
#  Пути
# ============================================================

BASE = Path(__file__).resolve().parent
CONFIG_FILE = BASE / "config" / "telegram.json"
DATA_DIR = BASE / "data"
HISTORY_DIR = BASE / "news_history"
HEALTH_FILE = DATA_DIR / "source_health.json"
BOT_LOG = DATA_DIR / "tg_bot.log"
PUSH_STATE = DATA_DIR / "push_state.json"


# ============================================================
#  Логирование
# ============================================================

def log(msg):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(BOT_LOG, "a", encoding="utf-8") as f:
            f.write("{} | {}\n".format(
                datetime.now(timezone.utc).isoformat(), msg))
    except Exception:
        pass
    print("[LOG] " + str(msg), flush=True)


# ============================================================
#  Конфиг
# ============================================================

def load_config():
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    ids = data.get("allowed_chat_ids", [])
    if isinstance(ids, int):
        ids = [ids]
    elif isinstance(ids, str):
        ids = [int(x.strip()) for x in ids.split(",")
               if x.strip().lstrip("-").isdigit()]
    data["allowed_chat_ids"] = [int(x) for x in ids]

    if not data.get("owner_id") and data["allowed_chat_ids"]:
        data["owner_id"] = data["allowed_chat_ids"][0]

    # Значения по умолчанию
    data.setdefault("push_enabled", True)
    data.setdefault("push_breaking", True)
    data.setdefault("push_alert", False)
    data.setdefault("push_throttle_seconds", 300)
    data.setdefault("push_check_interval", 30)
    data.setdefault("daily_digest", False)
    data.setdefault("daily_digest_hour", 9)

    return data


def save_config(config):
    tmp = CONFIG_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_FILE)


# ============================================================
#  Telegram API
# ============================================================

def api(token, method, params=None, timeout=35):
    url = "https://api.telegram.org/bot{}/{}".format(token, method)
    if params:
        data = json.dumps(params).encode("utf-8")
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def send(token, chat_id, text, preview=False):
    chunks = [text[i:i + 4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        try:
            r = api(token, "sendMessage", {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": "HTML",
                "disable_web_page_preview": not preview,
            })
            if not r.get("ok"):
                log("sendMessage failed: {}".format(r.get("description")))
        except Exception as e:
            log("sendMessage error: {}".format(e))


# ============================================================
#  Чтение данных
# ============================================================

def load_items(hours=24):
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


def esc(text):
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;"))


def title_of(item):
    return item.get("title_ru") or item.get("title", "")


def fmt_time(item, fmt="%H:%M"):
    try:
        return item["time"].astimezone(LOCAL_TZ).strftime(fmt)
    except Exception:
        return "??:??"


# ============================================================
#  PUSH STATE — что уже отправлено
# ============================================================

def load_push_state():
    if not PUSH_STATE.exists():
        return {"sent_keys": [], "throttle": {}}
    try:
        with open(PUSH_STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"sent_keys": [], "throttle": {}}


def save_push_state(state):
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = PUSH_STATE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        tmp.replace(PUSH_STATE)
    except Exception as e:
        log("save_push_state error: {}".format(e))


# ============================================================
#  PUSHER — отдельный поток
# ============================================================

class Pusher:
    """
    Отдельный поток: проверяет news_history/ раз в N секунд,
    отправляет новые BREAKING/ALERT владельцу.
    """

    def __init__(self, token, config):
        self.token = token
        self.config = config
        self.stop_event = threading.Event()
        self.thread = None
        self.state = load_push_state()

        # Ограничим sent_keys — хранить последние 2000
        if len(self.state.get("sent_keys", [])) > 2000:
            self.state["sent_keys"] = self.state["sent_keys"][-2000:]

    def start(self):
        if not self.config.get("push_enabled", True):
            log("Pusher: disabled (push_enabled=false)")
            return
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()
        log("Pusher: started")

    def stop(self):
        self.stop_event.set()

    def _should_send(self, item):
        """Решает, отправлять ли push для этого item."""
        # 1. Проверка уровня
        level = item.get("level", "NORMAL")
        if level == "BREAKING" and self.config.get("push_breaking", True):
            pass
        elif level == "ALERT" and self.config.get("push_alert", False):
            pass
        else:
            return False

        # 2. Уже отправляли?
        key = item.get("key")
        if not key:
            return False
        if key in self.state.get("sent_keys", []):
            return False

        # 3. Throttle по topic_key
        topic = item.get("topic_key", "")
        throttle_sec = int(self.config.get("push_throttle_seconds", 300))
        if topic:
            last_sent = self.state.get("throttle", {}).get(topic, 0)
            if time.time() - last_sent < throttle_sec:
                return False

        return True

    def _send_push(self, item):
        """Отправляет push владельцу."""
        owner = self.config.get("owner_id", 0)
        if not owner:
            return

        level = item.get("level", "NORMAL")
        title = title_of(item)
        source = item.get("source", "?")
        ts = fmt_time(item)
        key = item.get("key")
        topic = item.get("topic_key", "")

        if level == "BREAKING":
            marker = "⚡ <b>BREAKING</b>"
        else:
            marker = "⚠ <b>ALERT</b>"

        text = (
            "{}\n\n"
            "🕐 {}  📰 <b>{}</b>\n\n"
            "{}"
        ).format(marker, ts, esc(source), esc(title[:400]))

        send(self.token, owner, text)

        # Обновить state
        if key:
            self.state.setdefault("sent_keys", []).append(key)
            if len(self.state["sent_keys"]) > 2000:
                self.state["sent_keys"] = self.state["sent_keys"][-2000:]

        if topic:
            self.state.setdefault("throttle", {})[topic] = time.time()

        save_push_state(self.state)
        log("PUSH sent: {} | {}".format(level, title[:80]))

    def _loop(self):
        interval = int(self.config.get("push_check_interval", 30))

        while not self.stop_event.is_set():
            try:
                # Читаем новые items за последние 30 минут
                items = load_items(0.5)
                items.sort(key=lambda x: x["time"])

                sent_count = 0
                for item in items:
                    if self._should_send(item):
                        self._send_push(item)
                        sent_count += 1
                        if sent_count >= 5:
                            # не более 5 push за один цикл
                            break
                        time.sleep(0.5)

                # Очистить старый throttle (старше 1 часа)
                now = time.time()
                self.state["throttle"] = {
                    k: v for k, v in self.state.get("throttle", {}).items()
                    if now - v < 3600
                }
                save_push_state(self.state)

            except Exception as e:
                log("Pusher error: {}".format(e))

            self.stop_event.wait(interval)


# ============================================================
#  Команды
# ============================================================

def cmd_start(token, chat_id, is_owner):
    lines = ["📰 <b>NEWS TERMINAL Bot</b>", "", "<b>Доступные команды:</b>",
             "  /latest — последние 10 новостей",
             "  /breaking — активные BREAKING",
             "  /stats — статистика за 24 часа",
             "  /search &lt;слово&gt; — поиск по заголовкам",
             "  /sources — состояние источников",
             "  /menu — показать меню",
             "  /help — справка"]
    if is_owner:
        lines.extend([
            "",
            "👑 <b>Вы владелец.</b>",
            "  /admin — админ-меню",
            "  /push — управление push-уведомлениями",
        ])
    send(token, chat_id, "\n".join(lines))


def cmd_admin(token, chat_id):
    send(token, chat_id,
         "👑 <b>Администратор</b>\n\n"
         "<b>Управление пользователями:</b>\n"
         "  /users — список пользователей\n"
         "  /adduser &lt;id&gt; — добавить\n"
         "  /removeuser &lt;id&gt; — удалить\n"
         "\n"
         "<b>Управление ботом:</b>\n"
         "  /push — статус push\n"
         "  /push_on — включить push\n"
         "  /push_off — выключить push\n"
         "  /stats_admin — расширенная статистика\n"
         "  /log — последние логи")


def cmd_users(token, chat_id, config):
    allowed = config["allowed_chat_ids"]
    owner = config.get("owner_id", 0)
    lines = ["<b>👥 Пользователи бота</b>", ""]
    for i, uid in enumerate(allowed, 1):
        mark = " 👑" if uid == owner else ""
        lines.append("{}. <code>{}</code>{}".format(i, uid, mark))
    lines.append("")
    lines.append("Всего: {}".format(len(allowed)))
    send(token, chat_id, "\n".join(lines))


def cmd_adduser(token, chat_id, config, arg):
    if not arg or not arg.strip().lstrip("-").isdigit():
        send(token, chat_id, "Используйте: <code>/adduser 123456789</code>")
        return
    new_id = int(arg.strip())
    if new_id in config["allowed_chat_ids"]:
        send(token, chat_id, "⚠️ Пользователь <code>{}</code> уже в списке.".format(new_id))
        return
    config["allowed_chat_ids"].append(new_id)
    save_config(config)
    log("OWNER {} added user {}".format(chat_id, new_id))
    send(token, chat_id,
         "✅ Пользователь <code>{}</code> добавлен.\n\n"
         "Теперь в whitelist: {}.".format(
             new_id, len(config["allowed_chat_ids"])))


def cmd_removeuser(token, chat_id, config, arg):
    if not arg or not arg.strip().lstrip("-").isdigit():
        send(token, chat_id, "Используйте: <code>/removeuser 123456789</code>")
        return
    rid = int(arg.strip())
    owner = config.get("owner_id", 0)
    if rid == owner:
        send(token, chat_id, "❌ Нельзя удалить владельца.")
        return
    if rid not in config["allowed_chat_ids"]:
        send(token, chat_id, "⚠️ Пользователь <code>{}</code> не найден.".format(rid))
        return
    config["allowed_chat_ids"].remove(rid)
    save_config(config)
    log("OWNER {} removed user {}".format(chat_id, rid))
    send(token, chat_id,
         "✅ Пользователь <code>{}</code> удалён.\n\n"
         "Осталось: {}.".format(rid, len(config["allowed_chat_ids"])))


def cmd_push_status(token, chat_id, config):
    enabled = config.get("push_enabled", True)
    breaking = config.get("push_breaking", True)
    alert = config.get("push_alert", False)
    throttle = config.get("push_throttle_seconds", 300)
    interval = config.get("push_check_interval", 30)

    status = "✅ ВКЛЮЧЁН" if enabled else "❌ ВЫКЛЮЧЕН"
    lines = [
        "<b>🔔 Push-уведомления</b>",
        "",
        "Статус: {}".format(status),
        "BREAKING: {}".format("✅" if breaking else "❌"),
        "ALERT: {}".format("✅" if alert else "❌"),
        "Throttle: {} сек".format(throttle),
        "Проверка: раз в {} сек".format(interval),
        "",
        "<b>Команды:</b>",
        "/push_on — включить push",
        "/push_off — выключить push",
    ]
    send(token, chat_id, "\n".join(lines))


def cmd_push_on(token, chat_id, config):
    config["push_enabled"] = True
    save_config(config)
    send(token, chat_id, "✅ Push-уведомления <b>включены</b>.")


def cmd_push_off(token, chat_id, config):
    config["push_enabled"] = False
    save_config(config)
    send(token, chat_id, "❌ Push-уведомления <b>выключены</b>.")


def cmd_latest(token, chat_id):
    items = load_items(24)
    if not items:
        send(token, chat_id, "📭 Нет новостей за последние 24 часа.")
        return
    items.sort(key=lambda x: x["time"], reverse=True)
    lines = ["<b>📰 Последние новости</b>", ""]
    for it in items[:10]:
        ts = fmt_time(it)
        src = esc(it.get("source", "?"))
        title = esc(title_of(it)[:200])
        lines.append("• <b>{}</b> [{}] {}".format(ts, src, title))
    lines.append("")
    lines.append("Всего за 24ч: {}".format(len(items)))
    send(token, chat_id, "\n".join(lines))


def cmd_breaking(token, chat_id):
    items = load_items(48)
    br = [x for x in items if x.get("level") == "BREAKING"]
    if not br:
        send(token, chat_id, "😌 Активных BREAKING нет.")
        return
    br.sort(key=lambda x: x["time"], reverse=True)
    lines = ["<b>⚡ BREAKING</b>", ""]
    for it in br[:10]:
        ts = fmt_time(it)
        src = esc(it.get("source", "?"))
        title = esc(title_of(it)[:200])
        lines.append("⚡ <b>{}</b> [{}] {}".format(ts, src, title))
    send(token, chat_id, "\n".join(lines))


def cmd_stats(token, chat_id):
    items = load_items(24)
    if not items:
        send(token, chat_id, "📭 Нет данных за 24 часа.")
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
        t = title_of(it).lower()
        if any(w in t for w in neg_words):
            neg += 1
        if any(w in t for w in pos_words):
            pos += 1

    total = len(items)
    breaking = sum(1 for x in items if x.get("level") == "BREAKING")
    alert = sum(1 for x in items if x.get("level") == "ALERT")

    lines = [
        "<b>📊 Статистика за 24 часа</b>",
        "",
        "Всего: {}".format(total),
        "⚡ BREAKING: {}".format(breaking),
        "⚠ ALERT: {}".format(alert),
        "",
        "⚠ Негативных: {} ({:.1f}%)".format(
            neg, 100.0 * neg / max(1, total)),
        "☺ Позитивных: {} ({:.1f}%)".format(
            pos, 100.0 * pos / max(1, total)),
        "",
    ]
    if neg > pos * 1.5:
        lines.append("→ <b>ПРЕОБЛАДАЮТ НЕГАТИВНЫЕ</b>")
    elif pos > neg * 1.5:
        lines.append("→ <b>ПРЕОБЛАДАЮТ ПОЗИТИВНЫЕ</b>")
    else:
        lines.append("→ <b>БАЛАНС</b>")
    send(token, chat_id, "\n".join(lines))


def cmd_search(token, chat_id, query):
    if not query:
        send(token, chat_id, "Используйте: <code>/search Путин</code>")
        return
    q = query.lower()
    items = load_items(24 * 7)
    found = [x for x in items if q in title_of(x).lower()]
    if not found:
        send(token, chat_id, "🔍 Ничего не найдено: <b>{}</b>".format(esc(query)))
        return
    found.sort(key=lambda x: x["time"], reverse=True)
    lines = ["<b>🔍 Поиск: {}</b> (найдено {})".format(esc(query), len(found)), ""]
    for it in found[:15]:
        ts = fmt_time(it, "%m-%d %H:%M")
        src = esc(it.get("source", "?"))
        title = esc(title_of(it)[:180])
        lines.append("• <b>{}</b> [{}] {}".format(ts, src, title))
    send(token, chat_id, "\n".join(lines))


def cmd_sources(token, chat_id):
    health = load_health()
    results = health.get("results", [])
    if not results:
        send(token, chat_id, "Нет данных о состоянии источников.")
        return
    healthy = [r for r in results if r.get("status") == "healthy"]
    failed = [r for r in results if r.get("status") != "healthy"]

    lines = [
        "<b>📡 Источники</b>",
        "",
        "Всего: {}".format(len(results)),
        "✅ Работают: {}".format(len(healthy)),
        "❌ Не работают: {}".format(len(failed)),
    ]
    if failed:
        lines.append("")
        lines.append("<b>Проблемные:</b>")
        for r in failed[:15]:
            name = esc(r.get("name", "?")[:30])
            err = esc(r.get("error", "?")[:40])
            lines.append("• {} — {}".format(name, err))
    send(token, chat_id, "\n".join(lines))


def cmd_stats_admin(token, chat_id):
    items_24 = load_items(24)
    items_7d = load_items(24 * 7)
    health = load_health()
    results = health.get("results", [])
    healthy = sum(1 for r in results if r.get("status") == "healthy")

    push_state = load_push_state()
    sent_count = len(push_state.get("sent_keys", []))

    lines = [
        "<b>📊 Статистика администратора</b>",
        "",
        "<b>Новости:</b>",
        "  За 24ч: {}".format(len(items_24)),
        "  За 7 дней: {}".format(len(items_7d)),
        "  ⚡ BREAKING 24ч: {}".format(
            sum(1 for x in items_24 if x.get("level") == "BREAKING")),
        "  ⚠ ALERT 24ч: {}".format(
            sum(1 for x in items_24 if x.get("level") == "ALERT")),
        "",
        "<b>Источники:</b>",
        "  Всего: {}".format(len(results)),
        "  ✅ Работают: {}".format(healthy),
        "  ❌ Не работают: {}".format(len(results) - healthy),
        "",
        "<b>Push:</b>",
        "  Отправлено всего: {}".format(sent_count),
        "",
        "<b>Файлы:</b>",
        "  news_history/: {} файлов".format(
            len(list(HISTORY_DIR.glob("news_*.jsonl")))
            if HISTORY_DIR.exists() else 0),
    ]
    send(token, chat_id, "\n".join(lines))


def cmd_log(token, chat_id, lines_count=25):
    if not BOT_LOG.exists():
        send(token, chat_id, "Лог пуст.")
        return
    try:
        with open(BOT_LOG, "r", encoding="utf-8") as f:
            lines = f.readlines()[-lines_count:]
        text = "".join(lines)
        send(token, chat_id,
             "<b>Последние {} строк:</b>\n\n<pre>{}</pre>".format(
                 len(lines), esc(text[:3500])))
    except Exception as e:
        send(token, chat_id, "Ошибка чтения: {}".format(esc(str(e))))


def cmd_menu(token, chat_id, is_owner):
    if is_owner:
        cmd_admin(token, chat_id)
    else:
        cmd_start(token, chat_id, False)


# ============================================================
#  Обработчик
# ============================================================

ADMIN_CMDS = {"/admin", "/users", "/adduser", "/removeuser",
              "/stats_admin", "/log",
              "/push", "/push_on", "/push_off"}


def handle(token, update, config):
    msg = update.get("message")
    if not msg:
        return
    chat_id = msg.get("chat", {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id:
        return

    allowed = config["allowed_chat_ids"]
    owner = config.get("owner_id", 0)
    is_owner = (chat_id == owner)

    print("[HANDLE] chat={} text={!r}".format(chat_id, text[:60]), flush=True)

    if allowed and chat_id not in allowed:
        log("ACCESS DENIED for {}".format(chat_id))
        send(token, chat_id, "⛔ Доступ запрещён.")
        return

    if not text:
        return

    parts = text.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    # ADMIN-команды
    if cmd in ADMIN_CMDS:
        if not is_owner:
            log("OWNER-CMD DENIED: {} tried {}".format(chat_id, cmd))
            send(token, chat_id, "⛔ Только владелец.")
            return
        if cmd == "/admin":
            cmd_admin(token, chat_id)
        elif cmd == "/users":
            cmd_users(token, chat_id, config)
        elif cmd == "/adduser":
            cmd_adduser(token, chat_id, config, arg)
        elif cmd == "/removeuser":
            cmd_removeuser(token, chat_id, config, arg)
        elif cmd == "/stats_admin":
            cmd_stats_admin(token, chat_id)
        elif cmd == "/log":
            cmd_log(token, chat_id)
        elif cmd == "/push":
            cmd_push_status(token, chat_id, config)
        elif cmd == "/push_on":
            cmd_push_on(token, chat_id, config)
        elif cmd == "/push_off":
            cmd_push_off(token, chat_id, config)
        return

    # Обычные
    if cmd in ("/start", "/help"):
        cmd_start(token, chat_id, is_owner)
    elif cmd == "/menu":
        cmd_menu(token, chat_id, is_owner)
    elif cmd == "/latest":
        cmd_latest(token, chat_id)
    elif cmd == "/breaking":
        cmd_breaking(token, chat_id)
    elif cmd == "/stats":
        cmd_stats(token, chat_id)
    elif cmd == "/search":
        cmd_search(token, chat_id, arg)
    elif cmd == "/sources":
        cmd_sources(token, chat_id)
    else:
        send(token, chat_id, "Неизвестная команда. /help")


# ============================================================
#  Main
# ============================================================

def main():
    print("=== BOT START ===", flush=True)
    config = load_config()
    token = config["bot_token"]
    owner = config.get("owner_id", 0)
    allowed = config["allowed_chat_ids"]

    print("Owner:", owner, flush=True)
    print("Allowed:", allowed, flush=True)
    print("Push:", config.get("push_enabled"), flush=True)
    log("Bot started. owner={} users={} push={}".format(
        owner, len(allowed), config.get("push_enabled")))

    # Запустить pusher
    pusher = Pusher(token, config)
    pusher.start()

    # Сбросить старые апдейты
    try:
        r = api(token, "getUpdates", {"offset": -1}, timeout=10)
        updates = r.get("result", [])
        if updates:
            last = updates[-1]["update_id"]
            api(token, "getUpdates", {"offset": last + 1}, timeout=10)
            print("Cleared updates up to", last, flush=True)
    except Exception as e:
        print("Clear error:", e, flush=True)

    offset = 0
    print("Listening...", flush=True)

    try:
        while True:
            try:
                r = api(token, "getUpdates",
                        {"offset": offset, "timeout": 20},
                        timeout=30)
                if not r.get("ok"):
                    time.sleep(5)
                    continue

                for u in r.get("result", []):
                    offset = u["update_id"] + 1
                    try:
                        handle(token, u, config)
                    except Exception as e:
                        print("[HANDLE] error:", e, flush=True)
                        log("handle error: {}".format(e))
            except KeyboardInterrupt:
                print("\nStopped.", flush=True)
                break
            except Exception as e:
                print("[POLL] error:", e, flush=True)
                log("polling error: {}".format(e))
                time.sleep(5)
    finally:
        pusher.stop()
        return 0


if __name__ == "__main__":
    sys.exit(main())