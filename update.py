#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
update.py — проверка и установка обновлений из Git.

Логика:
- check_for_updates() — узнать, есть ли новые коммиты на GitHub
- apply_update() — выполнить git pull, pip install, перезапустить сервисы

Безопасность:
- не трогает data/, news_history/, config/telegram.json
- сохраняет локальные изменения через git stash
- перезапускает сервисы через systemctl
"""

import subprocess
from pathlib import Path

from config import BASE_DIR


def _run(cmd, cwd=None, timeout=60):
    """Выполняет команду, возвращает (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd, cwd=cwd or BASE_DIR, capture_output=True,
            text=True, timeout=timeout
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", "TIMEOUT"
    except Exception as e:
        return -1, "", str(e)


def _git(*args, timeout=30):
    return _run(["git"] + list(args), timeout=timeout)


# ============================================================
#  Проверка обновлений
# ============================================================

def check_for_updates():
    """
    Проверяет, есть ли новые коммиты в origin/main.
    Возвращает dict со статусом.
    """
    result = {
        "ok": False, "available": False,
        "local_sha": "", "remote_sha": "",
        "local_msg": "", "remote_msg": "",
        "behind": 0,
        "error": None,
    }

    # 1. Есть ли git-репозиторий?
    rc, _, err = _git("rev-parse", "--is-inside-work-tree")
    if rc != 0:
        result["error"] = "Не git-репозиторий: {}".format(err)
        return result

    # 2. Fetch с GitHub
    rc, _, err = _git("fetch", "origin", "main", timeout=60)
    if rc != 0:
        result["error"] = "Не удалось fetch: {}".format(err)
        return result

    # 3. SHA локально и на сервере
    rc, local_sha, _ = _git("rev-parse", "HEAD")
    rc2, remote_sha, _ = _git("rev-parse", "origin/main")
    if rc != 0 or rc2 != 0:
        result["error"] = "Не удалось определить SHA"
        return result

    result["ok"] = True
    result["local_sha"] = local_sha[:8]
    result["remote_sha"] = remote_sha[:8]

    # 4. Сообщения коммитов
    _, local_msg, _ = _git("log", "-1", "--pretty=%s", "HEAD")
    _, remote_msg, _ = _git("log", "-1", "--pretty=%s", "origin/main")
    result["local_msg"] = local_msg
    result["remote_msg"] = remote_msg

    # 5. На сколько коммитов отстаём
    rc, behind, _ = _git("rev-list", "--count", "HEAD..origin/main")
    if rc == 0 and behind.isdigit():
        result["behind"] = int(behind)

    # 6. Есть ли новые коммиты?
    result["available"] = (local_sha != remote_sha)
    return result


# ============================================================
#  Применение обновления
# ============================================================

def apply_update(log_callback=None):
    """
    Скачивает и применяет обновление.
    Возвращает (success, message).
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    # 1. Проверить, есть ли обновление
    info = check_for_updates()
    if not info["ok"]:
        return False, "Ошибка проверки: {}".format(info["error"])
    if not info["available"]:
        return False, "Обновлений нет"

    log("Было:  {} {}".format(info["local_sha"], info["local_msg"]))
    log("Будет: {} {}".format(info["remote_sha"], info["remote_msg"]))
    log("Новых коммитов: {}".format(info["behind"]))

    # 2. Сохранить локальные изменения (если есть)
    rc, status, _ = _git("status", "--porcelain")
    if status:
        log("Сохраняем локальные изменения через git stash...")
        rc, _, err = _git("stash", "push", "-u", "-m", "auto-stash before update")
        if rc != 0:
            return False, "Не удалось сделать stash: {}".format(err)

    # 3. Pull
    log("Скачиваем новую версию...")
    rc, out, err = _git("pull", "origin", "main", timeout=120)
    if rc != 0:
        return False, "Не удалось pull: {}".format(err)
    if out:
        log(out)

    # 4. Установить зависимости
    log("Обновляем зависимости...")
    venv_python = BASE_DIR / ".venv" / "bin" / "python"
    if not venv_python.exists():
        venv_python = BASE_DIR / ".venv" / "Scripts" / "python.exe"  # Windows

    if venv_python.exists():
        rc, _, err = _run(
            [str(venv_python), "-m", "pip", "install", "-r",
             str(BASE_DIR / "requirements.txt"), "--quiet"],
            timeout=180
        )
        if rc != 0:
            log("Предупреждение: pip install завершился с ошибкой: {}".format(err))
        else:
            log("Зависимости обновлены")
    else:
        log("venv не найден — пропускаем pip install")

    # 5. Перезапуск сервисов (только на Linux)
    import platform
    if platform.system() == "Linux":
        log("Перезапускаем сервисы...")
        for svc in ("news-terminal.service", "news-bot.service"):
            rc, _, _ = _run(["systemctl", "restart", svc], timeout=30)
            if rc == 0:
                log("Сервис {} перезапущен".format(svc))
    else:
        log("Windows: перезапуск сервисов пропущен")

    return True, "Обновление применено"