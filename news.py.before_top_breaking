#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""news.py — ключи, классификация, dedup и живые BREAKING NEWS темы."""

import hashlib
import re
import time
from datetime import datetime, timezone, timedelta

import feedparser

from config import (
    RECLASSIFY_HOURS, FLASH_DURATION, now_utc,
    HOT_TOPIC_MAX, HOT_TOPIC_TTL_SECONDS,
    HOT_TOPIC_HARD_TTL_SECONDS, HOT_TOPIC_MIN_SIMILARITY,
)


# ============================================================
# Parsing
# ============================================================

def parse_entry_time(entry):
    value = entry.get("published_parsed") or entry.get("updated_parsed")
    if value:
        try:
            return datetime(*value[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    for key in ("published", "updated", "created"):
        raw = entry.get(key)
        if raw:
            try:
                parsed = feedparser._parse_date(raw)
                if parsed:
                    return datetime(*parsed[:6], tzinfo=timezone.utc)
            except Exception:
                pass
    return now_utc()


# ============================================================
#  CJK (китайские, японские, корейские иероглифы)
# ============================================================

CJK_RE = re.compile(
    "[" 
    "\u3040-\u30ff"   # хирагана + катакана (японский)
    "\u3400-\u4dbf"   # CJK Extension A
    "\u4e00-\u9fff"   # CJK Unified Ideographs
    "\uf900-\ufaff"   # CJK Compatibility Ideographs
    "\uac00-\ud7af"   # хангыль (корейский)
    "]"
)


def has_cjk(text):
    """True, если в тексте есть CJK-символы."""
    if not text:
        return False
    return bool(CJK_RE.search(text))


def strip_cjk(text):
    """Удаляет CJK-символы из текста (для нормализации/дедупликации)."""
    if not text:
        return ""
    return CJK_RE.sub(" ", text)


# ============================================================
#  Normalization & keys
# ============================================================

def normalize_title(title):
    """
    Нормализует заголовок для дедупликации.
    CJK-иероглифы удаляются — иначе дубли китайских лент не схлопываются.
    """
    title = str(title).lower()
    title = strip_cjk(title)              # ← ключевой фикс
    title = re.sub(r"https?://\S+", " ", title)
    title = re.sub(r"[^\w\sа-яё]", " ", title, flags=re.UNICODE)
    words = [w for w in title.split() if len(w) > 2]
    return " ".join(words[:18])


def source_news_key(source_id, title):
    normalized = normalize_title(title)
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]
    return source_id + ":" + digest


def topic_key(title):
    normalized = normalize_title(title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def is_valid_title(title):
    """
    Отбрасывает мусорные заголовки:
    - пустые;
    - только из CJK (непереводимые);
    - состоящие из одной буквы или символа.
    """
    if not title:
        return False
    title = str(title).strip()
    if len(title) < 3:
        return False
    # Полностью CJK-заголовок без латиницы/кириллицы — бесполезен
    if has_cjk(title) and not re.search(r"[a-zA-Zа-яА-ЯёЁ]", title):
        return False
    return True


# ============================================================
# Classification markers
# ============================================================

STRONG_PHRASES = (
    "СРОЧНО", "МОЛНИЯ", "ЭКСТРЕННО", "BREAKING NEWS", "URGENT NEWS",
    "JUST IN", "FLASH",
    "ТЕРАКТ", "ВЗРЫВ", "ПОЖАР", "ЗЕМЛЕТРЯСЕНИ", "ЦУНАМИ",
    "ЯДЕРН", "РАДИАЦИ", "ХИМАТАК", "ЭВАКУАЦ",
    "EARTHQUAKE", "TSUNAMI", "EXPLOSION",
    "NUCLEAR", "CHEMICAL ATTACK", "EVACUATION",
    "УБИЙСТВО", "ПОКУШЕНИ", "АВАРИЯ", "КАТАСТРОФ", "КРУШЕНИ",
)

STRONG_WORDS = (
    "WAR", "ATTACK", "STRIKE", "MISSILE", "INVASION",
    "BREAKING", "URGENT", "ALERT",
)

ALERT_PHRASES = (
    "ВНИМАНИЕ", "ЭКСТРЕННО", "ОПАСНОСТ", "УГРОЗА",
    "ПРЕДУПРЕЖД", "ОГРАНИЧЕН",
)

ALERT_WORDS = (
    "WARNING", "EMERGENCY", "CRISIS", "ALERT",
)

EMOJI_BREAKING = ("⚡", "❗", "🚨")
EMOJI_ALERT = ("⚠", "🔥")

_STRONG_WORDS_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in STRONG_WORDS) + r")\b"
)
_ALERT_WORDS_RE = re.compile(
    r"\b(" + "|".join(re.escape(w) for w in ALERT_WORDS) + r")\b"
)


