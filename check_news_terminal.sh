#!/bin/bash
# Watchdog: проверяет tmux-сессию news. Если нет — перезапускает сервис.

LOG=/var/log/check_news_terminal.log
TS=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

# 1. Проверяем tmux
if ! /usr/bin/tmux has-session -t news 2>/dev/null; then
    echo "$TS tmux-сессия news отсутствует, перезапускаю news-terminal.service" >> "$LOG"
    systemctl restart news-terminal.service
    sleep 5
    if /usr/bin/tmux has-session -t news 2>/dev/null; then
        echo "$TS OK: сессия восстановлена" >> "$LOG"
    else
        echo "$TS FAIL: сессия не создалась" >> "$LOG"
    fi
    # После рестарта терминала даём ttyd 3 секунды
    sleep 3
fi

# 2. Проверяем ttyd
if ! systemctl is-active --quiet news-ttyd.service; then
    echo "$TS news-ttyd.service не активен, запускаю" >> "$LOG"
    systemctl start news-ttyd.service
    sleep 2
    if systemctl is-active --quiet news-ttyd.service; then
        echo "$TS OK: ttyd восстановлен" >> "$LOG"
    fi
fi

# 3. Проверяем бота
if ! systemctl is-active --quiet news-bot.service; then
    echo "$TS news-bot.service не активен, запускаю" >> "$LOG"
    systemctl start news-bot.service
fi
