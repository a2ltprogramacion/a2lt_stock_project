"""
Tests de seguridad: SEC-06 (403 con template HTML) y SEC-02b (CSP middleware).

Remediaciones del bloque "seguridad HTTP/UX" de docs/AUDIT_REPORT.md
(ronda 2026-10, sin spec formal):

- SEC-06: los 403 se servian en texto plano (middleware del tenant y
  vista contactos). Ahora renderizan inventory/403.html con el branding
  del sistema (hereda de base.html), conservando los mensajes literales
  y el status 403.
- SEC-02b: Content-Security-Policy aplicada via middleware a TODAS las
  respuestas (incluidos los 403 del TenantMiddleware). La politica se
  define en settings.CSP_POLICY (overridable por env).

Decision de colocacion (importante): CspMiddleware se registra ANTES de
TenantMiddleware en settings.MIDDLEWARE. TenantMiddleware retorna sus 403
con "return forbidden" SIN invocar self.get_response (early return), por
lo que ninguno de los middlewares por DEBAJO de el en la cadena llega a
procesar esas respuestas. Colocar CspMiddleware al final de la lista lo
dejarria debajo del TenantMiddleware y los 403 del tenant NO llevarian
la cabecera CSP (el test test_sec02b_csp_header_en_403_del_middleware
garantiza la cobertura).
"""
from pathlib import Path

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render
from django.test import RequestFactory, SimpleTestCase, TestCase
from django.urls import reverse

from inventory.models import Empresa

# Titulo literal que debe mostrar el template 403 (SEC-06). Em-dash
# incluido: el test garantiza el branding exacto de la pagina.
TITULO_403 = '403 — Acceso Denegado'


class FixtureSec06Sec02b(TestCase):
    """
    Fixture comun: empresa activa + usuario autenticado con perfil y
    UNA sola empresa permitida (mismo patron del resto de la suite).
    """

    @classmethod
    def setUpTestData(cls):
        cls.empresa = Empresa.objects.create(
            nombre='Csp403Corp', rif='J-CSP403-001', activa=True
        )
        cls.user = User.objects.create_user('csp403_user', password='pw12345')
        cls.perfil = cls.user.perfil
        cls.perfil.empresas_permitidas.add(cls.empresa)
        cls.perfil.empresa_activa = cls.empresa
        cls.perfil.save()


