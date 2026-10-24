# Plan técnico + Tareas — Estructurales (EST-01, EST-02, EST-04, EST-05, EST-06, CSP nonces)

> **Spec aprobada:** `docs/specs/EST_ESTRUCTURALES_EST01_EST02_EST04_EST06_CSP_NONCES.md` (2026-10-22) · **Gate G1 — cierre de decisiones: 2026-10-23**.

## 1. Decisiones fijadas (Gate G1 — 2026-10-23)

Las 10 disyuntivas abiertas de la spec (§6) quedaron cerradas en el Gate G1 adoptando en todas la recomendación del arquitecto:

| # | Disyuntiva (spec §6) | Decisión adoptada (recomendación G1) |
|---|---|---|
| 1 | §6.1 — EST-01: dureza del enforcement | **Señales + guard de QuerySet**: `pre_save`/`pre_delete` + QuerySet custom + escape hatch contextual; triggers SQL descartados (todo en Python, testeable, 0 migraciones) |
| 2 | §6.2 — EST-01: guard de INSERT directo | **Sí**: `pre_save` exige contexto de escritura autorizada (Regla Sagrada bidireccional); solo 2 sitios de creación existen hoy |
| 3 | §6.3 — EST-02: fase 2 (guard `.update()` en documentos) | **Diferir**: 0 usos en services/views; riesgo residual documentado en ADR; fase 1 (señales) + admin cerrado cubren los vectores reales |
| 4 | §6.4 — EST-02: admin totalmente readonly | **Sí**: mixin `ReadOnlyDocumentoAdminMixin` (NE, DetalleNE, DC) + inline `can_delete=False` — cierra el vector "anular sin reversar stock" |
| 5 | §6.5 — EST-02: NC pre-create vs allowlist de monto | **Refactor pre-create**: la NC nace con `monto_total_reembolso` definitivo (doble pasada); matriz homogénea; 29 tests NC como red de seguridad |
| 6 | §6.6 — EST-06: renombrar+delegar o eliminar la property | **Renombrar a `total_bs_bruto` + delegar** en `calculos.calcular_totales_documento`; `total_documento_bs` desaparece **sin alias deprecado** |
| 7 | §6.7 — EST-04: usuario por POST y usuario en reversos | **Ambos sí**: `usuario` por POST/JSON deprecado (ignorado con `logger.warning`; fuente forense = `request.user`); `reversar_*` aceptan `usuario: str \| User = 'Sistema'` |
| 8 | §6.8 — CSP: Django nativo vs django-csp vs middleware propio | **Django 6.0 nativo**: `django.middleware.csp.ContentSecurityPolicyMiddleware` + `SECURE_CSP` dict con `CSP.NONCE` + context processor `csp` (cero dependencias nuevas) |
| 9 | §6.9 — CSP: ventana Report-Only | **Sí**: knob `CSP_MODE` por entorno (`report` default · `enforce`); flip a enforcing y rollback de emergencia sin cambios de código |
| 10 | §6.10 — EST-05: incluir el anexo `AuditoriaTasa` | **Incluirlo**: mismo patrón EST-04, 2 writers, migración `0030`, ~2 h |

## 2. Orden de implementación y checkpoints de suite

Orden global de ejecución con la **secuencia normalizada de suite acumulada** (485 → 522; `skipped=6` constante en todos los checkpoints):

| Paso | Fix | Tareas | Δ tests | Checkpoint de suite tras el fix |
|---|---|---|---|---|
| 0 | Base actual | — | — | **485 OK, skipped=6** |
| 1 | EST-06 | 2 | +3 | **488 OK, skipped=6** |
| 2 | CSP nonces | 3 | +6 | **494 OK, skipped=6** |
| 3 | EST-04 | 3 | +7 | **501 OK, skipped=6** |
| 4 | EST-05 (anexo) | 1 | +3 | **504 OK, skipped=6** |
| 5 | EST-01 | 3 | +8 | **512 OK, skipped=6** |
| 6 | EST-02 | 4 | +10 | **522 OK, skipped=6** (final) |

**Dependencias entre fixes (spec §7.2):**

- **EST-06** — warmup, sin dependencias, riesgo nulo.
- **CSP nonces** — independiente: settings + plantillas; verificación paso 0 del middleware nativo antes de tocar plantillas.
- **EST-04** — esquema de kárdex ANTES de los guards (rename `usuario`→`usuario_nombre` + FK `usuario` + migración `0029`).
- **EST-05 (anexo)** — inmediatamente después de EST-04: reutiliza su patrón (helper `resolver_usuario`; migración `0030` depende de `0029`). En la secuencia normalizada se ejecuta antes de EST-01 (checkpoint 504; TASK-EST01-01 parte de TASK-EST05-01 ya mergeado).
- **EST-01** — guards sobre el kárdex ya migrado; introduce el escape hatch reutilizable.
- **EST-02** — patrón de señales ya probado en EST-01; dead code + admin readonly + refactor NC pre-create.

**Convivencia EST-01 ↔ EST-04 (por qué EST-04 va primero)**: ambos tocan `MovimientoKardex`. EST-04 cambia el esquema (`usuario` → FK + snapshot) y las firmas de `registrar_movimiento`; EST-01 añade el `pre_save` que intercepta la creación del servicio. Hacer EST-01 primero obligaría a re-trabajar el contexto autorizado del guard con el esquema nuevo (doble rework de los mismos tests). EST-04 primero deja el esquema estable; EST-01 entonces cablea el guard una sola vez.

**El escape hatch de EST-01 es la pieza compartida**: EST-02 lo reutiliza para `seed_db --clear` y teardowns (mismo bypass, misma allowlist) — se diseña una vez en EST-01.

**Normalización de cifras por tarea (verificación de la secuencia)**: las cifras intermedias por tarea de los capítulos **ya respetan** los checkpoints globales de la secuencia normalizada — no fue necesario ajustar ninguna cifra:

| Fix | Cifras por tarea (capítulos) | Suma | Checkpoint global |
|---|---|---|---|
| EST-06 | 486 → 488 (+1, +2) | +3 | 488 ✓ |
| CSP | 489 → 492 → 494 (+1, +3, +2) | +6 | 494 ✓ |
| EST-04 | 497 → 500 → 501 (+3, +3, +1) | +7 | 501 ✓ |
| EST-05 | 504 (+3) | +3 | 504 ✓ |
| EST-01 | 507 → 510 → 512 (+3, +3, +2) | +8 | 512 ✓ |
| EST-02 | 516 → 519 → 521 → 522 (+4, +3, +2, +1) | +10 | 522 ✓ |

## 3. Tabla global de tareas

Las 16 tareas de los 5 capítulos (2 + 3 + 4 + 3 + 4). `skipped=6` constante; el checkpoint es el conteo de suite acumulado tras completar la tarea:

| ID | Fix | Objetivo (1 línea) | Fixtures de suite (checkpoint tras la tarea) | Depende de |
|---|---|---|---|---|
| TASK-EST06-01 | EST-06 | `total_bs_bruto` en NotaEntrega delegando en calculos; `total_documento_bs` eliminada; tests legacy migrados al contrato nuevo | **486 OK** (+1) · nuevo `test_totales_brutos.py` | Ninguna (primera del orden global) |
| TASK-EST06-02 | EST-06 | `total_bs_bruto` en DocumentoCompra con idéntico tratamiento + guard de inspección de fuente única (REQ-EST06-01) | **488 OK** (+2) · checkpoint del fix | TASK-EST06-01 |
| TASK-CSP-01 | CSP | Adoptar el CSP nativo con knob de modo; eliminar `CSP_POLICY` + `CspMiddleware` propio; suite sec02b verde contra el nuevo contrato | **489 OK** (+1) · rework de `test_security_csp_403.py` | Ninguna (base 488) |
| TASK-CSP-02 | CSP | Los 16 `<script>` inline llevan `nonce="{{ csp_nonce }}"`; gate estático anti-regresión de plantillas | **492 OK** (+3) · 16 tags en 14 plantillas | TASK-CSP-01 |
| TASK-CSP-03 | CSP | Cerrar el knob: default Report-Only probado, flip a enforcing probado, operación documentada | **494 OK** (+2) · checkpoint del fix | TASK-CSP-02 |
| TASK-EST04-01 | EST-04 | Rename `usuario`→`usuario_nombre` preservando datos + FK `usuario` en kárdex/NC + backfill por match de username + presentación por snapshot | **497 OK** (+3) · nuevo `test_usuario_fk.py` + migración `0029` | Fix CSP mergeado |
| TASK-EST04-02 | EST-04 | Helper único de resolución `str\|User`; los 3 sitios de persistencia llenan FK+snapshot; fin del `'Sistema'` hardcoded en `reversar_*` | **500 OK** (+3) | TASK-EST04-01 |
| TASK-EST04-03 | EST-04 | Las 8 vistas escritoras pasan `request.user`; `usuario` por POST/JSON deprecado con warning; reversos pasan usuario | **501 OK** (+1) · checkpoint del fix | TASK-EST04-02 |
| TASK-EST05-01 | EST-05 | `AuditoriaTasa.usuario`: FK + snapshot con migración `0030` y resolución en sus 2 writers (patrón EST-04) | **504 OK** (+3) · migración `0030` | TASK-EST04-03 (0030 tras 0029) |
| TASK-EST01-01 | EST-01 | `kardex_guard` (bypass reentrante + receivers) + `KardexQuerySet` + allowlist silenciada; guards activos con la suite verde | **507 OK** (+3) · nuevo `test_kardex_inmutable.py` | Fix EST-04/EST-05 mergeado |
| TASK-EST01-02 | EST-01 | `.update()` bloqueado en ambos managers + cascada de `Empresa.delete()` bloqueada + `eliminar_tenant` como única vía de teardown | **510 OK** (+3) | TASK-EST01-01 |
| TASK-EST01-03 | EST-01 | Camino legítimo (reverso N+1 sin borrados) y exención de históricos probados; ADR de la allowlist | **512 OK** (+2) · checkpoint del fix | TASK-EST01-02 |
| TASK-EST02-01 | EST-02 | Señal + matriz en cabeceras NE/DC + `DocumentoInmutableError` + dead code `nc.delete()` eliminado (pre_save de NC diferido) | **516 OK** (+4) · nuevo `test_inmutabilidad_documentos.py` | Fix EST-01 mergeado |
| TASK-EST02-02 | EST-02 | Detalles inmutables (matriz vacía) + deletes bloqueados + devolución no muta la línea origen | **519 OK** (+3) | TASK-EST02-01 |
| TASK-EST02-03 | EST-02 | Admin totalmente readonly para documentos emitidos (mixin) — cierra "anular sin reversar stock" en /admin/ | **521 OK** (+2) | TASK-EST02-01 |
| TASK-EST02-04 | EST-02 | Refactor pre-create NC (nace con monto definitivo) + conexión de `pre_save` de NotaCredito + ADR matriz y fase 2 | **522 OK** (+1) · final de la suite | TASK-EST02-01..03 |

## 4. Capítulos

Contenido íntegro de los 5 capítulos en orden de implementación. Los headers internos de cada capítulo están rebajados un nivel (los `##`/`###` originales pasan a `###`/`####` bajo el header de nivel 2 de cada capítulo); las cifras de suite por tarea son las verificadas en §2.

## Capítulo 1 — EST-06: Totales honestos vía fuente única

### Plan técnico

**Defecto**: `total_documento_bs` promete "total del documento" pero computa `subtotal_bs + total_iva_bs` — bruto, SIN aplicar `descuento_global`. Huérfana en producción (DATA-01 movió los totales reales a `calculos`). `DocumentoCompra` **padece el mismo defecto** (spec §2.4, líneas 41/61): recibe idéntico tratamiento; ninguna queda intacta. Decisión 6 G1: rename a `total_bs_bruto` + eliminación total del nombre viejo, **sin alias deprecado** (un alias con la misma firma y distinto valor sería una trampa silenciosa).

**Firma exacta de la property nueva** (idéntica en ambos modelos; el identificador `total_bs_bruto` no existe hoy en el repo y el dict de `calculos` no tiene esa clave — la property es el ensamblador):

```python
@property
def total_bs_bruto(self):
    """Total bruto en Bs (subtotal + IVA, SIN descuento_global). DATA-01: delega en calculos."""
    totales = calcular_totales_documento(self.detalles.all(), self.descuento_global)
    return totales['subtotal_bs_bruto'] + totales['total_iva_bs_bruto']
```

