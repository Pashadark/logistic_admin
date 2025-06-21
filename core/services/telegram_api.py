import requests
from django.conf import settings
import logging
from time import sleep

logger = logging.getLogger(__name__)


def send_telegram_message(chat_id, text, parse_mode='HTML'):
    if not hasattr(settings, 'TELEGRAM_BOT_TOKEN'):
        logger.error("Telegram token not configured")
        return False

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"

    for attempt in range(settings.TELEGRAM_RETRY_COUNT):
        try:
            response = requests.post(
                url,
                json={
                    'chat_id': chat_id,
                    'text': text,
                    'parse_mode': parse_mode,
                    'disable_web_page_preview': True
                },
                timeout=settings.TELEGRAM_API_TIMEOUT
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            logger.warning(f"Attempt {attempt + 1} failed: {str(e)}")
            if attempt < settings.TELEGRAM_RETRY_COUNT - 1:
                sleep(settings.TELEGRAM_RETRY_DELAY * (2 ** attempt))
                continue
            logger.error(f"Failed to send message: {str(e)}")
            return False