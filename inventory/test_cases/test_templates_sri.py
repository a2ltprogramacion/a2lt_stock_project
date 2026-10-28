"""
Tests de Subresource Integrity (SRI) en plantillas: SEC-05.

Remediacion del hallazgo SEC-05 de docs/AUDIT_REPORT.md (ronda 2026-10,
sin spec formal): los recursos de CDN referenciados desde las plantillas
se sirven sin `integrity`, por lo que un compromiso del CDN (o del
dominio cdn.tailwindcss.com, que ademas sirve "latest" sin version
pineada) inyectaria JS/CSS arbitrario en la aplicacion.

Remediacion implementada:

- Tailwind CDN pineado a version exacta (`/<mayor>.<minor>.<patch>`) en
  las 4 plantillas que lo referencian. Sin pineo no hay SRI posible:
  el dominio pelado sirve "latest" y el contenido cambia sin aviso.
- Todo recurso externo lleva `referrerpolicy="no-referrer"` (no filtra
  la URL de origen a los CDNs de terceros).
- HOTFIX 2026-10-27 (revierte parte de cc59926): cdn.tailwindcss.com
  NO envia Access-Control-Allow-Origin (verificado con
  Invoke-WebRequest/curl, con y sin header Origin, 2 UAs), por lo que
  `crossorigin="anonymous"` + `integrity` en su script ROMPEN la carga
  en navegadores reales (el fetch CORS es rechazado -> CORS block +
  `tailwind is not defined`). Los hosts de CDN_SIN_CORS quedan
  EXENTOS de integrity/crossorigin (la URL versionada sigue exigida);
  el resto de CDNs (jsDelivr SI envia ACAO:*) conserva
  integrity+crossorigin. Riesgo residual: version pineada + CSP
  script-src acota el origen; cierre definitivo: build local de
  Tailwind (backlog).
- El `@import` de Google Fonts dentro de `<style>` en base.html NO
  admite SRI (el CSS servido varia por user-agent). Queda como riesgo
  residual documentado en un comentario junto al propio `@import`.
"""
import re
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.test import SimpleTestCase
from django.urls import reverse

# Plantillas que referencian el script de Tailwind via CDN (inventario
# de la auditoria; si se agrega otra, el test la detecta igualmente).
PLANTILLAS_TAILWIND = [
    'inventory/base.html',
    'inventory/login.html',
    'inventory/impresion_coordenadas.html',
    'inventory/nota_entrega_print.html',
]

# Tags externos: script con src https y link con href https. Regex
# "razonable": tag de una sola linea con la URL entre comillas dobles
# (formato de todas las plantillas del proyecto).
SCRIPT_EXTERNO = re.compile(
    r'<script\b[^>]*\bsrc="(https?://[^"]+)"[^>]*>', re.IGNORECASE)
LINK_EXTERNO = re.compile(
    r'<link\b[^>]*\bhref="(https?://[^"]+)"[^>]*>', re.IGNORECASE)

# Src de Tailwind pineado: dominio + version exacta, sin query ni path
# adicional. El dominio pelado (sirve "latest") esta prohibido.
TAILWIND_PINEADO = re.compile(r'^https://cdn\.tailwindcss\.com/\d+\.\d+\.\d+$')

# integrity="sha384-<64 chars base64> [= opcional]" (sha384 = 48 bytes
# = exactamente 64 caracteres base64 sin padding).
SRI_VALIDO = re.compile(r'^sha384-[A-Za-z0-9+/]{64}={0,1}$')

ATRIBUTO_SRI = re.compile(r'integrity="(sha384-[^"]+)"', re.IGNORECASE)

# Hosts de CDN que NO envian Access-Control-Allow-Origin (verificado
# 2026-10-27 con Invoke-WebRequest/curl, con y sin header Origin, 2
# UAs): sin ACAO el navegador rechaza el fetch en modo CORS que
# dispara `crossorigin="anonymous"` y el recurso NO carga en
# navegadores reales (defecto introducido por SEC-05 en cc59926:
# CORS block + `tailwind is not defined`). En estos hosts el SRI es
# IMPOSIBLE: sus recursos quedan EXENTOS de integrity/crossorigin,
# pero deben seguir con URL versionada. jsDelivr SI envia
# `Access-Control-Allow-Origin: *` y conserva su SRI exigido.
CDN_SIN_CORS = {'cdn.tailwindcss.com'}

# Version exacta en la ruta del recurso (X.Y.Z): requisito minimo de
# los tags de hosts en CDN_SIN_CORS — exentos del SRI (imposible sin
# ACAO) pero no del pineo: sin version el contenido cambia sin aviso.
URL_VERSIONADA = re.compile(r'/\d+\.\d+\.\d+(?:$|[/?#])')