class TestSec06Pagina403Html(FixtureSec06Sec02b):
    """SEC-06: los 403 son paginas HTML con branding, no texto plano."""

    # ── 1. Middleware 403 renderiza HTML con branding ─────────────────

    def test_sec06_middleware_403_renderiza_html_con_branding(self):
        """
        Disparo (patron existente en tests.py::TestMiddleware, caso
        "sin empresa en sesion"): usuario autenticado con perfil, sin
        empresa_id en la sesion, accede a una vista protegida
        (/dashboard/). TenantMiddleware._authorize retorna 403 en su
        validacion #3 ("no se encontro empresa asociada en la sesion").

        Criterio: status 403, content_type HTML, cuerpo con el titulo
        del template, el branding del base layout y el mensaje literal
        del sitio disparado (los mensajes NO se modifican).
        """
        self.client.login(username='csp403_user', password='pw12345')
        # Sin empresa_id en sesion → validacion #3 del TenantMiddleware.
        resp = self.client.get(reverse('inventory:dashboard'))

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(
            resp['Content-Type'].startswith('text/html'),
            f"El 403 debe ser HTML, no texto plano. got {resp['Content-Type']}"
        )
        body = resp.content.decode('utf-8')
        self.assertIn(
            TITULO_403, body,
            "El 403 debe renderizar el titulo del template 403.html"
        )
        self.assertIn(
            'A2LT Stock', body,
            "El 403 debe heredar el branding del layout (base.html)"
        )
        self.assertIn(
            'no se encontro empresa asociada en la sesion', body,
            "El mensaje literal del sitio de 403 debe conservarse"
        )

    # ── 2. Guard: el template renderiza sin contexto vivo ────────────

    def test_sec06_template_renderiza_sin_contexto_vivo(self):
        """
        Guard del riesgo real: el 403 del middleware se dispara JUSTO
        cuando la sesion/tenant esta roto, asi que 403.html (y el
        base.html que hereda) debe renderizar con un request anonimo
        SIN sesion, SIN tenant (ContextVar None) y sin contexto extra.

        Criterio: render() NO lanza, responde 403 HTML con el titulo y
        el mensaje recibido.
        """
        from inventory.managers import reset_current_empresa, set_current_empresa

        request = RequestFactory().get('/')
        # ContextVar explicitamente None (sin depender del estado que
        # hayan dejado otros tests en este hilo).
        token = set_current_empresa(None)
        try:
            resp = render(
                request, 'inventory/403.html',
                {'mensaje': 'Mensaje guard test'}, status=403
            )
        finally:
            reset_current_empresa(token)

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(resp['Content-Type'].startswith('text/html'))
        body = resp.content.decode('utf-8')
        self.assertIn(TITULO_403, body)
        self.assertIn('Mensaje guard test', body)

    # ── 3. Vista contactos (views.py:1383) responde HTML ──────────────

    def test_sec06_vista_empresa_no_detectada_es_html(self):
        """
        Disparo del 403 de views.py (contactos, "Sesion de empresa no
        detectada."): la vista es defense-in-depth — por el flujo
        completo del TenantMiddleware el ContextVar siempre esta seteado
        cuando la vista corre (si el tenant falla, el middleware 403
        antes) — asi que se invoca la vista directamente con
        RequestFactory (mismo patron del test C5 de la suite) y el
        ContextVar forzado a None, que es el unico estado en el que esa
        rama puede dispararse.

        Criterio: 403 HTML con el mensaje literal "Sesión de empresa no
        detectada." (este mensaje SI lleva acentos).
        """
        from inventory import views
        from inventory.managers import reset_current_empresa, set_current_empresa

        request = RequestFactory().get(reverse('inventory:contactos'))
        request.user = self.user  # autenticado: pasa el @login_required

        token = set_current_empresa(None)
        try:
            resp = views.contactos(request)
        finally:
            reset_current_empresa(token)

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(
            resp['Content-Type'].startswith('text/html'),
            f"El 403 de la vista debe ser HTML. got {resp['Content-Type']}"
        )
        body = resp.content.decode('utf-8')
        self.assertIn(TITULO_403, body)
        self.assertIn('Sesión de empresa no detectada.', body)

    # ── 4. No queda ningun 403 en texto plano ──────────────────────────

    def test_sec06_no_queda_403_en_texto_plano(self):
        """
        Invariante estructural: middleware.py y views.py ya no pueden
        contener la construccion HttpResponseForbidden(...) (texto
        plano). Los 403 deben construirse con render(..., status=403).
        """
        raiz = Path(settings.BASE_DIR)
        for relativa in ('inventory/middleware.py', 'inventory/views.py'):
            ruta = raiz / relativa
            fuente = ruta.read_text(encoding='utf-8')
            self.assertNotIn(
                'HttpResponseForbidden(', fuente,
                f"{relativa} todavia construye 403 en texto plano "
                f"(SEC-06 exige render con template HTML)"
            )


