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

### Etapa N — Emisión de Notas de Entrega / Facturas

**Decisión ADR-23:** `procesar_venta` se extiende con `tipo_documento` 
(`NOTA_ENTREGA` | `FACTURA`) y `numero_factura` único por empresa, 
manteniendo el snapshot inmutable de `DetalleNotaEntrega`.

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| N1 | Modelos — NotaEntrega/DetalleNotaEntrega con 4 precios snapshot + IVA + descuento | `66e3aba` | ✅ |
| N1 | ConfiguracionEmpresa: `prefijo_nota_entrega` + `correlativo_inicial_nota` + `ivas_disponibles` | `66e3aba` | ✅ |
| N2 | `procesar_venta` ampliado con tipo_documento + iva + descuento_global | `712ba8c` | ✅ |
| N2 | 17 tests nuevos (TestModelos NE N1 + TestProcesarVenta N2) | `712ba8c` | ✅ |
| N3 | Template `ventas.html` con radio NOTA_ENTREGA/FACTURA + descuento_global | `712ba8c` | ✅ |
| N4 | Interlock UI: button `confirm-sale-btn` disabled si FACTURA sin `numero_factura` | `712ba8c` | ✅ |
| N5 | `vista_detalle_nota` + `generar_pdf_nota` (reportlab A4) + URLs `/ventas/<id>/`, `/ventas/<id>/pdf/` | `712ba8c` | ✅ |
| N5 | Template `nota_detalle.html` con bloque de totales + bloque de descuento condicional | `712ba8c` | ✅ |

### Etapa C — Módulo de Compras a Proveedores

**Decisión ADR-24:** snapshots de 4 precios + IVA + descuento + seriales 
en `DetalleDocumentoCompra`, con `registrar_compra_proveedor` validando 
FKs multi-tenant y `reversar_documento_compra` con contramovimiento 
auditado.

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| C1 | Modelos — DocumentoCompra + DetalleDocumentoCompra + manager + signal correlativo | `08e8ada` | ✅ |
| C1 | Service `registrar_compra_proveedor` con 4 snapshots + IVA + descuento + seriales | `08e8ada` | ✅ |
| C3 | Template `compras.html` con UI completa + `escapeHtml()` | `487a525` | ✅ |
| C3 | `vista_detalle_compra` + `generar_pdf_compra` (reportlab) + URLs `/compras/<id>/`, `/compras/<id>/pdf/` | `487a525` | ✅ |
| C3 | Template `compra_detalle.html` con bloque de totales + descuento condicional | `487a525` | ✅ |

### Etapa F — Auditoría Ventas/Compras (Seguridad + UX)

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| C1 | Bug `Max('id')` → `Max('numero')` DocumentoCompra eliminado | `c470093` | ✅ |
| C2 | 4 vistas detalle/PDF filtran por `empresa_id=session['empresa_id']` | `c470093` | ✅ |
| C3 | `escapeHtml()` JS + 26 sinks de innerHTML escapados | `c470093` | ✅ |
| C4 | Tag roto `<h-sm">` eliminado de `nota_detalle.html` | `c470093` | ✅ |
| M1 | `descuento_global` aplicado en totales de 4 vistas/PDFs | `c470093` | ✅ |
| M2 | Labels "IVA (16%)" → "IVA:" | `c470093` | ✅ |
| M5 | `confirm-*-btn` disable+spinner+restore durante fetch | `c470093` | ✅ |
| M7 | Variable muerta `iva_total_bs` eliminada | `c470093` | ✅ |
| M8 | `total_bs_neto` alineado en vista_detalle_nota/compra | `c470093` | ✅ |
| B1 | Código muerto eliminado + balance HTML | `c470093` | ✅ |
| B4 | `if (!r.ok)` guard + `.catch()` mejorado en processSale/Purchase | `c470093` | ✅ |

### Etapa FA — Fichas de Artículos (Tokens de Precio + Toolbar)

