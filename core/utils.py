import os
from django.core.files import File
from django.conf import settings
from telegram import Update


def save_telegram_file(file_data, subfolder):
    """Сохраняет файл из Telegram в media/"""
    file_path = os.path.join(settings.MEDIA_ROOT, subfolder, file_data['file_path'].split('/')[-1])

    # Создаем директорию, если ее нет
    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    # Скачиваем и сохраняем файл
    file_data['file'].download(file_path)

    return os.path.join(subfolder, os.path.basename(file_path))