- **NotaEntrega**: sustituye in situ models.py:1698-1701 (inmediatamente tras `total_iva_bs`, 1693-1696).
- **DocumentoCompra**: sustituye in situ models.py:1184-1187 (tras `total_iva_bs`, 1179-1182).
- **Import**: `from .calculos import calcular_totales_documento` a nivel de módulo, tras `from .managers import ...` (models.py:31). Sin riesgo circular: `calculos.py` solo importa `decimal` (líneas 22-26) y models.py hoy no referencia `calculos`.

**Delegación en `calculos.calcular_totales_documento`** (firma actual, calculos.py:116-118: `calcular_totales_documento(detalles, descuento_global, *, usa_precio_ajustado=True)`):
- La property llama `(self.detalles.all(), self.descuento_global)` (spec §2.4 escribe `self.detalles`; `.all()` es equivalente y explícito — la función itera con `list(detalles)`, línea 144).
- `detalles`: related_name='detalles' en ambos (DetalleDocumentoCompra models.py:1204; DetalleNotaEntrega 1719). `descuento_global`: campo en ambos (DocumentoCompra 1070-1073; NotaEntrega 1607-1612; default 0.00); `None` → 0 vía `_a_decimal` (calculos.py:29-32). `usa_precio_ajustado` queda en default: solo afecta al fallback de detalles sin properties, y ambos detalles las exponen (DetalleDocumentoCompra 1244-1271; DetalleNotaEntrega ídem).
- **Devuelve** dict de 14 claves cuantizadas a 2 decimales (calculos.py:183-198): `descuento_global`, `factor_descuento`, brutos (`subtotal_usd_bruto`, `subtotal_bs_bruto`, `total_iva_usd_bruto`, `total_iva_bs_bruto`), netos (`subtotal_usd_neto`, `subtotal_bs_neto`, `total_iva_usd_neto`, `total_iva_bs_neto`), `monto_descuento_usd`, `monto_descuento_bs`, `total_usd_neto`, `total_bs_neto`.
- **Derivación**: la property consume solo `subtotal_bs_bruto` (suma de `d.subtotal_bs`, 149-153) + `total_iva_bs_bruto` (suma de `d.iva_bs`, 170). Los brutos NO aplican `factor_descuento` — solo los netos (172-181): de ahí `total_bs_bruto != total_bs_neto` cuando `descuento_global > 0`.
- **Sin fórmula duplicada (REQ-EST06-01 / DATA-01)**: la property no suma `self.subtotal_bs + self.total_iva_bs`; su única aritmética es ensamblar dos claves ya cuantizadas por la fuente única. Pantallas/PDF siguen con `total_bs_neto`/`total_usd_neto` desde las 5 llamadas de vistas (views.py:842, 947, 996, 1102, 1850) — **intactas** (REQ-EST06-03).

**Inventario de usos de `total_documento_bs`** (grep repo completo):

| Sitio | Líneas | Acción |
|---|---|---|
| `inventory/models.py` | 1185-1187 (DocumentoCompra), 1699-1701 (NotaEntrega) | Eliminar ambas definiciones |
| `inventory/tests.py` | 6222 (docstring), 6231 (`assertTrue hasattr`), 6240 (`assertEqual 0`) | Únicos consumidores de código; actualizar al contrato nuevo (TASK-01) |
| views / templates / exporters | 0 usos | Nada que tocar |
| `docs/AUDIT_REPORT.md` (2223-2239), `docs/auditoria_2026-08.md` (62) | registro histórico | No se tocan |

**Sin migración**: property = cálculo puro, ningún campo cambia → `makemigrations --check` limpio; la última migración sigue siendo `0028`.

**Trazabilidad Gherkin → tests**:

| Escenario (spec §Gherkin) | Test | Tarea |
|---|---|---|
| EST06-01 bruto delega y difiere del neto | `test_nota_total_bs_bruto_es_bruto_y_difiere_del_neto` | 01 |
| EST06-03 property vieja desaparece sin alias | tests.py:6231 actualizado (`assertFalse hasattr`) | 01 |
| EST06-04 DocumentoCompra mismo tratamiento | `test_compra_total_bs_bruto_delega_con_descuento_de_compra` | 02 |
| EST06-05 models.py sin fórmula duplicada | `test_models_py_no_contiene_formula_duplicada` | 02 |
| EST06-02 neto sigue viniendo de calculos | ya cubierto: `test_las_cuatro_vistas_usan_el_helper` (test_calculos.py:253-264) + `test_pdf_nota_muestra_iva_bs_neto` (266-279) | regresión |

### Tareas

#### TASK-EST06-01 — `total_bs_bruto` en NotaEntrega + contrato de tests
- **Objetivo**: `NotaEntrega` expone el bruto honesto delegante; `total_documento_bs` desaparece del modelo; tests legacy migrados al contrato nuevo.
- **Archivos**: `inventory/test_cases/test_totales_brutos.py` (NUEVO), `inventory/tests.py` (6221-6240), `inventory/models.py` (import + bloque 1698-1701).
- **RED**:
  1. Crear `test_totales_brutos.py`: `class TestTotalBsBruto(TestCase)`; setUp replicando `test_calculos.py` (empresa, almacén, user, artículos `DATA01-01/02`, `ConfiguracionEmpresa` vía signals) + helper `_crear_nota` copiado de test_calculos.py:176-209 (`procesar_venta`, 2 líneas, `descuento_global` parametrizable).
  2. `test_nota_total_bs_bruto_es_bruto_y_difiere_del_neto`: `nota = self._crear_nota('1.0000', descuento_global=Decimal('10'))`; `totales = calcular_totales_documento(list(nota.detalles.all()), nota.descuento_global)`; asserts: `nota.total_bs_bruto == totales['subtotal_bs_bruto'] + totales['total_iva_bs_bruto']` y `nota.total_bs_bruto != totales['total_bs_neto']`.
  3. Actualizar legacy en `tests.py::TestModelosNotaEntregaFaseN2`: docstring 6222 (nombra `total_bs_bruto`); 6231 → `assertTrue(hasattr(nota, 'total_bs_bruto'))` + `assertFalse(hasattr(nota, 'total_documento_bs'))`; 6240 → `assertEqual(nota.total_bs_bruto, Decimal('0'))`.
  4. `python manage.py test inventory.test_cases.test_totales_brutos inventory.tests.TestModelosNotaEntregaFaseN2` → 3 FAIL (AttributeError `total_bs_bruto` ×2; `assertFalse(hasattr(...))` ×1).
- **GREEN**: (1) import en models.py:31; (2) sustituir bloque 1698-1701 por la property de §Plan técnico. No tocar las 5 vistas.
- **VERIFICACIÓN**: `python manage.py test inventory` → **486 OK, skipped=6, 0 failures** (485 + 1 nuevo). `python manage.py test inventory.test_cases.test_calculos` verde (REQ-EST06-03 intacto). `python manage.py makemigrations --check` → "No changes detected".
- **Dependencias**: ninguna (primera tarea del orden global EST-06 → CSP → EST-04 → EST-01 → EST-02).
- **Commit**: `feat(est06): total_bs_bruto en NotaEntrega delegando en calculos; eliminada total_documento_bs`.

#### TASK-EST06-02 — `total_bs_bruto` en DocumentoCompra + guard de fuente única
- **Objetivo**: `DocumentoCompra` recibe el mismo tratamiento; guard de inspección de fuente blinda REQ-EST06-01 contra re-duplicaciones.
- **Archivos**: `inventory/test_cases/test_totales_brutos.py`, `inventory/models.py` (bloque 1184-1187).
- **RED** (añadir a `TestTotalBsBruto`):
  1. `test_compra_total_bs_bruto_delega_con_descuento_de_compra`: compra por ORM (patrón test_models_managers.py:60-82): `DocumentoCompra.objects.create(empresa=..., proveedor=..., tipo_documento='FACTURA_COMPRA', monto_total_usd=Decimal('100.00'), descuento_global=Decimal('10'), tasa_bcv_aplicada=Decimal('60.0000'))` (campo models.py:1080; necesario para `iva_bs` != 0 — ver DetalleDocumentoCompra.iva_bs, 1265-1271) + 2 `DetalleDocumentoCompra` (cantidad, costo_base, costo_ajustado, costo_directo_bcv, costo_ajustado_bcv, iva_porcentaje). Asserts: `compra.total_bs_bruto == totales['subtotal_bs_bruto'] + totales['total_iva_bs_bruto']` con `totales = calcular_totales_documento(list(compra.detalles.all()), compra.descuento_global)`; y `compra.total_bs_bruto != totales['total_bs_neto']`.
  2. `test_models_py_no_contiene_formula_duplicada`: patrón test_calculos.py:253-264 — `import inventory.models as models_mod; fuente = inspect.getsource(models_mod)`; `assertNotIn('def total_documento_bs', fuente)`; `assertNotIn('self.subtotal_bs + self.total_iva_bs', fuente)` (grep confirma: la fórmula solo existe en 1187 y 1701). RED: definición y fórmula viven aún en 1185-1187.
  3. `python manage.py test inventory.test_cases.test_totales_brutos` → 2 FAIL (los tests de TASK-01 siguen verdes).
- **GREEN**: sustituir bloque 1184-1187 (DocumentoCompra) con la misma property de §Plan técnico.
- **VERIFICACIÓN**: `python manage.py test inventory` → **488 OK, skipped=6** (objetivo del capítulo: 486 + 2). `python manage.py makemigrations --check` limpio. `grep -rn "total_documento_bs" inventory/` → 0 usos (o `findstr /s /n /c:"total_documento_bs" inventory\*.py`); solo quedan menciones históricas en `docs/`.
- **Dependencias**: TASK-EST06-01.
- **Commit**: `feat(est06): total_bs_bruto en DocumentoCompra + guard de fuente unica`.

## Capítulo 2 — CSP: migración a nonces con Django 6 nativo

### Plan técnico