class TestSec02bContentSecurityPolicy(FixtureSec06Sec02b):
    """SEC-02b: Content-Security-Policy en todas las respuestas."""

    # ── 5. Login anonimo lleva la CSP ─────────────────────────────────

    def test_sec02b_csp_header_en_login(self):
        """
        La pantalla de login (anonima, sin tenant) lleva la cabecera CSP.

        Nota: la URL efectiva del login es la raiz '/' (name='login';
        no existe '/login/' como ruta separada), ver inventory/urls.py.
        """
        resp = self.client.get(reverse('inventory:login'))
        self.assertEqual(resp.status_code, 200)

        csp = resp.get('Content-Security-Policy', '')
        for directiva in (
            "default-src 'self'",
            'cdn.tailwindcss.com',
            "object-src 'none'",
            "frame-ancestors 'none'",
        ):
            self.assertIn(
                directiva, csp,
                f"La CSP del login debe contener '{directiva}'. got: {csp!r}"
            )

    # ── 6. Pagina autenticada lleva la CSP ────────────────────────────

    def test_sec02b_csp_header_en_pagina_autenticada(self):
        """
        Login + empresa en sesion + dashboard → la respuesta autenticada
        tambien lleva la cabecera CSP.
        """
        self.client.login(username='csp403_user', password='pw12345')
        session = self.client.session
        session['empresa_id'] = self.empresa.id
        session.save()

        resp = self.client.get(reverse('inventory:dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            resp.has_header('Content-Security-Policy'),
            "La respuesta autenticada debe llevar Content-Security-Policy"
        )

    # ── 7. Los 403 del TenantMiddleware tambien llevan la CSP ─────────

    def test_sec02b_csp_header_en_403_del_middleware(self):
        """
        El 403 del TenantMiddleware (mismo disparo del test SEC-06 #1)
        TAMBIEN lleva la CSP. Esto exige que CspMiddleware este POR
        ENCIMA del TenantMiddleware en settings.MIDDLEWARE: el 403 del
        tenant se retorna con early return (sin llamar get_response),
        asi que los middlewares por debajo de el nunca lo procesan.
        """
        self.client.login(username='csp403_user', password='pw12345')
        resp = self.client.get(reverse('inventory:dashboard'))  # sin empresa en sesion

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(
            resp.has_header('Content-Security-Policy'),
            "El 403 del TenantMiddleware debe llevar Content-Security-Policy"
        )

    # ── 9. La politica cubre los origenes externos reales ──────────────

    def test_sec02b_politica_cubre_recursos_reales(self):
        """
        settings.CSP_POLICY debe listar los 4 origenes externos que el
        frontend realmente referencia (inventario de la auditoria):
        Tailwind CDN, jsdelivr (bootstrap-icons + woff2), Google Fonts
        (@import CSS) y fonts.gstatic.com (ficheros de fuente).
        """
        for origen in (
            'cdn.tailwindcss.com',
            'cdn.jsdelivr.net',
            'fonts.googleapis.com',
            'fonts.gstatic.com',
        ):
            self.assertIn(
                origen, settings.CSP_POLICY,
                f"CSP_POLICY debe permitir el origen real {origen}"
            )


class TestSec02bCspMiddlewareUnit(SimpleTestCase):
    """SEC-02b: unit test del middleware (sin BD)."""

    # ── 8. El middleware no sobrescribe un header existente ───────────

    def test_sec02b_csp_no_sobrescribe_header_existente(self):
        """
        CspMiddleware respeta responses que ya traen su propia CSP
        (has_header check): no debe sobrescribir 'X' pre-fijado.
        Control positivo en el mismo test: un response sin CSP previa
        si recibe settings.CSP_POLICY.
        """
        from inventory.middleware import CspMiddleware

        request = RequestFactory().get('/')

        # Arrange/Act: response con CSP pre-fijada.
        resp_preexistente = HttpResponse('contenido')
        resp_preexistente['Content-Security-Policy'] = 'X'
        middleware = CspMiddleware(get_response=lambda r: resp_preexistente)

        # Assert: el middleware NO cambia el header existente.
        salida = middleware(request)
        self.assertEqual(salida['Content-Security-Policy'], 'X')

        # Control positivo: sin header previo se aplica la politica.
        resp_fresca = HttpResponse('contenido')
        middleware_fresco = CspMiddleware(get_response=lambda r: resp_fresca)
        salida_fresca = middleware_fresco(request)
        self.assertEqual(salida_fresca['Content-Security-Policy'], settings.CSP_POLICY)


if __name__ == '__main__':
    import unittest
    unittest.main()