NON_BREAKING_SOURCES = {
    "habr", "theverge", "techcrunch", "wired", "arstechnica",
    "engadget", "cointelegraph", "spaceflight", "spacedotcom", "nasa",
}


def classify_item(item, source_count_for_topic, now):
    title = item["title"]
    upper = title.upper()
    score = 0

    if any(p in upper for p in STRONG_PHRASES):
        score += 100
    if any(p in upper for p in ALERT_PHRASES):
        score += 50
    if _STRONG_WORDS_RE.search(upper):
        score += 100
    if _ALERT_WORDS_RE.search(upper):
        score += 50
    if any(e in title for e in EMOJI_BREAKING):
        score += 80
    if any(e in title for e in EMOJI_ALERT):
        score += 40

    letters = [c for c in title if c.isalpha()]
    if len(letters) > 15:
        ratio = sum(1 for c in letters if c.isupper()) / len(letters)
        if ratio > 0.6:
            score += 30

    score += item.get("priority", 50) // 10

    age = (now - item["time"]).total_seconds()
    if age < 300:
        score += 50
    elif age < 900:
        score += 30
    elif age < 3600:
        score += 10

    if source_count_for_topic >= 5:
        score += 80
    elif source_count_for_topic >= 3:
        score += 50
    elif source_count_for_topic >= 2:
        score += 20

    if item.get("source_id") in NON_BREAKING_SOURCES:
        score -= 100

    if score >= 120:
        return "BREAKING"
    if score >= 60:
        return "ALERT"
    return "NORMAL"


def reclassify_recent(history, hours=RECLASSIFY_HOURS):
    now = now_utc()
    cutoff = now - timedelta(hours=hours)

    topic_sources = {}
    for item in history:
        if item["time"] < cutoff:
            continue
        tk = item["topic_key"]
        topic_sources.setdefault(tk, set()).add(item["source_id"])

    for item in history:
        if item["time"] < cutoff:
            continue
        count = len(topic_sources.get(item["topic_key"], set()))
        old_level = item.get("level", "NORMAL")
        new_level = classify_item(item, count, now)
        if new_level != old_level:
            item["level"] = new_level
            if new_level == "BREAKING":
                item["flash_until"] = time.time() + FLASH_DURATION


# ============================================================
# Dedup
# ============================================================

def dedup_by_topic(items):
    by_topic = {}
    for item in items:
        tk = item["topic_key"]
        existing = by_topic.get(tk)
        if existing is None:
            copy = dict(item)
            copy["sources"] = [item["source"]]
            by_topic[tk] = copy
        else:
            if item["source"] not in existing["sources"]:
                existing["sources"].append(item["source"])
            if (item["priority"] > existing["priority"] or
                    (item["priority"] == existing["priority"] and
                     item["time"] > existing["time"])):
                sources_backup = existing["sources"]
                new_copy = dict(item)
                new_copy["sources"] = sources_backup
                by_topic[tk] = new_copy
    return list(by_topic.values())


# ============================================================
# Live BREAKING NEWS board
# ============================================================