**Base documental (context7 `/websites/djangoproject_en_6_0`):** `SECURE_CSP` — *"The setting must be a mapping (typically a dictionary) of directive names to their values. Each key should be a valid CSP directive such as `default-src` or `script-src`."* (https://docs.djangoproject.com/en/6.0/ref/settings/#secure-csp); release notes 6.0: `SECURE_CSP = {"default-src": [CSP.SELF], "script-src": [CSP.SELF, CSP.NONCE]}` → header `default-src 'self'; script-src 'self' 'nonce-SECRET'`; `SECURE_CSP_REPORT_ONLY` *"instructs the ContentSecurityPolicyMiddleware to apply a Content-Security-Policy-Report-Only header"* sin bloquear (https://docs.djangoproject.com/en/6.0/releases/6.0/). **⚠️ Corrección a la spec** (REQ-CSP-01/§4.4 escribieron `django.middleware.security`): el paquete 6.0.6 verificado expone `django.middleware.csp.ContentSecurityPolicyMiddleware` (MiddlewareMixin; `request._csp_nonce = LazyNonce()` en process_request; process_response respeta headers existentes). Usar la ruta `django.middleware.csp`.

#### 1. Política exacta (dict definido UNA vez, settings.py)

Reemplaza el string `CSP_POLICY` (settings.py:196-214). Claves = strings directivas; valores = constantes `django.utils.csp.CSP` + orígenes (formato oficial verificado arriba):

```python
from django.utils.csp import CSP

_CSP_DICT = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF, CSP.NONCE, "https://cdn.tailwindcss.com"],  # sin 'unsafe-inline' (CSP3: con nonce el navegador lo ignora; eliminación efectiva)
    "style-src": [CSP.SELF, CSP.UNSAFE_INLINE, "https://cdn.jsdelivr.net",
                  "https://fonts.googleapis.com"],  # unsafe-inline = DEUDA Tailwind CDN JIT (inyecta <style> en runtime, SEC-05)
    "font-src": [CSP.SELF, "https://cdn.jsdelivr.net", "https://fonts.gstatic.com"],
    "img-src": [CSP.SELF, "data:"],
    "connect-src": [CSP.SELF],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "form-action": [CSP.SELF],
}
```

#### 2. Knob Report-Only → enforcing (REQ-CSP-06, sin duplicar settings)

```python
CSP_MODE = os.environ.get('CSP_MODE', 'report')  # 'report' | 'enforce'
if CSP_MODE not in ('report', 'enforce'):
    raise ImproperlyConfigured(f"CSP_MODE invalido: {CSP_MODE!r}")
if CSP_MODE == 'enforce':
    SECURE_CSP = _CSP_DICT            # header bloqueante
else:
    SECURE_CSP_REPORT_ONLY = _CSP_DICT  # header -Report-Only (default)
```

- **Default `'report'`**: despliegue seguro gradual; el nativo solo emite el header que esté poblado (el otro queda en su default `{}` → no se emite). Violaciones Report-Only sin `report-uri` se loguean en consola del navegador (doc oficial) — suficiente para la ventana de adopción en LAN.
- **Flip a enforcing**: `CSP_MODE=enforce` + restart del proceso (env-only, cero código). **Rollback de emergencia**: re-setear a `report` + restart. Mapea el `CSP_REPORT_ONLY=true` de REQ-CSP-06 a un knob de un solo valor con validación estricta en arranque (typo → boot falla, no fail-silent).

#### 3. Cambios en settings.py, middleware.py, TEMPLATES

| Cambio | Detalle exacto |
|---|---|
| MIDDLEWARE (settings.py:80) | `'inventory.middleware.CspMiddleware'` → `'django.middleware.csp.ContentSecurityPolicyMiddleware'` **en la MISMA posición (antes de `TenantMiddleware`)**; actualizar el comentario 75-79. |
| Posición (análisis) | Correcta e equivalente: el nativo es `MiddlewareMixin` — process_request (fase bajada, top→down) setea `request._csp_nonce` ANTES de que `TenantMiddleware` renderice sus 403 early-return (→ el `{{ csp_nonce }}` del base.html del 403 existe); su `__call__` hace `response = self.get_response(request)` + `process_response(...)`, así que CUALQUIER respuesta de abajo — incluido el early-403 que nunca invoca el `get_response` del tenant — sube por su frame y recibe el header. La garantía es "estar POR ENCIMA del tenant" (comentario settings.py:75-79 sigue válido); debajo, el early-403 jamás lo alcanzaría. `test_sec02b_csp_header_en_403_del_middleware` (test_security_csp_403.py:234-249) sigue probándolo. |
| TEMPLATES (settings.py:92-97) | Añadir `'django.template.context_processors.csp'` tras `request` (expone `{{ csp_nonce }}`; lee `request._csp_nonce`; NO está registrado hoy — sin él los 16 scripts renderizan `nonce=""` y el JS muere en enforcing). |
| Eliminaciones | settings.py:196-214 (`CSP_POLICY` completo, sin alias deprecado — consumidor único era nuestro middleware y 2 tests, ambos en rework); `inventory/middleware.py:161-181` (`class CspMiddleware` — `TenantMiddleware` se conserva intacto). |
| Checks nativos | `manage.py check` ejecuta E026 (valida el dict); `csp_override`/`csp_report_only_override` disponibles per-view (fuera de scope, no usar). |

#### 4. Inventario REAL de nonceficación (grep `<script` sobre templates)

**16 bloques inline en 14 plantillas** (confirma spec §1.5): `base.html` ×3 (**L10** getCsrfToken, **L29** theme+`tailwind.config`, **L394** sidebar/getCookie), `articulos.html:226`, `compras.html:285`, `contactos.html:293`, `catalogo.html:215`, `configuracion.html:281`, `carga.html:129`, `impresion_coordenadas.html:106`, `login.html:13`, `movimientos.html:224`, `notas_credito.html:183`, `ventas.html:284`, `reversos.html:144`, `reportes/detalle.html:117`.
**NO tocar** los 4 tags externos SRI (nonce solo autoriza inline): `base.html:24`, `impresion_coordenadas.html:7`, `login.html:10`, `nota_entrega_print.html:9` (`test_templates_sri.py` ×5 tests debe seguir verde). Los 7 consumidores de `getCsrfToken()` no cambian (la función ya nocificada en base sigue global). Ningún script inline lleva hoy `defer`/`async` → `nonce` es el único atributo añadido.

**Patrón** (base.html:10-19):

```html
<!-- ANTES -->
    <script>
        // SEC-02: obtiene el token CSRF desde el DOM (la cookie es HttpOnly).
        function getCsrfToken() {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }
    </script>
<!-- DESPUÉS -->
    <script nonce="{{ csp_nonce }}">
        // SEC-02: obtiene el token CSRF desde el DOM (la cookie es HttpOnly).
        function getCsrfToken() {
            const meta = document.querySelector('meta[name="csrf-token"]');
            return meta ? meta.getAttribute('content') : '';
        }
    </script>
```

`LazyNonce` garantiza header y template usan el MISMO valor por request. REQ-CSP-09: hoy no hay caching de HTML → nonce-per-request seguro; documentar en `docs/OPERACION.md` la advertencia (excluir header/nonce si algún día se cachean páginas).

#### 5. Rework de `inventory/test_cases/test_security_csp_403.py` + aritmética de suite

Helper nuevo a nivel de módulo (modo-agnóstico, la suite corre sin env → `'report'`): `def csp_de(resp)` → devuelve el valor del header activo (probar `Content-Security-Policy` y `Content-Security-Policy-Report-Only`).

| Test existente (línea) | Rework |
|---|---|
| `test_sec02b_csp_header_en_login` (191) | Vía `csp_de()`; añade `nonce-` presente en script-src y `'unsafe-inline'` NO en script-src (sí en style-src); conserva fragmentos `default-src 'self'`, `object-src 'none'`, `frame-ancestors 'none'`, `cdn.tailwindcss.com`. |
| `test_sec02b_csp_header_en_pagina_autenticada` (215) | `csp_de()` truthy en vez de `has_header('Content-Security-Policy')` (header es Report-Only por defecto). |
| `test_sec02b_csp_header_en_403_del_middleware` (234) | Ídem — el guard del 403 se conserva con el nativo en la misma posición. |
| `test_sec02b_politica_cubre_recursos_reales` (253) | Lee el dict (`settings.SECURE_CSP_REPORT_ONLY` o `SECURE_CSP` según `CSP_MODE`) en vez de `settings.CSP_POLICY` (AttributeError tras eliminación). |
| `test_sec02b_csp_no_sobrescribe_header_existente` (277) | Importa `django.middleware.csp.ContentSecurityPolicyMiddleware` (mismo patrón RequestFactory + lambda; response con header propio no se sobrescribe, response fresco recibe política del modo activo). |

Los 4 tests SEC-06 de la clase superior NO se tocan. **Nuevos (6, neto +6):** `test_csp_csp_policy_y_middleware_propio_eliminados` (estructural: `CSP_POLICY` ausente en settings; `class CspMiddleware` ausente en middleware.py; MIDDLEWARE tiene el nativo inmediatamente antes de TenantMiddleware), `test_csp_gate_estatico_scripts_inline_con_nonce` (REQ-CSP-05: recorre `inventory/templates/` + `templates/`; todo `<script` sin `src=` debe contener `nonce=`; falla con archivo:línea), `test_csp_nonce_header_coincide_con_scripts_renderizados` (GET dashboard: nonce del header aparece en cada script inline del body), `test_csp_nonces_distintos_entre_requests` (CSP-03), `test_csp_report_only_default_emite_header_no_bloqueante` (header `-Report-Only` presente, bloqueante ausente), `test_csp_enforce_flip_emite_header_bloqueante` (`override_settings(SECURE_CSP=settings._CSP_DICT, SECURE_CSP_REPORT_ONLY={})` → header bloqueante; el nativo lee settings por request).

**Aritmética:** entra en 488 (tras EST-06) → sale en **494** (archivo: 9 tests existentes + 6 nuevos = 15; los 5 sec02b rework no cambian conteo). Skipped sigue =6.

### Tareas

#### TASK-CSP-01 — Settings + middleware nativo + context processor + rework suite sec02b
- **Objetivo:** adoptar el CSP nativo con knob de modo; eliminar `CSP_POLICY` + `CspMiddleware` propio; dejar la suite CSP verdes contra el nuevo contrato.
- **Archivos:** `a2lt_stock_project/settings.py`, `inventory/middleware.py`, `inventory/test_cases/test_security_csp_403.py`, `docs/ADR.md` (ADR: dict + knob CSP_MODE + deuda style-src unsafe-inline).
- **RED:** los 5 `test_sec02b_*` rework (nombres conservados) + `test_csp_csp_policy_y_middleware_propio_eliminados` fallan contra el código actual (AttributeError CSP_POLICY / ImportError CspMiddleware / header nativo ausente).
- **GREEN:** dict `_CSP_DICT` + `CSP_MODE` (§1-2); swap middleware misma posición (§3); context processor `csp`; borrar settings.py:196-214 y middleware.py:161-181; helper `csp_de()`; ADR.
- **VERIFICACIÓN:** `python manage.py test inventory` → **489 OK** (skipped=6); `python manage.py check` (E026 verde); `python manage.py makemigrations --check` (sin cambios, 0029 es del capítulo EST-04).
- **Dependencias:** ninguna (primera tarea del capítulo; suite base 488).

#### TASK-CSP-02 — Nonceficación de los 16 scripts inline + gate anti-regresión
- **Objetivo:** todos los `<script>` inline llevan `nonce="{{ csp_nonce }}"`; gate estático que impide plantillas nuevas sin nonce.
- **Archivos:** las 14 plantillas de §4 (16 tags; base ×3), `inventory/test_cases/test_security_csp_403.py`.
- **RED:** `test_csp_gate_estatico_scripts_inline_con_nonce`, `test_csp_nonce_header_coincide_con_scripts_renderizados`, `test_csp_nonces_distintos_entre_requests` fallan (scripts sin nonce; body sin `nonce="<valor>"`).
- **GREEN:** patrón §4 en los 16 tags (solo se añade `nonce`; SRI externos intactos); render del 403 (hereda base) también queda nocificado gratis.
- **VERIFICACIÓN:** suite → **492 OK** (skipped=6); `test_templates_sri.py` verde; `makemigrations --check` limpio.
- **Dependencias:** TASK-CSP-01 (context processor + middleware activos).

#### TASK-CSP-03 — Ventana Report-Only + flip enforcing documentado
- **Objetivo:** cerrar el knob: default report-only probado, flip a enforce probado, operación documentada.
- **Archivos:** `inventory/test_cases/test_security_csp_403.py`, `docs/OPERACION.md`.
- **RED:** `test_csp_report_only_default_emite_header_no_bloqueante` + `test_csp_enforce_flip_emite_header_bloqueante` fallan (verifican contrato del knob).
- **GREEN:** 2 tests (`override_settings` para enforce; fallback si hiciera falta: subprocess con `CSP_MODE=enforce`); `docs/OPERACION.md`: knob `CSP_MODE`, flip/rollback por env, advertencia caching (REQ-CSP-09), nota console-only de Report-Only sin `report-uri`.
- **VERIFICACIÓN:** suite → **494 OK (skipped=6)**; `makemigrations --check` limpio; navegación manual de las 7 vistas con JS (ventas, compras, carga, notas_credito, movimientos, reversos, articulos) con `CSP_MODE=enforce` — cero errores CSP en consola (criterio spec §2.5).
- **Dependencias:** TASK-CSP-02 (plantillas nocificadas; sin esto enforcing rompe JS).

## Capítulo 3 — EST-04 y EST-05: usuario forense (FK a User + snapshot)

Orden global: EST-06 → CSP → **EST-04 → EST-05** → EST-01 → EST-02. Base acumulada entrante: **494 OK, skipped=6**. `models.py:28` ya importa `User`.

### Plan técnico (EST-04)

**Nombre de la FK: `usuario`** (no `usuario_fk`/`usuario_ref`). El G1 fijo (REQ-EST04-01/02, Gherkin usa `usuario_id`+`usuario_nombre`) renombra el CharField a `usuario_nombre` y libera `usuario` para la FK: paralelismo FK/snapshot es el patrón idiomático, y el *kwarg* de servicio también se llama `usuario` (distinto del campo) — los ~60 call-sites de tests no se tocan.

**Esquema (models.py):**
- `MovimientoKardex` (sustituir 1397-1401): `usuario_nombre = CharField(max_length=150, blank=True, verbose_name='Usuario que Realizó el Movimiento')` (datos preservados por RenameField) + `usuario = ForeignKey(settings.AUTH_USER_MODEL, on_delete=SET_NULL, null=True, blank=True, related_name='kardex_registrado_por', verbose_name='Usuario (FK)')`.
- `NotaCredito` (2029-2032) ídem: snapshot conserva `default='Sistema'`; FK `related_name='notas_credito_emitidas'` (sin colisión con `Empresa.movimientos_kardex`, models.py:1336). FK GLOBAL a User (REQ-EST04-08: PerfilUsuario gobierna el per-tenant).

**Helper único de resolución** (services.py, público — views lo reusan en EST-05; nuevo import `from django.contrib.auth.models import User` en el header):

```python
def resolver_usuario(usuario):
    """EST-04 REQ-EST04-05: str|User|None -> (User|None, snapshot). Sin match: FK None + snapshot."""
    if not usuario:
        return None, ''
    if isinstance(usuario, User):
        return usuario, usuario.username
    nombre = str(usuario)
    try:
        return User.objects.get(username=nombre), nombre
    except User.DoesNotExist:
        return None, nombre
```

**Solo 3 sitios de persistencia resuelven** (los writers intermedios reenvían el kwarg, cuerpos intactos): (a) create de `registrar_movimiento` (services.py:210-223): `usuario=usuario or ''` (222) → resolver + `usuario=usuario_fk, usuario_nombre=usuario_nombre`; (b) `NotaCredito.objects.create` de `procesar_devolucion_venta` (2492-2499, kwarg 2497); (c) idem `procesar_devolucion_compra` (2696-2703, kwarg 2701). `User.DoesNotExist` nunca rompe: es la rama snapshot.

**Firmas nuevas** (defaults actuales conservados para no romper tests):

| Función (línea firma) | Firma nueva |
|---|---|
| `registrar_movimiento` (services.py:71) | `usuario: str \| User \| None = None` |
| `procesar_salida_combo` (380) · `procesar_carga_masiva` (570) · `procesar_carga_masiva_excel` (861) · `resolver_colision` (1080) · `procesar_venta` (1253) · `revertir_carga_masiva` (1733) · `transferir_mercancia` (1852) · `ejecutar_ajuste_manual` (1900) · `registrar_compra_proveedor` (1962) | idem |
| `reversar_nota_entrega` (2338) · `reversar_documento_compra` (2371) | **nuevo param** `usuario: str \| User = 'Sistema'` (REQ-EST04-07) |
| `procesar_devolucion_venta` (2432) · `_compra` (2662) | `usuario: str \| User = 'Sistema'` |

`reversar_*`: 2360 y 2400 (`usuario='Sistema'` hardcoded) → `usuario=usuario` (passthrough).

**Deprecación POST + `request.user`** (las 8 vistas son `@login_required` → `request.user` es SIEMPRE instancia; los fallbacks `'anónimo'/'API'/'Sistema'` son código muerto). El valor de POST/JSON SOLO iría al snapshot — pero se IGNORA con warning: la FK y el snapshot vienen del autenticado.

| Vista (líneas) | Cambio exacto |
|---|---|
| `vista_carga_masiva` 469/486 | 469 → `if request.POST.get('usuario'): logger.warning('[EST04] POST "usuario" deprecado e ignorado; fuente forense = request.user')`; 486 → `usuario=request.user` |
| `vista_resolver_colision` 611/630 | idem: 611 warning (JSON body `datos.get('usuario')`); 630 → `usuario=request.user` |
| `vista_carga_masiva_excel` 548/554 | 548 elimina fallback; 554 → `usuario=request.user` |
| `vista_crear_venta` 759 | → `usuario=request.user` |
| `vista_registrar_asiento_manual` 1345 | `str(request.user.username)` → `usuario=request.user` |
| `registrar_compra_api` 2057 | → `usuario=request.user` |
| `api_crear_nc` 2426/2434 | `request.user.username or 'Sistema'` → `usuario=request.user` |
| `api_reversar_venta` 2110 · `api_reversar_compra` 2131 | añadir 4º arg `usuario=request.user` |

**Presentación por snapshot** (la FK puede ser None): template `nota_credito_detalle.html:51` → `{{ nc.usuario_nombre|default:"Sistema" }}`. **PDF views.py:2534** (`f"<b>Usuario:</b> {nc.usuario}"` — sitio NO inventariado en spec §1.5; tras rename renderizaría `None`) → `{nc.usuario_nombre or 'Sistema'}`. `admin.py:334` readonly_fields → `'usuario', 'usuario_nombre'`.

**Migración `0029_usuario_fk_kardex_nc.py`** (dependencies: `('inventory', '0028_alter_tasacambio_moneda_destino_and_more')` + auth auto):

```python
operations = [
    migrations.RenameField('movimientokardex', 'usuario', 'usuario_nombre'),
    migrations.AddField('movimientokardex', 'usuario', models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='kardex_registrado_por')),
    migrations.RenameField('notacredito', 'usuario', 'usuario_nombre'),
    migrations.AddField('notacredito', 'usuario', models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='notas_credito_emitidas')),
    migrations.RunPython(backfill_usuario_fk, limpiar_usuario_fk),
]

def backfill_usuario_fk(apps, schema_editor):   # REQ-EST04-03; manager histórico plano (EmpresaManager sin use_in_migrations)
    User = apps.get_model('auth', 'User')
    mapa = dict(User.objects.values_list('username', 'pk'))
    for nombre in ('MovimientoKardex', 'NotaCredito'):
        M = apps.get_model('inventory', nombre)
        for fila in M.objects.exclude(usuario_nombre=''):
            pk = mapa.get(fila.usuario_nombre)
            if pk is not None and pk != fila.usuario_id:  # sin match -> FK NULL; 2ª pasada -> no-op (idempotente)
                fila.usuario_id = pk
                fila.save(update_fields=['usuario'])

def limpiar_usuario_fk(apps, schema_editor):    # reversibilidad (spec §5.3): FK a NULL; snapshot NUNCA se toca
    for nombre in ('MovimientoKardex', 'NotaCredito'):
        apps.get_model('inventory', nombre).objects.update(usuario=None)
```

**Paso 0 del implementador — auditoría usernames (REQ-EST04-04):** `python manage.py shell`: comparar `MovimientoKardex.objects.values_list('usuario').distinct()` + `NotaCredito…` vs `User.objects.values_list('username')`; registrar % de match en el PR (no bloqueante). Esperado SIN match (→ FK NULL por diseño): `'seed_db'` (seed_db.py:359,421), `'Sistema'`, `'Demo Setup'`/`'Demo User'` (generate_demo_data.py:207,338), `'anónimo'`, `'API'`, literales de tests (`'test'`, `'Admin'`, `'DevSys'`, `'data03'`, `'setUp'`, `'Thread-N'`, `'operador_audit'`). Match esperado: operadores humanos reales.

**Único test legacy que SE toca**: `tests.py:1646` (fixture de create directo, `usuario='Admin'` kwarg al MODELO, no al servicio) → `usuario_nombre='Admin'`. Es el único create directo fuera de services (grep verificado); el resto de los ~60 call-sites pasan por firmas de servicio → intactos.

### Plan técnico (EST-05)

`AuditoriaTasa` (models.py:1435-1492) NO tiene usuario hoy → **sin RenameField**: `AddField usuario` FK (SET_NULL, null=True, blank=True, related_name='tasas_registradas') + `usuario_nombre = CharField(max_length=150, blank=True, default='')`, insertados tras `fuente` (1472). Migración **0030** (auto-name, p. ej. `0030_auditoriataasa_usuario…`): solo 2 AddField, **sin RunPython** (campo nuevo: histórico queda FK NULL + snapshot '' por diseño).

Writers (2, patrón EST-04 + helper `resolver_usuario`):
1. `services.sincronizar_tasa_cambio` — firma 1628 `def sincronizar_tasa_cambio() -> dict:` → `def sincronizar_tasa_cambio(usuario: str | User | None = None) -> dict:`; create 1713-1719 añade `usuario=usuario_fk, usuario_nombre=usuario_nombre`; caller `vista_sincronizar_tasa` (views.py:1148) → `sincronizar_tasa_cambio(usuario=request.user)`.
2. `views.configuracion_view` (views.py:1702-1709, fuente='MANUAL'): añade `usuario=…, usuario_nombre=…` vía `svc.resolver_usuario(request.user)`.

### Tareas

#### TASK-EST04-01 — Esquema `usuario_nombre` + FK `usuario`; migración 0029 con backfill
- **Objetivo**: rename preservando datos + FK nueva en MovimientoKardex/NotaCredito + backfill por match de username + presentación por snapshot.
- **Archivos**: `inventory/models.py` (1397-1401, 2029-2032), `inventory/migrations/0029_usuario_fk_kardex_nc.py` (NUEVO), `inventory/services.py` (import User; create 210-223 → solo `usuario_nombre=usuario or ''`, sin FK aún), `inventory/views.py` (2534), `inventory/admin.py` (334), `inventory/templates/inventory/nota_credito_detalle.html` (51), `inventory/tests.py` (1646), `inventory/test_cases/test_usuario_fk.py` (NUEVO).
- **RED** (`class TestBackfillUsuarioFK`; setUp empresa/almacén/artículo patrón test_calculos.py:35-146):
  1. `test_esquema_fk_y_snapshot`: `isinstance(MovimientoKardex._meta.get_field('usuario'), ForeignKey)` con `remote_field.on_delete == SET_NULL` y `related_query_name`/'kardex_registrado_por' en `User._meta`; `get_field('usuario_nombre').max_length == 150`; idem NotaCredito ('notas_credito_emitidas'). RED: hoy `usuario` es CharField.
  2. `test_backfill_match_de_username`: `User.objects.create_user('op_backfill', password='pw')`; fixture `MovimientoKardex.objects.create(empresa=…, articulo=…, almacen=…, tipo='ENTRADA', cantidad=1, saldo_resultante=1, concepto='AJUSTE_ENTRADA', usuario_nombre='op_backfill', usuario=None)`; `mod = importlib.import_module('inventory.migrations.0029_usuario_fk_kardex_nc')`; `mod.backfill_usuario_fk(django.apps.apps, None)`; assert `mov.usuario_id == user.pk` y `usuario_nombre == 'op_backfill'`.
  3. `test_backfill_sin_match_preserva_snapshot_y_es_idempotente`: filas `usuario_nombre='seed_db'` y `'Sistema'` → FK `None` tras backfill, snapshot intacto; segunda pasada de `backfill_usuario_fk` sin cambios (assert par `(usuario_id, usuario_nombre)` idéntico).
  ⚠️ Los fixtures (2)-(3) crean kárdex directo → al llegar EST-01 (capítulo 4) se envuelven en `kardex_bypass` y se suman a la allowlist REQ-EST01-04 junto a tests.py:1638.
- **GREEN**: renames+FKs en models; `makemigrations inventory` (genera RenameField+AddField; verificar related_names) + RunPython manual del §Plan técnico; services.py:222 → `usuario_nombre=usuario or ''`; 2534/334/51 por snapshot; tests.py:1646 → `usuario_nombre='Admin'`.
- **VERIFICACIÓN**: `python manage.py test inventory` → **497 OK, skipped=6** (494+3). `python manage.py makemigrations --check` → "No changes detected". `python manage.py showmigrations inventory` → `[X] 0029_usuario_fk_kardex_nc`. Reversibilidad: `python manage.py migrate inventory 0028` (snapshot intacto) y re-`migrate`.
- **Dependencias**: capítulo 2 (CSP) mergeado. **Commit**: `feat(est04): FK usuario + snapshot usuario_nombre en kardex/NC; migracion 0029 con backfill`

#### TASK-EST04-02 — Resolución `str|User` en writers; `reversar_*` registran usuario real
- **Objetivo**: helper único; los 3 sitios de persistencia llenan FK+snapshot; fin del `'Sistema'` hardcoded.
- **Archivos**: `inventory/services.py` (helper tras imports ~60; firmas 71/380/570/861/1080/1253/1733/1852/1900/1962/2338/2371/2432/2662; create 210-223; NC 2492-2499/2696-2703; 2360/2400), `inventory/test_cases/test_usuario_fk.py`.
- **RED** (`class TestResolucionUsuario`):
  1. `test_user_instancia_llena_fk_y_snapshot`: `registrar_movimiento(…, usuario=self.user)` → `usuario_id == self.user.pk` + `usuario_nombre == self.user.username` (Gherkin EST04-01).
  2. `test_str_match_resuelve_fk_y_no_match_deja_null`: `registrar_movimiento(…, usuario='op_resolver')` (user existente) → FK resuelta; `registrar_movimiento(…, usuario='data03')` → `usuario_id is None` + `usuario_nombre == 'data03'` (Gherkin EST04-02/03 — la rama que mantienen los ~60 literales).
  3. `test_reversar_registran_usuario`: venta vía `procesar_venta(usuario=self.user)` + compra vía `registrar_compra_proveedor(usuario=self.user)`; `reversar_nota_entrega(eid, nota.pk, 'error', usuario=<User admin>)` → movimientos `DEVOLUCION_VENTA` con `usuario_id == admin.pk`, `usuario_nombre == 'admin'`; sin el arg → snapshot `'Sistema'` (backward-compat, Gherkin EST04-08).
- **GREEN**: helper + firmas (defaults conservados) + 222/2497/2701 resuelven + 2360/2400 passthrough.
- **VERIFICACIÓN**: `python manage.py test inventory` → **500 OK, skipped=6** (+3). `makemigrations --check` limpio (sin cambios de esquema). Tests legacy de reversos y devoluciones verdes sin edición.
- **Dependencias**: TASK-EST04-01. **Commit**: `feat(est04): resolucion str|User en writers; reversar_* registran usuario real`

#### TASK-EST04-03 — Vistas: instancia `request.user`; `usuario` por POST deprecado
- **Objetivo**: las 8 vistas escritoras pasan instancia; POST/JSON `usuario` ignorado con warning (carga masiva y colisión); reversos pasan usuario.
- **Archivos**: `inventory/views.py` (469-486, 548-554, 611-630, 759, 1345, 2057, 2110, 2131, 2426-2434), `inventory/test_cases/test_usuario_fk.py`.
- **RED** (`class TestVistasUsuarioForense`): `test_post_usuario_deprecado_carga_y_colision`: login `op_carga` (patrón tests.py:4302); (a) POST a carga masiva con `_crear_excel_bytes` (`from inventory.tests import _crear_excel_bytes`, tests.py:469) + `usuario='farsante'` en el form → kárdex del lote con `usuario_id == op_carga.pk`, `usuario_nombre == 'op_carga'` y `assertLogs('inventory.views', level='WARNING')` menciona deprecado; (b) colisión armada con patrón `TestResolverColision` (tests.py:754) + POST JSON con `usuario='farsante'` → kárdex de la decisión con FK del autenticado + warning.
- **GREEN**: diffs exactos de la tabla §Deprecación (fallbacks muertos eliminados).
- **VERIFICACIÓN**: `python manage.py test inventory` → **501 OK, skipped=6** (+1). Suite de vistas existente (carga/colisión/venta/compra/NC/reversos) verde — regresión cubierta por los tests legacy.
- **Dependencias**: TASK-EST04-02. **Commit**: `feat(est04): vistas pasan request.user; usuario por POST deprecado con warning`

#### TASK-EST05-01 — `AuditoriaTasa.usuario`: FK + snapshot; migración 0030; 2 writers
- **Objetivo**: REQ-EST05-A1 — mismo patrón EST-04 en `AuditoriaTasa`.
- **Archivos**: `inventory/models.py` (campos tras 1472), `inventory/migrations/0030_…` (NUEVO, 2 AddField), `inventory/services.py` (1628, 1713-1719), `inventory/views.py` (1148, 1702-1709), `inventory/test_cases/test_usuario_fk.py`.
- **RED** (`class TestAuditoriaTasaUsuario`):
  1. `test_configuracion_manual_registra_usuario_fk`: POST a configuración con tasa cambiada (patrón tests.py:1103) → `AuditoriaTasa.objects.last()` con `usuario_id == user.pk` + `usuario_nombre == username`.
  2. `test_sincronizar_api_registra_usuario`: patrón del test de sync existente (mock de la fuente de tasa) + `sincronizar_tasa_cambio(usuario=self.user)` → última AuditoriaTasa con FK y snapshot.
  3. `test_baja_usuario_preserva_snapshot_auditoria`: auditoría con FK; `user.delete()` → fila persiste con `usuario_id is None` + snapshot intacto (SET_NULL).
- **GREEN**: 2 AddField en models + `makemigrations` (0030); firma 1628 + create 1713-1719; views 1148/1702-1709 vía `svc.resolver_usuario(request.user)`.
- **VERIFICACIÓN**: `python manage.py test inventory` → **504 OK, skipped=6** (+3). `makemigrations --check` limpio. `showmigrations inventory` → `[X] 0029`, `[X] 0030`. `migrate inventory 0029` y vuelta (AddField reversible, sin datos que perder).
- **Dependencias**: TASK-EST04-03 (0030 depende de 0029; helper ya existe). **Commit**: `feat(est05): FK usuario + snapshot en AuditoriaTasa; migracion 0030`

## Capítulo 4 — EST-01: Kárdex inmutable (señales + QuerySet + escape hatch)

Posición: EST-01 va DESPUÉS de EST-04/EST-05 (cap. 3) — el fixture de tests.py:1646 ya es `usuario_nombre='Admin'` y la FK `usuario` existe. Base entrante: **504 OK, skipped=6** → salida **512** (+8). **Sin migraciones nuevas**: el wiring de managers no toca el estado del esquema (`use_in_migrations` inactivo en `EmpresaManager`). Salidas: `inventory/kardex_guard.py` y `inventory/test_cases/test_kardex_inmutable.py` (NUEVOS). Decisiones G1 fijas: señales `pre_save`/`pre_delete` + QuerySet custom + escape hatch con allowlist, SIN triggers SQL; guard de INSERT directo incluido (Regla Sagrada bidireccional).

### Plan técnico

#### Módulo NUEVO `inventory/kardex_guard.py` (recomendado sobre `services.py`/`signals.py`)

Justificación (2 líneas): (1) un único archivo auditable para ContextVar+bypass+receivers hace la allowlist (REQ-EST01-04) verificable por grep/ADR, sin mezclar enforcement con la siembra de negocio de `signals.py` (solo post_save de Empresa) ni engordar `services.py` (~2800 líneas); (2) la arista de import es una sola: `kardex_guard → models`; services/seed_db/tests importan `kardex_guard`, y `models.py` solo lo importa perezosamente (sin ciclos). El cap. 5 (EST-02) reusa este módulo: añade receivers de los 6 modelos de documento sobre la base `IntegridadDocumentalError`.

Mecanismo: `contextvars.ContextVar` con **contador apilable** (reentrante; thread/async-safe por diseño). El bypass público loguea `WARNING` con el motivo **al entrar** (REQ-EST01-03); el contexto interno del service loguea `INFO` — el camino legítimo no genera ruido de WARNING (REQ-EST01-06). El `finally` con `reset(token)` impide fugas de contexto ante excepciones.

```python
"""EST-01 (G1): inmutabilidad del kárdex — bypass contextual + señales pre_save/pre_delete."""
import logging
import contextvars
from contextlib import contextmanager
from django.db.models.signals import pre_save, pre_delete
from django.dispatch import receiver
from .models import MovimientoKardex, KardexProtegidoError

logger = logging.getLogger(__name__)
_nivel = contextvars.ContextVar('kardex_bypass_nivel', default=0)  # contador apilable

def bypass_activo() -> bool:
    return _nivel.get() > 0

@contextmanager
def kardex_bypass(motivo: str):
    """REQ-EST01-03 — escape hatch de la allowlist (ADR). WARNING audible por diseño."""
    logger.warning('[KARDEX BYPASS] activado: %s', motivo)
    token = _nivel.set(_nivel.get() + 1)
    try:
        yield
    finally:
        _nivel.reset(token)

@contextmanager
def escritura_kardex_autorizada(concepto: str = ''):
    """REQ-EST01-05/06 — contexto INTERNO de registrar_movimiento; mismo contador, log INFO."""
    logger.info('[KARDEX] escritura autorizada via services (concepto=%s)', concepto)
    token = _nivel.set(_nivel.get() + 1)
    try:
        yield
    finally:
        _nivel.reset(token)

def bloquear_kardex(operacion: str, instance=None):
    """REQ-EST01-08 — log ERROR (modelo, operación, pk, traceback) y luego raise."""
    logger.error('[EST-01] Bloqueado %s de MovimientoKardex (pk=%s). Use services.registrar_movimiento '
                 'o kardex_guard.kardex_bypass (allowlist ADR).',
                 operacion, getattr(instance, 'pk', None), exc_info=True)
    raise KardexProtegidoError(f'Kárdex inmutable: {operacion} prohibido. Vía legítima: services.registrar_movimiento.')

@receiver(pre_save, sender=MovimientoKardex)      # INSERT y UPDATE directos (opción (a) del G1)
def _kardex_pre_save(sender, instance, **kwargs):
    if not bypass_activo():
        bloquear_kardex('INSERT/UPDATE directo', instance)

@receiver(pre_delete, sender=MovimientoKardex)    # instancia + bulk + cascada (doc Django 6.0)
def _kardex_pre_delete(sender, instance, **kwargs):
    if not bypass_activo():
        bloquear_kardex('DELETE', instance)
```

**pre_save exige bypass SIEMPRE** (opción (a) del G1, REQ-EST01-05): `registrar_movimiento` es el único creador legítimo (grep: services.py:210 + fixtures de test) y él mismo entra en contexto — un INSERT/UPDATE de kárdex sin contexto activo no puede ser legítimo; no se requiere flag por instancia. Conexión: `apps.py ready()` añade `import inventory.kardex_guard  # noqa: F401` junto al `import inventory.signals` existente (apps.py:10). Los receivers se conectan con `sender=MovimientoKardex` (clase real): los modelos históricos de migraciones (clases reconstruidas por ModelState, sin relación con la clase real) **no los disparan** (REQ-EST01-07; test en TASK-03 + roundtrip de `migrate` como prueba end-to-end).

#### Excepciones + QuerySet custom en `inventory/models.py`

Excepciones tras el bloque de imports (~línea 30; `PermissionDenied` — no `ValidationError` — porque semánticamente es "operación no permitida" y, si algún camino HTTP lo provocara, la vista responde 403 y no 500):

```python
class IntegridadDocumentalError(PermissionDenied):
    """Base común EST-01/EST-02: operación prohibida sobre registros históricos del sistema."""
class KardexProtegidoError(IntegridadDocumentalError):
    """EST-01: el kárdex solo muta vía services.registrar_movimiento o kardex_bypass."""

class KardexQuerySet(models.QuerySet):
    """REQ-EST01-02: .update() no emite pre_save (doc Django) y bulk_create tampoco → se bloquean aquí."""
    def update(self, **kwargs):
        from .kardex_guard import bypass_activo, bloquear_kardex  # perezoso: rompería el ciclo models↔kardex_guard
        if not bypass_activo():
            bloquear_kardex('.update()')
        return super().update(**kwargs)
    def bulk_create(self, objs, **kwargs):
        from .kardex_guard import bypass_activo, bloquear_kardex
        if not bypass_activo():
            bloquear_kardex('bulk_create')
        return super().bulk_create(objs, **kwargs)
```

`bulk_create` se bloquea pese a no estar en el G1 literal: es INSERT directo (Regla Sagrada) y la doc oficial confirma que **no emite señales** — dejarlo abierto sería un guard con bypass conocido. `delete()` de queryset NO se overridea: `pre_delete` SÍ se dispara por instancia en bulk y cascada (doc Django 6.0, spec §1.4.1).

**Wiring de managers** (sustituye `objects = EmpresaManager()` / `global_objects = models.Manager()`, models.py:1403-1404):

```python
objects = EmpresaManager.from_queryset(KardexQuerySet)()   # tenant-filter preservado + update bloqueado
global_objects = KardexQuerySet.as_manager()               # sin filtro de tenant + update bloqueado (Gherkin EST01-05)
```

`from_queryset` genera una subclase de `EmpresaManager` con `_queryset_class=KardexQuerySet`: su `get_queryset()` (managers.py:46-51) sigue aplicando `.none()`/`.filter(empresa_id=…)` SOBRE un KardexQuerySet, y los métodos copiados delegan al queryset → `objects.update(...)` también queda bloqueado. **`managers.py` NO se toca**: ningún otro modelo hereda el bloqueo (el cambio es una subclase nueva solo para kárdex).

#### Service (`inventory/services.py`)

- Import `from .kardex_guard import escritura_kardex_autorizada` (~línea 48, tras el de models) y el create de `registrar_movimiento` (210-223) se envuelve: `with escritura_kardex_autorizada(concepto):` — comportamiento idéntico (REQ-EST01-06), el contexto solo autoriza el INSERT. Los demás services (ventas, compras, cargas, transferencias, ajustes, devoluciones, reversos) crean kárdex vía `registrar_movimiento` → quedan cubiertos sin cambios.
- NUEVO `eliminar_tenant` (pública, junto a los `reversar_*` ~2430):

```python
def eliminar_tenant(empresa, motivo: str) -> None:
    """EST-01 (Gherkin EST01-08): ÚNICA vía autorizada de teardown de un tenant con datos."""
    if not motivo:
        raise ValueError('eliminar_tenant exige un motivo auditable.')
    from .kardex_guard import kardex_bypass
    with kardex_bypass(f'teardown tenant {empresa.rif}: {motivo}'):
        empresa.delete()
```

#### Cascada del teardown — decisión explícita (la interacción más delicada)

`pre_delete` se dispara para cada fila de kárdex que el collector de `Empresa.delete()` recoge (FK `empresa` CASCADE, models.py:1336) → **`Empresa.delete()` directo sobre un tenant CON kárdex queda BLOQUEADO** (`KardexProtegidoError`, rollback total: ni empresa ni kárdex se tocan). NO se auto-exime la cascada: `pre_delete` no recibe origen de la eliminación (detectar "viene de Empresa" exigiría husmear el collector — frágil y no soportado) y auto-eximir reabriría el agujero "borro el kárdex borrando la empresa" para cualquier caller. Contrato: **`Empresa.delete()` directo prohibido para tenants con kárdex; usar `services.eliminar_tenant(empresa, motivo)`** — que registra el motivo en el WARNING del bypass. Verificado HOY: `test_tenant_lifecycle.py:98` borra tenants recién sembrados SIN filas de kárdex → `pre_delete` de kárdex no dispara → test verde SIN cambios (PROTECT→RESTRICT de TasaCambio en 5d137fa no interfiere). Se registra en ADR (TASK-03).

#### Allowlist EXACTA (REQ-EST01-04; grep completo del repo: 0 bulk_create, 0 `.save()` de instancia de kárdex, 0 `.update()` fuera de tests.py:1649)

| Call-site | Tratamiento |
|---|---|
| `services.registrar_movimiento` create (services.py:210) | Contexto interno `escritura_kardex_autorizada(concepto)` (INFO) — no es bypass público |
| `seed_db.py:499` `_clear_all` (secuencia 499-510) | Envolver la secuencia de deletes en `kardex_bypass('seed_db --clear: reseed demo')` (cubre también a EST-02, mismo ContextVar) |
| `tests.py:1638` create + `:1649` `.update(fecha_hora)` (`TestExportacionLogicaSaaS.setUp`, 1646 ya `usuario_nombre=`) | Envolver ambas en `kardex_bypass('fixture export SaaS: movimiento viejo')` |
| `test_cases/test_usuario_fk.py` (cap. 3): creates fixture + `backfill_usuario_fk(django.apps.apps, None)` (sus `fila.save()`) incl. 2ª pasada idempotente | Envolver en `kardex_bypass('fixture EST-04: backfill 0029')` |
| `generate_demo_data.py:199/338` | **Ya no aplica**: usa `registrar_movimiento` → contexto del service |
| Teardown de tenant con datos (hoy NO existe como call-site: grep solo test_tenant_lifecycle sin kárdex) | `services.eliminar_tenant(empresa, motivo)` — NUEVO, única vía autorizada |
| Migraciones 0029/0030 (RunPython `save`/`update` sobre históricos) | **Ya no aplica**: exentas por `sender=clase real` (REQ-EST01-07) |
| Admin (`MovimientoKardexAdmin` has_add/change/delete_permission=False, admin.py:338-346; inline de compras can_delete=False, 404-409) | **Ya no aplica**: vector cerrado hoy (REQ-EST01-09, 0 cambios de admin en EST-01; el guard es backstop) |

**Ruido de suite**: SOLO (a) `TestExportacionLogicaSaaS` (1638/1649) y (b) `test_usuario_fk.py` (fixtures del cap. 3) suenan al activar los guards → se envuelven en bypass = **actualización legítima de contrato** (fixture declarado, no relajación). Resto verificado silencioso: TestCase desmonta por rollback (no deletes ORM); reversos solo INSERTAN compensatorios (2348/2386 mutan nota/compra, no kárdex); todo lo demás pasa por services. Un 4º uso del bypass en services/views/admin = defecto de diseño, no caso del bypass (REQ-EST01-04).

### Tareas

#### TASK-EST01-01 — kardex_guard (bypass reentrante + receivers) + KardexQuerySet + silencio de la allowlist
- **Objetivo**: REQ-EST01-01/02/03/05/06/08 — escape hatch + señales + wiring, activando los guards con la suite y `seed_db --clear` verdes (la allowlist se aplica JUNTO a la activación — corte del prompt ajustado para no dejar ventana roja entre tasks).
- **Archivos**: `inventory/kardex_guard.py` (NUEVO, §Plan), `inventory/models.py` (excepciones+KardexQuerySet ~línea 30; wiring 1403-1404), `inventory/apps.py` (ready(), línea 10), `inventory/services.py` (import ~48 + wrap 210-223), `inventory/management/commands/seed_db.py` (import ~29 + wrap 499-510), `inventory/tests.py` (wrap 1638-1649), `inventory/test_cases/test_usuario_fk.py` (wrap fixtures `TestBackfillUsuarioFK`), `inventory/test_cases/test_kardex_inmutable.py` (NUEVO).
- **RED** (`class TestKardexGuard`; setUp patrón test_calculos.py:35-146: empresa + tenant en sesión + artículo FISICO + `registrar_movimiento(ENTRADA, 10, 'AJUSTE_ENTRADA')`):
  1. `test_delete_instancia_y_queryset_bloqueados`: `mov.delete()` → `assertRaises(KardexProtegidoError)` y conteo intacto; `MovimientoKardex.objects.all().delete()` → ídem (Gherkin EST01-02/03).
  2. `test_create_directo_y_bulk_create_bloqueados`: `MovimientoKardex.objects.create(empresa=…, articulo=…, almacen=…, tipo='ENTRADA', cantidad=1, saldo_resultante=1, concepto='AJUSTE_ENTRADA', usuario_nombre='test')` → `KardexProtegidoError` + 0 filas nuevas; `global_objects.bulk_create([m1, m2])` → ídem (Gherkin EST01-06 + hueco bulk).
  3. `test_bypass_permite_todo_loggea_warning_y_es_apilable`: dentro de `kardex_bypass('prueba guard')`: create directo OK, `.update(detalle_adicional='x')` OK, `.delete()` OK; `assertLogs('inventory.kardex_guard', level='WARNING')` contiene el motivo; anidado `with kardex_bypass('b'):` OK; tras salir, create vuelve a lanzar `KardexProtegidoError` (Gherkin EST01-07).
- **GREEN**: kardex_guard.py íntegro + excepciones/QuerySet/wiring en models + apps.ready + wrap del create en services + wraps de allowlist (seed_db, tests.py, test_usuario_fk).
- **VERIFICACIÓN**: `python manage.py test inventory.test_cases.test_kardex_inmutable -v 2` → 3 OK; `python manage.py test inventory` → **507 OK, skipped=6** (504+3, suite VERDE — fixtures ya envueltos); `python manage.py makemigrations --check` → "No changes detected" (0 migraciones).
- **Dependencias**: capítulo 3 (TASK-EST05-01 mergeado). **Commit**: `feat(est01): kardex_guard (bypass reentrante + senales) + KardexQuerySet; allowlist aplicada`

#### TASK-EST01-02 — `.update()` bloqueado en ambos managers + cascada de tenant + `eliminar_tenant`
- **Objetivo**: REQ-EST01-02 completa + Gherkin EST01-04/05/08 — verificar el bloqueo de `.update()` en `objects`/`global_objects`, la cascada bloqueada y la vía legítima de teardown.
- **Archivos**: `inventory/services.py` (`eliminar_tenant` NUEVA ~2430), `inventory/test_cases/test_kardex_inmutable.py`.
- **RED** (`class TestKardexUpdateTeardown`; setUp con empresa + 1 movimiento legítimo):
  1. `test_update_bloqueado_en_objects_y_global_objects`: `MovimientoKardex.objects.filter(pk=mov.pk).update(cantidad=999)` → `KardexProtegidoError` y cantidad persistida intacta; `MovimientoKardex.global_objects.filter(empresa=self.empresa).update(detalle_adicional='x')` → ídem (Gherkin EST01-04/05).
  2. `test_empresa_delete_directo_con_kardex_bloqueado`: `self.empresa.delete()` → `assertRaises(KardexProtegidoError)`; la empresa y sus movimientos persisten (rollback del collector).
  3. `test_eliminar_tenant_teardown_completo_y_motivo_obligatorio`: `svc.eliminar_tenant(self.empresa, motivo='fin de prueba')` → empresa, `movimientos_kardex` y notas en 0 (vía `global_objects`); `assertLogs` WARNING contiene `teardown tenant`; `eliminar_tenant(otra, motivo='')` → `ValueError` (Gherkin EST01-08).
- **GREEN**: `eliminar_tenant` en services (§Plan); sin más cambios de código.
- **VERIFICACIÓN**: `python manage.py test inventory` → **510 OK, skipped=6** (+3); `makemigrations --check` limpio; `test_tenant_lifecycle.py` verde sin edición (tenant sin kárdex).
- **Dependencias**: TASK-EST01-01. **Commit**: `feat(est01): eliminar_tenant como unica via de teardown; empresa.delete directo bloqueado con kardex`

#### TASK-EST01-03 — Camino legítimo y migraciones probados; ADR de la allowlist
- **Objetivo**: REQ-EST01-04/06/07 — regresión del reverso (solo INSERT compensatorio), exención de modelos históricos, y registro ADR de la allowlist + contrato `eliminar_tenant`.
- **Archivos**: `inventory/test_cases/test_kardex_inmutable.py`, `docs/ADR.md` (ADR allowlist del bypass — 3 entradas: allowlist REQ-EST01-04, prohibición de `Empresa.delete()` directo, bypass como mecanismo compartido EST-02).
- **RED** (`class TestKardexCaminoLegitimo`):
  1. `test_reverso_venta_inserta_compensatorio_sin_borrados`: venta vía `procesar_venta` (1 detalle) → N movimientos; `reversar_nota_entrega(empresa_id, nota.pk, 'error')` → sin excepción, nota ANULADA y **N+1** movimientos (nuevo `DEVOLUCION_VENTA`; 0 borrados) (Gherkin EST01-10).
  2. `test_receivers_cableados_solo_a_la_clase_real`: `pre_save.receivers` y `pre_delete.receivers` contienen un `lookup_key` con `id(MovimientoKardex)` como sender → las clases históricas de migraciones (reconstruidas por ModelState: id distinto, sin relación de subclase) no los disparan (REQ-EST01-07, Gherkin EST01-09).
- **GREEN**: los 2 tests pasan sin tocar código (verifican el TASK-01/02 ya mergeado).
- **VERIFICACIÓN**: `python manage.py test inventory` → **512 OK, skipped=6** (510+2) — acumulada final del capítulo; `makemigrations --check` limpio; roundtrip de migraciones con guards activos: `python manage.py migrate inventory 0028 && python manage.py migrate inventory` → el backfill de 0029 (`fila.save()` sobre históricos) completa sin `KardexProtegidoError` (prueba end-to-end de REQ-EST01-07). Smoke manual OPCIONAL (destructivo, solo dev): `python manage.py seed_db --clear` → "Base de datos limpia".
- **Dependencias**: TASK-EST01-02. **Commit**: `test(est01): reverso N+1 sin borrados + exencion de historicos; ADR allowlist kardex_bypass`

## Capítulo 5 — EST-02: Inmutabilidad de documentos emitidos

Posición: DESPUÉS de EST-01 (cap. 4) — reusa `kardex_guard.py` (mismo ContextVar: cubre `seed_db --clear` ya envuelto y `services.eliminar_tenant`). Base entrante: **512 OK, skipped=6** → salida **522** (+10). **Sin migraciones**: la matriz es comportamiento, no esquema (0 columnas nuevas). G1 fijas: par único `estado`→ANULADO + `motivo_anulacion`; guard `.update()`/bulk = fase 2 DIFERIDA (riesgo residual documentado); admin TOTALMENTE readonly; NC pre-create (no allowlist de `monto_total_reembolso`); dead code `nc.delete()` eliminado. Salida nueva: `inventory/test_cases/test_inmutabilidad_documentos.py`.

### Plan técnico

#### 1. Matriz de campos mutables tras emisión (el corazón)

Estados (grep `ESTADO_CHOICES`): NE (models.py:1505-1508), DC (1103-1106) y NC (1971-1974) tienen EXACTAMENTE `PROCESADO|ANULADO` — no hay borradores: todo documento nace emitido (`procesar_venta`, `registrar_compra_proveedor`, `procesar_devolucion_*` crean con `estado='PROCESADO'`, services.py:2498/2702). La NC NO nace anulada y HOY ningún flujo la anula: no existe `reversar_nota_credito` (grep 0) ni `anular_compra` (la anulación real de compra es `reversar_documento_compra`, 2371-2407, que valida seriales VENDIDO en 2380-2382). **No existen timestamps de anulación** (grep `anulada_en|fecha_anulacion|anulado_en` = 0 en el repo; `fecha`/`fecha_registro` son auto_now_add de emisión): la marca temporal forense de la anulación la portan los MovimientoKardex compensatorios (`fecha_hora`) + `motivo_anulacion` — NO se añade campo (0 migraciones).

| Modelo | Mutable tras emisión | Escritor legítimo (único) | Regla de transición |
|---|---|---|---|
| `NotaEntrega` (1498) | `estado`, `motivo_anulacion` | `reversar_nota_entrega` (2346-2348) | solo PROCESADO→ANULADO; `motivo_anulacion` solo EN el mismo save de esa transición |
| `DocumentoCompra` (1032) | `estado`, `motivo_anulacion` | `reversar_documento_compra` (2384-2386) | ídem |
| `NotaCredito` (1957) | `estado`, `motivo_anulacion` | **ninguno hoy** (par reservado por spec §2.2 para futura anulación de NC) | ídem; tras TASK-04 la NC nace completa y no vuelve a salvarse |
| `DetalleNotaEntrega` (1708) | **ninguno** (matriz vacía) | — | re-save con valores idénticos pasa (REQ-EST02-03) |
| `DetalleDocumentoCompra` (1194) | **ninguno** | — | ídem |
| `DetalleNotaCredito` (2106) | **ninguno** | — | su `save()` (2207-2221) recalcula derivados (`subtotal_devuelto_usd`,`iva_usd`,`linea_total_usd`) de entradas idénticas → diff vacío → pasa (Gherkin EST02-08) |

**Aclaración `cantidad_devuelta_acumulada`** (la trampa del prompt): NO es columna — es `@property` que SUMA las filas `DetalleNotaCredito` del related `devoluciones` (`DetalleNotaEntrega` 1866-1878; `DetalleDocumentoCompra` 1277-1285). Su "writer legítimo" es el **INSERT de `DetalleNotaCredito`** en `procesar_devolucion_venta` (2549) / `_compra` (2744), que NO toca la fila origen → la matriz de líneas sigue VACÍA y el flujo de devolución queda intacto por construcción (REQ-EST02-10). TASK-02 lo certifica: tras una devolución, la línea origen re-salva sin diff.

#### 2. Señal pre_save compartida: UN handler + matriz como datos, en `kardex_guard.py`

**Dónde vive**: SE MANTIENE `inventory/kardex_guard.py` (no renombrar a `guards.py`, no crear `immutable_docs.py`). (1) El ContextVar del bypass debe ser UNO — un módulo nuevo importaría `bypass_activo` de kardex_guard igualmente (frontera artificial); (2) renombrar rompe 6 import-sites ya mergeados (apps.ready, services, seed_db, tests.py:1638-1649, test_usuario_fk, test_kardex_inmutable) y las referencias del ADR del cap. 4; (3) la allowlist REQ-EST01-04 se audita por grep en UN archivo. El docstring pasa a "guards de integridad documental (EST-01 kárdex + EST-02 documentos)". **Un handler para los 6 senders** (no 6): la lógica fetch→diff es idéntica; la matriz es un dict — la allowlist entera vive en un símbolo auditable. Excepción en `models.py` junto a `KardexProtegidoError` (cap. 4): `class DocumentoInmutableError(IntegridadDocumentalError)`.

Fetch del original: `type(instance)._base_manager.filter(pk=…)` — **NO `objects`**: `EmpresaManager.get_queryset` retorna `.none()` sin request (managers.py:46-51) → el guard quedaría ciego en shell/tests/commands. `_base_manager` es `Manager` plano por defecto (ninguno de los 6 define `Meta.base_manager_name`; doc: "By default, Django uses an instance of the Model._base_manager… the normal base manager class (django.db.models.Manager)" — https://docs.djangoproject.com/en/6.0/topics/db/managers/). `global_objects` serviría en NE/DC/NC pero `DetalleNotaEntrega` NO lo define (manager por defecto, 1708-1817) → `_base_manager` es el único mecanismo uniforme. `pre_save` entrega `update_fields` (set|None) y `raw` (doc: https://docs.djangoproject.com/en/6.0/ref/signals/#pre-save).

```python
# kardex_guard.py — añadidos (imports de los 6 modelos junto al de MovimientoKardex)
MATRIZ = {NotaEntrega: {'estado', 'motivo_anulacion'},
          DocumentoCompra: {'estado', 'motivo_anulacion'},
          NotaCredito: {'estado', 'motivo_anulacion'},  # su pre_save se conecta en TASK-04 (§5)
          DetalleNotaEntrega: frozenset(), DetalleDocumentoCompra: frozenset(),
          DetalleNotaCredito: frozenset()}
CABECERAS = (NotaEntrega, DocumentoCompra, NotaCredito)

def bloquear_documento(operacion, instance, cambios=()):
    logger.error('[EST-02] %s de %s pk=%s cambios=%s. Vía legítima: services.reversar_*.',
                 operacion, type(instance).__name__, getattr(instance, 'pk', None),
                 sorted(cambios), exc_info=True)
    raise DocumentoInmutableError(f'Documento emitido inmutable: {operacion} prohibido '
                                 f'(campos: {sorted(cambios)}). Use services.reversar_*.')

def _documento_pre_save(sender, instance, raw=False, update_fields=None, **kw):
    if raw or bypass_activo() or instance.pk is None:   # fixture / allowlist / CREATE: permitido
        return
    original = type(instance)._base_manager.filter(pk=instance.pk).first()
    if original is None:
        return
    mutables = MATRIZ[sender]
    if update_fields is not None and (ajenos_uf := set(update_fields) - mutables):
        bloquear_documento('save(update_fields=…)', instance, ajenos_uf)  # ajenos → bloquear, aunque el valor no cambie
    changed = {f.name for f in sender._meta.concrete_fields
               if f.name != 'id' and (update_fields is None or f.name in update_fields)
               and f.value_from_object(instance) != f.value_from_object(original)}  # FK por attname → id, sin fetch
    if not changed:
        return                                           # re-save idempotente (Gherkin EST02-06/08)
    if sender in CABECERAS:
        if original.estado == 'ANULADO':                # documento cerrado (REQ-EST02-02)
            bloquear_documento('mutación de documento ANULADO', instance, changed)
        if 'estado' in changed and instance.estado != 'ANULADO':
            bloquear_documento('transición de estado ≠ ANULADO', instance, changed)
        if 'motivo_anulacion' in changed and 'estado' not in changed:
            bloquear_documento('motivo_anulacion sin transición', instance, changed)
    if (ajenos := changed - mutables):
        bloquear_documento('modificación de campos inmutables', instance, ajenos)

def _documento_pre_delete(sender, instance, **kw):
    if not bypass_activo():
        bloquear_documento('DELETE', instance)
```

Registro (final de kardex_guard.py): `for m in (NotaEntrega, DocumentoCompra, DetalleNotaEntrega, DetalleDocumentoCompra, DetalleNotaCredito): pre_save.connect(_documento_pre_save, sender=m); pre_delete.connect(_documento_pre_delete, sender=m)` + `pre_delete.connect(_documento_pre_delete, sender=NotaCredito)`. **`pre_save` de `NotaCredito` NO se conecta aquí** — dependencia de orden REAL del capítulo: `procesar_devolucion_*` termina con `nc.save(update_fields=['monto_total_reembolso'])` (2631/2791) sobre NC PROCESADO; conectar hoy rompería los 29 tests NC. Se conecta en TASK-04 junto al refactor pre-create. `pre_delete` de NC sí activa ya (0 deletes legítimos tras el §4). Cascadas cubiertas: `seed_db --clear` (499-510, ya envuelto por TASK-EST01-01) y `eliminar_tenant` (cap. 4) usan el MISMO ContextVar. **Fase 2 DIFERIDA** (G1, REQ-EST02-07): `.update()`/`bulk_update`/`bulk_create` no emiten señales → sin guard; 0 usos en services/views (spec §1.5) → riesgo residual documentado en ADR (TASK-04).

#### 3. Admin TOTALMENTE readonly

Superficie (grep admin.py): `NotaEntregaAdmin` (373-383 — HOY permite editar `estado`/`motivo_anulacion`/`cliente`/`moneda_pago`/`descuento_global`/`observaciones` de un PROCESADO: vector "anular sin reversar stock"), `DetalleNotaEntregaInline` (367-370, editable con delete), `DetalleNotaEntregaAdmin` (386-393, CRUD completo), `DocumentoCompraAdmin` (411-418, cabecera editable). `MovimientoKardexCompraInline` ya cerrado (400-409). **No existe admin de `NotaCredito`** → nada que cerrar; NO se añade (scope creep; el guard es backstop). Mecanismo: mixin ANTES de los ModelAdmin de documentos (~365):

```python
class ReadOnlyDocumentoAdminMixin:
    """EST-02 (REQ-EST02-08): documento emitido = registro histórico; el admin solo mira."""
    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj)  # no amplía exposición: solo quien ya tenía view/add/change/delete
    def get_readonly_fields(self, request, obj=None):
        if obj is not None:  # todos los campos concretos + los readonly estáticos (379-381)
            return [f.name for f in self.model._meta.concrete_fields] + list(super().get_readonly_fields(request, obj))
        return super().get_readonly_fields(request, obj)
```

Aplicar en `NotaEntregaAdmin`, `DetalleNotaEntregaAdmin`, `DocumentoCompraAdmin` (mismo MRO que `TenantGlobalAdminMixin`); `DetalleNotaEntregaInline.can_delete = False`. Con `has_change=False` + view, la vista de detalle del padre renderiza TODOS los campos readonly y los inlines en modo view (sin "Agregar otro" ni checkbox de borrar) — **el readonly del padre fuerza el de los inlines**; `can_delete=False` y `get_readonly_fields` son cinturón y tirantes si alguien re-concede change por User/Group. La acción "Eliminar seleccionados" desaparece con `has_delete_permission=False` (patrón ya probado de `MovimientoKardexAdmin`, 338-346). `DocumentoInmutableError` es `PermissionDenied` → si algún POST forzado llegara al ORM, responde 403-amable, no 500 (elección de la base común, cap. 4).

#### 4. Dead code `nc.delete()` — qué es y eliminación segura

`nc.delete() if nc.pk else None` en `procesar_devolucion_venta` (services.py:2627, dentro de `except Exception:` 2625-2628) y `procesar_devolucion_compra` (2787, except 2786-2788). Son restos de compensación manual previa a `@transaction.atomic` (decoradores en 2426/2656): hoy el `raise` marca rollback total y el delete es **no-op puro** — la tx ya está abortada. Bajo EST-02, su `pre_delete` lanzaría `DocumentoInmutableError` ENMASCARANDO la excepción original (p.ej. `ValueError` "No se pueden devolver…"). Eliminación: quitar el envoltorio `try/except` completo (venta 2510-2628, compra 2708-2788) dejando el `for` plano — el atomic garantiza que ningún NC/DetalleNC/kárdex huérfano sobrevive a un fallo. **Aterriza en TASK-01**, no después: los error-paths de los 29 tests NC (exceder `cantidad_pendiente_devolver`, iva fuera de rango) pasan por ese except y son la RED que exige la eliminación.

#### 5. Refactor pre-create de NotaCredito (REQ-EST02-06, Gherkin EST02-07)

Hoy la NC nace VACÍA (`create` 2492-2499 con monto default 0) y se "corrige" al final: `monto_total_usd += det_nc.linea_total_usd` en el loop (2559) → `nc.monto_total_reembolso = …; nc.save(update_fields=[…])` (2630-2631; compra 2790-2791). Con el guard §2 ese save es ilegítimo; además una NC PROCESADO existe 100ms con monto mentido. Doble pasada:

1. **Pasada 1 (validar+calcular, sin persistir)**: mover las validaciones por item (2512-2546: cantidad>0, detalle pertenece al doc, `cantidad_pendiente_devolver`, precio≥0, iva∈[0,100]) a un primer loop que computa por línea `subtotal, iva, total = calculos.calcular_linea_devolucion(cantidad, precio_unitario, iva_pct)` y acumula `monto_total = Σ total` (cada total quantizado 0.0001 — aritmética idéntica al `linea_total_usd` actual).
2. **NUEVO en `calculos.py`** (fuente única, DATA-01): `def calcular_linea_devolucion(cantidad, precio_unitario, iva_porcentaje) -> tuple[Decimal, Decimal, Decimal]` con la MISMA fórmula/quantize de `DetalleNotaCredito.save()` (2213-2220). **`DetalleNotaCredito.save()` pasa a delegar** en ella → modelo y pre-create comparten fórmula, drift imposible.
3. **Pasada 2 (persistir)**: `nc = NotaCredito.objects.create(…, monto_total_reembolso=monto_total.quantize(_D('0.0001')))` → loop de `DetalleNotaCredito.objects.create` (2549; su save recalcula derivados deterministas idénticos) → kárdex ENTRADA/SALIDA + seriales (2563-2624 / 2757-2785, sin cambios).
4. **Eliminar** el tail `nc.save(update_fields=['monto_total_reembolso'])` (2630-2631 / 2790-2791) y el try/except del §4. **Firma pública INTACTA** (`procesar_devolucion_venta(empresa_id, nota_id, items_devueltos, motivo, usuario='Sistema')`; views.py:2421/2429 sin cambios; return dict igual). En esta tarea se conecta `pre_save` de `NotaCredito` (§2).

**RED net**: los 29 tests NC existentes (TestNotasCreditoBackend, tests.py:7313, 15; TestNotasCreditoUI, 7792, 14) asertan montos exactos, snapshots, kárdex DEVOLUCION_*, seriales → deben quedar VERDES sin edición (igualdad pre/post garantizada por la fórmula compartida).

#### 6. Ruido de suite (auditado: 0 ediciones de tests existentes)

| Call-site | Efecto bajo EST-02 | Tratamiento |
|---|---|---|
| tests.py:7581-7591 `test_nc_check_constraint_un_origen_unico` | save de instancia NUEVA → INSERT permitido | verde sin cambios |
| `TestReversoIdempotencia` (2543-2562) | 2º reverso lanza ValueError en 2343-2344 ANTES de todo save | sin ruido |
| Reversos (2118, 2175, 8780, 8943) y 29 NC | writers del par de la matriz (`update_fields` permitidos) | verdes |
| `seed_db._clear_all` (499-510: borra DetalleNotaEntrega/NE/DC + cascada NC) | pre_delete dispararía | YA envuelto en `kardex_bypass` por TASK-EST01-01 (mismo ContextVar) |
| test_tenant_lifecycle.py:98 | borra tenants SIN documentos emitidos → pre_delete no dispara | sin cambios |
| SerialArticulo `.update(estado=…)` (tests 1765/1794) | NO es uno de los 6 modelos | fuera de alcance |
| grep total | 0 `.update()` sobre los 6, 0 `detalle.save()`, 0 asignaciones de campos de cabecera en tests | **EST-02 no edita ningún test existente** |

### Tareas

#### TASK-EST02-01 — Señal + matriz en cabeceras NE/DC + dead code fuera
- **Objetivo**: REQ-EST02-01/02/04/05/07 — pre_save NE/DC, pre_delete de los 6, `DocumentoInmutableError`, dead code eliminado; NC pre_save diferido (§2).
- **Archivos**: `inventory/kardex_guard.py` (§2 completo), `inventory/models.py` (`DocumentoInmutableError` junto a `KardexProtegidoError`), `inventory/services.py` (eliminar try/except 2510-2628 y 2708-2788), `inventory/test_cases/test_inmutabilidad_documentos.py` (NUEVO).
- **RED** (`class TestCabecerasInmutables(TestCase)`; setUp patrón tests.py:932: empresa+tenant+artículo FISICO+`procesar_venta`): 1) `test_ne_y_dc_campo_fuera_de_matriz_bloqueado` — `nota.moneda_pago='BS_EFECTIVO'; nota.save()` → `DocumentoInmutableError` y refresh intacto (Gherkin EST02-05); `compra.observaciones='x'; compra.save()` ídem. 2) `test_anulado_es_documento_cerrado` — `reversar_nota_entrega(…)` → ANULADA; `nota.estado='PROCESADO'; save()` → bloqueado; `nota.motivo_anulacion='y'; save(update_fields=['motivo_anulacion'])` → bloqueado (Gherkin EST02-04). 3) `test_resave_idempotente_ok_y_update_fields_ajenos_bloqueados` — save() sin cambios pasa; `save(update_fields=['observaciones'])` con valor idéntico → bloqueado (Gherkin EST02-06). 4) `test_devolucion_fallida_rollback_limpio_sin_guard` — items con cantidad > pendiente → `ValueError` (NO `DocumentoInmutableError`); 0 NC tras rollback (RED net del §4).
- **GREEN**: kardex_guard §2 (sin conectar pre_save de NotaCredito) + excepción + dead code fuera.
- **VERIFICACIÓN**: `python manage.py test inventory.test_cases.test_inmutabilidad_documentos -v 2` → 4 OK; `python manage.py test inventory` → **516 OK, skipped=6** (512+4; 29 NC y reversos verdes); `makemigrations --check` → "No changes detected".
- **Dependencias**: cap. 4 (TASK-EST01-01..03). **Commit**: `feat(est02): pre_save/pre_delete de documentos con matriz; dead code nc.delete() eliminado`

