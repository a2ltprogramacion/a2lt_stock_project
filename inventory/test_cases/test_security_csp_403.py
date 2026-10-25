"""
Tests de seguridad: SEC-06 (403 con template HTML) y SEC-02b (CSP nativo).

Remediaciones del bloque "seguridad HTTP/UX" de docs/AUDIT_REPORT.md
(SEC-06) y migracion al CSP nativo de Django 6 con nonces (SEC-02b,
REQ-CSP-* del Capitulo 2 de docs/plans/EST_ESTRUCTURALES_PLAN_Y_TAREAS.md):

- SEC-06: los 403 se servian en texto plano (middleware del tenant y
  vista contactos). Ahora renderizan inventory/403.html con el branding
  del sistema (hereda de base.html), conservando los mensajes literales
  y el status 403.
- SEC-02b: Content-Security-Policy via el middleware NATIVO de Django 6
  (django.middleware.csp.ContentSecurityPolicyMiddleware). La politica
  es el dict settings.SECURE_CSP / settings.SECURE_CSP_REPORT_ONLY
  (segun el knob CSP_MODE, default 'report') con nonce por request;
  el context processor django.template.context_processors.csp expone
  {{ csp_nonce }} a las plantillas.

Decision de colocacion (importante): el middleware CSP (nativo) se registra
ANTES de TenantMiddleware en settings.MIDDLEWARE. TenantMiddleware retorna sus 403
con "return forbidden" SIN invocar self.get_response (early return).
El middleware nativo es MiddlewareMixin: setea request._csp_nonce en
process_request (fase de bajada, ANTES de que el tenant renderice sus
403) y aplica el header en process_response al SUBIR la respuesta por
su frame, asi que estando POR ENCIMA cubre tambien los 403 del tenant
(el test test_sec02b_csp_header_en_403_del_middleware garantiza la
cobertura).
"""
from pathlib import Path
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import render
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from inventory.models import Empresa

# Titulo literal que debe mostrar el template 403 (SEC-06). Em-dash
# incluido: el test garantiza el branding exacto de la pagina.
TITULO_403 = '403 — Acceso Denegado'


def csp_de(resp):
    """
    Valor del header CSP ACTIVO para el modo configurado (modo-agnostico,
    REQ-CSP-06): con CSP_MODE='report' (default de la suite, que corre sin
    env) el header es Content-Security-Policy-Report-Only; con 'enforce'
    es el bloqueante. None si ninguno presente.
    """
    return (resp.get('Content-Security-Policy')
            or resp.get('Content-Security-Policy-Report-Only'))


