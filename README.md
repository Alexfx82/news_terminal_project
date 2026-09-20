# NEWS TERMINAL

Модульный новостной терминал для Raspberry Pi Zero / Windows.

## Установка

    pip install -r requirements.txt

## Запуск

    python main.py
    python main.py --diagnostics
    python main.py --once
    python main.py --no-fresh-scan
    python main.py --source rbc

## Клавиши в live-режиме

| Клавиша | Действие |
|---|---|
| S | Меню настроек |
| D | Пересканировать источники |
| R | Мгновенный fetch |
| Q | Выход |

## Модули

| Модуль | Ответственность |
|---|---|
| config | пути, константы, Color, ANSI |
| textutils | fit/pad/box/borders |
| storage | settings, sources, history I/O |
| news | ключи, классификация, dedup |
| sources | диагностика RSS |
| fetcher | фоновый поток |
| translator | перевод EN-RU с кэшем |
| render | frame builder |
| menu | интерактивное меню |
| live | главный цикл |
| main | entry point |