#### TASK-EST02-02 — Detalles inmutables + devolución intacta
- **Objetivo**: REQ-EST02-03/04/10 — matriz vacía en los 3 Detalle*, deletes bloqueados, `cantidad_devuelta_acumulada` como property no-tocada.
- **Archivos**: `inventory/test_cases/test_inmutabilidad_documentos.py` (los receivers ya viven en kardex_guard del TASK-01).
- **RED** (`class TestDetallesInmutables(TestCase)`; setUp con venta + devolución vía `procesar_devolucion_venta`): 1) `test_detalle_precio_y_snapshot_bloqueados` — `detalle.precio_base=999; save()` → `DocumentoInmutableError`; `det_nc.precio_unitario_snapshot=1; save()` → ídem (Gherkin EST02-02). 2) `test_deletes_de_cabecera_y_detalles_bloqueados` — `nota.detalles.all().delete()` → `DocumentoInmutableError` y persisten; `nota.delete()`, `nc.delete()` y `NotaEntrega.objects.all().delete()` bulk → ídem (Gherkin EST02-03; pre_delete por instancia en bulk/cascada, doc Django §1.4.1). 3) `test_resave_idempotente_detalle_nc_y_origen_intacto` — re-fetch `DetalleNotaCredito` → `save()` OK (derivados idénticos, Gherkin EST02-08); re-fetch `DetalleNotaEntrega` origen → `save()` OK (la devolución NO muta la fila; §1).
- **GREEN**: los 3 pasan sin tocar código (verifican el wiring del TASK-01 sobre los Detalle*).
- **VERIFICACIÓN**: `python manage.py test inventory` → **519 OK, skipped=6** (516+3); `makemigrations --check` limpio.
- **Dependencias**: TASK-EST02-01. **Commit**: `test(est02): detalles y deletes bloqueados; devolucion no muta la linea origen`