_TOPIC_STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "will", "has",
    "have", "into", "after", "over", "says", "said", "new", "news",
    "на", "и", "в", "во", "не", "что", "это", "как", "к", "ко", "из",
    "за", "по", "о", "об", "от", "до", "для", "после", "новые", "новый",
    "сообщил", "сообщила", "сообщает", "стало", "стали", "может", "могут",
}


def _topic_tokens(title):
    # убираем CJK, чтобы не сравнивать иероглифы
    clean = strip_cjk(title).lower()
    words = re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9]{4,}", clean)
    return {w for w in words if w not in _TOPIC_STOPWORDS}


def _topic_similarity(a, b):
    """
    Улучшенная схожесть: требуем минимум 4 общих слова для 0.75,
    иначе считаем относительно ДЛИННОГО заголовка, а не короткого.
    """
    ta = _topic_tokens(a)
    tb = _topic_tokens(b)
    if not ta or not tb:
        return 0.0
    common = ta & tb
    if len(common) >= 4:
        return 0.75
    return len(common) / max(1, max(len(ta), len(tb)))


def _topic_cluster_key(title, existing):
    for cluster in existing:
        similarity = _topic_similarity(title, cluster["representative_title"])
        if similarity >= HOT_TOPIC_MIN_SIMILARITY:
            return cluster["hot_key"]
    normalized = normalize_title(title)
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def build_hot_topics(history, now=None, limit=HOT_TOPIC_MAX):
    if now is None:
        now = now_utc()

    candidates = [
        item for item in history
        if item.get("level") in ("BREAKING", "ALERT")
    ]
    candidates.sort(key=lambda x: x.get("time", now), reverse=True)

    clusters = []
    for item in candidates:
        age = (now - item["time"]).total_seconds()
        if age < 0:
            age = 0
        if age > HOT_TOPIC_HARD_TTL_SECONDS:
            continue

        matched = None
        for cluster in clusters:
            if _topic_similarity(item["title"], cluster["representative_title"]) >= HOT_TOPIC_MIN_SIMILARITY:
                matched = cluster
                break

        if matched is None:
            matched = {
                "hot_key": _topic_cluster_key(item["title"], clusters),
                "representative_title": item["title"],
                "items": [],
                "latest": item,
                "last_update": item["time"],
                "first_seen": item["time"],
                "sources": set(),
                "level": item.get("level", "ALERT"),
            }
            clusters.append(matched)

        matched["items"].append(item)
        matched["sources"].add(item.get("source_id", ""))
        if item["time"] > matched["last_update"]:
            matched["last_update"] = item["time"]
            matched["latest"] = item
            matched["representative_title"] = item["title"]
        if item["time"] < matched["first_seen"]:
            matched["first_seen"] = item["time"]
        if item.get("level") == "BREAKING":
            matched["level"] = "BREAKING"

    active = []
    for cluster in clusters:
        silence = (now - cluster["last_update"]).total_seconds()
        lifetime = (now - cluster["first_seen"]).total_seconds()
        if silence > HOT_TOPIC_TTL_SECONDS or lifetime > HOT_TOPIC_HARD_TTL_SECONDS:
            continue

        latest = cluster["latest"]
        age = (now - latest["time"]).total_seconds()
        freshness = max(0, 100 - int(age / 10))
        source_bonus = min(40, len(cluster["sources"]) * 10)
        level_bonus = 80 if cluster["level"] == "BREAKING" else 35
        priority_bonus = int(latest.get("priority", 50)) // 5
        score = freshness + source_bonus + level_bonus + priority_bonus

        active.append({
            "hot_key": cluster["hot_key"],
            "item": latest,
            "items": cluster["items"],
            "level": cluster["level"],
            "source_count": len(cluster["sources"]),
            "sources": sorted(x for x in cluster["sources"] if x),
            "first_seen": cluster["first_seen"],
            "last_update": cluster["last_update"],
            "silence_seconds": int(silence),
            "score": score,
            "updates": len(cluster["items"]),
        })

    active.sort(key=lambda x: (x["score"], x["last_update"]), reverse=True)
    return active[:limit]