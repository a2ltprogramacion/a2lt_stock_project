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

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent

# ─────────────────────────────────────────────────────────────────────────────
# 1. Seguridad: SECRET_KEY obligatoria desde variable de entorno
# ─────────────────────────────────────────────────────────────────────────────
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    raise ImproperlyConfigured(
        'SECRET_KEY no definida en variables de entorno. '
        'Generar con: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )

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
    # SEC-02b: CSP ANTES del TenantMiddleware (no al final de la lista):
    # el TenantMiddleware retorna sus 403 con early return, sin invocar
    # get_response. El middleware NATIVO de Django 6 es MiddlewareMixin:
    # setea request._csp_nonce en process_request (fase de bajada, antes
    # de que el tenant renderice sus 403) y aplica el header en
    # process_response al SUBIR la respuesta por su frame. Por encima,
    # cubre tambien los 403 del tenant con la cabecera CSP activa.
    'django.middleware.csp.ContentSecurityPolicyMiddleware',
    'inventory.middleware.TenantMiddleware',
]

ROOT_URLCONF = 'a2lt_stock_project.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                # SEC-02b/REQ-CSP-04: expone {{ csp_nonce }} (lee
                # request._csp_nonce que setea el middleware nativo).
                # Sin el, los scripts inline renderizan nonce="" y el
                # JS muere en modo enforcing.
                'django.template.context_processors.csp',
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
    # SEC-07: SECURE_BROWSER_XSS_FILTER fue eliminado (no-op desde
    # Django 5: el header X-XSS-Protection fue deprecado por los
    # navegadores por introducir vulnerabilidades propias).
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    # On-premise over HTTP LAN: no forzar HTTPS redirect (delega a
    # reverse-proxy si lo hubiere). Si se quiere HTTPS obligatorio,
    # definir SECURE_SSL_REDIRECT=True via env var.
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'False').lower() == 'true'
    # SEC-03: este setting ASUME un reverse proxy confiable (Apache/Nginx)
    # que fija/sobrescribe X-Forwarded-Proto antes de que la request llegue
    # a Django. Si se despliega SIN proxy, ELIMINAR esta linea: cualquiera
    # en la LAN podria inyectar X-Forwarded-Proto: https, forzar
    # request.is_secure()=True y bypassear el origin-check de CSRF
    # (ver docs/OPERACION.md, "Despliegue con y sin reverse proxy").
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    # Cookies y HSTS solo bajo HTTPS real para permitir operar en LAN local sobre HTTP sin romper auth
    SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT
    CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT
    if SECURE_SSL_REDIRECT:
        SECURE_HSTS_SECONDS = 31536000  # 1 anio
        SECURE_HSTS_INCLUDE_SUBDOMAINS = True
        SECURE_HSTS_PRELOAD = True  # silencia W021 del check --deploy

# SEC-02b/REQ-CSP-01/03: Content-Security-Policy NATIVA de Django 6.
# Dict unico con constantes django.utils.csp.CSP; el middleware nativo
# (django.middleware.csp.ContentSecurityPolicyMiddleware) lo serializa
# con build_policy() y el nonce por request (LazyNonce garantiza que
# header y {{ csp_nonce }} usan el MISMO valor).
# 'unsafe-inline' ELIMINADO de script-src (CSP3: con nonce el navegador
# lo ignoraria de todos modos — eliminacion efectiva). style-src SI lo
# conserva: DEUDA ACEPTADA, Tailwind CDN JIT inyecta <style> en runtime
# (SEC-05 mantiene el CDN hasta que exista build de Tailwind).
# FUERA del bloque `if not DEBUG:`: la CSP aplica tambien en dev (header
# inocuo para el ciclo de desarrollo local) y en la suite de tests.
_CSP_DICT = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE, "https://cdn.tailwindcss.com"],
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, "https://cdn.jsdelivr.net",
                  "https://fonts.googleapis.com"],
    "font-src": [CSP.SELF, "https://cdn.jsdelivr.net", "https://fonts.gstatic.com"],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
}

# REQ-CSP-06: knob Report-Only -> enforcing (env-only, sin duplicar la
# politica). 'report' (default): emite Content-Security-Policy-Report-Only
# (no bloqueante) para la ventana de adopcion — las violaciones sin
# report-uri se loguean en la consola del navegador. 'enforce': emite el
# header bloqueante. Flip y rollback de emergencia = variable de entorno
# + restart del proceso, cero codigo. Typo => ImproperlyConfigured en
# arranque (fail-fast, no fail-silent).
CSP_MODE = os.environ.get('CSP_MODE', 'report')  # 'report' | 'enforce'
if CSP_MODE not in ('report', 'enforce'):
    raise ImproperlyConfigured(f"CSP_MODE invalido: {CSP_MODE!r}")
if CSP_MODE == 'enforce':
    SECURE_CSP = _CSP_DICT            # header bloqueante
else:
    SECURE_CSP_REPORT_ONLY = _CSP_DICT  # header -Report-Only (default)


# ─────────────────────────────────────────────────────────────────────────────
# 9. LOGGING (always-on: file rotativo + console + mail_admins para 500)
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
            'encoding': 'utf-8',
            'formatter': 'verbose',
            'level': 'INFO',
        },
        # SEC-04: notifica los ERROR (500) a ADMINS por correo. El backend
        # de correo se define por entorno mas abajo (default console).
        'mail_admins': {
            'level': 'ERROR',
            'class': 'django.utils.log.AdminEmailHandler',
        },
    },
    'loggers': {
        'inventory': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': False,
        },
        'django.request': {
            # SEC-04: los 500 van a archivo, consola y correo de ADMINS.
            'handlers': ['file', 'console', 'mail_admins'],
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
# SEC-02: la cookie CSRF no debe ser legible por JS (mitiga robo de token vía XSS).
# El token se expone al frontend mediante <meta name="csrf-token"> en base.html.
CSRF_COOKIE_HTTPONLY = True


# ─────────────────────────────────────────────────────────────────────────────
# 11. ADMINS (para AdminEmailHandler de errores 500)
# ─────────────────────────────────────────────────────────────────────────────
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@localhost')
ADMINS = [('Admin A2LT', ADMIN_EMAIL)]
MANAGERS = ADMINS

# SEC-04: el handler mail_admins necesita un backend de correo. Default
# console (escribe el "email" en stdout): seguro en dev y tests. En
# produccion definir EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# + EMAIL_HOST/USER/PASSWORD en el .env (ver docs/OPERACION.md).
EMAIL_BACKEND = os.environ.get('EMAIL_BACKEND', 'django.core.mail.backends.console.EmailBackend')
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '25'))
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'False').lower() == 'true'


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
