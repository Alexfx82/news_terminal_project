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
            "8. Translation status",
            "9. Обновить программу из GitHub",
        ]
        draw_menu_screen("SETTINGS", lines, width)
        print()
        try:
            choice = input("Select (1-9): ").strip()
        except (KeyboardInterrupt, EOFError):
            return "back"

        if choice == "1":
            # ... (существующий код)
            pass
        elif choice == "2":
            # ...
            pass
        elif choice == "3":
            return "rescan"
        elif choice == "4":
            # ...
            pass
        elif choice == "5":
            return "clear_buffer"
        elif choice == "6":
            return "back"
        elif choice == "7":
            return "quit"
        elif choice == "8":
            # ...
            pass
        elif choice == "9":
            # === Пункт обновления ===
            clear_and_show_cursor()
            draw_menu_screen("UPDATE", [], width)
            print()

            from update import check_for_updates, apply_update

            print("Проверяем обновления...")
            info = check_for_updates()

            if not info["ok"]:
                print("Ошибка проверки:", info["error"])
                input("\nEnter для возврата...")
                continue

            if not info["available"]:
                print("Обновлений нет.")
                print("Текущая версия:", info["local_sha"])
                print("Сообщение:", info["local_msg"])
                input("\nEnter для возврата...")
                continue

            print("Доступно обновление:")
            print("  Было:  {} {}".format(info["local_sha"], info["local_msg"]))
            print("  Будет: {} {}".format(info["remote_sha"], info["remote_msg"]))
            print()
            confirm = input("Применить? [y/N]: ").strip().lower()
            if confirm != "y":
                continue

            print()
            print("Обновление...")
            success, msg = apply_update(log_callback=lambda m: print(" ", m))
            print()
            if success:
                print("✓", msg)
                print("Перезапустите программу, чтобы применить изменения.")
            else:
                print("✗", msg)
            input("\nEnter для возврата...")
        else:
            continue