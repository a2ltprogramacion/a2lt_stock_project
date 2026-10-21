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
- Todos los `<script src="https://...">` y `<link href="https://...">`
  llevan `integrity="sha384-..."` (hash del recurso), 
  `crossorigin="anonymous"` (requerido por SRI en recursos cross-origin)
  y `referrerpolicy="no-referrer"` (no filtra la URL de origen a los
  CDNs de terceros).
- El `@import` de Google Fonts dentro de `<style>` en base.html NO
  admite SRI (el CSS servido varia por user-agent). Queda como riesgo
  residual documentado en un comentario junto al propio `@import`.
"""
import re
from pathlib import Path

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

    # ── 2. Todo script/link externo con SRI ────────────────────────────

    def test_sec05_todo_script_link_externo_tiene_sri(self):
        """
        SEC-05: todo recurso externo (script/link https) debe llevar
        `integrity="sha384-..."` y `crossorigin="anonymous"`. Sin SRI,
        un compromiso del CDN inyecta codigo arbitrario en la app.
        """
        diagnosticos = []
        for ruta, contenido in _plantillas():
            for match in _tags_externos(contenido):
                tag = match.group(0)
                plantilla = self._relativa(ruta)
                if 'integrity="sha384-' not in tag:
                    diagnosticos.append(
                        f'{plantilla}: SIN integrity -> {tag}')
                if 'crossorigin="anonymous"' not in tag:
                    diagnosticos.append(
                        f'{plantilla}: SIN crossorigin="anonymous" -> {tag}')
        self.assertEqual(
            diagnosticos, [],
            'Tags externos sin SRI completo (integrity + crossorigin):\n'
            + '\n'.join(diagnosticos),
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
        login (cliente anonimo) debe contener atributos integrity
        sha384. Verifica que los atributos de las plantillas sobreviven
        al render de Django (no solo al archivo en disco).

        Nota: NO se re-descarga el CDN desde la suite (dependencia de
        red); la correccion de los hashes contra el CDN se valida al
        pinear cada version (ver comentario SEC-05 en las plantillas).
        """
        respuesta = self.client.get(reverse('inventory:login'))
        self.assertEqual(respuesta.status_code, 200)
        html = respuesta.content.decode('utf-8')
        self.assertIn(
            'integrity="sha384-', html,
            'El HTML renderizado del login no contiene SRI: '
            'los atributos no llegan al cliente.',
        )


if __name__ == '__main__':
    import unittest
    unittest.main()
