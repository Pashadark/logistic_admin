import logging
from django.template.loader import render_to_string
from django.conf import settings
from .telegram_api import send_telegram_message

logger = logging.getLogger(__name__)

class NotificationService:
    TEMPLATES = {
        'status_changed': 'telegram/status_changed.html',
        'shipment_created': 'telegram/shipment_created.html',
        'shipment_updated': 'telegram/shipment_updated.html',
        'shipment_deleted': 'telegram/shipment_deleted.html'
    }

    @classmethod
    def _render_template(cls, template_name, context):
        try:
            return render_to_string(template_name, context).strip()
        except Exception as e:
            logger.error(f"Template render error: {str(e)}")
            return None

    @classmethod
    def send_notification(cls, notification_type, context, chat_id=None):
        template = cls.TEMPLATES.get(notification_type)
        if not template:
            logger.error(f"Unknown notification type: {notification_type}")
            return False

        message = cls._render_template(template, context)
        if not message:
            return False

        try:
            if chat_id:
                return send_telegram_message(chat_id, message)
            elif hasattr(settings, 'TELEGRAM_GROUP_ID'):
                return send_telegram_message(settings.TELEGRAM_GROUP_ID, message)
            return True
        except Exception as e:
            logger.error(f"Notification send error: {str(e)}")
            return False

    @classmethod
    def notify_status_change(cls, shipment, old_status, new_status, chat_id=None):
        return cls.send_notification(
            'status_changed',
            {
                'shipment': shipment,
                'old_status': old_status,
                'new_status': new_status
            },
            chat_id
        )