#### TASK-EST02-03 — Admin totalmente readonly
- **Objetivo**: REQ-EST02-08 — cerrar el vector "anular sin reversar stock" en /admin/.
- **Archivos**: `inventory/admin.py` (mixin §3 ~365; aplicarlo a 373/386/411; `DetalleNotaEntregaInline.can_delete=False` en 367), `inventory/test_cases/test_inmutabilidad_documentos.py`.
- **RED** (`class TestAdminDocumentosReadonly(TestCase)`): 1) `test_admins_documentos_permisos_readonly_totales` — para `NotaEntregaAdmin`/`DetalleNotaEntregaAdmin`/`DocumentoCompraAdmin` (vía `admin.site._registry`, request de superuser con RequestFactory): `has_add/change/delete_permission` → False, `has_view_permission` → True; `DetalleNotaEntregaInline.can_delete is False`; `get_readonly_fields(request, obj)` == todos los concrete fields. 2) `test_admin_post_no_anula_sin_reversar_stock` — superuser `client.post(/admin/inventory/notaentrega/{pk}/change/, {estado:'ANULADO'})` → fila sigue PROCESADO y stock intacto (Gherkin EST02-10).
- **GREEN**: mixin + aplicación (§3). Los ModelAdmin de NE traen `fields`/`search_fields` intactos — solo cambian permisos y readonly.
- **VERIFICACIÓN**: `python manage.py test inventory` → **521 OK, skipped=6** (519+2); `makemigrations --check` limpio; smoke manual: changelist NE accesible, sin botones Agregar/Eliminar, detalle 200 readonly.
- **Dependencias**: TASK-EST02-01. **Commit**: `feat(est02): admin de documentos emitidos totalmente readonly (mixin)`