def _host_de(url):
    """Host (lowercase) de una URL absoluta; '' si no se puede parsear."""
    return urlparse(url).hostname or ''


def _plantillas():
    """Iterable de (Path, contenido) de todo el arbol de plantillas."""
    raiz = Path(settings.BASE_DIR) / 'inventory' / 'templates'
    for ruta in sorted(raiz.rglob('*.html')):
        yield ruta, ruta.read_text(encoding='utf-8')


def _tags_externos(contenido):
    """Lista de matches de tags externos (<script src=https...> y <link href=https...>)."""
    return [
        *SCRIPT_EXTERNO.finditer(contenido),
        *LINK_EXTERNO.finditer(contenido),
    ]


class TestTemplatesSRI(SimpleTestCase):
    """SEC-05: SRI + pineo de version en recursos de CDN."""

    def _relativa(self, ruta):
        return str(ruta.relative_to(Path(settings.BASE_DIR) / 'inventory' / 'templates')).replace('\\', '/')

    # ── 1. Tailwind pineado a version exacta ──────────────────────────

    def test_sec05_tailwind_esta_pineado_a_version(self):
        """
        SEC-05: todo script de Tailwind debe referenciar una version
        exacta (https://cdn.tailwindcss.com/X.Y.Z). El dominio pelado
        sirve "latest": el contenido cambia sin aviso, el hash SRI se
        invalida solo y (peor) un ataque al CDN no es detectable.
        """
        hallados = {}  # plantilla -> [srcs tailwind]
        for ruta, contenido in _plantillas():
            srcs = [m for m in SCRIPT_EXTERNO.findall(contenido)
                    if 'cdn.tailwindcss.com' in m]
            if srcs:
                hallados[self._relativa(ruta)] = srcs

        # Las 4 plantillas del inventario tienen exactamente un tag.
        for plantilla in PLANTILLAS_TAILWIND:
            self.assertIn(
                plantilla, hallados,
                f'{plantilla} debe referenciar el script de Tailwind',
            )
            self.assertEqual(
                len(hallados[plantilla]), 1,
                f'{plantilla}: se esperaba 1 solo tag de Tailwind, '
                f'hay {len(hallados[plantilla])}: {hallados[plantilla]}',
            )

        # TODO tag de Tailwind (en cualquier plantilla) esta pineado.
        for plantilla, srcs in hallados.items():
            for src in srcs:
                self.assertRegex(
                    src, TAILWIND_PINEADO,
                    f'{plantilla}: el src de Tailwind debe estar pineado a '
                    f'version exacta (X.Y.Z), es "{src}". El dominio pelado '
                    f'sirve "latest" y hace imposible el SRI.',
                )

    # ── 2. SRI exigido en todo script/link externo, salvo hosts sin ACAO ──

    def test_sec05_todo_script_link_externo_tiene_sri(self):
        """
        SEC-05: todo recurso externo (script/link https) debe llevar
        `integrity="sha384-..."` y `crossorigin="anonymous"`, EXCEPTO
        los de hosts en CDN_SIN_CORS: cdn.tailwindcss.com no envia
        ACAO (verificado 2026-10-27) y el fetch CORS que dispara
        crossorigin BLOQUEA la carga en navegadores reales. A los
        exentos se les PROHIBE integrity/crossorigin (regresion del
        hotfix) y se les EXIGE URL versionada; el resto (jsDelivr,
        que envia ACAO:*) conserva el SRI exigido.
        """
        diagnosticos = []
        for ruta, contenido in _plantillas():
            for match in _tags_externos(contenido):
                tag = match.group(0)
                plantilla = self._relativa(ruta)
                if _host_de(match.group(1)) in CDN_SIN_CORS:
                    # Host sin ACAO: integrity/crossorigin PROHIBIDOS
                    # (rompen la carga); la URL debe seguir versionada.
                    if 'integrity=' in tag:
                        diagnosticos.append(
                            f'{plantilla}: host sin ACAO con integrity '
                            f'(bloquea la carga en el navegador) -> {tag}')
                    if 'crossorigin=' in tag:
                        diagnosticos.append(
                            f'{plantilla}: host sin ACAO con crossorigin '
                            f'(bloquea la carga en el navegador) -> {tag}')
                    if not URL_VERSIONADA.search(match.group(1)):
                        diagnosticos.append(
                            f'{plantilla}: exento de SRI pero SIN version '
                            f'en la URL -> {tag}')
                    continue
                if 'integrity="sha384-' not in tag:
                    diagnosticos.append(
                        f'{plantilla}: SIN integrity -> {tag}')
                if 'crossorigin="anonymous"' not in tag:
                    diagnosticos.append(
                        f'{plantilla}: SIN crossorigin="anonymous" -> {tag}')
        self.assertEqual(
            diagnosticos, [],
            'Tags externos con SRI incorrecto (hosts CON ACAO: SRI '
            'exigido; hosts en CDN_SIN_CORS: SRI prohibido + URL '
            'versionada exigida):\n' + '\n'.join(diagnosticos),
        )

    # ── 3. Formato del hash SRI ────────────────────────────────────────

    def test_sec05_integrity_es_sha384_base64_valido(self):
        """
        SEC-05: cada valor `integrity` debe ser un sha384 bien formado
        (sha384-<64 chars base64> [padding opcional]). Un hash mal
        formado bloquea el recurso en el navegador (SRI actua igual).
        """
        diagnosticos = []
        for ruta, contenido in _plantillas():
            for match in _tags_externos(contenido):
                tag = match.group(0)
                m = ATRIBUTO_SRI.search(tag)
                if m is None:
                    continue  # lo reporta el test de presencia de SRI
                if not SRI_VALIDO.match(m.group(1)):
                    diagnosticos.append(
                        f'{self._relativa(ruta)}: integrity invalido -> '
                        f'"{m.group(1)}" en {tag}')
        self.assertEqual(
            diagnosticos, [],
            'Valores integrity mal formados:\n' + '\n'.join(diagnosticos),
        )

    # ── 4. referrerpolicy en recursos externos ─────────────────────────

    def test_sec05_referrerpolicy_presente(self):
        """
        SEC-05: todo recurso externo debe llevar
        `referrerpolicy="no-referrer"` para no filtrar la URL de
        origen (puede contener tokens de sesion en el query string)
        a CDNs de terceros.
        """
        diagnosticos = []
        for ruta, contenido in _plantillas():
            for match in _tags_externos(contenido):
                tag = match.group(0)
                if 'referrerpolicy="no-referrer"' not in tag:
                    diagnosticos.append(
                        f'{self._relativa(ruta)}: SIN referrerpolicy -> {tag}')
        self.assertEqual(
            diagnosticos, [],
            'Tags externos sin referrerpolicy="no-referrer":\n'
            + '\n'.join(diagnosticos),
        )

    # ── 5. Smoke funcional: el login renderiza SRI ─────────────────────

    def test_sec05_login_renderizado_contiene_sri(self):
        """
        SEC-05 (smoke funcional): el HTML servido por la vista de
        login (cliente anonimo) debe contener el tag de
        bootstrap-icons (jsDelivr) con su `integrity` sha384, y el de
        Tailwind versionado SIN integrity/crossorigin
        (cdn.tailwindcss.com no envia ACAO; ver CDN_SIN_CORS).
        Verifica que los atributos de las plantillas sobreviven al
        render de Django (no solo al archivo en disco).

        Nota: NO se re-descarga el CDN desde la suite (dependencia de
        red); la correccion de los hashes contra el CDN se valida al
        pinear cada version (ver comentario SEC-05 en las plantillas).
        """
        respuesta = self.client.get(reverse('inventory:login'))
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode('utf-8')

        # jsDelivr (bootstrap-icons): SRI completo en el HTML renderizado.
        link = re.search(r'<link\b[^>]*bootstrap-icons[^>]*>', html)
        self.assertIsNotNone(
            link,
            'El tag de bootstrap-icons (jsDelivr) no llega al cliente.',
        )
        self.assertIn(
            'integrity="sha384-', link.group(0),
            'El link de bootstrap-icons (jsDelivr) llego al cliente SIN '
            'su integrity sha384: los atributos SRI no sobreviven al '
            'render de Django.',
        )
        self.assertIn('crossorigin="anonymous"', link.group(0))

        # Tailwind (host sin ACAO): versionado, SIN SRI en el HTML final.
        script = re.search(r'<script\b[^>]*cdn\.tailwindcss\.com[^>]*>', html)
        self.assertIsNotNone(
            script, 'El tag de Tailwind no llega al cliente.')
        self.assertRegex(
            script.group(0),
            r'src="https://cdn\.tailwindcss\.com/\d+\.\d+\.\d+"',
            'El src de Tailwind llego al cliente sin version exacta.',
        )
        self.assertNotIn(
            'integrity=', script.group(0),
            'Tailwind llego al cliente con integrity: el host no envia '
            'ACAO y el navegador bloquea la carga.',
        )
        self.assertNotIn(
            'crossorigin=', script.group(0),
            'Tailwind llego al cliente con crossorigin: el host no envia '
            'ACAO y el navegador bloquea la carga.',
        )


if __name__ == '__main__':
    import unittest
    unittest.main()
