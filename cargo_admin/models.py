from django.db import models
import requests
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver


class Shipment(models.Model):
    STATUS_CHOICES = [
        ('created', '📝 Создано'),
        ('processing', '🔄 В обработке'),
        ('transit', '🚚 В пути'),
        ('delivered', '✅ Доставлено'),
        ('problem', '⚠️ Проблема'),
    ]

    def get_status_display(self):
        status_map = {
            'created': '📝 Создано',
            'processing': '🔄 В обработке',
            'transit': '🚚 В пути',
            'delivered': '✅ Доставлено',
            'problem': '⚠️ Проблема'
        }
        return status_map.get(self.status, self.status)
    OPERATION_TYPES = [
        ('send', 'Отправка'),
        ('receive', 'Получение'),
    ]

    id = models.CharField(max_length=36, primary_key=True)
    user_id = models.BigIntegerField()
    type = models.CharField(max_length=10, choices=OPERATION_TYPES)
    waybill_photo = models.CharField(max_length=255)
    product_photo = models.CharField(max_length=255)
    waybill_number = models.CharField(max_length=100)
    city = models.CharField(max_length=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='created')
    comment = models.TextField(blank=True, null=True)
    timestamp = models.DateTimeField()

    class Meta:
        db_table = 'shipments'
        verbose_name = 'Отправление'
        verbose_name_plural = 'Отправления'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.get_type_display()} #{self.waybill_number}"


@receiver(post_save, sender=Shipment)
def log_shipment_save(sender, instance, created, **kwargs):
    action = "создано" if created else "обновлено"
    message = (
        f"📦 Отправление {action}:\n"
        f"ID: {instance.id}\n"
        f"Тип: {instance.get_type_display()}\n"
        f"Накладная: {instance.waybill_number}\n"
        f"Город: {instance.city}\n"
        f"Статус: {instance.get_status_display()}"
    )
    send_telegram_message(message)


@receiver(post_delete, sender=Shipment)
def log_shipment_delete(sender, instance, **kwargs):
    message = (
        f"🗑️ Отправление удалено:\n"
        f"ID: {instance.id}\n"
        f"Накладная: {instance.waybill_number}\n"
        f"Город: {instance.city}"
    )
    send_telegram_message(message)


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": settings.TELEGRAM_LOG_CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Ошибка отправки в Telegram: {e}")