#### TASK-EST02-04 — Refactor pre-create NC + conexión pre_save de NotaCredito + ADR
- **Objetivo**: REQ-EST02-06/07 cierre — NC nace con `monto_total_reembolso` definitivo; guard completo en los 6 modelos; riesgo residual fase 2 en ADR.
- **Archivos**: `inventory/calculos.py` (`calcular_linea_devolucion` NUEVA), `inventory/models.py` (`DetalleNotaCredito.save()` delega, 2207-2221), `inventory/services.py` (doble pasada + eliminar tails 2630-2631/2790-2791, §5), `inventory/kardex_guard.py` (conectar `pre_save` de `NotaCredito`), `docs/ADR.md` (matriz de inmutabilidad + `.update()`/bulk diferido + admin readonly + NC pre-create), `inventory/test_cases/test_inmutabilidad_documentos.py`.
- **RED** (`class TestNotaCreditoPreCreate(TestCase)`): 1) `test_nc_nace_con_monto_definitivo_sin_segundo_save` — venta 2 items (uno con `precio_unitario`+`iva_porcentaje` override) → `nc.monto_total_reembolso` == Σ esperada == `Σ detalles.linea_total_usd`; compra 1 item ídem; gate de fuente (patrón test_calculos.py:264): `inspect.getsource` de ambos services SIN `nc.save(` posterior al create y SIN `nc.delete()`; re-fetch NC → `save()` sin cambios OK (pre_save ya conectado). RED net: los 29 tests NC existentes (7313/7792) deben quedar VERDES sin edición.
- **GREEN**: doble pasada + helper compartido + conexión del sender NC (§5).
- **VERIFICACIÓN**: `python manage.py test inventory` → **522 OK, skipped=6** (521+1, acumulada final del capítulo); `makemigrations --check` limpio; `python manage.py test inventory.tests.TestNotasCreditoBackend inventory.tests.TestNotasCreditoUI` → 29 OK.
- **Dependencias**: TASK-EST02-01..03. **Commit**: `refactor(est02): NC pre-create con monto definitivo; pre_save NC conectado; ADR matriz y fase 2 diferida`

