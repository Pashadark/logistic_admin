# logistic_admin/wsgi.py
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'logistic_admin.settings')

application = get_wsgi_application()