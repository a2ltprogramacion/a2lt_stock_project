# Plan de Estabilización y Crecimiento — A2LT Stock

**Fecha:** 2026-07-10  
**Aprobado por:** Ing. Angel Argenis León Torres (A2LT Soluciones)

## Visión general

A2LT Stock es un sistema on-premise de control de inventario 
multi-tenant inspirado en Profit Plus 2K, dirigido al mercado 
venezolano. Sus directives no negociables:

- **Sin PostgreSQL** (on-premise en Venezuela con SQLite WAL+BK).
- **Sin Celery/Redis/JWT/DRF** — frontend monolítico Django + Tailwind CDN.
- **Sin migrar `Articulo.sku` PK** (CharField PK).
- **No dividir `services.py`** antes de estabilizar.

## Etapas

### Etapa A — Estabilización (PRIORIDAD CRÍTICA)

**Objetivo:** eliminar riesgos topológicos (código muerto, bugs críticos, 
 CSRF faltante, multi-tenant incompleto) antes de añadir features.

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| A1-A3 | Eliminación de código muerto | `88746dc`, `5296279`, `710f710` | ✅ |
| A4 | Bug ANULADO/ANULADA + tests | `76490a5` | ✅ |
| A5 | Bug MARKUP/MARGIN respetado | `06a038f` | ✅ |
| A6 | `base.html` getCookie + block JS | `dc699a6` | ✅ |
| A7-A9 | `@csrf_exempt` removido (3 vistas) | `4db49f0`, `596a691` | ✅ |
| A10-A12 | Compras/ventas/combos multi-tenant | `9adb793`, `c637495`, `29a09ec` | ✅ |
| A13-A15 | Compras → kardex, imprimir nota, kardex manual | `31739ef`, `00ecc00`, `d6bdaac` | ✅ |
| A16 | `settings.py` hardening + WAL PRAGMA | `f52afea` | ✅ |
| Setup | `.env` cargador stdlib | `d71a6c3` | ✅ |

### Etapa B — Seguridad Multi-Tenant

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| B-1 | Tests migrados a `self.client.login()` | `e2dd562` | ✅ |
| B-2/B-7 | `TenantMiddleware._authorize()` 5 condiciones | `78ef1e7` | ✅ |
| B-3 | `@login_required` defense-in-depth (16 vistas) | `42992e8` | ✅ |

### Fase 3 — Multimoneda y Snapshots Inmutables

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| 3.1 | Modelos `Moneda`, `TasaCambio` + signal siembra USD/VES | `f46b194` | ✅ |
| 3.2 | Snapshot en `DocumentoCompra` (tasa_bcv, factor, etc.) | `f46b194` | ✅ |
| 3.3 | Tests C14/C15 inmutabilidad | `f46b194` | ✅ |

### Fase 4 — Reportes y KPIs Live

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| 4.1-4.8 | 8 reportes (kardex, inventario, ventas, CxC, CxP, top, obsoletos, estado) || ✅ |
| 4.exp | Exporters CSV (BOM) + PDF (reportlab A4 landscape) || ✅ |
| 4.vistas | `vista_reportes` + `vista_reporte_detalle` unificadas || ✅ |
| 4.dash | Dashboard KPIs live (combos, sync real, conteo notas) | `cc5b475` | ✅ |
| 4.tests | Tests C16 (reportes + vistas) + C17 (dashboard) || ✅ |

### Fase 5 — Refactor Estructural services.py

**Decisión ADR-21:** mantener `services.py` como módulo único (2085+ 
líneas), agregar índice de secciones, NO partir en submódulos.

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| 5.1 | Índice de secciones en header | `5d5e45f` | ✅ |
| 5.2 | Tests API surface (17 funciones) | `5d5e45f` | ✅ |

### Fase 6 — Operación: Backup Automático

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| 6.1 | `backup_db` management command (VACUUM INTO) | `71a215b` | ✅ |
| 6.2 | `--retention N` borra backups viejos | `71a215b` | ✅ |
| 6.3 | `--check` dry-run | `71a215b` | ✅ |
| 6.4 | Tests C19 (3 tests) | `71a215b` | ✅ |

### Etapa F — Documentación

