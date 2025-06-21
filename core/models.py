from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.views.generic import TemplateView
from django.core.paginator import Paginator
from django.db.models import Q
from django.views import View
from django.contrib.auth import login
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db import transaction
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
import requests
from django.conf import settings
import os
import shutil
import pytz
from django.core import management
from datetime import datetime

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    position = models.CharField(max_length=100, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    telegram_id = models.CharField(max_length=100, blank=True, null=True)
    two_factor_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Profile of {self.user.username}'

    @property
    def full_name(self):
        return f'{self.user.first_name} {self.user.last_name}'.strip()

    def get_user_group(self):
        """Возвращает первую группу пользователя или None"""
        return self.user.groups.first()

    def get_group_icon(self):
        """Возвращает иконку для группы пользователя"""
        group = self.get_user_group()
        if group:
            icons = {
                'Администратор': 'bi-person-fill-gear',
                'Разработчик': 'bi-code-square',
                'Офис-менеджер': 'bi-briefcase-fill',
                'Менеджер': 'bi-person-lines-fill'
            }
            return icons.get(group.name, 'bi-person-circle')
        return 'bi-person-circle'

    @property
    def telegram_username(self):
        return self.telegram_id if self.telegram_id else None


class Shipment(models.Model):
    STATUS_CHOICES = [
        ('created', '📝 Создано'),
        ('processing', '🔄 В обработке'),
        ('transit', '🚚 В пути'),
        ('delivered', '✅ Доставлено'),
        ('problem', '⚠️ Проблема'),
    ]

    TYPE_CHOICES = [
        ('send', '📤 Отправка'),
        ('receive', '📥 Получение'),
    ]

    id = models.CharField(primary_key=True, max_length=50)
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    waybill_number = models.CharField(max_length=50)
    city = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    comment = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    waybill_photo = models.CharField(max_length=255, blank=True, null=True)
    product_photo = models.CharField(max_length=255, blank=True, null=True)
    telegram_waybill_file_id = models.CharField(max_length=255, blank=True, null=True)
    telegram_product_file_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'shipments'  # Явно указываем имя таблицы
        verbose_name = '📦 Отправление'
        verbose_name_plural = '📦 Отправления'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_type_display()} #{self.waybill_number}"

    def get_status_display(self):
        status_map = {
            'created': '📝 Создано',
            'processing': '🔄 В обработке',
            'transit': '🚚 В пути',
            'delivered': '✅ Доставлено',
            'problem': '⚠️ Проблема'
        }
        return status_map.get(self.status, self.status)

    def get_verbose_status(self):
        status_icons = {
            'created': '📝',
            'processing': '🔄',
            'transit': '🚚',
            'delivered': '✅',
            'problem': '⚠️'
        }
        return f"{status_icons.get(self.status, '')} {self.get_status_display()}"

    def clean(self):
        super().clean()
        errors = {}

        # Проверка номера накладной
        if not self.waybill_number:
            errors['waybill_number'] = 'Номер накладной обязателен'

        # Проверка города
        if not self.city:
            errors['city'] = 'Город обязателен'

        if errors:
            from django.core.exceptions import ValidationError
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()  # Вызывает clean() перед сохранением
        super().save(*args, **kwargs)


class UserActivity(models.Model):
    ACTION_CHOICES = [
        ('LOGIN', '🔑 Вход в систему'),
        ('LOGOUT', '🚪 Выход из системы'),
        ('PROFILE_UPDATE', '📝 Обновление профиля'),
        ('PASSWORD_CHANGE', '🔒 Смена пароля'),
        ('BOT_TEST', '🤖 Тест бота'),
        ('SHIPMENT_CREATE', '📦 Создание отправки'),
        ('SHIPMENT_UPDATE', '✏️ Обновление отправки'),
        ('SHIPMENT_DELETE', '❌ Удаление отправки'),
        ('BACKUP_CREATE', '💾 Создание бэкапа'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action_type = models.CharField(max_length=20, choices=ACTION_CHOICES)
    description = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Лог активности'
        verbose_name_plural = 'Логи активности'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['-timestamp']),
            models.Index(fields=['user']),
        ]

    def __str__(self):
        return f"{self.get_action_type_display()} - {self.user.username}"

    @property
    def formatted_timestamp(self):
        return self.timestamp.strftime("%d.%m.%Y %H:%M:%S")

    @property
    def user_display_name(self):
        if self.user.first_name and self.user.last_name:
            return f"{self.user.first_name} {self.user.last_name}"
        return self.user.username

    @property
    def icon(self):
        icons = {
            'LOGIN': 'bi-box-arrow-in-right',
            'LOGOUT': 'bi-box-arrow-right',
            'PROFILE_UPDATE': 'bi-person-lines-fill',
            'PASSWORD_CHANGE': 'bi-shield-lock',
            'BOT_TEST': 'bi-robot',
            'SHIPMENT_CREATE': 'bi-plus-square',
            'SHIPMENT_UPDATE': 'bi-pencil-square',
            'SHIPMENT_DELETE': 'bi-trash',
            'BACKUP_CREATE': 'bi-save',
        }
        return icons.get(self.action_type, 'bi-info-circle')

    @property
    def color(self):
        color_map = {
            'LOGIN': 'success',
            'LOGOUT': 'secondary',
            'PROFILE_UPDATE': 'primary',
            'PASSWORD_CHANGE': 'warning',
            'AVATAR_CHANGE': 'info',
            'SHIPMENT_CREATE': 'success',
            'SHIPMENT_UPDATE': 'primary',
            'SHIPMENT_DELETE': 'danger',
            'SHIPMENT_STATUS': 'info',
            'SHIPMENT_VIEW': 'secondary',
            '2FA_TOGGLE': 'warning'
        }
        return color_map.get(self.action_type, 'secondary')


