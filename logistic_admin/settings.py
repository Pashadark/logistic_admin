import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = 'django-insecure-*0q3#v1g@_$1@!fqk$mz#d^0o&9v$c=0t!y@k#%b8!v!4j@4$d'
DEBUG = True
ALLOWED_HOSTS = ['*']

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django_bootstrap5',
    'core',
    'cargo_admin'
]

# Настройки для резервных копий
BACKUP_PATH = os.path.join(BASE_DIR, 'backups')

# Создаем директорию для бэкапов, если ее нет
os.makedirs(BACKUP_PATH, exist_ok=True)

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
]

ROOT_URLCONF = 'logistic_admin.urls'

# Статические файлы
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
    BASE_DIR / 'core/static',
]

# Для разработки
if DEBUG:
    STATICFILES_DIRS.append(BASE_DIR / 'core/static')

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'core/templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

LOGIN_REDIRECT_URL = 'dashboard'  # Редирект после входа
LOGOUT_REDIRECT_URL = 'login'     # Редирект после выхода

LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'login'

WSGI_APPLICATION = 'logistic_admin.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'cargo_bot.db',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

# Настройки для работы с медиафайлами
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Создаем папку для медиа, если не существует
if not os.path.exists(MEDIA_ROOT):
    os.makedirs(MEDIA_ROOT)
    os.makedirs(os.path.join(MEDIA_ROOT, 'waybills'), exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'products'), exist_ok=True)
    os.makedirs(os.path.join(MEDIA_ROOT, 'avatars'), exist_ok=True)

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

TELEGRAM_BOT_TOKEN = "7833491235:AAEeP3bJWIgWxAjdMhYv6zvTE6dIbe7Ob2U"
TELEGRAM_LOG_CHAT_ID = -1002580459963

# Добавьте в конец файла
ADMIN_SITE_HEADER = "Искра"
ADMIN_SITE_TITLE = "Админ панель"

print("\nMEDIA DEBUG:")
print("MEDIA_ROOT:", MEDIA_ROOT)
print("MEDIA_URL:", MEDIA_URL)
print("Waybills exists:", os.path.exists(os.path.join(MEDIA_ROOT, 'waybills')))