# Auditoría Independiente — A2LT Stock

- **Proyecto:** a2lt_stock_project (Django multi-tenant, inventario/stock)
- **Fecha:** 2026-08-22
- **Auditor:** Auditor de software (revisión de funcionalidad, seguridad y calidad)
- **Alcance:** Revisión del código actual en `Y:\Proyectos\a2lt_stock_project`, contrastado contra la auditoría previa `docs/auditoria_a2lt_stock.md` (2026-07-15). Esta auditoría **verifica el estado real del código**, no asume ciertos los puntos del informe anterior.
- **Entregable:** Informe de hallazgos + plan de remediación (sin modificaciones de código en esta fase).

---

## 1. Veredicto general

La base del sistema es **sólida**. Tres pilares están bien implementados:

1. **Aislamiento multi-tenant** — Los modelos críticos (`NotaEntrega`, `NotaCredito`, `SerialArticulo`, `Articulo`, …) usan `EmpresaManager` como `.objects`, que auto-filtra por el `ContextVar` `current_empresa` del tenant activo (ver `inventory/managers.py:46-51`). Una lectura `get_object_or_404(Model.objects, pk=...)` ya está acotada al tenant.
2. **Atomicidad del Kárdex/Kárdex** — Las operaciones transaccionales están envueltas en `@transaction.atomic` con `select_for_update()` adecuado (ver `services.py:2176`, `2210`, `2310`).
3. **Snapshots financieros inmutables** — Los totales Bs/USD y el IVA se guardan como snapshot en cada documento, de modo que cambios posteriores en `Articulo` no alteran documentos ya emitidos.

Esto contradice la auditoría previa en sus puntos más alarmantes (ver sección 3).

---

## 2. Metodología

- Exploración de estructura (`glob` de `.py/.md/.env`) + lectura directa de archivos clave: `settings.py`, `middleware.py`, `managers.py`, `models.py`, `services.py`, `views.py`, `reports.py`, `.env`, `urls.py`.
- Verificación de reclamos de la auditoría previa contra el código actual (no se confió ciegamente en ella).
- Revisión de aislamiento multi-tenant en rutas de lectura **y** de escritura, control de errores, validación de entradas y consistencia de cálculos financieros.

---

## 3. Correcciones a la auditoría previa (false positives)

La auditoría de julio afirmó escapes multi-tenant / IDOR graves. **No son ciertos en el código actual**:

| ID previo | Afirmación | Estado | Evidencia |
|---|---|---|---|
| S-05 | IDOR en `nota_id` (lectura cross-tenant) | ❌ Falso | `NotaEntrega.objects` es `EmpresaManager`; `vista_imprimir_coordenadas` (`views.py:1403`) y `vista_imprimir_nota` (`views.py:728`) quedan acotadas al tenant. |
| S-08 | Fuga en endpoint de seriales | ❌ Falso | `SerialArticulo.objects = EmpresaManager()` (`models.py:1716`); el filtro de tenant aplica aunque se pase `almacen_id` externo. |
| S-09 | `db.sqlite3` commiteado | ❌ Falso | El archivo **está** en `.gitignore:5` y **no** está trackeado (`git ls-files db.sqlite3` vacío). |
| X-02 | Sin paginación en movimientos | ❌ Falso | `vista_movimientos` usa `Paginator` (`views.py:1188`). |

Además, las rutas de **escritura** cruzan el `empresa_id` del body contra el de sesión:
- `procesar_venta` (`services.py:1202-1215`)
- `registrar_compra_proveedor` (`services.py:1844-1857`)

Ambas abortan con `ValueError` si difieren → **no hay inyección cross-tenant por `empresa_id`**. Lo mismo en reversos/devoluciones (`reversar_nota_entrega` `services.py:2176`, `reversar_documento_compra` `2210`, `procesar_devolucion_venta` `2310`), que filtran por `(pk, empresa_id)`.

---

## 4. Hallazgos reales (priorizados)

### [ALTA] SSRF en sincronización de tasa de cambio
- **Dónde:** `configuracion_view` guarda `config.api_url = request.POST.get('api_url')` sin validación (`views.py:1589`). `sincronizar_tasa_cambio` ejecuta `requests.request(url=config.api_url, ...)` (`services.py:1497`) y `requests` **sigue redirects por defecto**.
- **Impacto:** Cualquier usuario autenticado (no hay chequeo de rol en `configuracion_view`, solo `@login_required`) puede apuntar `api_url` a `http://169.254.169.254/...`, `http://localhost:...`, o IPs internas → lectura de metadata cloud / servicios internos (SSRF).
- **Fix simple:** Validar la URL al guardar (esquema `http/https`; resolver el host y bloquear rangos `127.0.0.0/8`, `10/8`, `172.16/12`, `192.168/16`, `169.254.0.0/16`, `::1`); y pasar `allow_redirects=False` en la petición.

### [ALTA] Inconsistencia en total Bs entre pantalla y PDF (bug de corrección financiera)
- **Dónde:**
  - `vista_detalle_nota` (`views.py:767`) calcula `total_bs = Σ(cantidad × precio_ajustado_bcv)` → **incluye** `factor_cobertura` (`precio_ajustado_bcv = precio_base × factor_cobertura × tasa_bcv`).
  - `generar_pdf_nota` (`views.py:889-898`) calcula `total_bs = subtotal_usd_neto × tasa_bcv_aplicada` usando `precio_base` → **omite** `factor_cobertura`.