**Decisión ADR-25:** 4 variables dinámicas para redactar mensajes de 
mercadeo en `social_quick` y `social_cross` sin reescribir al cambiar 
precios/tasas.

| Sub | Descripción | Commit | Estado |
|-----|-------------|--------|---------|
| FA1 | Backend: cálculo de `precio_bs_base = precio_divisa × tasa_bcv` (sin factor) en `vista_catalogo` | `c470093` | ✅ |
| FA2 | `catalogo.html`: atributo `data-precio-bs-base` en tarjeta + 7 botones + sustitución del 4to token | `c470093` | ✅ |
| FA3 | `articulos.html`: toolbar con 4 botones (USD/BCV/Bs.Base/Bs.Ajust.) sobre form-p-cross y form-p-quick | `c470093` | ✅ |
| FA3 | Función JS `injectToken()` con caret tracking (sobrescribe selección, restaura foco, no envía al servidor) | `c470093` | ✅ |
| FA4 | 21 tests nuevos (4 clases) — de 213 a 234 tests | `c470093` | ✅ |

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

1. **Toda feature o bugfix debe pasar 234+ tests** antes de commit 
   (157 en 1.0.0 + 56 añadidos en 1.1.0: 17 Emisión NE + 18 Compras + 
   21 Fichas).
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
7. **Toda vista detalle/PDF de documento** (`vista_detalle_nota`, 
   `generar_pdf_nota`, `vista_detalle_compra`, `generar_pdf_compra`) 
   debe filtrar por `empresa_id=request.session.get('empresa_id')` 
   en el `get_object_or_404` (regla C2 — anti-leak multi-tenant).
8. **Los tokens `$[PRECIO_USD]`, `$[PRECIO_BCV]`, `$[PRECIO_BS_BASE]`, 
   `$[PRECIO_BS]`** se persisten como texto literal en `social_quick` 
   y `social_cross`. La sustitución ocurre solo al mostrar/copiar el 
   mensaje en `catalogo.html`. La toolbar de `articulos.html` 
   (**NO** envía datos al servidor).

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
| C20 | Etapa N1-N2 | Modelos + servicio Emisión NE/Factura (4 precios, IVA, descuento) | 17 |
| C21 | Etapa N3-N5 | Template ventas + interlock UI + vista detalle + PDF | 6 |
| C22 | Etapa C | Módulo Compras: vistas detalle/PDF + templates (TestRegistrarCompraProveedor + snapshot + multi-tenant) | 18 |
| C23 | Etapa FA | Fichas Artículos: 4 precios cuádruple + 4to token + toolbar + JS injectToken | 21 |

Otras suites sin código C: TestMovimientosBasicos, 
TestRollbackAtomicidad (ADR-08), TestVentaExitosa, 
TestCoberturaCritica (reversos notificados, correlativo por empresa), 
TestProcesarVentaN2/N3/N4/N5, TestInterlockFacturaN4, 
TestNotaEntregaFaseN5. **Suite total: 234 tests verdes en ~151s.**

## Documentos relacionados

- `docs/AUDITORIA_INICIAL.md` — hallazgos previos a la Fase A.
- `docs/ARQUITECTURA.md` — diagrama, multi-tenant, regla sagrada 
  kardex, snapshots, mapa de services, migraciones, tests.
- `docs/ADR.md` — 20 ADRs formales (01-26 con saltos; ADR-23 a ADR-26 
  añadidos en 1.1.0 para Emisión NE/Factura, snapshots 4 precios, 
  tokens de precio y toolbar caret tracking).
- `docs/ROADMAP.md` — features post-100% (cuentas por cobrar/pagar, 
  factura electrónica Seniat, bitácora de auditoría).
- `docs/OPERACION.md` — guía de instalación detallada, módulos, 
  troubleshooting y reglas operativas.
- `CHANGELOG.md` (raíz) — versión + cambios notables por release.
- `README.md` (raíz) — instalación rápida + features + reglas.