def format_message(header_icon, header_text, items, footer=None):
    """Форматирует сообщение в едином стиле"""
    message = [
        f"{header_icon} <b>{header_text}</b>",
        "▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬"
    ]

    for item in items:
        message.append(f"• <b>{item['label']}:</b> {item['value']}")

    if footer:
        message.append(f"• <b>{footer['label']}:</b> {footer['value']}")

    message.append("▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬▬")
    return "\n".join(message)


def send_telegram_message(text):
    """Отправляет сообщение в Telegram"""
    if not all([settings.TELEGRAM_BOT_TOKEN, settings.TELEGRAM_LOG_CHAT_ID]):
        print("⚠️ Telegram credentials not configured")
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_LOG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"⚠️ Ошибка отправки в Telegram: {e}")
        return False
    except Exception as e:
        print(f"⚠️ Неожиданная ошибка: {e}")
        return False


def backup_database():
    """Создает резервную копию базы данных и отправляет уведомление"""
    try:
        # Создаем директорию для бэкапов, если ее нет
        backup_dir = os.path.join(settings.BASE_DIR, 'backups')
        os.makedirs(backup_dir, exist_ok=True)

        # Генерируем имя файла с timestamp
        timestamp = datetime.now(pytz.timezone('Europe/Moscow')).strftime("%Y%m%d_%H%M")
        backup_name = f"db_backup_{timestamp}.json"
        backup_path = os.path.join(backup_dir, backup_name)

        # Создаем бэкап
        with open(backup_path, 'w', encoding='utf-8') as f:
            management.call_command('dumpdata', exclude=['contenttypes', 'auth.permission'], stdout=f)

        # Формируем сообщение
        items = [
            {'label': 'Файл', 'value': f"<code>{backup_name}</code>"},
            {'label': 'Размер', 'value': f"{os.path.getsize(backup_path) / 1024:.1f} KB"}
        ]

        footer = {
            'label': 'Дата',
            'value': timestamp.replace('_', ' ')
        }

        message = format_message("💾", "БАЗА ДАННЫХ СОХРАНЕНА", items, footer)

        # Отправляем сообщение
        if not send_telegram_message(message):
            raise Exception("Не удалось отправить уведомление в Telegram")

        return True

    except Exception as e:
        error_items = [{'label': 'Ошибка', 'value': str(e)}]
        error_message = format_message("⚠️", "ОШИБКА СОХРАНЕНИЯ БАЗЫ", error_items)
        send_telegram_message(error_message)
        return False


@receiver(post_save, sender=Shipment)
def notify_shipment_save(sender, instance, created, **kwargs):
    action_icon = "🆕" if created else "🔄"
    action_text = "НОВОЕ ОТПРАВЛЕНИЕ" if created else "ОТПРАВЛЕНИЕ ОБНОВЛЕНО"

    items = [
        {'label': 'ID', 'value': f"<code>{instance.id}</code>"},
        {'label': 'Тип', 'value': instance.get_type_display()},
        {'label': 'Накладная', 'value': instance.waybill_number},
        {'label': 'Город', 'value': instance.city},
        {'label': 'Статус', 'value': instance.get_verbose_status()}
    ]

    footer = {
        'label': 'Дата',
        'value': datetime.now().strftime('%d.%m.%Y %H:%M')
    }

    message = format_message(action_icon, action_text, items, footer)
    send_telegram_message(message)


@receiver(post_delete, sender=Shipment)
def notify_shipment_delete(sender, instance, **kwargs):
    items = [
        {'label': 'ID', 'value': f"<code>{instance.id}</code>"},
        {'label': 'Накладная', 'value': instance.waybill_number},
        {'label': 'Город', 'value': instance.city}
    ]

    footer = {
        'label': 'Дата удаления',
        'value': datetime.now().strftime('%d.%m.%Y %H:%M')
    }

    message = format_message("🗑️", "ОТПРАВЛЕНИЕ УДАЛЕНО", items, footer)
    send_telegram_message(message)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)
        UserActivity.log_activity(
            user=instance,
            action_type='PROFILE_CREATE',
            description='Профиль пользователя создан'
        )


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()