- **Impacto:** Cuando `factor_cobertura != 1` (el caso de uso central del sistema), el total impreso en Bs **discrepa** del mostrado en pantalla. Peor aún: en el PDF, el subtotal no aplica el factor pero `d.iva_bs` sí (porque deriva de `precio_ajustado_bcv`) → inconsistencia interna dentro del propio PDF. `vista_imprimir_nota`/`imprimir_coordenadas` usan `precio_ajustado_bcv` (correcto).
- **Fix simple:** Usar las propiedades del modelo (`subtotal_bs`, `total_iva_bs`, `total_documento_bs`) o `precio_ajustado_bcv` en el PDF, en vez de reconstruir la fórmula. *(Nota: verificar patrón análogo en `generar_pdf_compra`.)*

### [MEDIA] Exposición de excepciones al cliente (`str(e)`)
- **Dónde:** `registrar_compra_api` (`views.py:1962`), `api_crear_nc` (`views.py:2332`), `api_reversar_venta`/`api_reversar_compra` (`views.py:2007`/`2027`) devuelven `str(e)` en 500/400.
- **Impacto:** Con `DEBUG=True` (el `.env` actual) vuelca trazas/tablas al cliente; aun con `DEBUG=False`, filtrar `str(e)` de excepciones genéricas puede filtrar datos internos.
- **Fix simple:** `logger.exception(...)` + devolver mensaje genérico en los `except Exception`; conservar `str(e)` solo en `ValueError` de negocio (mensajes user-friendly).

### [MEDIA] Sin rate-limiting en login
- **Dónde:** `login_view` (`views.py:33`) — fuerza bruta ilimitada.
- **Fix simple:** `django-axes` (5 intentos / 1h) o, si se prefiere ligero, un decorador que bloquee por IP+username tras N fallos.

### [BAJA] `configuracion_view` frágil a `ContextVar=None`
- **Dónde:** `views.py:1566` hace `config = ConfiguracionEmpresa.objects.first()` y luego `config.tasa_bcv` sin None-check.
- **Impacto:** Hoy lo protege el middleware, pero es frágil si se reusa la vista.
- **Fix:** `config = get_object_or_404(ConfiguracionEmpresa, empresa_id=empresa_id)`.

### [BAJA] Logout por GET
- **Dónde:** `logout_view` (`views.py:72`) acepta GET.
- **Impacto:** CSRF de disponibilidad (un `<img>` cierra sesión).
- **Fix:** `@require_POST` + form en el sidebar.

### [BAJA] Lógica financiera duplicada (A-05)
- **Dónde:** Totales recalculados a mano en `vista_detalle_nota`, `generar_pdf_nota`, `vista_detalle_compra`, `generar_pdf_compra` con fórmulas que **ya divergieron** (ver ALTA arriba).
- **Fix:** Usar las propiedades del modelo en todas las vistas/PDF y eliminar la reconstrucción manual.

---

## 5. Notas de arquitectura (baja prioridad)

- **God-files**: `services.py` (~2633 líneas) y `views.py` (~2469) son grandes. Riesgo real **bajo**; el ADR-21 los mantiene intactos hasta justificación funcional. No refactorizar por purismo.
- **Imports diferidos** masivos (`from .models import ...` dentro de funciones): ruido menor, no urgente.

---

## 6. Plan de remediación por fases

| Fase | Alcance | Hallazgos |
|---|---|---|
| **F1 — Alta** | SSRF (validar `api_url` + `allow_redirects=False`); unificar cálculo de totales Bs pantalla/PDF usando propiedades del modelo. | ALTA ×2 |
| **F2 — Media** | Centralizar manejo de errores (`str(e)` → `logger.exception` + mensaje genérico); rate-limiting en login. | MEDIA ×2 |
| **F3 — Baja** | `get_object_or_404` en configuración; `@require_POST` en logout; dedup de lógica financiera. | BAJA ×3 |

**Criterio de aceptación:** tras F1, un atacante autenticado no puede alcanzar servicios internos vía `api_url`, y el total Bs del PDF coincide con el de pantalla para `factor_cobertura != 1`.

---

## 7. Estado de remediación (2026-08-22)

| Fase | Estado | Cambios |
|---|---|---|
| **F1 — Alta** | ✅ Implementada y verificada | `inventory/services.py`: `es_url_api_segura()` (bloquea esquemas no http/https y rangos privados/loopback/link-local, incl. `169.254.169.254`) + `allow_redirects=False` en `sincronizar_tasa_cambio`. `inventory/views.py`: validación de `api_url` al guardar en `configuracion_view`; total Bs del PDF unificado con `precio_ajustado_bcv` (coherente con pantalla). Tests: `TestValidacionUrlApiSegura`. Suite: 313 OK. |
| **F2 — Media** | ✅ Implementada y verificada | `inventory/views.py`: throttle de login por IP vía `LocMemCache` (5 intentos / 5 min, bloqueo 15 min, respeta `X-Forwarded-For`); `except Exception` en `registrar_compra_api`, `api_reversar_venta`, `api_reversar_compra`, `api_crear_nc` → `logger.exception` + mensaje genérico (sin `str(e)` al cliente); logging en `configuracion_view`. Tests: `TestThrottleLogin`. |
| **F3 — Baja** | ✅ Implementada y verificada | `inventory/views.py`: `configuracion_view` ahora resuelve `get_current_empresa()` y hace `get_or_create(empresa_id=...)` (elimina fragilidad a `ContextVar=None`); `logout_view` con `@require_POST` + formulario POST con CSRF en `base.html` (cierra vector CSRF de logout por GET); `generar_pdf_compra` usa propiedades del modelo (`documento.subtotal_usd`, `documento.total_iva_bs`, `d.subtotal_usd`) en vez de reconstruir fórmulas. Suite: 315 OK. |

---

*Fin del informe. Los archivos revisados incluyen `a2lt_stock_project/settings.py`, `inventory/middleware.py`, `inventory/managers.py`, `inventory/models.py`, `inventory/services.py`, `inventory/views.py`, `inventory/reports.py`, `urls.py` y `.env`.*
