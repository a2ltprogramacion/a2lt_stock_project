"""
Tests de seguridad para configuración de despliegue (TASK-SEC01-01, SEC-02).

Verifica que check --deploy falle sin SECRET_KEY en el entorno y que el
token CSRF expuesto por DOM (<meta name="csrf-token">) sea funcional.
"""
import os
import re
import subprocess
import sys
import unittest
from django.conf import settings
from django.test import TestCase


class TestSecuritySettings(TestCase):
    """Pruebas de configuración de seguridad para despliegue."""

    def test_sec01_check_deploy_fails_without_secret_key(self):
        """
        check --deploy debe fallar si SECRET_KEY no está en entorno.

        Actualmente el test DEBE fallar (RED) porque existe un fallback
        inseguro en settings.py: SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod')
        """
        # Guardar SECRET_KEY actual si existe
        old_secret = os.environ.get('SECRET_KEY')
        # Establecer SECRET_KEY como string vacío para impedir que setdefault() lo sobrescriba
        os.environ['SECRET_KEY'] = ''

        try:
            # Ejecutar check --deploy
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            result = subprocess.run(
                ['python', 'manage.py', 'check', '--deploy'],
                capture_output=True, text=True, env=os.environ,
                cwd=project_root
            )
            # RED: Actualmente PUEDE pasar (fallback inseguro existe en .env y settings.py)
            # El test DEBE fallar porque check --deploy DEBE fallar sin SECRET_KEY
            self.assertNotEqual(
                result.returncode, 0,
                f"check --deploy DEBE fallar sin SECRET_KEY en entorno. "
                f"Return code: {result.returncode}, stdout: {result.stdout}, stderr: {result.stderr}"
            )
        finally:
            # Restaurar SECRET_KEY al estado original
            if old_secret is not None:
                os.environ['SECRET_KEY'] = old_secret
            else:
                # Si no existía originalmente, eliminar la clave
                if 'SECRET_KEY' in os.environ:
                    del os.environ['SECRET_KEY']

    def test_sec01_error_message_contains_generation_command(self):
        """
        Verificar que mensaje de error incluye comando de generación de SECRET_KEY.
        """
        import os
        import subprocess
        
        old_secret = os.environ.get('SECRET_KEY')
        os.environ['SECRET_KEY'] = ''
        
        try:
            project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            result = subprocess.run(
                ['python', 'manage.py', 'check', '--deploy'],
                capture_output=True, text=True, env=os.environ,
                cwd=project_root
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('python -c "import secrets; print(secrets.token_urlsafe(64))"', result.stderr)
        finally:
            if old_secret is not None:
                os.environ['SECRET_KEY'] = old_secret
            else:
                if 'SECRET_KEY' in os.environ:
                    del os.environ['SECRET_KEY']

    def test_sec01_dev_env_works_with_dotenv(self):
        """
        Con .env local, manage.py check pasa (sin --deploy).
        """
        import subprocess
        
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        result = subprocess.run(
            ['python', 'manage.py', 'check'],
            capture_output=True, text=True,
            cwd=project_root
        )
        self.assertEqual(result.returncode, 0)

    def test_sec01_no_hardcoded_fallback_in_code(self):
        """
        Grep confirma ausencia de 'dev-insecure-key-change-in-prod' en settings.py.
        """
        import os
        from django.conf import settings
        
        settings_path = os.path.join(settings.BASE_DIR, 'a2lt_stock_project', 'settings.py')
        with open(settings_path) as f:
            content = f.read()
        self.assertNotIn('dev-insecure-key-change-in-prod', content)

    def test_sec01_improperly_configured_raised(self):
        """
        Importar settings sin SECRET_KEY lanza ImproperlyConfigured.
        """
        import os
        import importlib
        from django.core.exceptions import ImproperlyConfigured
        
        old = os.environ.get('SECRET_KEY')
        os.environ['SECRET_KEY'] = ''
        
        try:
            import a2lt_stock_project.settings as settings_mod
            importlib.reload(settings_mod)
        except ImproperlyConfigured as e:
            self.assertIn('SECRET_KEY', str(e))
            self.assertIn('secrets.token_urlsafe(64)', str(e))
        finally:
            if old:
                os.environ['SECRET_KEY'] = old
            else:
                os.environ.pop('SECRET_KEY', None)

    def test_sec02_csrf_cookie_httponly_true(self):
        """
        CSRF_COOKIE_HTTPONLY debe ser True para seguridad.

        RED: Actualmente DEBE fallar porque CSRF_COOKIE_HTTPONLY = False en settings.py
        (línea 246: "False para que JS (getCookie) pueda leerlo via A6").
        """
        from django.conf import settings
        self.assertTrue(
            settings.CSRF_COOKIE_HTTPONLY,
            "CSRF_COOKIE_HTTPONLY debe ser True para prevenir robo de token CSRF via XSS"
        )

    def test_sec02_deploy_check_falla_con_debug_true(self):
        """
        SEC-02 (SEC02-05 + SEC02-07): con DEBUG=True el despliegue DEBE bloquearse.

        check --deploy --fail-level WARNING debe fallar (returncode != 0) y
        reportar security.W018 ("You have 'DEBUG = True'"). Este es el gate
        determinista que impide publicar una build de produccion con DEBUG activo.

        Nota: NO se usa el caso DEBUG=False (dejar limpio check --deploy exige
        HTTPS/HSTS reales y no es determinista en este entorno).
        """
        env = dict(os.environ)
        # manage.py usa os.environ.setdefault() al cargar .env, por lo que una
        # variable ya presente en env NO es sobrescrita.
        env['DEBUG'] = 'True'
        result = subprocess.run(
            [sys.executable, 'manage.py', 'check', '--deploy',
             '--fail-level', 'WARNING'],
            capture_output=True, text=True, env=env, cwd=str(settings.BASE_DIR),
        )
        out = (result.stdout or '') + (result.stderr or '')
        self.assertNotEqual(
            result.returncode, 0,
            "check --deploy --fail-level WARNING DEBE fallar si DEBUG=True. "
            f"returncode={result.returncode}. Salida: {out}"
        )
        self.assertIn(
            'security.W018', out,
            "Debe reportar W018 (DEBUG=True en despliegue). "
            f"Salida: {out}"
        )

    def test_sec02_dotenv_example_debug_false(self):
        """
        SEC-02 (TASK-SEC02-06): .env.example debe existir y ser seguro.

        Plantilla publica (siempre commiteable) con DEBUG=False por defecto.
        """
        path = os.path.join(settings.BASE_DIR, '.env.example')
        self.assertTrue(os.path.exists(path), '.env.example debe existir')
        with open(path, encoding='utf-8') as f:
            content = f.read()
        self.assertIn('DEBUG=False', content)
        self.assertNotIn('DEBUG=True', content)


class TestSecurityCsrfDom(TestCase):
    """SEC-02: el token CSRF debe exponerse por DOM (cookie HttpOnly)."""

    def _read(self, rel):
        import os
        from django.conf import settings as dj_settings
        path = os.path.join(dj_settings.BASE_DIR, rel)
        with open(path, encoding='utf-8') as f:
            return f.read()

    def test_sec02_meta_csrf_token_in_base_html(self):
        content = self._read('inventory/templates/inventory/base.html')
        self.assertIn('name="csrf-token"', content)
        self.assertIn('{{ csrf_token }}', content)

    def test_sec02_js_getcsrftoken_reads_from_dom(self):
        content = self._read('inventory/templates/inventory/base.html')
        self.assertIn('function getCsrfToken', content)
        self.assertIn('meta[name="csrf-token"]', content)

    def test_sec02_no_template_reads_csrftoken_cookie(self):
        import glob
        import os
        from django.conf import settings as dj_settings
        root = os.path.join(dj_settings.BASE_DIR, 'inventory', 'templates')
        offenders = []
        for path in glob.glob(os.path.join(root, '**', '*.html'), recursive=True):
            with open(path, encoding='utf-8') as f:
                if "getCookie('csrftoken')" in f.read():
                    offenders.append(os.path.relpath(path, dj_settings.BASE_DIR))
        self.assertEqual(offenders, [], f"Plantillas que aun leen la cookie CSRF: {offenders}")


class TestSecurityCsrfAjax(TestCase):
    """
    SEC-02 / TASK-SEC02-04: prueba FUNCIONAL end-to-end.

    El token que el JS lee del DOM (<meta name="csrf-token">, via
    getCsrfToken()) debe ser ACEPTADO por el servidor Django cuando
    enforce_csrf_checks=True. Esto valida la migracion completa:
    cookie HttpOnly (ilegible por JS) -> token expuesto en el DOM.

    Endpoint POST autenticado reutilizado: /movimientos/registrar/
    (inventory:registrar_asiento_manual), el mismo endpoint AJAX que ya
    validan TestRegistrarAsientoManualKardex y TestSecurityCSRFEnforcedOnAllPOST.
    """

    def setUp(self):
        from django.contrib.auth.models import User
        from django.test import Client

        # Reutiliza los helpers canonicos de inventario (mismo patron de login
        # y tenant que TestRegistrarAsientoManualKardex en inventory/tests.py).
        from inventory.tests import (
            crear_empresa, crear_almacen, crear_articulo_fisico,
        )

        self.empresa = crear_empresa(nombre='CsrfMetaT', rif='J-CSRFM-001')
        self.almacen = crear_almacen(self.empresa, nombre='Almacen CSRF Meta')
        self.articulo = crear_articulo_fisico(
            self.empresa, sku='CSRFM-001', nombre='Articulo CSRF Meta'
        )

        self.user = User.objects.create_user('csrfmeta', password='pw1234')
        perfil = self.user.perfil
        perfil.empresas_permitidas.add(self.empresa)
        perfil.empresa_activa = self.empresa
        perfil.save()

        # Cliente con CSRF FORTIFICADO: el middleware valida de verdad.
        self.client = Client(enforce_csrf_checks=True)
        self.assertTrue(
            self.client.login(username='csrfmeta', password='pw1234'),
            'login del usuario de prueba fallo'
        )
        session = self.client.session
        session['empresa_id'] = self.empresa.id
        session.save()

    def _post_ajustes(self, token):
        """POST JSON al endpoint AJAX con el token indicado como X-CSRFToken."""
        import json as _json
        from django.urls import reverse

        return self.client.post(
            reverse('inventory:registrar_asiento_manual'),
            data=_json.dumps({
                'articulo_id': self.articulo.pk,
                'almacen_id': self.almacen.pk,
                'tipo': 'ENTRADA',
                'cantidad': 3,
                'detalle': 'Verificacion funcional del token del <meta>',
            }),
            content_type='application/json',
            HTTP_X_CSRFTOKEN=token,
        )

    def test_sec02_meta_token_aceptado_por_servidor(self):
        """
        El token del <meta csrf-token> (lo que lee getCsrfToken()) es valido
        para Django con enforce_csrf_checks=True.
        """
        from django.urls import reverse

        # 1. GET a una pagina que extiende base.html (inyecta el <meta>).
        resp = self.client.get(reverse('inventory:movimientos'))
        self.assertEqual(resp.status_code, 200, f"GET movimientos={resp.status_code}")

        # 2. Extraer el token del DOM: exactamente lo que hace getCsrfToken().
        match = re.search(
            r'name="csrf-token" content="([^"]+)"', resp.content.decode()
        )
        self.assertIsNotNone(
            match,
            "base.html debe renderizar <meta name=\"csrf-token\" content=\"...\">"
        )
        token = match.group(1)
        self.assertGreaterEqual(len(token), 32, f"token CSRF muy corto: {token!r}")
        self.assertEqual(
            len(token), 64,
            f"token CSRF ofuscado esperado de 64 chars, recibido {len(token)}"
        )

        # 3. POST autenticado usando SOLO el token del DOM.
        resp = self._post_ajustes(token)
        body = resp.content.decode()[:2000]
        self.assertNotEqual(
            resp.status_code, 403,
            f"El token del <meta> fue RECHAZADO por el servidor (403): {body}"
        )
        self.assertNotIn(
            'CSRF', body,
            f"La respuesta menciona un fallo CSRF: {body}"
        )

    def test_sec02_token_invalido_rechazado_403(self):
        """
        Control negativo: con un token basura, el server DEBE rechazar (403).

        Garantiza que el test positivo no pasa "por accidente" (si la
        proteccion CSRF estuviese desactivada, este control fallaria).
        """
        resp = self._post_ajustes('x' * 64)
        self.assertEqual(
            resp.status_code, 403,
            f"Con token invalido el server debe responder 403, respondio "
            f"{resp.status_code}: {resp.content.decode()[:500]}"
        )


if __name__ == '__main__':
    unittest.main()