def fragmento_directiva(politica, directiva):
    """
    Valor de `directiva` dentro de una politica CSP serializada
    (build_policy une directivas con '; ' y valores con ' ').
    '' si la directiva no esta presente.
    """
    for parte in politica.split(';'):
        trozos = parte.strip().split(None, 1)
        if trozos and trozos[0] == directiva:
            return trozos[1] if len(trozos) > 1 else ''
    return ''


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
        La pantalla de login (anonima, sin tenant) lleva la cabecera CSP
        del modo activo (default de la suite: -Report-Only).

        Nota: la URL efectiva del login es la raiz '/' (name='login';
        no existe '/login/' como ruta separada), ver inventory/urls.py.

        REQ-CSP-03: script-src lleva nonce y NO lleva 'unsafe-inline'
        (con nonce, CSP3 lo ignoraria de todos modos — eliminacion
        efectiva, no cosmética); style-src SI lo conserva (deuda
        documentada: Tailwind CDN JIT inyecta <style> en runtime).
        """
        resp = self.client.get(reverse('inventory:login'))
        self.assertEqual(resp.status_code, 200)

        csp = csp_de(resp)
        self.assertTrue(
            csp, "El login debe llevar la cabecera CSP del modo activo"
        )
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

        script_src = fragmento_directiva(csp, 'script-src')
        self.assertIn(
            "'nonce-", script_src,
            f"script-src debe llevar el nonce por request (la pagina de "
            f"login renderiza scripts inline nocificados). got: {script_src!r}"
        )
        self.assertNotIn(
            "'unsafe-inline'", script_src,
            "REQ-CSP-03: script-src no debe llevar 'unsafe-inline' "
            f"(el nonce lo reemplaza). got: {script_src!r}"
        )
        self.assertIn(
            "'unsafe-inline'", fragmento_directiva(csp, 'style-src'),
            "style-src conserva 'unsafe-inline' (deuda Tailwind CDN JIT)"
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
            csp_de(resp),
            "La respuesta autenticada debe llevar la cabecera CSP "
            "del modo activo (default: -Report-Only)"
        )

    # ── 7. Los 403 del TenantMiddleware tambien llevan la CSP ─────────

    def test_sec02b_csp_header_en_403_del_middleware(self):
        """
        El 403 del TenantMiddleware (mismo disparo del test SEC-06 #1)
        TAMBIEN lleva la CSP. Esto exige que el middleware CSP nativo
        este POR ENCIMA del TenantMiddleware en settings.MIDDLEWARE:
        el 403 del tenant se retorna con early return (sin llamar
        get_response); al ser MiddlewareMixin, el nativo lo procesa
        en process_response al subir la respuesta por su frame.
        """
        self.client.login(username='csp403_user', password='pw12345')
        resp = self.client.get(reverse('inventory:dashboard'))  # sin empresa en sesion

        self.assertEqual(resp.status_code, 403)
        self.assertTrue(
            csp_de(resp),
            "El 403 del TenantMiddleware debe llevar la cabecera CSP "
            "del modo activo"
        )

    # ── 9. La politica cubre los origenes externos reales ──────────────

    def test_sec02b_politica_cubre_recursos_reales(self):
        """
        El dict activo (settings.SECURE_CSP_REPORT_ONLY o settings.SECURE_CSP
        segun el knob settings.CSP_MODE) debe listar los 4 origenes externos
        que el frontend realmente referencia (inventario de la auditoria):
        Tailwind CDN, jsdelivr (bootstrap-icons + woff2), Google Fonts
        (@import CSS) y fonts.gstatic.com (ficheros de fuente).
        """
        modo = getattr(settings, 'CSP_MODE', 'report')
        politica = (settings.SECURE_CSP if modo == 'enforce'
                    else settings.SECURE_CSP_REPORT_ONLY)
        # Aplana dict -> string para no acoplarse a la directiva exacta
        # en la que vive cada origen.
        valores = ' '.join(
            str(v) for vals in politica.values() for v in (vals or [])
        )
        for origen in (
            'cdn.tailwindcss.com',
            'cdn.jsdelivr.net',
            'fonts.googleapis.com',
            'fonts.gstatic.com',
        ):
            self.assertIn(
                origen, valores,
                f"El dict CSP del modo {modo!r} debe permitir el "
                f"origen real {origen}. got: {valores!r}"
            )

    # ── 11. Nonce del header == nonce de los scripts renderizados ─────

    def test_csp_nonce_header_coincide_con_scripts_renderizados(self):
        """
        REQ-CSP-04: en una pagina real (dashboard, hereda los 3 scripts
        inline de base.html) el nonce del header script-src es el MISMO
        que renderiza cada <script> inline del body (LazyNonce: header y
        plantilla comparten valor por request).
        """
        self.client.login(username='csp403_user', password='pw12345')
        session = self.client.session
        session['empresa_id'] = self.empresa.id
        session.save()

        resp = self.client.get(reverse('inventory:dashboard'))
        self.assertEqual(resp.status_code, 200)

        csp = csp_de(resp)
        self.assertTrue(csp, "El dashboard debe llevar la CSP del modo activo")
        m = re.search(r"'nonce-([^']+)'", fragmento_directiva(csp, 'script-src'))
        self.assertIsNotNone(
            m, f"script-src del header debe llevar 'nonce-<token>'. got: {csp!r}"
        )
        token = m.group(1)

        body = resp.content.decode('utf-8')
        inline = [
            tag for tag in re.findall(r'<script\b[^>]*>', body)
            if 'src=' not in tag
            and 'application/json' not in tag  # json_script = data block
        ]
        self.assertTrue(
            inline, "El dashboard debe renderizar scripts inline (base.html)"
        )
        for tag in inline:
            self.assertIn(
                f'nonce="{token}"', tag,
                f"Cada script inline debe llevar el nonce del header "
                f"({token!r}). tags: {inline!r}"
            )

    # ── 13. Nonces distintos entre requests (no reuso) ─────────────────

    def test_csp_nonces_distintos_entre_requests(self):
        """
        REQ-CSP-03: el nonce es por request (secrets.token_urlsafe(16)
        via LazyNonce). Dos GET al login deben producir tokens
        DISTINTOS en el header — el reuso permitiria eludir la politica
        si un nonce filtrado sobreviviera.
        """
        tokens = []
        for _ in range(2):
            resp = self.client.get(reverse('inventory:login'))
            csp = csp_de(resp)
            self.assertTrue(csp, "El login debe llevar la CSP del modo activo")
            m = re.search(r"'nonce-([^']+)'", fragmento_directiva(csp, 'script-src'))
            self.assertIsNotNone(
                m,
                f"script-src del header debe llevar 'nonce-<token>' "
                f"(login.html renderiza script inline). got: {csp!r}"
            )
            tokens.append(m.group(1))
        self.assertNotEqual(
            tokens[0], tokens[1],
            "El nonce debe regenerarse por request (CSP-03): dos GET al "
            "login produjeron el mismo token"
        )

    # ── 14. Default del knob: Report-Only, no bloqueante ───────────────

    def test_csp_report_only_default_emite_header_no_bloqueante(self):
        """
        REQ-CSP-06: con el knob en su default (CSP_MODE='report', la
        suite corre sin env) la politica viaja como
        Content-Security-Policy-Report-Only (ventana de adopcion: no
        bloquea nada) y el header bloqueante NO se emite (SECURE_CSP
        queda en su default {} = sin header).
        """
        self.assertEqual(
            getattr(settings, 'CSP_MODE', None), 'report',
            "El default del knob CSP_MODE debe ser 'report' "
            "(despliegue seguro gradual)"
        )
        resp = self.client.get(reverse('inventory:login'))
        self.assertEqual(resp.status_code, 200)

        self.assertTrue(
            resp.get('Content-Security-Policy-Report-Only'),
            "Modo report: el header -Report-Only debe estar presente"
        )
        self.assertFalse(
            resp.get('Content-Security-Policy'),
            "Modo report: el header bloqueante NO debe emitirse"
        )

    # ── 15. Flip a enforcing: header bloqueante por settings ───────────

    def test_csp_enforce_flip_emite_header_bloqueante(self):
        """
        REQ-CSP-06: el flip a enforcing es un cambio de SETTINGS (en
        produccion: CSP_MODE=enforce + restart; aqui se simula con
        override_settings, que el nativo respeta porque lee
        settings.SECURE_CSP / SECURE_CSP_REPORT_ONLY por request): se
        emite el header BLOQUEANTE y el -Report-Only desaparece.
        """
        with override_settings(
            SECURE_CSP=settings._CSP_DICT,
            SECURE_CSP_REPORT_ONLY={},
        ):
            resp = self.client.get(reverse('inventory:login'))
            self.assertEqual(resp.status_code, 200)

            bloqueante = resp.get('Content-Security-Policy')
            self.assertTrue(
                bloqueante,
                "Modo enforce: el header bloqueante debe estar presente"
            )
            self.assertFalse(
                resp.get('Content-Security-Policy-Report-Only'),
                "Modo enforce: el header -Report-Only NO debe emitirse"
            )
            # El nonce sigue viajando en el header bloqueante.
            self.assertIn(
                "'nonce-", fragmento_directiva(bloqueante, 'script-src'),
                f"El flip conserva el nonce en script-src. got: {bloqueante!r}"
            )


class TestSec02bCspMiddlewareUnit(SimpleTestCase):
    """SEC-02b: unit tests del middleware nativo + invariantes estructurales."""

    # ── 8. El middleware no sobrescribe un header existente ───────────

    def test_sec02b_csp_no_sobrescribe_header_existente(self):
        """
        El middleware NATIVO respeta responses que ya traen su propia
        CSP: no debe sobrescribir 'X' pre-fijado. Control positivo en
        el mismo test: un response sin CSP previa si recibe la politica
        del modo activo (default: header -Report-Only con nonce).
        """
        from django.middleware.csp import ContentSecurityPolicyMiddleware

        request = RequestFactory().get('/')

        # Arrange/Act: response con CSP pre-fijada.
        resp_preexistente = HttpResponse('contenido')
        resp_preexistente['Content-Security-Policy'] = 'X'
        middleware = ContentSecurityPolicyMiddleware(
            get_response=lambda r: resp_preexistente
        )

        # Assert: el middleware NO cambia el header existente.
        salida = middleware(request)
        self.assertEqual(salida['Content-Security-Policy'], 'X')

        # Control positivo: sin header previo se aplica la politica
        # del modo activo (REQ-CSP-03: sin 'unsafe-inline' en
        # script-src). Nota: este unit test NO renderiza plantillas,
        # asi que el LazyNonce nunca se evalua y el header sale sin
        # nonce (comportamiento nativo: el nonce solo viaja si la
        # respuesta lo consumio) — no se afirma el nonce aqui.
        resp_fresca = HttpResponse('contenido')
        middleware_fresco = ContentSecurityPolicyMiddleware(
            get_response=lambda r: resp_fresca
        )
        salida_fresca = middleware_fresco(request)
        politica = csp_de(salida_fresca)
        self.assertTrue(
            politica,
            "Un response fresco debe recibir la CSP del modo activo"
        )
        self.assertIn(
            'cdn.tailwindcss.com', politica,
            f"La politica del modo activo debe permitir Tailwind CDN. "
            f"got: {politica!r}"
        )
        self.assertNotIn(
            "'unsafe-inline'", fragmento_directiva(politica, 'script-src'),
            f"script-src no debe llevar 'unsafe-inline' (REQ-CSP-03). "
            f"got: {politica!r}"
        )

    # ── 10. Migracion al CSP nativo: eliminaciones y posicion ─────────

    def test_csp_csp_policy_y_middleware_propio_eliminados(self):
        """
        Invariante estructural de la migracion (REQ-CSP-01/02):
          - settings.py ya no define CSP_POLICY (string crudo retirado
            sin alias deprecado: su consumidor unico era el middleware
            propio, ya eliminado).
          - inventory/middleware.py ya no define class CspMiddleware
            (TenantMiddleware se conserva intacto).
          - settings.MIDDLEWARE tiene el middleware nativo
            inmediatamente ANTES de TenantMiddleware.
        """
        raiz = Path(settings.BASE_DIR)

        fuente_settings = (
            raiz / 'a2lt_stock_project' / 'settings.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn(
            'CSP_POLICY', fuente_settings,
            "settings.py no debe definir CSP_POLICY: la configuracion "
            "canonica es el dict SECURE_CSP / SECURE_CSP_REPORT_ONLY"
        )

        fuente_middleware = (
            raiz / 'inventory' / 'middleware.py'
        ).read_text(encoding='utf-8')
        self.assertNotIn(
            'class CspMiddleware', fuente_middleware,
            "inventory/middleware.py no debe definir CspMiddleware: la "
            "CSP la aplica el middleware nativo de Django 6"
        )

        mw = settings.MIDDLEWARE
        self.assertIn(
            'django.middleware.csp.ContentSecurityPolicyMiddleware', mw
        )
        self.assertEqual(
            mw.index('django.middleware.csp.ContentSecurityPolicyMiddleware')
            + 1,
            mw.index('inventory.middleware.TenantMiddleware'),
            "El middleware CSP nativo debe estar inmediatamente ANTES "
            "del TenantMiddleware (los 403 early-return del tenant "
            "suben por su frame y reciben el header)"
        )


class TestCspNocificacionPlantillas(SimpleTestCase):
    """REQ-CSP-04/05: gate estatico de plantillas (scan de archivos)."""

    # ── 12. Gate estatico: todo script inline lleva nonce ───────────────

    def test_csp_gate_estatico_scripts_inline_con_nonce(self):
        """
        REQ-CSP-05: anti-regresion estatico. Recorre TODO el arbol de
        plantillas (inventory/templates/ + templates/ del proyecto) y
        exige que cada tag <script> SIN src= (inline) lleve nonce=. Los
        tags externos con SRI (src=) NO se tocan: el nonce solo autoriza
        scripts inline. Falla reportando archivo:linea exactos.
        """
        raiz = Path(settings.BASE_DIR)
        faltantes = []
        vistos = 0
        for sub in ('inventory/templates', 'templates'):
            base_dir = raiz / sub
            if not base_dir.exists():
                continue
            for ruta in sorted(base_dir.rglob('*.html')):
                contenido = ruta.read_text(encoding='utf-8')
                for m in re.finditer(r'<script\b[^>]*>', contenido):
                    tag = m.group(0)
                    if 'src=' in tag:
                        continue  # externo SRI: fuera del alcance del gate
                    vistos += 1
                    if 'nonce=' not in tag:
                        linea = contenido.count('\n', 0, m.start()) + 1
                        faltantes.append(
                            f'{ruta.relative_to(raiz)}:{linea}'
                        )
        self.assertTrue(
            vistos > 0,
            "El gate no escaneo ningun <script> inline: revisa el arbol "
            "de plantillas (inventory/templates/)"
        )
        self.assertEqual(
            faltantes, [],
            "REQ-CSP-05: TODO <script> inline debe llevar nonce= (un "
            "script sin nonce rompe el JS de esa pagina al activar "
            "enforcing). Scripts sin nonce en: "
            + ', '.join(faltantes)
        )


if __name__ == '__main__':
    import unittest
    unittest.main()
