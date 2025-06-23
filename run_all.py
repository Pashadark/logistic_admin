import os
import sys
import subprocess
import psutil
import signal
import time
import logging
from pathlib import Path

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_manager.log')
    ]
)
logger = logging.getLogger(__name__)


def kill_previous_instances():
    """Завершает все предыдущие процессы бота и Django сервера"""
    current_pid = os.getpid()
    killed = 0

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if (proc.info['name'] in ['python', 'python3', 'python.exe'] and
                    proc.info['pid'] != current_pid):

                # Определяем тип процесса
                if 'cargo_bot.py' in cmdline or 'run_all.py' in cmdline:
                    process_type = "бота"
                elif 'manage.py' in cmdline and 'runserver' in cmdline:
                    process_type = "Django сервера"
                else:
                    continue

                logger.info(f"Завершаем процесс {process_type} (PID: {proc.info['pid']})...")
                try:
                    if os.name == 'nt':  # Windows
                        os.kill(proc.info['pid'], signal.CTRL_BREAK_EVENT)
                    else:  # Unix-like
                        os.kill(proc.info['pid'], signal.SIGTERM)
                    killed += 1
                    time.sleep(1)
                except ProcessLookupError:
                    continue

        except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
            logger.warning(f"Ошибка доступа к процессу: {e}")
            continue

    if killed > 0:
        logger.info(f"Завершено {killed} процессов. Ожидание завершения...")
        time.sleep(5)
    return killed


def run_process(command, name):
    """Запускает процесс с логированием"""
    log_file = open(f'{name}.log', 'w')
    process = subprocess.Popen(
        command,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
    )
    logger.info(f"Запущен процесс {name} (PID: {process.pid})")
    return process


def check_processes():
    """Проверяет запущенные процессы"""
    bot_processes = []
    django_processes = []

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            cmdline = ' '.join(proc.info['cmdline'] or [])
            if 'python' in proc.info['name']:
                if 'cargo_bot.py' in cmdline:
                    bot_processes.append(proc.info['pid'])
                elif 'manage.py' in cmdline and 'runserver' in cmdline:
                    django_processes.append(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    logger.info(f"Найдено процессов бота: {len(bot_processes)}, Django: {len(django_processes)}")
    return len(bot_processes), len(django_processes)


def main():
    logger.info("=== Запуск системы управления ===")

    # 1. Завершаем предыдущие экземпляры
    logger.info("1. Завершение предыдущих экземпляров...")
    killed = kill_previous_instances()
    if killed > 0:
        logger.info(f"Завершено {killed} процессов")

    # 2. Запускаем Django сервер
    logger.info("2. Запуск Django сервера...")
    django_path = Path(__file__).parent / "manage.py"
    if not django_path.exists():
        logger.error(f"Файл manage.py не найден: {django_path}")
        return

    django_process = run_process(
        [sys.executable, str(django_path), "runserver", "--noreload"],
        "django_server"
    )

    # 3. Запускаем бота
    logger.info("3. Запуск Telegram бота...")
    bot_path = Path(__file__).parent / "cargo_bot.py"
    if not bot_path.exists():
        logger.error(f"Файл бота не найден: {bot_path}")
        return

    bot_process = run_process(
        [sys.executable, str(bot_path), "--drop-pending-updates"],
        "telegram_bot"
    )

    # 4. Проверка запуска
    logger.info("4. Проверка запущенных процессов...")
    time.sleep(5)
    bot_count, django_count = check_processes()

    if bot_count != 1 or django_count != 1:
        logger.error("Ошибка запуска: неверное количество процессов!")
        logger.error(f"Бот: {bot_count}, Django: {django_count}")
    else:
        logger.info("Все процессы успешно запущены")

    # 5. Бесконечный цикл для поддержания работы
    try:
        while True:
            time.sleep(60)
            # Периодическая проверка процессов
            bot_count, django_count = check_processes()
            if bot_count == 0:
                logger.warning("Бот не запущен, перезапускаем...")
                bot_process = run_process(
                    [sys.executable, str(bot_path), "--drop-pending-updates"],
                    "telegram_bot"
                )
            if django_count == 0:
                logger.warning("Django сервер не запущен, перезапускаем...")
                django_process = run_process(
                    [sys.executable, str(django_path), "runserver", "--noreload"],
                    "django_server"
                )
    except KeyboardInterrupt:
        logger.info("Получен сигнал прерывания, завершаем процессы...")
        bot_process.terminate()
        django_process.terminate()
        logger.info("Процессы завершены. Выход.")


if __name__ == "__main__":
    main()