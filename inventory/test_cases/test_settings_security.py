"""
Tests de seguridad de configuracion: SEC-03, SEC-04 y SEC-07.

Remediaciones del bloque "seguridad de configuracion" de
docs/AUDIT_REPORT.md §7.5 (ronda 2026-10, sin spec formal):

- SEC-07: SECURE_BROWSER_XSS_FILTER eliminado. El setting es un no-op
  desde Django 5 (el header X-XSS-Protection fue deprecado por los
  navegadores porque introdujo vulnerabilidades propias).
- SEC-03: SECURE_PROXY_SSL_HEADER documentado como dependiente de un
  reverse proxy confiable (docs/OPERACION.md). La remediation es
  documentacion: el setting ya esta correctamente dentro de
  `if not DEBUG:`.
- SEC-04: los errores 500 se notifican a ADMINS via el handler
  `mail_admins` (AdminEmailHandler) en LOGGING, con EMAIL_BACKEND por
  entorno (default console: seguro en dev y tests, sin SMTP silencioso).

Nota sobre el entorno de la suite: el `.env` de desarrollo define
DEBUG=True, por lo que el bloque `if not DEBUG:` de settings.py NO se
ejecuta al importar dentro de la suite (el runner solo fuerza
settings.DEBUG=False en runtime, despues del import). Ademas, el runner
sobreescribe settings.EMAIL_BACKEND con el backend locmem. Por eso las
verificaciones que dependen del bloque condicional o del backend de
correo usan un subproceso con DEBUG forzado (mismo patron de los gates
de test_security.py) o leen el modulo de settings directamente, para
ser deterministicas independientemente del .env local.
"""
import os
import subprocess
import sys
import unittest
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase


class TestSettingsSecurity(SimpleTestCase):
    """SEC-03 + SEC-04 + SEC-07: settings.py y docs/OPERACION.md."""

    def _shell_con_debug(self, debug_value, code):
        """
        Ejecuta `manage.py shell -c <code>` en un subproceso con DEBUG
        forzado en el entorno. Permite verificar el settings "en modo
        produccion" (DEBUG=False) de forma deterministica, sin depender
        del DEBUG=True del .env local (que impide que el bloque
        `if not DEBUG:` corra dentro de esta suite).
        """
        env = dict(os.environ)
        env['DEBUG'] = debug_value
        return subprocess.run(
            [sys.executable, 'manage.py', 'shell', '-c', code],
            capture_output=True, text=True, env=env,
            cwd=str(settings.BASE_DIR), timeout=120,
        )

    # ── SEC-07: setting deprecado eliminado ────────────────────────────

    def test_sec07_browser_xss_filter_eliminado(self):
        """
        SEC-07: SECURE_BROWSER_XSS_FILTER no debe existir.

        El setting es un no-op en Django 5+ (el header X-XSS-Protection
        fue deprecado por los navegadores). No debe existir ni en la
        sesion de tests ni en modo produccion (subproceso con DEBUG=False,
        donde el bloque `if not DEBUG:` si se ejecuta).
        """
        # En la suite actual (import con DEBUG=True del .env) el bloque
        # condicional no corre, pero el setting tampoco debe existir.
        self.assertFalse(hasattr(settings, 'SECURE_BROWSER_XSS_FILTER'))

        # Gate determinista: en modo produccion tampoco debe existir.
        result = self._shell_con_debug(
            'False',
            'from django.conf import settings; '
            'assert not hasattr(settings, "SECURE_BROWSER_XSS_FILTER"), '
            '"SEC-07: el setting deprecado sigue definido"',
        )
        self.assertEqual(
            result.returncode, 0,
            f"SECURE_BROWSER_XSS_FILTER sigue presente en modo produccion. "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    # ── SEC-03: proxy SSL header documentado ───────────────────────────

    def test_sec03_proxy_ssl_header_solo_sin_debug(self):
        """
        SEC-03: con DEBUG=False debe existir SECURE_PROXY_SSL_HEADER con
        la tupla canonica ('HTTP_X_FORWARDED_PROTO', 'https').

        La suite corre con settings.DEBUG=False (el runner lo fuerza),
        pero el bloque `if not DEBUG:` se evalua al importar con el DEBUG
        del .env, por eso el setting se verifica en un subproceso con
        DEBUG=False forzado.
        """
        # Premisa: la suite corre con DEBUG=False en runtime.
        self.assertIs(settings.DEBUG, False)

        result = self._shell_con_debug(
            'False',
            'from django.conf import settings; '
            'assert hasattr(settings, "SECURE_PROXY_SSL_HEADER"), '
            '"SECURE_PROXY_SSL_HEADER ausente con DEBUG=False"; '
            'assert settings.SECURE_PROXY_SSL_HEADER == '
            '("HTTP_X_FORWARDED_PROTO", "https"), '
            'settings.SECURE_PROXY_SSL_HEADER',
        )
        self.assertEqual(
            result.returncode, 0,
            f"Con DEBUG=False debe existir SECURE_PROXY_SSL_HEADER == "
            f"('HTTP_X_FORWARDED_PROTO', 'https'). "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_sec03_operacion_documenta_proxy(self):
        """
        SEC-03: docs/OPERACION.md debe documentar el despliegue con y sin
        reverse proxy confiable (la cabecera X-Forwarded-Proto y el
        riesgo de inyectarla sin proxy).
        """
        operacion = Path(settings.BASE_DIR) / 'docs' / 'OPERACION.md'
        with open(operacion, encoding='utf-8') as f:
            contenido = f.read()
        self.assertIn(
            'X-Forwarded-Proto', contenido,
            'docs/OPERACION.md debe explicar la cabecera X-Forwarded-Proto',
        )
        self.assertIn(
            'reverse proxy', contenido,
            'docs/OPERACION.md debe explicar el supuesto del reverse '
            'proxy confiable',
        )

    # ── SEC-04: mail_admins + EMAIL_BACKEND por entorno ────────────────

    def test_sec04_logging_define_handler_mail_admins(self):
        """
        SEC-04: LOGGING debe definir el handler mail_admins con
        AdminEmailHandler a nivel ERROR (notif de 500 a ADMINS).
        """
        handlers = settings.LOGGING['handlers']
        self.assertIn(
            'mail_admins', handlers,
            'LOGGING debe definir el handler mail_admins (SEC-04)',
        )
        self.assertEqual(
            handlers['mail_admins']['class'],
            'django.utils.log.AdminEmailHandler',
        )
        self.assertEqual(handlers['mail_admins']['level'], 'ERROR')

    def test_sec04_django_request_notifica_a_admins(self):
        """
        SEC-04: el logger django.request debe incluir mail_admins (los 500
        llegan por correo) conservando los handlers existentes (file y
        console) para no degradar el log actual.
        """
        handlers = settings.LOGGING['loggers']['django.request']['handlers']
        self.assertIn('mail_admins', handlers)
        self.assertIn('file', handlers)
        self.assertIn('console', handlers)

    def test_sec04_email_backend_default_console(self):
        """
        SEC-04: el EMAIL_BACKEND por defecto debe ser el backend console
        (escribe el "email" en stdout: seguro en dev y tests, sin SMTP
        silencioso que rompa).

        Se lee del MODULO de settings porque el runner de tests
        sobreescribe settings.EMAIL_BACKEND (instancia LazySettings) con
        el backend locmem durante la suite.
        """
        from importlib import import_module
        modulo = import_module('a2lt_stock_project.settings')
        self.assertEqual(
            getattr(modulo, 'EMAIL_BACKEND', None),
            'django.core.mail.backends.console.EmailBackend',
            'EMAIL_BACKEND por defecto debe ser el backend console',
        )

    def test_sec04_admins_configurados(self):
        """
        SEC-04: ADMINS no vacio y el correo proviene de ADMIN_EMAIL
        (destinatario de las notificaciones de error 500).
        """
        self.assertTrue(settings.ADMINS, 'ADMINS no debe estar vacio')
        self.assertTrue(settings.ADMIN_EMAIL, 'ADMIN_EMAIL no debe ser vacio')
        correos = [correo for _, correo in settings.ADMINS]
        self.assertIn(settings.ADMIN_EMAIL, correos)


if __name__ == '__main__':
    unittest.main()
