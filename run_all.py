import os
import sys
import subprocess
import psutil
import signal
import time
import logging
import traceback
from pathlib import Path

# Настройка расширенного логирования
logging.basicConfig(
    level=logging.DEBUG,  # Изменено на DEBUG для более детального вывода
    format='%(asctime)s - %(levelname)s - %(message)s\n%(pathname)s:%(lineno)d',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot_manager.log', mode='w')  # Перезаписываем файл при каждом запуске
    ]
)
logger = logging.getLogger(__name__)


def setup_exception_logging():
    """Перехват всех необработанных исключений"""

    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return

        logger.critical("Необработанное исключение:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception


def kill_previous_instances():
    """Завершает все предыдущие процессы с детальным логированием"""
    current_pid = os.getpid()
    killed = 0

    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                logger.debug(f"Проверяем процесс PID {proc.info['pid']}: {cmdline}")

                if (proc.info['name'] in ['python', 'python3', 'python.exe'] and
                        proc.info['pid'] != current_pid):

                    process_type = None
                    if 'cargo_bot.py' in cmdline or 'run_all.py' in cmdline:
                        process_type = "бота"
                    elif 'manage.py' in cmdline and 'runserver' in cmdline:
                        process_type = "Django сервера"

                    if process_type:
                        logger.info(f"Завершаем процесс {process_type} (PID: {proc.info['pid']})...")
                        try:
                            if os.name == 'nt':
                                os.kill(proc.info['pid'], signal.CTRL_BREAK_EVENT)
                            else:
                                os.kill(proc.info['pid'], signal.SIGTERM)

                            killed += 1
                            time.sleep(1)
                        except ProcessLookupError:
                            logger.warning(f"Процесс {proc.info['pid']} уже завершен")
                        except Exception as e:
                            logger.error(
                                f"Ошибка завершения процесса {proc.info['pid']}: {str(e)}\n{traceback.format_exc()}")

            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.warning(f"Ошибка доступа к процессу: {str(e)}\n{traceback.format_exc()}")
                continue

    except Exception as e:
        logger.error(f"Критическая ошибка в kill_previous_instances: {str(e)}\n{traceback.format_exc()}")
        raise

    if killed > 0:
        logger.info(f"Завершено {killed} процессов. Ожидание завершения...")
        time.sleep(5)
    return killed


def run_process(command, name):
    """Запускает процесс с расширенным логированием"""
    try:
        log_file = open(f'{name}.log', 'w')
        logger.debug(f"Запуск команды: {' '.join(command)}")

        process = subprocess.Popen(
            command,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            text=True,
            encoding='utf-8'
        )

        logger.info(f"Запущен процесс {name} (PID: {process.pid})")
        return process

    except Exception as e:
        logger.error(f"Ошибка запуска процесса {name}: {str(e)}\n{traceback.format_exc()}")
        raise


def check_processes():
    """Проверяет запущенные процессы с детальным выводом"""
    bot_processes = []
    django_processes = []

    try:
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                logger.debug(f"Проверка процесса PID {proc.info['pid']}: {cmdline}")

                if 'python' in proc.info['name']:
                    if 'cargo_bot.py' in cmdline:
                        bot_processes.append(proc.info['pid'])
                    elif 'manage.py' in cmdline and 'runserver' in cmdline:
                        django_processes.append(proc.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied) as e:
                logger.warning(f"Ошибка проверки процесса: {str(e)}")
                continue

    except Exception as e:
        logger.error(f"Ошибка в check_processes: {str(e)}\n{traceback.format_exc()}")
        return 0, 0

    logger.info(f"Найдено процессов бота: {len(bot_processes)}, Django: {len(django_processes)}")
    return len(bot_processes), len(django_processes)


def main():
    setup_exception_logging()
    logger.info("=== Запуск системы управления ===")

    try:
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
            logger.error(f"Текущий рабочий каталог: {os.getcwd()}")
            logger.error(f"Содержимое директории: {os.listdir(Path(__file__).parent)}")
            return

        django_process = run_process(
            [sys.executable, str(django_path), "runserver", "--noreload", "--verbosity", "3"],
            "django_server"
        )

        # 3. Запускаем бота
        logger.info("3. Запуск Telegram бота...")
        bot_path = Path(__file__).parent / "cargo_bot.py"
        if not bot_path.exists():
            logger.error(f"Файл бота не найден: {bot_path}")
            logger.error(f"Содержимое директории: {os.listdir(Path(__file__).parent)}")
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
            logger.error("Проверьте логи в файлах django_server.log и telegram_bot.log")
        else:
            logger.info("Все процессы успешно запущены")

        # 5. Бесконечный цикл для поддержания работы
        while True:
            time.sleep(60)
            bot_count, django_count = check_processes()

            if bot_count == 0:
                logger.warning("Бот не запущен, перезапускаем...")
                bot_process = run_process(
                    [sys.executable, str(bot_path), "--drop-pending-updates"],
                    "telegram_bot_restart"
                )

            if django_count == 0:
                logger.warning("Django сервер не запущен, перезапускаем...")
                django_process = run_process(
                    [sys.executable, str(django_path), "runserver", "--noreload", "--verbosity", "3"],
                    "django_server_restart"
                )

    except Exception as e:
        logger.critical(f"Критическая ошибка в main: {str(e)}\n{traceback.format_exc()}")
    finally:
        logger.info("Завершение работы системы управления")


if __name__ == "__main__":
    main()