import os
import subprocess
import threading
import time


def run_web():
    os.system("python manage.py runserver")


def run_bot():
    # Укажите путь к вашему файлу с ботом
    os.system("cargo_bot.py")


if __name__ == "__main__":
    print("Запуск веб-приложения и бота...")

    # Запускаем веб-приложение в отдельном потоке
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Даем серверу время на запуск
    time.sleep(3)

    # Запускаем бота в основном потоке
    run_bot()