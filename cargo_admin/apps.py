from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)

class CargoAdminConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'cargo_admin'
