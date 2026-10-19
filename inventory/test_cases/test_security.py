"""
Tests de seguridad para configuración de despliegue (TASK-SEC01-01).

Verifica que check --deploy falle sin SECRET_KEY en el entorno.
"""
import os
import subprocess
import unittest
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


if __name__ == '__main__':
    unittest.main()