## 5. Reglas de integración por fix

Regla de integración de la spec §7.2 (verificabilidad inmediata):

1. **Cada fix termina con `python manage.py test inventory` verde y `python manage.py makemigrations --check` limpio.**
2. **Ningún fix se mezcla en la rama con tests rojos.**

Cierre esperado de cada fix contra la secuencia normalizada de §2:

| Fix | Cierre del fix (suite + `makemigrations --check`) | Migraciones |
|---|---|---|
| EST-06 | 488 OK, skipped=6 · `--check` limpio (la última migración sigue siendo `0028`) | 0 |
| CSP nonces | 494 OK, skipped=6 · `manage.py check` (E026) · `--check` limpio | 0 |
| EST-04 | 501 OK, skipped=6 · `--check` limpio · `showmigrations` con `[X] 0029` | `0029_usuario_fk_kardex_nc` |
| EST-05 | 504 OK, skipped=6 · `--check` limpio · `showmigrations` con `[X] 0029`, `[X] 0030` | `0030` (AuditoriaTasa) |
| EST-01 | 512 OK, skipped=6 · `--check` limpio (0 migraciones) | 0 |
| EST-02 | 522 OK, skipped=6 · `--check` limpio (0 migraciones) | 0 |

## Gate G2: Aprobación Requerida

> **⚠️ ESTE PLAN REQUIERE APROBACIÓN EXPLÍCITA ANTES DE IMPLEMENTAR** las 16 tareas de la tabla global (§3).
>
> - **Número de tareas:** **16** — EST-06: 2 · CSP: 3 · EST-04: 3 · EST-05: 1 · EST-01: 3 · EST-02: 4
> - **Suite final esperada:** **522 tests OK, skipped=6** (485 base + 37 nuevos)
> - **Migraciones nuevas:** `0029_usuario_fk_kardex_nc` (EST-04) y `0030` AuditoriaTasa (EST-05) — ningún otro fix añade migraciones
> - **Horas estimadas (spec §7.1):** **25-36 h** + **2 h** del anexo EST-05
>
> Una vez revisado, responda con **"APROBADO"** (o indique los cambios).
