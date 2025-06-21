import os
import psutil
import signal
import time


def kill_previous_bots():
    """Принудительно завершает все процессы cargo_bot.py"""
    current_pid = os.getpid()
    killed = 0

    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if (proc.info['name'] in ['python', 'python3'] and
                    'cargo_bot.py' in ' '.join(proc.info['cmdline'] or []) and
                    proc.info['pid'] != current_pid):
                print(f"[KILL] Process {proc.info['pid']}")
                try:
                    os.kill(proc.info['pid'], signal.SIGTERM)
                    time.sleep(0.3)
                    if proc.is_running():
                        os.kill(proc.info['pid'], signal.SIGKILL)
                    killed += 1
                except ProcessLookupError:
                    continue
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    print(f"Убито процессов: {killed}")
    return killed


if __name__ == '__main__':
    print("=== Очистка старых процессов бота ===")
    killed = kill_previous_bots()
    if killed > 0:
        print(f"Успешно завершено {killed} процессов. Теперь можно запускать бота.")
    else:
        print("Активных процессов бота не найдено. Можно запускать новый.")
