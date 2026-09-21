#!/bin/bash
# update.sh — обновить программу с GitHub

cd /root/news_terminal_project

echo "=== Проверка обновлений ==="
git fetch origin main

LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)

if [ "$LOCAL" = "$REMOTE" ]; then
    echo "Обновлений нет. Текущая версия: $(git log -1 --oneline)"
    exit 0
fi

echo "Есть обновление!"
echo "Было:  $(git log -1 --oneline)"
echo "Будет: $(git log -1 --oneline origin/main)"

echo "=== Скачиваем ==="
git pull origin main

echo "=== Устанавливаем зависимости (если есть изменения) ==="
source .venv/bin/activate
pip install -r requirements.txt --quiet

echo "=== Перезапускаем сервис терминала ==="
sudo systemctl restart news-terminal.service 2>/dev/null || true

echo "=== Перезапускаем бота ==="
sudo systemctl restart news-bot.service 2>/dev/null || true

echo "=== Готово ==="