| Sub | Descripción | Estado |
|-----|-------------|--------|
| F1 | `docs/AUDITORIA_INICIAL.md` | ✅ |
| F2 | `docs/PLAN.md` (este archivo) | ✅ |
| F3 | `docs/ROADMAP.md` (próximas features) | ✅ |
| F4 | `docs/OPERACION.md` (instalación + troubleshooting) | ✅ |
| F5 | `README.md` raíz | ✅ |
| F6 | `requirements.txt` actualizado | ✅ |

## Reglas de calidad

1. **Toda feature o bugfix debe pasar 157+ tests** antes de commit.
2. **Ningún commit toca `migrations/` sin identificarse** qué 
   migración → `manage.py makemigrations --name-ticket`.
3. **`services.py` es la única vía para modificar stock**. 
   Modificar `InventarioAlmacen.cantidad_disponible` fuera de 
   `services.registrar_movimiento()` se considera bug crítico.
4. **Todo movimiento de kardex graba snapshot** de tasas y precios 
   (`costo_unitario_snapshot`, `tasa_bcv_aplicada`, etc.) — los 
   reportes históricos deben ser inmutables incluso si la config 
   global cambia posteriormente.
5. **`ContextVar.get_current_empresa()` es la única forma** de 
   resolver el tenant activo; nunca `Empresa.objects.first()` ni 
   `request.empresa`.
6. **`@login_required` + `TenantMiddleware`** actúan en paralelo: 
   middleware corta con 403 si no hay sesión válida; `@login_required` 
   redirige a /login/ con 302 si no hay usuario.

## Matriz de tests (C1-C19)

| Cód | Etapa | Cobertura | Tests |
|---|---|---|---|
| C1 | A4 | Reverso idempotente NotaEntrega | 1 |
| C2 | A5 | `metodo_ganancia` (MARKUP/MARGIN) | 2 |
| C3 | A6 | `base.html` getCookie + block extra_js | 2 |
| C4 | A7 | `articulos_view` multi-tenant + CSRF | 2 |
| C5 | A8 | `contactos` + respaldo multi-tenant | 2 |
| C6 | A9 | `vista_crear_venta` sin @csrf_exempt | 2 |
| C7 | A10 | `registrar_compra_proveedor` multi-tenant | 2 |
| C8 | A11 | `procesar_venta` valida almacen por empresa | 2 |
| C9 | A12 | `calcular_stock_combo` Decimal floor | 1 |
| C10 | A13 | Compras usa `/catalogo/buscar/` | 2 |
| C11 | A14 | Ventas ofrece imprimir nota | 1 |
| C12 | A15 | Kardex manual endpoint | 2 |
| C13 | A16 | `settings.py` hardening | 2 |
| C14 | B-2 | TenantMiddleware 5 condiciones | 7 |
| C15 | Fase 3 | Snapshot inmutable Moneda/TasaCambio | 5 |
| C16 | Fase 4 | 8 reportes + vistas + exporters | 21 |
| C17 | Fase 4 | Dashboard KPIs live | 4 |
| C18 | Fase 5 | API surface services.py | 2 |
| C19 | Fase 6 | backup_db VACUUM INTO | 3 |

Otras suites sin código C: TestMovimientosBasicos, 
TestRollbackAtomicidad (ADR-08), TestVentaExitosa, 
TestCoberturaCritica (reversos notificados, correlativo por empresa).

## Documentos relacionados

- `docs/AUDITORIA_INICIAL.md` — hallazgos previos a la Fase A.
- `docs/ARQUITECTURA.md` — diagrama, multi-tenant, regla sagrada 
  kardex, snapshots, mapa de services, migraciones, tests.
- `docs/ADR.md` — 16 ADRs formales (01-22 con saltos).
- `docs/ROADMAP.md` — features post-100% (cuentas por cobrar/pagar, 
  factura electrónica Seniat, bitácora de auditoría).
- `docs/OPERACION.md` — guía de instalación detallada, módulos, 
  troubleshooting y reglas operativas.
- `CHANGELOG.md` (raíz) — versión + cambios notables por release.
- `README.md` (raíz) — instalación rápida + features + reglas.
