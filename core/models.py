import os
import random
import string
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone
from datetime import timedelta
from django.conf import settings

def generate_short_code():
    return ''.join(random.choices(string.digits, k=6))

class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    position = models.CharField(max_length=100, blank=True, default='')
    phone = models.CharField(max_length=20, blank=True, default='')
    address = models.TextField(blank=True, default='')
    telegram_id = models.CharField(max_length=100, blank=True, default='')
    two_factor_enabled = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Профиль'
        verbose_name_plural = 'Профили'
        ordering = ['-created_at']

    def __str__(self):
        return f'Профиль {self.user.username}'

    @property
    def is_online(self):
        return self.last_activity and (timezone.now() - self.last_activity < timedelta(minutes=5))

class Shipment(models.Model):
    STATUS_CHOICES = [
        ('created', '📝 Создано'),
        ('processing', '🔄 В обработке'),
        ('transit', '🚚 В пути'),
        ('transfer', '🔄 Перемещение'),
        ('delivered', '✅ Доставлено'),
        ('problem', '⚠️ Проблема'),
    ]

    TYPE_CHOICES = [
        ('send', '📤 Отправка'),
        ('receive', '📥 Получение'),
        ('transfer', '🔄 Перемещение'),
    ]

    id = models.CharField(primary_key=True, max_length=6, default=generate_short_code, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    waybill_number = models.CharField(max_length=50)
    city = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    comment = models.TextField(blank=True, null=True)
    weight = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, verbose_name='Вес (кг)')
    timestamp = models.DateTimeField(auto_now_add=True)
    waybill_photo = models.ImageField(upload_to='waybills/', blank=True, null=True)
    product_photo = models.ImageField(upload_to='products/', blank=True, null=True)
    telegram_waybill_file_id = models.CharField(max_length=255, blank=True, null=True)
    telegram_product_file_id = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        db_table = 'shipments'
        verbose_name = '📦 Отправление'
        verbose_name_plural = '📦 Отправления'
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['waybill_number']),
            models.Index(fields=['status']),
            models.Index(fields=['timestamp']),
        ]

    def __str__(self):
        return f"{self.get_type_display()} #{self.waybill_number}"

    @property
    def verbose_status(self):
        STATUS_ICONS = {
            'created': '📝',
            'processing': '🔄',
            'transit': '🚚',
            'transfer': '🔄',
            'delivered': '✅',
            'problem': '⚠️'
        }
        return f"{STATUS_ICONS.get(self.status, '')} {self.get_status_display()}"

class UserActivity(models.Model):
    ACTION_CHOICES = [
        ('LOGIN', 'Вход в систему'),
        ('LOGOUT', 'Выход из системы'),
        ('SHIPMENT_CREATE', 'Создание отправки'),
        ('SHIPMENT_UPDATE', 'Обновление отправки'),
        ('SHIPMENT_DELETE', 'Удаление отправки'),
        ('SHIPMENT_VIEW', 'Просмотр отправки'),
        ('SHIPMENT_STATUS', 'Изменение статуса отправки'),
        ('PROFILE_CREATE', 'Создание профиля'),
        ('PROFILE_UPDATE', 'Обновление профиля'),
        ('AVATAR_CHANGE', 'Изменение аватара'),
        ('PASSWORD_CHANGE', 'Изменение пароля'),
        ('2FA_TOGGLE', 'Изменение 2FA'),
        ('USER_CREATE', 'Создание пользователя'),
        ('USER_UPDATE', 'Обновление пользователя'),
        ('USER_DELETE', 'Удаление пользователя'),
        ('BOT_TEST', 'Тест бота'),
        ('BACKUP_CREATE', 'Создание бэкапа'),
        ('BACKUP_DOWNLOAD', 'Скачивание бэкапа'),
        ('BACKUP_INTERVAL_UPDATE', 'Обновление интервала бэкапов'),
        ('DATABASE_CLEAR', 'Очистка базы данных'),
        ('DATABASE_RESTORE', 'Восстановление базы данных'),
        ('BOT_ACCESS_UPDATE', 'Обновление доступа к боту'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    action_type = models.CharField(max_length=25, choices=ACTION_CHOICES)
    description = models.TextField()
    timestamp = models.DateTimeField(default=timezone.now)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = 'Активность пользователя'
        verbose_name_plural = 'Активности пользователей'
        ordering = ['-timestamp']

    def __str__(self):
        return f'{self.user.username} - {self.get_action_type_display()}'

@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if hasattr(instance, 'profile'):
        instance.profile.save()