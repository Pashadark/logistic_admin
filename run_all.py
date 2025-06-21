import os
import subprocess
import threading
import sys
import time
import psutil
import signal


def kill_previous_instances():
    """Завершает все предыдущие процессы бота"""
    current_pid = os.getpid()
    killed = 0

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if (proc.info['name'] in ['python', 'python3'] and
                    'cargo_bot.py' in ' '.join(proc.info['cmdline'] or []) and
                    proc.info['pid'] != current_pid):
                print(f"Завершаем процесс {proc.info['pid']}...")
                os.kill(proc.info['pid'], signal.SIGTERM)
                killed += 1
                time.sleep(0.5)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    print(f"Завершено процессов: {killed}")
    return killed > 0


def run_web():
    """Запуск Django сервера"""
    os.system("python manage.py runserver")


def run_bot():
    """Запуск Telegram бота с принудительным завершением старых экземпляров"""
    try:
        # Убиваем предыдущие процессы
        if kill_previous_instances():
            time.sleep(3)  # Даем время на завершение

        # Запускаем бота с параметром для сброса pending updates
        bot_path = os.path.join(os.path.dirname(__file__), "cargo_bot.py")
        process = subprocess.Popen(
            [sys.executable, bot_path, "--drop-pending-updates"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )

        # Логируем вывод бота
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                print(output.strip())

        return_code = process.poll()
        if return_code != 0:
            print(f"Бот завершился с ошибкой (код {return_code})")
            for line in process.stderr:
                print(line.strip())

    except subprocess.CalledProcessError as e:
        print(f"Ошибка запуска бота: {e}")
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")


if __name__ == "__main__":
    print("Запуск веб-приложения и бота...")

    # Проверка media директорий
    media_root = os.path.join(os.path.dirname(__file__), "media")
    waybills_dir = os.path.join(media_root, "waybills")

    print(f"\nMEDIA DEBUG:")
    print(f"MEDIA_ROOT: {media_root}")
    print(f"Waybills exists: {os.path.exists(waybills_dir)}\n")

    # Запуск веб-сервера в отдельном потоке
    web_thread = threading.Thread(target=run_web)
    web_thread.daemon = True
    web_thread.start()

    # Даем серверу время на запуск
    time.sleep(5)

    # Запуск бота в основном потоке
    try:
        run_bot()
    except KeyboardInterrupt:
        print("\nПриложение остановлено")
    except Exception as e:
        print(f"Ошибка при запуске: {e}")