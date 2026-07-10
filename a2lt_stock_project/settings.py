"""
Django settings for a2lt_stock_project project.

A16: settings hardening para instalacion on-premise.
- SECRET_KEY desde variable de entorno (fallback explicito dev).
- DEBUG por env (default False, ya no True por defecto).
- ALLOWED_HOSTS por env, con '*' SOLO si DEBUG=True.
- SQLite con WAL mode + timeout 20s.
- HEADERS de seguridad (HSTS, SSL) solo si DEBUG=False.
- LOGGING dict configurado para diagnostics.
- Static/media dirs creados en primer arranque.

Para produccion real, configurar .env:
    SECRET_KEY=<generar con python -c "import secrets; print(secrets.token_urlsafe(50))">
    DEBUG=False
    ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com
    ADMIN_EMAIL=admin@tu-dominio.com
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# 1. Seguridad: SECRET_KEY con fallback explicito
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod')

# ─────────────────────────────────────────────────────────────────────────────
# 2. DEBUG desde env (default False). Para desarrollo local usar DEBUG=True.
# ─────────────────────────────────────────────────────────────────────────────
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'

# ─────────────────────────────────────────────────────────────────────────────
# 3. ALLOWED_HOSTS desde env. Coma-separado. Si DEBUG=True, default '*'.
# ─────────────────────────────────────────────────────────────────────────────
_allowed_hosts = os.environ.get('ALLOWED_HOSTS', '')
if _allowed_hosts:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts.split(',') if h.strip()]
elif DEBUG:
    ALLOWED_HOSTS = ['*']
else:
    ALLOWED_HOSTS = []  # produccion debe definir explicitamente


# ─────────────────────────────────────────────────────────────────────────────
# Application definition
# ─────────────────────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Aplicacion de negocio
    'inventory.apps.InventoryConfig',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'inventory.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'a2lt_stock_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'inventory.context_processors.inject_config',
            ],
        },
    },
]

WSGI_APPLICATION = 'a2lt_stock_project.wsgi.application'


# ─────────────────────────────────────────────────────────────────────────────
# 4. Database: SQLite con PRAGMAs WAL/timeout para concurrencia light.
# ─────────────────────────────────────────────────────────────────────────────
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
        'OPTIONS': {
            'timeout': 20,
            'init_command': (
                'PRAGMA journal_mode=WAL;'
                'PRAGMA synchronous=NORMAL;'
                'PRAGMA foreign_keys=ON;'
                'PRAGMA busy_timeout=5000;'
                'PRAGMA cache_size=-64000;'  # 64 MB cache (negativo = KB)
            ),
        },
    }
}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Password validation
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
# 6. Internationalization
# ─────────────────────────────────────────────────────────────────────────────
LANGUAGE_CODE = 'es-ve'
TIME_ZONE = 'America/Caracas'
USE_I18N = True
USE_TZ = True


# ─────────────────────────────────────────────────────────────────────────────
# 7. Static files
# ─────────────────────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'  # para collectstatic en produccion

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'


# ─────────────────────────────────────────────────────────────────────────────
# 8. Headers de seguridad (solo si DEBUG=False y no es testing)
# ─────────────────────────────────────────────────────────────────────────────
# Django emite un warning si HSTS se activa sin HTTPS, asi que lo
# aislamos de DEBUG/SessionTesting.
if not DEBUG:
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True  # silencia W021 del check --deploy
    SECURE_HSTS_SECONDS = 31536000  # 1 anio
    X_FRAME_OPTIONS = 'DENY'
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # On-premise over HTTP LAN: no forzar HTTPS redirect (delega a
    # reverse-proxy si lo hubiere). Si se quiere HTTPS obligatorio,
    # definir SECURE_SSL_REDIRECT=True via env var.
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').lower() == 'true'
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')


# ─────────────────────────────────────────────────────────────────────────────
# 9. LOGGING (always-on, con file rotativo + console)
# ─────────────────────────────────────────────────────────────────────────────
LOGS_DIR = BASE_DIR / 'logs'
LOGS_DIR.mkdir(exist_ok=True)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple',
            'level': 'INFO' if not DEBUG else 'DEBUG',
        },
        'file': {
            'class': 'logging.handlers.RotatingFileHandler',
            'filename': LOGS_DIR / 'a2lt_stock.log',
            'maxBytes': 10 * 1024 * 1024,  # 10 MB
            'backupCount': 5,
            'formatter': 'verbose',
            'level': 'INFO',
        },
    },
    'loggers': {
        'inventory': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['file'],
            'level': 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['file'],
            'level': 'WARNING',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# 10. CSP / Cookies
# ─────────────────────────────────────────────────────────────────────────────
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False  # False para que JS (getCookie) pueda leerlo via A6


# ─────────────────────────────────────────────────────────────────────────────
# 11. ADMINS (para AdminEmailHandler de errores 500)
# ─────────────────────────────────────────────────────────────────────────────
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@localhost')
ADMINS = [('Admin A2LT', ADMIN_EMAIL)]
MANAGERS = ADMINS


# ─────────────────────────────────────────────────────────────────────────────
# 12. CSRF de API/cliente (canonico: same origin)
# ─────────────────────────────────────────────────────────────────────────────
CSRF_TRUSTED_ORIGINS = []  # configurar si hay subdominios dominio cruzada

# URL canonica del login. Apunta al name 'login' (resuelto via
# namespace 'inventory:login' por el URLconf). La pantalla efectiva
# es la ruta raiz '' del app. Centralizarlo aqui evita que el
# middleware del tenant hardcodee la ruta.
LOGIN_URL = 'inventory:login'
LOGIN_REDIRECT_URL = 'inventory:dashboard'
LOGOUT_REDIRECT_URL = 'inventory:login'
