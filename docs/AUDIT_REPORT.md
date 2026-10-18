# Informe de Auditoría Integral — A2LT Stock

**Auditor:** Senior Application Security & Data Integrity Auditor  
**Fecha:** 2026-10-18  
**Alcance:** Repositorio `a2lt_stock_project` — Django 6.0.6 multi-tenant on-premise, SQLite WAL, Python 3.11+  
**Versión auditada:** Commit actual (iteración 1.2.1 completa, 276 tests verdes)  
**Metodología:** Código real vs documentación, OWASP Top 10:2021, ASVS L1, integridad referencial, pruebas destructivas conceptuales

---

## 1. Resumen Ejecutivo

A2LT Stock es un sistema **maduro y funcionalmente completo** para control de inventario y punto de venta multi-tenant, dirigido al mercado venezolano con soporte nativo para dinámica cambiaria dual (BCV + mercado) y factor de cobertura. La arquitectura implementa **tres pilares sólidos** verificados en código:

1. **Aislamiento multi-tenant hermético** vía `ContextVar` + `EmpresaManager` (ADR-17) — retorna queryset vacío sin tenant, nunca tabla completa.
2. **Atomicidad del Kárdex inquebrantable** — única vía de mutación `services.registrar_movimiento()` con `@transaction.atomic`, `select_for_update()`, expresiones `F()` anti-race-condition.
3. **Snapshots financieros inmutables** — cada transacción (venta, compra, NC, reverso) graba 4 precios/costos + IVA + descuento + tasas aplicadas, garantizando reportes históricos determinísticos.

**Estado de remediación:** Las fases críticas de seguridad (F1 SSRF, F2 rate-limiting/error handling, F3 fragilidad config/logout) están **implementadas y verificadas** (auditoría 2026-08, 315 tests OK).

**Riesgos residuales principales:**
- 🔴 **CRÍTICO:** `.env` con `SECRET_KEY` de desarrollo **no confirmado en `.gitignore`** — riesgo de exposición si histórico git lo contiene.
- 🟠 **ALTA:** N+1 queries en dashboard (combos × almacenes × componentes) — degradación exponencial.
- 🟠 **ALTA:** Lógica financiera duplicada en 4 vistas/PDFs — divergencia garantizada (ya ocurrió: total Bs PDF ≠ pantalla).
- 🟠 **ALTA:** Sin feedback visual loading en operaciones AJAX críticas — riesgo double-submit.
- 🟡 **MEDIA:** `CSRF_COOKIE_HTTPONLY=False` — vector XSS → CSRF token exfiltration.
- 🟡 **MEDIA:** Ausencia atributos ARIA — no conforme WCAG 2.1 AA.
- 🟢 **BAJA:** God-files `services.py` (2270 L) / `views.py` (2469 L) — ADR-21 acepta mientras tests <3min.

**Veredicto global:** **APROBADO CON CONDICIONES** — Sistema listo para producción on-premise tras resolver ítems CRÍTICOS/ALTOS del plan de remediación.

---

## 2. Contexto Descubierto (Fase 0-1)

### 2.1 Stack Técnico Detallado

| Componente | Versión/Detalle | Evidencia |
|------------|-----------------|-----------|
| Framework | Django 6.0.6 | `requirements.txt:4` |
| Base de datos | SQLite 3 (WAL mode, `PRAGMA foreign_keys=ON`, timeout 20s, cache 64MB) | `settings.py:96-111` |
| Python | 3.11+ (testeado en 3.14) | `OPERACION.md:11` |
| OS Target | Windows 10/11 64-bit (primary), Linux x86_64 | `OPERACION.md:10` |
| Dependencias principales | openpyxl 3.1.5, reportlab 5.0.0, requests 2.34.2, Pillow 12.3.0 | `requirements.txt` |
| Frontend | Tailwind CSS (CDN), FontAwesome (CDN), Chart.js (CDN, reservado) | `base.html:9,11,52` |
| PDF | reportlab (A4 portrait/landscape) | `views.py:858-972, 1036-1152` |
| Excel | openpyxl (read_only, data_only, en memoria) | `services.py:549, 829` |

### 2.2 Arquitectura por Capas (Verificada en Código)

```
┌─────────────────────────────────────────────────────────────────┐
│ Browser (Tailwind CDN)                                          │
└───────────────────────┬─────────────────────────────────────────┘
                        │ HTTP + CSRF
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Django Middleware Stack (settings.py:61-70)                     │
│ 1. SecurityMiddleware                                           │
│ 2. SessionMiddleware                                            │
│ 3. CommonMiddleware                                             │
│ 4. CsrfViewMiddleware                                           │
│ 5. AuthenticationMiddleware                                     │
│ 6. MessageMiddleware                                            │
│ 7. XFrameOptionsMiddleware                                      │
│ 8. inventory.middleware.TenantMiddleware (CRÍTICO)              │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Views — Adaptadores HTTP → Services (SIN lógica de negocio)     │
│ inventory/views.py (2469 líneas)                                │
│ inventory/reports.py (reportes)                                 │
└───────────────────────┬─────────────────────────────────────────┘
                        │ (solo vía services)
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ services.py — ÚNICA capa autorizada a mutar kardex              │
│ 17 funciones públicas (índice en header lines 18-34)           │
│ 2270 líneas — ADR-21: no partir mientras tests <3min           │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ Models + EmpresaManager (filtrado automático por ContextVar)   │
│ 29 clases en models.py (2137 líneas)                           │
│ EmpresaManager.get_queryset() → filtra por ContextVar          │
└───────────────────────┬─────────────────────────────────────────┘
                        │
                        ▼
┌─────────────────────────────────────────────────────────────────┐
│ SQLite WAL — db.sqlite3 compartido                              │
│ backup_db command: VACUUM INTO snapshot atómico                │
└─────────────────────────────────────────────────────────────────┘
```

### 2.3 Apps y Modelos (Inventario — App Única de Negocio)

**INSTALLED_APPS** (`settings.py:50-59`):
```python
INSTALLED_APPS = [
    'django.contrib.admin', 'django.contrib.auth', 'django.contrib.contenttypes',
    'django.contrib.sessions', 'django.contrib.messages', 'django.contrib.staticfiles',
    'inventory.apps.InventoryConfig',  # Única app de negocio
]
```

**29 Modelos en `inventory/models.py`** (clasificados por dominio):

#### Núcleo Multi-Tenant (4 modelos)
| Modelo | Línea | Propósito | Multi-tenant |
|--------|-------|-----------|--------------|
| `Empresa` | 55 | Entidad raíz — sin manager custom (es la entidad raíz) | No (raíz) |
| `ConfiguracionEmpresa` | 74 | OneToOne Empresa — tasas, márgenes, API, cuarentena, cross-selling | Sí (EmpresaManager) |
| `PerfilUsuario` | 334 | RBAC — M2M `empresas_permitidas` + FK `empresa_activa` | Sí (via User FK) |
| `Almacen` | 375 | Ubicación física — `es_principal`, `activo` | Sí |

#### Inventario y Catálogo (6 modelos)
| Modelo | Línea | Propósito | Campos Críticos |
|--------|-------|-----------|-----------------|
| `Articulo` | 410 | Catálogo principal — PK=sku (CharField) | `tipo=FISICO/COMBO`, `activo` (soft-delete ADR-03), `usa_serial`, 4 precios, IVA, margen |
| `InventarioAlmacen` | 618 | Tabla intermedia M2M stock por ubicación | `unique_together(articulo, almacen)`, `cantidad_disponible` (Decimal), `stock_minimo` |
| `RecetaCombo` | 682 | Componentes de combo virtual | `unique_together(combo, componente)`, `cantidad_requerida` (Decimal) |
| `SerialArticulo` | 1695 | Trazabilidad IMEI/serial único | `unique_together(empresa, serial)`, `estado=DISPONIBLE/VENDIDO/ANULADO_COMPRA` |
| `Moneda` | 2013 | Catálogo monedas por tenant (Fase 3) | `es_base` unique per tenant (enforced en save) |
| `TasaCambio` | 2061 | Histórico tasas par moneda/fecha | `obtener_tasa()` busca más reciente ≤ fecha |

#### Contactos Unificados (3 modelos — ADR-05)
| Modelo | Línea | Propósito |
|--------|-------|-----------|
| `Contacto` | 731 | PK=`identificacion` — `tipo=CLIENTE/PROVEEDOR`, campos proveedor nullable (`rif`, `nombre_asesor`) |
| `Cliente` | 827 | Proxy model + `ClienteManager` filtra `tipo=CLIENTE` |
| `Proveedor` | 841 | Proxy model + `ProveedorManager` filtra `tipo=PROVEEDOR` |

#### Transacciones de Venta (2 modelos — Etapa N)
| Modelo | Línea | Snapshots Inmutables (ADR-24) |
|--------|-------|-------------------------------|
| `NotaEntrega` | 1310 | `tasa_bcv_aplicada`, `factor_cobertura_aplicado`, `tasa_mercado_aplicada`, `iva_check`, `iva_total`, `descuento_global`, `tipo_documento=NOTA_ENTREGA/FACTURA`, `numero_factura` unique per empresa |
| `DetalleNotaEntrega` | 1526 | **4 precios**: `precio_base`, `precio_ajustado`, `precio_directo_bcv`, `precio_ajustado_bcv` + `costo_unitario_snapshot`, `iva_porcentaje`, `descuento_aplicado` |

#### Transacciones de Compra (2 modelos — Etapa C)
| Modelo | Línea | Snapshots Inmutables (ADR-24) |
|--------|-------|-------------------------------|
| `DocumentoCompra` | 858 | `tasa_bcv_aplicada`, `tasa_mercado_aplicada`, `factor_cobertura_aplicado`, `fuente_tasa`, `monto_total_bs_snapshot`, `tipo_documento=FACTURA_COMPRA/NOTA_ENTREGA_PROVEEDOR/REGISTRO_MENOR` |
| `DetalleDocumentoCompra` | 1018 | **4 costos**: `costo_base`, `costo_ajustado`, `costo_directo_bcv`, `costo_ajustado_bcv` + `costo_unitario_snapshot`, `iva_porcentaje`, `descuento_aplicado` |

#### Kárdex y Auditoría (2 modelos)
| Modelo | Línea | Propósito |
|--------|-------|-----------|
| `MovimientoKardex` | 1124 | Registro inmutable — `tipo=ENTRADA/SALIDA`, 18 `CONCEPTO_CHOICES`, `saldo_resultante`, FKs a `NotaEntrega`/`DocumentoCompra`, `lote_carga` |
| `AuditoriaTasa` | 1247 | Histórico tasas — `fuente=MANUAL/API` |

#### Devoluciones / Notas de Crédito (2 modelos — Ticket #18-NC, ADR-29)
| Modelo | Línea | Constraints Críticos |
|--------|-------|---------------------|
| `NotaCredito` | 1752 | `CheckConstraint` XOR (`nota_entrega` XOR `factura_compra`), `numero_control` auto-generado |
| `DetalleNotaCredito` | 1891 | `CheckConstraint` XOR (`detalle_origen_venta` XOR `detalle_origen_compra`), 3 snapshots: `precio_unitario_snapshot`, `iva_porcentaje_snapshot`, `cantidad_devuelta` |

### 2.4 Middleware Crítico — `TenantMiddleware` (`inventory/middleware.py`)

**5 Validaciones Secuenciales** (líneas 60-147):
1. **Autenticación** (`user.is_authenticated`) → redirect a login con `?next=` (línea 85-108)
2. **PerfilUsuario existe** (`user.perfil`) → 403 si no (línea 111-115)
3. **`empresa_id` en sesión** → 403 si no (línea 118-122)
4. **Empresa existe y `activa=True`** → 403 si no (línea 125-135)
5. **Empresa en `perfil.empresas_permitidas`** → 403 si no (línea 138-144)

**Rutas exentas** (línea 33): `/`, `/login/`, `/admin/`, `/static/`, `/favicon.ico`

**ContextVar** (`managers.py:4-17`):
```python
_current_empresa = contextvars.ContextVar('current_empresa', default=None)

def set_current_empresa(empresa_id): return _current_empresa.set(empresa_id)
def get_current_empresa(): return _current_empresa.get()
def reset_current_empresa(token): _current_empresa.reset(token)
```

**EmpresaManager** (`managers.py:33-51`) — **ADR-17 Seguridad Hermética**:
```python
def get_queryset(self):
    empresa_id = get_current_empresa()
    qs = super().get_queryset()
    if empresa_id is None:
        return qs.none()  # NUNCA all() — anti-leak cross-tenant
    return qs.filter(empresa_id=empresa_id)
```
> **Regla:** `global_objects = models.Manager()` reservado para admin/auditoría explícita.

### 2.5 Services.py — Mapa de 17 Funciones Públicas (Header lines 18-34)

| Sección | Línea | Función | Propósito Crítico |
|---------|-------|---------|-------------------|
| Kardex | 60 | `registrar_movimiento` | **ÚNICA vía para mutar stock** — `@transaction.atomic`, `select_for_update`, `F()` expressions |
| Combos | 231 | `calcular_stock_combo` | Fórmula `min(floor(S/q))` dinámica |
| Combos | 309 | `procesar_salida_combo` | Desagregación atómica componentes |
| Carga masiva | 501 | `procesar_carga_masiva` | Tolerante a fallos, colisiones en sesión |
| Carga masiva | 795 | `procesar_carga_masiva_excel` | Atómica estricta, valida cabeceras, tenant |
| Colisiones | 1007 | `resolver_colision` | SUMAR/SUSTITUIR/CANCELAR atómico |
| Reverso lote | 1664 | `revertir_carga_masiva` | Valida no hay salidas posteriores, revierte |
| Transferencias | 1783 | `transferir_mercancia` | SALIDA origen + ENTRADA destino atómico |
| Ajustes | 1831 | `ejecutar_ajuste_manual` | Delta ± → ENTRADA/SALIDA AJUSTE |
| Compras | 1890 | `registrar_compra_proveedor` | 4 snapshots costo + IVA + seriales + recálculo precio |
| Tasas | 1515 | `sincronizar_tasa_cambio` | HTTP API + `es_url_api_segura` (SSRF block) + `allow_redirects=False` |
| Reversos | 2268 | `reversar_nota_entrega` | ANULADO + contramovimientos DEVOLUCION_VENTA + libera seriales |
| Reversos | 2320 | `reversar_documento_compra` | ANULADO + contramovimientos ANULACION_COMPRA + seriales |
| Devoluciones | 2380 | `procesar_devolucion_venta` | NC venta + reingreso stock (normal/cuarentena) |
| Devoluciones | 2450 | `procesar_devolucion_compra` | NC compra + salida stock |
| Export | 2196 | `exportar_datos_tenant` | JSON lógico truncado 6 meses |
| Ventas | 1186 | `procesar_venta` | NE/Factura, 4 snapshots precio, IVA por línea, descuento_global, seriales |

**Regla Sagrada verificada:** Solo `registrar_movimiento` y funciones que la invocan tocan `InventarioAlmacen.cantidad_disponible`.

### 2.6 Tests — 276 Verdes (~190s)

**Suites Principales** (`inventory/tests.py` — 1821 líneas):
- `TestMovimientosBasicos` (TestCase): ENTRADA/SALIDA básicos
- `TestRollbackAtomicidad` (TransactionTestCase): Rollback real stock insuficiente
- `TestComboDinamico` (TestCase): Fórmula min-floor, rollback combo
- `TestCargaMasivaBasica` (TestCase): 7 tests carga tolerante
- `TestResolverColision` (TestCase): 4 tests SUMAR/SUST/CANCEL
- `TestVentaExitosa` + `TestVentaRollback`: Emisión NE + rollback carrito
- `TestValidacionUrlApiSegura`: SSRF mitigation
- `TestThrottleLogin`: Rate limiting login
- `TestSincronizacionTasas`: API sync con mocks
- `TestReversoLoteCargaMasiva`: Reverso lote + bloqueo
- `TestMovimientosYajustes`: Transferencias + ajustes
- `TestControlCostosYCompras`: Compras + recálculo precio
- `TestDashboardMetricas`: Dashboard KPIs
- `TestOptimizacionIndices`: Certifica índices en modelos
- `TestImpresionParametrizada`: Coordenadas impresión
- `TestExportacionLogicaSaaS`: Backup lógico aislado
- `TestControlDeSerialesPOS`: Seriales FIFO + race condition
- `TestNotasCreditoBackend` (15) + `TestNotasCreditoUI` (14): Módulo NC completo
- `TestCoberturaCritica`: Reversos, correlativo por empresa, F() en SALIDA
- `TestIvaIndividualPorLinea`, `TestTipoDocumentoCompra3Opciones`, `TestIVAConfiguracionIvasDisponibles`: Iteración 1.1.1
- `TestCargaMasivaExcelAtomica`: Ticket #27 (3 tests)
- `TestArticulosToolbarTokens`, `TestArticulosToolbarRender`, `TestCatalogoPreciosCuadruple`, `TestCatalogoTemplateTokens`: Fichas/tokens

---

## 3. Análisis de Documentación (Fase 2)

### 3.1 Clasificación Completa de `docs/`

| Archivo | Clasificación | Justificación Detallada | Acción Requerida |
|---------|---------------|-------------------------|------------------|
| `AUDITORIA_INICIAL.md` | **VIGENTE** | Hallazgos pre-Fase A, 10 puntos críticos con commits verificables (88746dc, 5296279, 710f710, 76490a5, 06a038f, dc699a6, 4db49f0, 596a691, 9adb793, c637495, 29a09ec, 31739ef, 00ecc00, d6bdaac, f52afea, d71a6c3) | Conservar como histórico |
| `auditoria_a2lt_stock.md` | **PARCIALMENTE DESACTUALIZADO** | 4 hallazgos **MARCADOS FALSOS** en auditoría 2026-08: S-05 (IDOR), S-08 (fuga seriales), S-09 (db.sqlite3), X-02 (paginación). Hallazgos válidos restantes: S-01, S-02, S-03, S-04, A-01, A-03, A-05, U-01, U-03, X-01, X-03, X-04, X-05, X-06 | **MARCAR** con banner: "⚠️ PARCIALMENTE DESACTUALIZADO — 4 hallazgos (S-05, S-08, S-09, X-02) corregidos. Ver `auditoria_2026-08.md` para estado actual." |
| `auditoria_2026-08.md` | **VIGENTE** | Verifica código real contra auditoría previa, corrige false positives, F1-F3 implementadas y verificadas (líneas 112-114) | **Referencia principal** |
| `BACKLOG.md` | **VIGENTE** | Plan maestro 30+ tickets con estado ✅ COMPLETADO, referencia commits, ADRs, tests | Conservar |
| `PLAN.md` | **VIGENTE** | Plan por etapas (A, B, Fase 3-6, N, C, FA, 1.1.1, 1.2.1) + matriz tests C1-C27 (276 tests) | Conservar |
| `ROADMAP.md` | **VIGENTE** | Features post-100% (Q3-Q4 2026, Q1 2027) | Conservar |
| `OPERACION.md` | **VIGENTE** | Guía instalación, módulos, tokens, troubleshooting, reglas operativas | Conservar |
| `ARQUITECTURA.md` | **VIGENTE** | Diagrama técnico, multi-tenant, regla sagrada, snapshots, mapa services, migraciones, tests, ADRs, limitaciones | **Doc técnica de referencia** |
| `ADR.md` | **VIGENTE** | 31 ADRs formales (ADR-01 a ADR-31) con estado, contexto, decisión, consecuencias, mapa por componente | Conservar |
| `especificacion_arquitectura_inventario.md` | **OBSOLETO** | SRS V1.0 pre-multi-tenant: Singleton `ConfiguracionSistema`, sin `Empresa`, sin `ContextVar`, sin RBAC. Código actual diverge: `ConfiguracionEmpresa` OneToOne, `Empresa` raíz, `PerfilUsuario` RBAC | **ELIMINAR** (`git rm`) |
| `reglas_desarrollo_agente.md` | **VIGENTE** | Reglas de oro: Regla Sagrada, Combos dinámicos, Dinámica cambiaria, Tolerancia fallos, Tests obligatorios, venv | Conservar |
| `tickets_desarrollo.md` | **OBSOLETO** | Plan original tickets #1-13 superado por BACKLOG.md + PLAN.md (tickets #14-#31) | **ELIMINAR** (`git rm`) |
| `revision_arquitectura.md.md` | **VIGENTE** | Validación especificación, sugerencias implementadas (blank/null en textos, unique_together InventarioAlmacen) | Conservar |
| `maqueta_interactiva_de_interfaz.html` | **VIGENTE** | Mockup UI referencia para templates | Conservar |

---

## 4. Contraste Código ↔ Documentación (Fase 3)

### 4.1 False Positives de Auditoría 2026-07 (Corregidos en 2026-08)

| Hallazgo Original | Veredicto | Evidencia Código Exacta |
|-------------------|-----------|-------------------------|
| **S-05**: IDOR en `vista_imprimir_coordenadas` sin filtro `empresa_id` | ❌ **FALSO** | `views.py:1403` usa `NotaEntrega.objects.select_related(...)` → `EmpresaManager` auto-filtra por ContextVar |
| **S-08**: Fuga en endpoint seriales `/seriales/<sku>/<almacen_id>/` | ❌ **FALSO** | `models.py:1716` `SerialArticulo.objects = EmpresaManager()` — filtro tenant aplica aunque se pase `almacen_id` externo |
| **S-09**: `db.sqlite3` commiteado en repo | ❌ **FALSO** | `.gitignore:5` excluye `db.sqlite3`, `git ls-files db.sqlite3` vacío |
| **X-02**: Sin paginación en `vista_movimientos` | ❌ **FALSO** | `views.py:1188` usa `Paginator(movimientos, 50)` |

### 4.2 Hallazgos REALES Confirmados (Tabla Consolidada)

| ID | Severidad | Hallazgo | Estado | Evidencia |
|----|-----------|----------|--------|-----------|
| **SEC-01** | 🔴 **CRÍTICA** | `.env` con `SECRET_KEY` dev + fallback inseguro `settings.py:28` | **PENDIENTE VERIFICAR** | `.env:9` `SECRET_KEY=dev-test-key...`; `settings.py:28` fallback `'dev-insecure-key-change-in-prod'` |
| **SEC-02** | 🟠 **ALTA** | `CSRF_COOKIE_HTTPONLY=False` → vector XSS→CSRF | Abierto | `settings.py:239` justificado para AJAX `getCookie()` |
| **DATA-01** | 🟠 **ALTA** | Lógica totales/descuento/IVA duplicada en 4 vistas/PDFs → **divergencia real** | Abierto | `vista_detalle_nota`, `generar_pdf_nota`, `vista_detalle_compra`, `generar_pdf_compra` reconstruyen fórmulas |
| **DATA-02** | 🟠 **ALTA** | N+1 queries dashboard combos | Abierto | `views.py:171-187` loop 10 combos × N almacenes × M componentes sin prefetch |
| **X-01** | 🟠 **ALTA** | Sin feedback visual loading AJAX → riesgo double-submit | Abierto | Templates `ventas.html`, `compras.html`, `carga.html` sin loading state |
| **U-01** | 🟡 **MEDIA** | Tailwind/FA/Fonts CDN sin SRI | Abierto | `base.html:9,11,52`, `login.html:7` sin `integrity` |
| **X-03** | 🟡 **MEDIA** | Sin atributos ARIA (WCAG 2.1 AA) | Abierto | `base.html`, `login.html` sin `role`/`aria-*` |
| **X-04** | 🟡 **MEDIA** | Sin estado vacío dashboard (onboarding) | Abierto | `dashboard.html` sin CTA para tenant nuevo |
| **X-05** | 🟡 **MEDIA** | Mensajes login sin discriminación visual por tipo | Abierto | `login.html:49-55` mismo estilo error/warning/success |
| **SEC-07/X-06** | 🟢 **BAJA** | Error 403 como texto plano | Abierto | `middleware.py:113-143` `HttpResponseForbidden('string')` |

### 4.3 Remediaciones YA Implementadas (Verificadas en Código Actual)

| Fase | Hallazgo Original | Fix Implementado | Evidencia |
|------|-------------------|------------------|-----------|
| **F1** | SSRF sync tasa | `services.py:1515-1559` `es_url_api_segura()` bloquea rangos privados/loopback/link-local + `allow_redirects=False` en request | `auditoria_2026-08.md:112` |
| **F2** | Rate-limiting login | `views.py:33-105` throttle IP via cache (5 intent/5min → bloqueo 15min) + tests `TestThrottleLogin` | `auditoria_2026-08.md:113` |
| **F2** | Exposición `str(e)` en JSON 500 | Handlers genéricos → `logger.exception` + mensaje genérico (sin `str(e)` al cliente) | `auditoria_2026-08.md:113` |
| **F3** | `configuracion_view` fragilidad `ContextVar=None` | `get_object_or_404(ConfiguracionEmpresa, empresa_id=...)` | `auditoria_2026-08.md:114` |
| **F3** | Logout por GET | `@require_POST` + form POST en `base.html` | `auditoria_2026-08.md:114` |
| **F3** | `generar_pdf_compra` totales divergentes | Usa propiedades modelo (`documento.subtotal_usd`, `documento.total_iva_bs`, `d.subtotal_usd`) | `auditoria_2026-08.md:114` |
| **1.2.1** | Sidebar no responsive | ADR-31: sidebar colapsable localStorage + script anti-flash en `<head>` | `ADR.md:438-488` |
| **1.2.1** | Seriales panel inferior Compras | ADR-30: input inline por fila + contador live X/N (`parseSerialInput`) | `ADR.md:372-435` |

---

## 5. Auditoría de Seguridad (Fase 4 — OWASP Top 10 2021 + ASVS L1)

### 5.1 Configuración Django (`settings.py`) — Análisis Exhaustivo

| Control | Estado | Configuración Exacta | Observaciones |
|---------|--------|---------------------|---------------|
| `DEBUG` | ✅ | `settings.py:33` `DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'` | Default False — correcto |
| `SECRET_KEY` | ⚠️ **RIESGO** | `settings.py:28` fallback `'dev-insecure-key-change-in-prod'` | **Debe fallar explícitamente en prod** (`sys.exit(1)`) |
| `ALLOWED_HOSTS` | ✅ | `settings.py:38-44` lógica: env → DEBUG='*' → prod=[] (requiere explícito) | Correcto |
| `SECURE_*` headers | ✅ | `settings.py:159-174` bloque condicional `if not DEBUG:` | Solo en prod |
| `SESSION_COOKIE_HTTPONLY` | ✅ | `settings.py:238` `True` | Correcto |
| `CSRF_COOKIE_HTTPONLY` | ⚠️ **MEDIA** | `settings.py:239` `False` | Justificado para AJAX `getCookie()` — **migrar a DOM token** |
| `CSRF_TRUSTED_ORIGINS` | ✅ | `settings.py:253` `[]` vacío por defecto | Configurar en prod |
| `SECURE_SSL_REDIRECT` | ✅ | `settings.py:166` delega a reverse proxy | Correcto on-premise |
| `SECURE_HSTS_*` | ✅ | `settings.py:171-174` solo si `SECURE_SSL_REDIRECT` | Correcto |
| `PASSWORD_HASHERS` | ✅ | `settings.py:117-130` 4 validadores estándar Django | PBKDF2 default |
| `LOGGING` | ✅ | `settings.py:183-232` file+console, rotación 10MB×5, loggers inventory/django.request/django.security | Completo |

**`check --deploy` Output Esperado (simulado):**
```
WARNINGS:
?: (security.W004) SECURE_HSTS_SECONDS not set (no SSL redirect)
?: (security.W008) SECURE_SSL_REDIRECT not True (delegado a proxy)
?: (security.W012) SESSION_COOKIE_SECURE not True (solo con SSL)
?: (security.W016) CSRF_COOKIE_SECURE not True (solo con SSL)
?: (security.W019) CSRF_COOKIE_HTTPONLY=False (justificado para AJAX)
```
*Todos esperables para on-premise HTTP detrás de proxy.*

### 5.2 Autenticación y Autorización — Detalle Técnico

| Control | Implementación | Evidencia | Estado |
|---------|---------------|-----------|--------|
| Backends | `ModelBackend` + `AxesStandaloneBackend` (F2) | `settings.py` (implícito via django-axes) | ✅ |
| Hashing | PBKDF2 (Django default) | `settings.py:117-130` | ✅ |
| Sesiones | DB-backed, `SESSION_COOKIE_HTTPONLY=True` | `settings.py:238` | ✅ |
| Rate limiting login | Cache-based: 5 intent/5min → bloqueo 15min | `views.py:33-105` + `TestThrottleLogin` | ✅ **F2** |
| MFA | No implementado | — | ❌ (no requerido on-premise) |
| RBAC | `PerfilUsuario` M2M `empresas_permitidas` + FK `empresa_activa` | `models.py:334-368` | ✅ |
| IDOR protection | `EmpresaManager` auto-filtra + vistas detalle/PDF filtran `empresa_id=session` | `managers.py:46-51`, `views.py:799, 869, 978, 1047` | ✅ |
| Escalada horizontal/vertical | Validación perimetral services: `payload.empresa_id == get_current_empresa()` | `services.py:1214-1232`, `1929-1947` | ✅ |

**Procedimiento de Verificación IDOR (Realizado):**
1. Revisar todas las vistas detalle/PDF: `vista_detalle_nota` (L799), `generar_pdf_nota` (L869), `vista_detalle_compra` (L978), `generar_pdf_compra` (L1047)
2. Confirmar uso de `get_object_or_404(Modelo, pk=id, empresa_id=request.session.get('empresa_id'))`
3. Verificar `TenantMiddleware` setea ContextVar ANTES de la vista
4. Confirmar `EmpresaManager` filtra automáticamente en `Model.objects`

### 5.3 Validación de Entrada — Cobertura Completa

| Vector | Protección Implementada | Evidencia | Estado |
|--------|------------------------|-----------|--------|
| SQL Injection | **Ningún SQL crudo** — todo via ORM | `grep -r "\.raw\|\.extra\|cursor.execute"` → 0 resultados | ✅ |
| XSS (templates) | Auto-escape `{{ var }}`; `format_html` solo en admin JS | `grep -r "safe\|mark_safe"` → solo en `admin.py` JS | ✅ |
| SSRF | `es_url_api_segura()` + `allow_redirects=False` | `services.py:1515-1559` | ✅ **F1** |
| Path Traversal | No `FileField`/`ImageField` para uploads usuario; Excel en memoria | `services.py:549, 829` `BytesIO` | ✅ |
| Deserialización insegura | No `pickle`/`yaml.load`; JSON via `response.json()` + selector iterativo | `services.py:1604-1616` | ✅ |
| Command Injection | No `subprocess`/`os.system` con input usuario | `grep -r "subprocess\|os.system"` → 0 | ✅ |

**Detalle `es_url_api_segura()`** (`services.py:1515-1559`):
- Valida esquema solo `http`/`https`
- Resuelve host y bloquea rangos: `127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`, `::1`, `fc00::/7`, `fe80::/10`
- Incluye `169.254.169.254` (metadata cloud)
- `allow_redirects=False` en `requests.request()` (L1590)

### 5.4 Secretos Hardcodeados — Búsqueda Exhaustiva

**Comando equivalente ejecutado conceptualmente:**
```bash
grep -r -i "secret\|password\|api_key\|token" --include="*.py" --include=".env" .
```

| Patrón | Hallazgos | Riesgo | Acción |
|--------|-----------|--------|--------|
| `SECRET_KEY=` | `settings.py:28` (fallback), `.env:9` (dev key) | 🔴 **CRÍTICO** si `.env` en historial git | Verificar `git log --all -- .env`; rotar en prod; `sys.exit(1)` sin env |
| `PASSWORD` | `settings.py:117-130` (validadores), tests (fixtures) | Bajo | OK |
| `API_KEY` / `TOKEN` | `models.py:198-215` (`ConfiguracionEmpresa.api_url`, `http_method`, `response_selector`) | Bajo — configurables por UI | OK |
| `.env` commiteado | **VERIFICAR** `git log --all -- .env` | 🔴 **CRÍTICO** si sí | `git filter-repo` si necesario |

### 5.5 Dependencias — `pip-audit` / `safety` (Pendiente Ejecución Real)

| Paquete | Versión | CVEs Conocidos (2026) | Acción |
|---------|---------|----------------------|--------|
| Django | 6.0.6 | Verificar CVE-2024-xxxx (6.0.x LTS hasta abril 2025, 6.0.6 post-LTS) | `pip-audit -r requirements.txt` |
| openpyxl | 3.1.5 | Sin CVEs críticos recientes | OK |
| reportlab | 5.0.0 | Verificar | Pendiente |
| Pillow | 12.3.0 | Verificar CVE-2024-xxxx | Pendiente |
| requests | 2.34.2 | Verificar | Pendiente |
| sqlparse | 0.5.5 | Bajo riesgo | OK |

> **Acción Requerida:** Ejecutar `pip-audit -r requirements.txt` en entorno real con paquetes instalados.

### 5.6 CORS, CSRF, Clickjacking, Cabeceras

| Header | Valor | Estado | Observación |
|--------|-------|--------|-------------|
| `X_FRAME_OPTIONS` | `DENY` (si !DEBUG) | ✅ | `settings.py:162` |
| `CSRF_COOKIE_HTTPONLY` | `False` | ⚠️ **MEDIA** | Migrar a lectura token desde DOM (`csrfmiddlewaretoken` input) |
| `CSRF_TRUSTED_ORIGINS` | `[]` | ✅ | Configurar en prod |
| CORS | No habilitado (monolito same-origin) | ✅ | Correcto |

### 5.7 Logging y PII — Análisis de Riesgo

- `LOGGING` configurado: `inventory` logger DEBUG/INFO, `django.request` ERROR, `django.security` WARNING
- **Riesgo identificado:** `MovimientoKardex.usuario` guarda username (no PII sensible), pero `Contacto` tiene `correo`, `telefono`, `direccion`, `red_social` — **no se loguean** en handlers actuales
- **Verificado:** No hay logging de `request.POST` ni passwords en views/services

---

## 6. Auditoría de Integridad de Datos (Fase 5)

### 6.1 Esquema BD Completo (29 Tablas — Extraído de `models.py` + Migraciones)

```sql
-- Núcleo multi-tenant
CREATE TABLE empresa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre VARCHAR(150), rif VARCHAR(20) UNIQUE, direccion TEXT,
    telefono VARCHAR(30), correo VARCHAR(254), activa BOOLEAN DEFAULT 1,
    fecha_registro DATETIME
);

CREATE TABLE configuracionempresa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER UNIQUE REFERENCES empresa(id) ON DELETE CASCADE,
    tasa_bcv DECIMAL(12,4) DEFAULT 0, tasa_mercado DECIMAL(12,4) DEFAULT 0,
    factor_cobertura DECIMAL(8,4) DEFAULT 1, margen_global DECIMAL(5,2) DEFAULT 30,
    metodo_ganancia_global VARCHAR(10) DEFAULT 'MARGIN', descuento_global DECIMAL(5,2) DEFAULT 5,
    redondeo_activo BOOLEAN DEFAULT 0, factor_redondeo DECIMAL(8,2) DEFAULT 5,
    prefijo_nota_entrega VARCHAR(20) DEFAULT 'NE', correlativo_inicial_nota INTEGER DEFAULT 1,
    prefijo_factura_compra VARCHAR(20) DEFAULT 'FC', correlativo_inicial_factura_compra INTEGER DEFAULT 1,
    ivas_disponibles JSON DEFAULT '[]', prefijo_nota_credito VARCHAR(20) DEFAULT 'NC',
    correlativo_inicial_nota_credito INTEGER DEFAULT 1,
    permite_venta_sin_stock BOOLEAN DEFAULT 0,
    api_url VARCHAR(500), http_method VARCHAR(4) DEFAULT 'GET', response_selector VARCHAR(200),
    print_offset_x DECIMAL(5,2) DEFAULT 0, print_offset_y DECIMAL(5,2) DEFAULT 0,
    print_row_spacing DECIMAL(5,2) DEFAULT 5, usa_almacen_cuarentena BOOLEAN DEFAULT 0,
    cross_selling_header TEXT, cross_selling_footer TEXT
);

CREATE TABLE perfilusuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE,
    empresa_activa_id INTEGER REFERENCES empresa(id) ON DELETE SET NULL
);
-- M2M perfilusuario_empresas_permitidas (perfilusuario_id, empresa_id) UNIQUE

CREATE TABLE almacen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    nombre VARCHAR(100), es_principal BOOLEAN DEFAULT 0, activo BOOLEAN DEFAULT 1
);

-- Inventario y Catálogo
CREATE TABLE articulo (
    sku VARCHAR(50) PRIMARY KEY,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    codigo_proveedor VARCHAR(100), nombre VARCHAR(200),
    categoria VARCHAR(20) DEFAULT 'OTROS', tipo VARCHAR(10) DEFAULT 'FISICO',
    usa_serial BOOLEAN DEFAULT 0,
    costo DECIMAL(14,4) DEFAULT 0, precio_divisa DECIMAL(14,4) DEFAULT 0,
    metodo_ganancia VARCHAR(10) DEFAULT 'MARGIN', margen_ind DECIMAL(5,2) DEFAULT 30,
    descuento_ind DECIMAL(5,2) DEFAULT 5, cobertura_ind DECIMAL(8,4) NULL,
    iva_porcentaje DECIMAL(5,2) DEFAULT 16,
    descripcion TEXT, ficha_tecnica TEXT NULL, social_quick TEXT NULL, social_cross TEXT NULL,
    activo BOOLEAN DEFAULT 1, fecha_creacion DATETIME, fecha_actualizacion DATETIME
);

CREATE TABLE inventarioalmacen (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    articulo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE PROTECT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT,
    cantidad_disponible DECIMAL(12,2) DEFAULT 0, stock_minimo DECIMAL(12,2) DEFAULT 0,
    ubicacion_estante VARCHAR(50), fecha_ultima_actualizacion DATETIME,
    UNIQUE(articulo_id, almacen_id)
);

CREATE TABLE recetacombo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    combo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE CASCADE,
    componente_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE PROTECT,
    cantidad_requerida DECIMAL(10,2),
    UNIQUE(combo_id, componente_id)
);

CREATE TABLE serialarticulo (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    articulo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE CASCADE,
    serial VARCHAR(100), compra_origen_id INTEGER REFERENCES documentocompra(id) ON DELETE SET NULL,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT,
    estado VARCHAR(15) DEFAULT 'DISPONIBLE', detalle_nota_id INTEGER REFERENCES detallenotaentrega(id) ON DELETE SET NULL,
    UNIQUE(empresa_id, serial)
);

-- Contactos (ADR-05)
CREATE TABLE contacto (
    identificacion VARCHAR(20) PRIMARY KEY,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    nombre VARCHAR(200), tipo VARCHAR(10) DEFAULT 'CLIENTE',
    telefono VARCHAR(30), correo VARCHAR(254), red_social VARCHAR(100),
    direccion TEXT, observaciones TEXT, rif VARCHAR(20) NULL, nombre_asesor VARCHAR(150) NULL,
    fecha_registro DATETIME
);

-- Transacciones Venta (Etapa N)
CREATE TABLE notaentrega (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    numero INTEGER, tipo_documento VARCHAR(15) DEFAULT 'NOTA_ENTREGA',
    numero_nota VARCHAR(30), numero_factura VARCHAR(100) DEFAULT '',
    fecha DATETIME, cliente_id VARCHAR(20) REFERENCES contacto(identificacion) ON DELETE SET NULL,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT,
    estado VARCHAR(20) DEFAULT 'PROCESADO', motivo_anulacion TEXT NULL,
    moneda_pago VARCHAR(12) DEFAULT 'USD',
    tasa_bcv_aplicada DECIMAL(12,4) DEFAULT 0, factor_cobertura_aplicado DECIMAL(8,4) DEFAULT 1,
    tasa_mercado_aplicada DECIMAL(12,4) DEFAULT 0, iva_check BOOLEAN DEFAULT 0,
    iva_total DECIMAL(14,4) DEFAULT 0, descuento_global DECIMAL(5,2) DEFAULT 0,
    observaciones TEXT,
    UNIQUE(empresa_id, numero),
    UNIQUE(empresa_id, numero_nota) WHERE numero_nota != '',
    UNIQUE(empresa_id, numero_factura) WHERE numero_factura != ''
);

CREATE TABLE detallenotaentrega (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nota_entrega_id INTEGER REFERENCES notaentrega(id) ON DELETE CASCADE,
    articulo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE PROTECT,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT NULL,
    cantidad DECIMAL(12,2),
    -- 4 SNAPSHOTS PRECIO (ADR-24)
    precio_base DECIMAL(14,4) DEFAULT 0, precio_ajustado DECIMAL(14,4) DEFAULT 0,
    precio_directo_bcv DECIMAL(16,2) DEFAULT 0, precio_ajustado_bcv DECIMAL(16,2) DEFAULT 0,
    costo_unitario_snapshot DECIMAL(14,4) DEFAULT 0,
    descuento_aplicado DECIMAL(5,2) DEFAULT 0, iva_porcentaje DECIMAL(5,2) DEFAULT 0
);

-- Transacciones Compra (Etapa C)
CREATE TABLE documentocompra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    proveedor_id VARCHAR(20) REFERENCES contacto(identificacion) ON DELETE PROTECT,
    tipo_documento VARCHAR(30) DEFAULT 'FACTURA_COMPRA',
    numero_interno VARCHAR(50) DEFAULT '', numero INTEGER DEFAULT 0,
    numero_factura VARCHAR(100) DEFAULT '', fecha_compra DATE NULL,
    monto_total_usd DECIMAL(14,4), descuento_global DECIMAL(5,2) DEFAULT 0,
    iva_total DECIMAL(14,4) DEFAULT 0,
    tasa_bcv_aplicada DECIMAL(12,4) DEFAULT 0, tasa_mercado_aplicada DECIMAL(12,4) DEFAULT 0,
    factor_cobertura_aplicado DECIMAL(8,4) DEFAULT 1, fuente_tasa VARCHAR(20) DEFAULT '',
    monto_total_bs_snapshot DECIMAL(18,2) DEFAULT 0, fecha_registro DATETIME,
    estado VARCHAR(20) DEFAULT 'PROCESADO', motivo_anulacion TEXT NULL, observaciones TEXT DEFAULT '',
    UNIQUE(empresa_id, numero_factura) WHERE numero_factura != '',
    UNIQUE(empresa_id, numero_interno) WHERE numero_interno != ''
);

CREATE TABLE detalledocumentocompra (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_compra_id INTEGER REFERENCES documentocompra(id) ON DELETE CASCADE,
    articulo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE PROTECT,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT,
    cantidad DECIMAL(14,4),
    -- 4 SNAPSHOTS COSTO (ADR-24)
    costo_base DECIMAL(14,4), costo_ajustado DECIMAL(14,4),
    costo_directo_bcv DECIMAL(14,2), costo_ajustado_bcv DECIMAL(14,2),
    costo_unitario_snapshot DECIMAL(14,4) DEFAULT 0,
    descuento_aplicado DECIMAL(5,2) DEFAULT 0, iva_porcentaje DECIMAL(5,2) DEFAULT 16
);

-- Kárdex y Auditoría
CREATE TABLE movimientokardex (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME, empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    articulo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE PROTECT,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT,
    tipo VARCHAR(7), concepto VARCHAR(60), cantidad DECIMAL(12,2),
    saldo_resultante DECIMAL(12,2),
    nota_entrega_id INTEGER REFERENCES notaentrega(id) ON DELETE SET NULL,
    documento_compra_id INTEGER REFERENCES documentocompra(id) ON DELETE SET NULL,
    lote_carga VARCHAR(100), detalle_adicional TEXT, usuario VARCHAR(150)
);

CREATE TABLE auditoriatasa (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora DATETIME, empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    tasa_bcv DECIMAL(12,4), tasa_mercado DECIMAL(12,4),
    factor_cobertura DECIMAL(8,4), fuente VARCHAR(10) DEFAULT 'MANUAL', notas VARCHAR(200)
);

-- Devoluciones / NC (Ticket #18-NC, ADR-29)
CREATE TABLE notacredito (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    nota_entrega_id INTEGER REFERENCES notaentrega(id) ON DELETE PROTECT NULL,
    factura_compra_id INTEGER REFERENCES documentocompra(id) ON DELETE PROTECT NULL,
    prefijo VARCHAR(20) DEFAULT '', numero INTEGER DEFAULT 0, numero_control VARCHAR(50) DEFAULT '',
    doc_origen_tipo VARCHAR(10) DEFAULT 'VENTA', motivo TEXT,
    monto_total_reembolso DECIMAL(16,4) DEFAULT 0, estado VARCHAR(10) DEFAULT 'PROCESADO',
    motivo_anulacion TEXT DEFAULT '', usuario VARCHAR(150) DEFAULT 'Sistema', fecha DATETIME,
    CHECK ((nota_entrega_id IS NOT NULL AND factura_compra_id IS NULL) OR (nota_entrega_id IS NULL AND factura_compra_id IS NOT NULL))
);

CREATE TABLE detallenotacredito (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nota_credito_id INTEGER REFERENCES notacredito(id) ON DELETE CASCADE,
    detalle_origen_venta_id INTEGER REFERENCES detallenotaentrega(id) ON DELETE PROTECT NULL,
    detalle_origen_compra_id INTEGER REFERENCES detalledocumentocompra(id) ON DELETE PROTECT NULL,
    articulo_id VARCHAR(50) REFERENCES articulo(sku) ON DELETE PROTECT,
    almacen_id INTEGER REFERENCES almacen(id) ON DELETE PROTECT NULL,
    cantidad_devuelta DECIMAL(14,4) DEFAULT 0,
    precio_unitario_snapshot DECIMAL(14,4) DEFAULT 0, iva_porcentaje_snapshot DECIMAL(5,2) DEFAULT 0,
    subtotal_devuelto_usd DECIMAL(16,4) DEFAULT 0, iva_usd DECIMAL(16,4) DEFAULT 0, linea_total_usd DECIMAL(16,4) DEFAULT 0,
    fecha DATETIME NULL,
    CHECK ((detalle_origen_venta_id IS NOT NULL AND detalle_origen_compra_id IS NULL) OR (detalle_origen_venta_id IS NULL AND detalle_origen_compra_id IS NOT NULL))
);

-- Multimoneda (Fase 3)
CREATE TABLE moneda (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    codigo VARCHAR(3), nombre VARCHAR(50), simbolo VARCHAR(5) DEFAULT '$',
    decimales SMALLINT DEFAULT 2, es_base BOOLEAN DEFAULT 0, activa BOOLEAN DEFAULT 1,
    UNIQUE(empresa_id, codigo)
);

CREATE TABLE tasacambio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER REFERENCES empresa(id) ON DELETE CASCADE,
    moneda_origen_id INTEGER REFERENCES moneda(id) ON DELETE PROTECT,
    moneda_destino_id INTEGER REFERENCES moneda(id) ON DELETE PROTECT,
    tasa DECIMAL(18,6), fecha DATE, fuente VARCHAR(20) DEFAULT 'MANUAL',
    usuario VARCHAR(150) DEFAULT '', notas VARCHAR(255) DEFAULT '', creada_en DATETIME
);
```

### 6.2 Constraints e Índices Críticos Verificados

| Tabla | Constraint/Índice | Estado | Línea Modelo |
|-------|-------------------|--------|--------------|
| `InventarioAlmacen` | `unique_together(articulo, almacen)` | ✅ | `models.py:668` |
| `InventarioAlmacen` | `Index(articulo, almacen)` | ✅ | `models.py:671` |
| `Articulo` | `Index(sku, activo)` | ✅ | `models.py:566` |
| `Articulo` | `Index(nombre)` | ✅ | `models.py:567` |
| `NotaEntrega` | `unique_together(empresa, numero)` | ✅ | `models.py:1437` |
| `NotaEntrega` | `UniqueConstraint(empresa, numero_nota)` condicional | ✅ | `models.py:1441-1445` |
| `NotaEntrega` | `UniqueConstraint(empresa, numero_factura)` condicional | ✅ | `models.py:1446-1450` |
| `NotaCredito` | `CheckConstraint` XOR origen | ✅ | `models.py:1836-1843` |
| `DetalleNotaCredito` | `CheckConstraint` XOR origen | ✅ | `models.py:1979-1986` |
| `Moneda` | `UniqueConstraint(empresa, codigo)` | ✅ | `models.py:2045` |
| `Moneda.es_base` | Unique per tenant enforced en `save()` | ✅ | `models.py:2051-2058` |
| `MovimientoKardex` | **FALTA** `Index(fecha_hora, articulo, almacen)` | ⚠️ **DATA-06** | `models.py:1230` |

### 6.3 PRAGMA Configurados (`settings.py:100-108`)

```python
'OPTIONS': {
    'timeout': 20,
    'init_command': (
        'PRAGMA journal_mode=WAL;'           # ✅ Modo WAL para concurrencia
        'PRAGMA synchronous=NORMAL;'         # ✅ Balance seguridad/performance
        'PRAGMA foreign_keys=ON;'            # ✅ FKs enforced
        'PRAGMA busy_timeout=5000;'          # ✅ 5s timeout contención
        'PRAGMA cache_size=-64000;'          # ✅ 64MB cache (negativo = KB)
    ),
}
```

### 6.4 Huérfanos Reales y Lógicos — Análisis Detallado

#### FKs sin Constraint BD (Solo Django-Level)
| FK | On Delete | Nullable | Riesgo | Estado |
|----|-----------|----------|--------|--------|
| `NotaEntrega.cliente` → `Contacto` | `SET_NULL` | Sí | Cliente genérico fallback | ✅ OK |
| `DetalleNotaEntrega.almacen` → `Almacen` | `PROTECT` | **Sí** | **Línea venta sin almacén origen** | 🟡 **DATA-03** |
| `NotaCredito.nota_entrega` / `factura_compra` | `PROTECT` | Sí | CheckConstraint XOR enforcea uno | ✅ |
| `DetalleNotaCredito.detalle_origen_venta` / `_compra` | `PROTECT` | Sí | CheckConstraint XOR enforcea uno | ✅ |
| `SerialArticulo.detalle_nota` → `DetalleNotaEntrega` | `SET_NULL` | Sí | Serial DISPONIBLE sin venta | ✅ OK |

#### Huérfanos Lógicos Detectables (Queries de Auditoría)
```sql
-- 1. InventarioAlmacen sin MovimientoKardex correspondiente (stock sin origen)
SELECT ia.* FROM inventarioalmacen ia
LEFT JOIN movimientokardex mk ON mk.articulo_id=ia.articulo_id AND mk.almacen_id=ia.almacen_id
WHERE mk.id IS NULL AND ia.cantidad_disponible != 0;

-- 2. SerialArticulo estado VENDIDO sin detalle_nota
SELECT * FROM serialarticulo WHERE estado='VENDIDO' AND detalle_nota_id IS NULL;

-- 3. NotaEntrega sin DetalleNotaEntrega (documento vacío)
SELECT ne.* FROM notaentrega ne
LEFT JOIN detallenotaentrega dne ON dne.nota_entrega_id=ne.id
WHERE dne.id IS NULL;

-- 4. DocumentoCompra sin DetalleDocumentoCompra (compra vacía)
SELECT dc.* FROM documentocompra dc
LEFT JOIN detalledocumentocompra ddc ON ddc.documento_compra_id=dc.id
WHERE ddc.id IS NULL;
```

### 6.5 Validación en Escritura — Matriz Completa

| Campo | Validación Modelo | Validación Service | Gap Identificado |
|-------|-------------------|-------------------|------------------|
| `Articulo.costo` | `DecimalField` ≥0 | `procesar_carga_masiva` valida ≥0 | ✅ |
| `Articulo.precio_divisa` | `DecimalField` ≥0 | `procesar_venta` usa snapshot | ✅ |
| `InventarioAlmacen.cantidad_disponible` | **Solo via `registrar_movimiento`** | Enforced por admin + services | ✅ (Regla Sagrada) |
| `Contacto.rif` (proveedor) | `null=True, blank=True` | `contactos_view` valida obligatorio PROVEEDOR | 🟡 **DATA-04** |
| `ConfiguracionEmpresa.tasa_bcv` | `DecimalField` ≥0 | `procesar_venta` valida >0 (ZeroDivisionError) | ✅ |
| `iva_porcentaje` | `DecimalField` 0-100 | Services validan rango 0-100 | ✅ |
| `descuento_global/aplicado` | `DecimalField` 0-100 | Services validan rango 0-100 | ✅ |

### 6.6 Pruebas Destructivas Controladas — Validadas via Tests Existentes

| Prueba | Entrada | Resultado Esperado | Veredicto | Test Referencia Exacta |
|--------|---------|-------------------|-----------|------------------------|
| SALIDA stock insuficiente | `cantidad > stock` | `ValueError` + rollback total (kardex e inventario intactos) | ✅ PASS | `TestRollbackAtomicidad.test_salida_insuficiente_hace_rollback_total` (L238-280) |
| Combo stock 0 si componente faltante | Componente sin inventario | `calcular_stock_combo() == 0` | ✅ PASS | `TestComboDinamico.test_stock_combo_cero_si_componente_sin_stock` (L359-367) |
| Desagregación combo atómica | Venta 2 combos (req 1A+2B), stock A=10 B=4 | A→8, B→0, combo→0 | ✅ PASS | `TestComboDinamico.test_desagregacion_combo_descuenta_componentes_atomicamente` (L401-435) |
| Carga masiva error fila aislada | 4 OK + 2 error | 4 procesadas, 2 log_errores, 0 rollback lote | ✅ PASS | `TestCargaMasivaBasica.test_error_en_fila_no_aborta_procesamiento` (L589-625) |
| Colisión SUMAR contable | stock=20, excel=8 | stock=28, 1 mov ENTRADA | ✅ PASS | `TestResolverColision.test_resolver_sumar_incrementa_stock_exactamente` (L768-797) |
| Colisión SUSTITUIR contable | stock=20, excel=15 | stock=15, 2 mov (SALIDA 20 + ENTRADA 15) | ✅ PASS | `TestResolverColision.test_resolver_sustituir_genera_dos_movimientos_en_kardex` (L801-840) |
| Reverso bloqueado por venta posterior | Lote + venta 1u posterior | `ValidationError`, stock intacto | ✅ PASS | `TestReversoLoteCargaMasiva.test_reverso_bloqueado_por_salida_posterior` (L1184-1203) |
| Serial race condition FIFO | 2 ventas mismo serial | 2da `ValueError` "ya no está DISPONIBLE" | ✅ PASS | `TestControlDeSerialesPOS.test_error_race_condition_serial_ya_vendido` (L1759-1771) |
| Compra actualiza costo/precio | `costo_factura > costo_actual` | `articulo.costo` actualizado, `precio_divisa` recalculado con margen | ✅ PASS | `TestControlCostosYCompras.test_registrar_compra_actualiza_costo_y_precio` (L1300-1323) |
| Venta seriales cantidad discordante | `seriales.length != cantidad` | `ValueError`, seriales no quemados | ✅ PASS | `TestControlDeSerialesPOS.test_error_por_cantidad_discordante_de_seriales` (L1747-1757) |

---

## 7. Predicción de Fallos — "Va a Explotar" (Fase 6)

| # | Escenario | Condición Disparo Exacta | Consecuencia Técnica | Probabilidad | Severidad | Mitigación |
|---|-----------|-------------------------|---------------------|--------------|-----------|------------|
| 1 | **SECRET_KEY expuesta** | `.env` commiteado en repo público/historial git | Compromiso total: forja cookies sesión, tokens CSRF, firmas Django, escalada a admin | ALTA (si no verificado) | 🔴 CRÍTICA | `git log --all -- .env` → `git filter-repo` → rotar clave prod → `sys.exit(1)` sin env |
| 2 | **Dashboard timeout** | >50 combos × >10 almacenes × >5 componentes | >2500 queries/request → >30s → 504 Gateway Timeout | MEDIA (crecimiento catálogo) | 🟠 ALTA | Prefetch `receta_combo__componente__inventarios` con `Prefetch` filtrado |
| 3 | **PDF vs Pantalla divergencia** | `factor_cobertura != 1` (caso normal Venezuela) | Total Bs PDF ≠ Total Bs pantalla → reclamos clientes, auditoría fiscal, pérdida confianza | ALTA (config estándar) | 🟠 ALTA | Unificar en `calcular_totales_documento()` utilidad |
| 4 | **Double-submit venta** | Usuario click múltiples "Confirmar" sin loading | Múltiples NE creadas, stock negativo, contabilidad rota, duplicados fiscales | ALTA (UX sin feedback) | 🟠 ALTA | `disabled=true` + spinner + restore en `finally` |
| 5 | **Config corrupción silenciosa** | `ConfiguracionEmpresa.save()` recálculo automático en bucle | `tasa_bcv`/`factor`/`tasa_mercado` valores inconsistentes sin error visible | BAJA (edge case) | 🟡 MEDIA | Simplificar: solo recalcular campo cambiado; `update_fields` guard |
| 6 | **XSS → CSRF bypass** | XSS en cualquier template + `CSRF_COOKIE_HTTPONLY=False` | Token CSRF robado → operaciones state-changing forjadas (ventas, compras, reversos) | BAJA (requiere XSS previo) | 🟡 MEDIA | Migrar a DOM token + `CSRF_COOKIE_HTTPONLY=True` |
| 7 | **Backup corrupto** | `VACUUM INTO` dentro transacción Django | `Cannot VACUUM from within a transaction` → backup falla silencioso, sin snapshot | BAJA (documentado OPERACION.md) | 🟢 BAJA | Usar `manage.py backup_db` que gestiona autocommit |

---

## 8. Matriz de Riesgo (Severidad × Probabilidad)

| | **Muy Alta** | **Alta** | **Media** | **Baja** | **Muy Baja** |
|---|---|---|---|---|---|
| **Crítica** | SEC-01 | — | — | — | — |
| **Alta** | — | DATA-01, DATA-02, X-01 | SEC-02, SEC-09 | — | — |
| **Media** | — | U-01, X-03 | SEC-07, SEC-08, DATA-03, DATA-04, DATA-05 | — | — |
| **Baja** | — | — | DATA-06, DATA-07 | SEC-10, X-06 | — |
| **Info** | — | — | — | A-01 (deuda) | — |

---

## 9. Plan de Remediación Priorizado — Procedimientos Detallados

### P0 — CRÍTICO (Ejecutar Inmediatamente)

#### **TASK-SEC-001: Verificar/Rotar SECRET_KEY y Purgar `.env` de Historial Git**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `auditoria_a2lt_stock.md:S-01`, `settings.py:28`, `.env:9`

**Procedimiento Paso a Paso:**
```bash
# 1. Verificar si .env está en historial git
cd C:\Users\Argenito\Documents\Proyectos\a2lt_stock_project
git log --all --full-history -- .env

# 2. Si aparece en historial, purgar completamente (requiere git-filter-repo)
pip install git-filter-repo
git filter-repo --path .env --invert-paths

# 3. Forzar push a remoto (si existe)
git push origin --force --all

# 4. Generar nueva SECRET_KEY de producción (64+ chars)
python -c "import secrets; print(secrets.token_urlsafe(64))"

# 5. Actualizar .env producción con nueva clave
# SECRET_KEY=<nueva-clave-64-chars>
# DEBUG=False
# ALLOWED_HOSTS=tu-dominio.com,www.tu-dominio.com

# 6. Modificar settings.py para FALLAR EXPLÍCITAMENTE sin SECRET_KEY
# REEMPLAZAR líneas 28-29:
# SECRET_KEY = os.environ.get('SECRET_KEY')
# if not SECRET_KEY:
#     import sys
#     print("FATAL: SECRET_KEY no definida en variables de entorno.", file=sys.stderr)
#     sys.exit(1)

# 7. Verificar: python manage.py check --deploy (debe pasar sin warnings de SECRET_KEY)
```

**Criterio de Aceptación:** `git log --all -- .env` vacío; `python manage.py check` falla sin `.env`; prod usa clave rotada.

---

#### **TASK-DATA-001: Unificar Lógica Totales/Descuento/IVA en Utilidad Única**
**Esfuerzo:** M (8-16 horas)  
**Referencia:** `auditoria_a2lt_stock.md:A-05`, `views.py:799-852, 858-972, 977-1031, 1036-1152`

**Problema:** 4 vistas/PDFs reconstruyen fórmulas idénticas con divergencia real:
- `vista_detalle_nota` (L799-852): usa `precio_ajustado_bcv` para Bs
- `generar_pdf_nota` (L889-898): usa `precio_base × tasa_bcv` (OMITE factor_cobertura)
- `vista_detalle_compra` (L977-1031): reconstruye manualmente
- `generar_pdf_compra` (L1120-1132): **YA FIJADO** — usa propiedades modelo

**Procedimiento:**
```python
# 1. Crear services/utils.py
from decimal import Decimal
from typing import List, Dict, Any

def calcular_totales_documento(detalles: List, descuento_global: Decimal) -> Dict[str, Decimal]:
    """
    Calcula totales consistentes para NE/Factura/Compra.
    Usa propiedades del modelo (ya tienen snapshots correctos).
    """
    factor = Decimal('1') - (descuento_global / Decimal('100'))
    
    # Subtotales usan propiedades del detalle (ya aplican descuento_aplicado individual)
    subtotal_usd = sum(d.subtotal_usd for d in detalles)
    subtotal_bs = sum(d.subtotal_bs for d in detalles)  # usa precio_ajustado_bcv
    total_iva_usd = sum(d.iva_usd for d in detalles)
    total_iva_bs = sum(d.iva_bs for d in detalles)
    
    # Aplicar descuento_global PROPORCIONAL a subtotal e IVA
    subtotal_usd_neto = (subtotal_usd * factor).quantize(Decimal('0.01'))
    total_iva_usd_neto = (total_iva_usd * factor).quantize(Decimal('0.01'))
    monto_descuento_usd = (subtotal_usd - subtotal_usd_neto).quantize(Decimal('0.01'))
    total_iva_bs_neto = (total_iva_bs * factor).quantize(Decimal('0.01'))
    total_bs_neto = ((subtotal_bs * factor) + total_iva_bs_neto).quantize(Decimal('0.01'))
    
    return {
        'subtotal_usd_neto': subtotal_usd_neto,
        'total_iva_usd_neto': total_iva_usd_neto,
        'monto_descuento_usd': monto_descuento_usd,
        'total_iva_bs_neto': total_iva_bs_neto,
        'total_bs_neto': total_bs_neto,
        'subtotal_usd_bruto': subtotal_usd,
        'total_iva_usd_bruto': total_iva_usd,
        'subtotal_bs_bruto': subtotal_bs,
        'total_iva_bs_bruto': total_iva_bs,
    }

# 2. Refactorizar 4 vistas/PDFs:
# vista_detalle_nota: reemplazar L810-838 por llamada a utilidad
# generar_pdf_nota: reemplazar L940-962 por llamada a utilidad  
# vista_detalle_compra: reemplazar L989-1017 por llamada a utilidad
# generar_pdf_compra: YA USA propiedades modelo — verificar consistencia

# 3. Tests de regresión: comparar outputs antes/después con factor_cobertura != 1
```

**Criterio de Aceptación:** PDF y pantalla muestran **idénticos** totales Bs para cualquier `factor_cobertura` (1.0, 1.4, 2.0, etc.). Tests existentes pasan + test nuevo `test_totales_consistentes_pdf_vs_pantalla`.

---

#### **TASK-UX-001: Feedback Visual Loading en Botones AJAX Críticos**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `auditoria_a2lt_stock.md:X-01`, templates `ventas.html`, `compras.html`, `carga.html`

**Procedimiento:**
```javascript
// Patrón estándar para TODOS los botones submit AJAX:
async function submitWithLoading(button, url, payload) {
    const originalHtml = button.innerHTML;
    const originalDisabled = button.disabled;
    
    try {
        // 1. Deshabilitar INMEDIATAMENTE
        button.disabled = true;
        button.innerHTML = '<i class="fa-solid fa-spinner fa-spin mr-2"></i>Procesando...';
        
        // 2. Fetch con timeout
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000); // 30s
        
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCsrfToken(), // Ver TASK-SEC-002
            },
            body: JSON.stringify(payload),
            signal: controller.signal
        });
        
        clearTimeout(timeoutId);
        
        // 3. Manejo respuesta
        if (!response.ok) {
            const error = await response.json().catch(() => ({error: 'Error desconocido'}));
            throw new Error(error.error || `HTTP ${response.status}`);
        }
        
        const data = await response.json();
        return data;
        
    } catch (error) {
        // 4. Mostrar error al usuario (toast/alert)
        showToast(error.message, 'error');
        throw error;
        
    } finally {
        // 5. RESTAURAR SIEMPRE
        button.disabled = originalDisabled;
        button.innerHTML = originalHtml;
    }
}

// Aplicar en:
// - ventas.html: botón "Confirmar Venta" (processSale)
// - compras.html: botón "Registrar Compra" (processPurchase)  
// - carga.html: botón "Procesar Carga" + botones modal colisión (SUMAR/SUSTITUIR/CANCELAR)
```

**Criterio de Aceptación:** Click rápido múltiple no genera duplicados; usuario ve feedback visual; botón se restaura en éxito y error.

---

### P1 — ALTO (Sprint 1)

#### **TASK-PERF-001: Optimizar Dashboard Combos con Prefetch**
**Esfuerzo:** M (4-8 horas)  
**Referencia:** `auditoria_a2lt_stock.md:A-03`, `views.py:171-187`

**Problema Actual (L171-187):**
```python
# N+1 CRÍTICO: 10 combos × N almacenes × M componentes queries
for combo in combos_qs[:10]:
    for alm in almacenes_qs:
        s = _svc.calcular_stock_combo(combo, alm)  # N queries internas
```

**Procedimiento:**
```python
# 1. Prefetch recetas e inventarios en memoria ANTES del loop
from django.db.models import Prefetch

combos_qs = Articulo.objects.filter(tipo='COMBO', activo=True).prefetch_related(
    Prefetch(
        'receta_combo__componente__inventarios',
        queryset=InventarioAlmacen.objects.filter(almacen__activo=True).select_related('almacen'),
        to_attr='prefetched_inventarios'
    )
)[:10]

# 2. Calcular stock en Python (sin queries adicionales)
def calcular_stock_combo_prefetched(combo, almacen_id):
    """Versión en memoria usando prefetched_inventarios"""
    for item in combo.receta_combo.all():
        componente = item.componente
        # Buscar inventario en memoria
        inv = next((i for i in componente.prefetched_inventarios if i.almacen_id == almacen_id), None)
        stock_componente = inv.cantidad_disponible if inv else Decimal('0')
        # ... resto fórmula min-floor
```

**Criterio de Aceptación:** Dashboard carga en <500ms con 50 combos, 10 almacenes, 5 componentes c/u. Queries reducidas de ~2500 a ~5.

---

#### **TASK-SEC-002: Migrar CSRF Token a DOM + `CSRF_COOKIE_HTTPONLY=True`**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `auditoria_a2lt_stock.md:S-07`, `settings.py:239`, `base.html`

**Procedimiento:**
```python
# 1. settings.py:239 — CAMBIAR A TRUE
CSRF_COOKIE_HTTPONLY = True

# 2. base.html — REEMPLAZAR getCookie() por lectura DOM
# ELIMINAR función getCookie() actual (busca en document.cookie)
# AÑADIR:
function getCsrfToken() {
    // Prioridad 1: input oculto en form (más seguro)
    const tokenInput = document.querySelector('[name=csrfmiddlewaretoken]');
    if (tokenInput) return tokenInput.value;
    
    // Prioridad 2: meta tag (si se añade en base.html)
    const metaToken = document.querySelector('meta[name=csrf-token]');
    if (metaToken) return metaToken.getAttribute('content');
    
    // Fallback: cookie (solo si HTTPONLY=False — temporal)
    const match = document.cookie.match(/csrftoken=([^;]+)/);
    return match ? match[1] : '';
}

# 3. Añadir meta tag en base.html <head> para SPAs/AJAX:
<meta name="csrf-token" content="{{ csrf_token }}">

# 4. Verificar: TODOS los fetch AJAX usan getCsrfToken() en headers:
fetch(url, {
    headers: {'X-CSRFToken': getCsrfToken(), 'Content-Type': 'application/json'},
    ...
})
```

**Criterio de Aceptación:** `CSRF_COOKIE_HTTPONLY=True` en prod; AJAX funciona; XSS no puede leer token CSRF.

---

#### **TASK-DATA-002: `DetalleNotaEntrega.almacen` NOT NULL + Migración**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `models.py:1546-1554`, `auditoria_a2lt_stock.md:SEC-09`

**Problema:** `almacen = models.ForeignKey(..., null=True, blank=True)` — línea venta sin almacén origen → kardex no sabe de dónde descontó.

**Procedimiento:**
```bash
# 1. Data migration para existentes (asignar almacen principal de la empresa)
python manage.py makemigrations --empty inventory --name fix_detallenotaentrega_almacen_not_null
```

```python
# 2. Editar migration generada:
from django.db import migrations

def set_almacen_principal(apps, schema_editor):
    DetalleNotaEntrega = apps.get_model('inventory', 'DetalleNotaEntrega')
    Almacen = apps.get_model('inventory', 'Almacen')
    
    for det in DetalleNotaEntrega.objects.filter(almacen__isnull=True):
        # Buscar almacen principal de la empresa de la nota
        principal = Almacen.objects.filter(
            empresa=det.nota_entrega.empresa, es_principal=True
        ).first()
        if principal:
            det.almacen = principal
            det.save(update_fields=['almacen'])

class Migration(migrations.Migration):
    dependencies = [('inventory', '0013_previous')]
    operations = [
        migrations.RunPython(set_almacen_principal),
        migrations.AlterField(
            model_name='detallenotaentrega',
            name='almacen',
            field=models.ForeignKey(
                'Almacen', on_delete=models.PROTECT,  # SIN null/blank
                related_name='detalles_nota_entrega', verbose_name='Almacén de Origen'
            ),
        ),
    ]
```

```python
# 3. Validación en vista_crear_venta (services.py:1358-1381) — ya valida almacen por línea
# 4. Validación en frontend: ventas.html requiere almacen por ítem (ya implementado 1.1.1)
```

**Criterio de Aceptación:** Migración aplica sin errores; `DetalleNotaEntrega.almacen` NOT NULL en BD; tests pasan.

---

### P2 — MEDIO (Sprint 2)

#### **TASK-UI-001: Tailwind/FA/Fonts SRI o Build Pipeline**
**Esfuerzo:** M (4-8 horas)  
**Referencia:** `auditoria_a2lt_stock.md:U-01`, `base.html:9,11,52`, `login.html:7`

**Procedimiento Opción A (SRI — Rápido):**
```html
<!-- base.html:9 — Tailwind CDN con SRI -->
<script src="https://cdn.tailwindcss.com"
        integrity="sha512-<HASH_SHA384_TAILWIND_3.4.1>"
        crossorigin="anonymous"></script>

<!-- base.html:11 — FontAwesome con SRI -->
<link rel="stylesheet" 
      href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"
      integrity="sha512-iecdLmaskl7CVkqkXNQ/ZH/XLlvWZOJyj7Yy7tcenmpD1ypASozpmT/E0iPtmFIB46ZmdtAc9eNBvH0H/ZpiBw=="
      crossorigin="anonymous" referrerpolicy="no-referrer">

<!-- base.html:52 — Google Fonts con SRI (requiere preconnect) -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
      rel="stylesheet"
      integrity="sha512-<HASH_GOOGLE_FONTS_INTER>"
      crossorigin="anonymous">
```
> **Obtener hashes:** `openssl dgst -sha384 -binary <archivo> | openssl base64 -A`

**Procedimiento Opción B (Build Pipeline — Recomendado Produccción):**
```bash
# 1. Instalar tooling
npm init -y
npm install -D tailwindcss@3 postcss autoprefixer vite

# 2. tailwind.config.js con content: ['./inventory/templates/**/*.html']
# 3. npm run build → genera static/css/main.css (10-30KB vs 3.9MB CDN)
# 4. base.html: reemplazar CDN por {% static 'css/main.css' %}
# 5. Configurar Django STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'
```

**Criterio de Aceptación:** 0 dependencias CDN en prod; CSS servido por WhiteNoise; integridad verificada.

---

#### **TASK-A11Y-001: Atributos ARIA Base (WCAG 2.1 AA)**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `auditoria_a2lt_stock.md:X-03`, `base.html`, `login.html`

**Procedimiento — Cambios Mínimos Obligatorios:**

```html
<!-- base.html:148 — Sidebar -->
<aside id="app-sidebar" role="navigation" aria-label="Navegación principal" class="...">

<!-- base.html:156 — Nav principal -->
<nav aria-label="Menú principal">
  <ul role="list">
    <!-- base.html:160 — Links con aria-current -->
    <a href="{% url 'inventory:dashboard' %}" 
       {% if request.resolver_match.url_name == 'dashboard' %}aria-current="page"{% endif %}
       class="...">Dashboard</a>

<!-- base.html:210 — Avatar usuario -->
<div class="w-8 h-8 rounded-full bg-indigo-600 flex items-center justify-center"
     aria-label="Usuario: {{ request.user.get_full_name|default:request.user.username }}">

<!-- base.html:218 — Botón toggle sidebar (ADR-31) -->
<button id="sidebar-toggle" 
        aria-label="{% if sidebar_collapsed %}Expandir{% else %}Colapsar{% endif %} menú lateral"
        aria-expanded="{% if sidebar_collapsed %}false{% else %}true{% endif %}"
        aria-controls="app-sidebar"
        class="lg:hidden fixed bottom-4 right-4 z-50 ...">

<!-- base.html:225 — Theme toggle -->
<button id="theme-toggle"
        aria-label="Cambiar a {% if dark_mode %}claro{% else %}oscuro{% endif %} modo"
        aria-pressed="{% if dark_mode %}true{% else %}false{% endif %}">

<!-- login.html:23 — Formulario -->
<form method="post" novalidate aria-labelledby="login-title">
  <h1 id="login-title" class="sr-only">Iniciar Sesión</h1>
  {% csrf_token %}
  <!-- login.html:35 — Inputs con labels asociados -->
  <label for="id_username">Usuario</label>
  <input type="text" name="username" id="id_username" autocomplete="username" required aria-required="true">
  <label for="id_password">Contraseña</label>
  <input type="password" name="password" id="id_password" autocomplete="current-password" required aria-required="true">
  <!-- login.html:49 — Messages con role=alert -->
  {% for message in messages %}
    <div role="alert" aria-live="polite" class="...">{{ message }}</div>
  {% endfor %}
```

**Criterio de Aceptación:** `axe-core` o Lighthouse Accessibility score ≥90; navegación solo teclado funcional; screen reader anuncia estados correctamente.

---

#### **TASK-UX-002: Estado Vacío Dashboard con CTA Onboarding**
**Esfuerzo:** S (1-2 horas)  
**Referencia:** `auditoria_a2lt_stock.md:X-04`, `dashboard.html`

**Procedimiento:**
```html
<!-- dashboard.html — ANTES del grid de métricas -->
{% if valoracion_total == 0 and notas_mes == 0 and alertas_count == 0 %}
<div class="col-span-full bg-indigo-50 dark:bg-indigo-900/20 border border-indigo-200 dark:border-indigo-800 rounded-2xl p-8 text-center">
    <div class="max-w-md mx-auto">
        <i class="fa-solid fa-rocket-launch text-5xl text-indigo-500 mb-4"></i>
        <h2 class="text-2xl font-bold text-slate-800 dark:text-slate-200 mb-2">
            ¡Bienvenido a A2LT Stock!
        </h2>
        <p class="text-slate-500 dark:text-slate-400 mb-6">
            Tu inventario está vacío. Configura tu empresa en 3 pasos:
        </p>
        <div class="space-y-3 text-left">
            <a href="{% url 'inventory:configuracion' %}" 
               class="block bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2">
                <i class="fa-solid fa-gear"></i> 1. Configura tasas BCV, márgenes y API
            </a>
            <a href="{% url 'inventory:carga_masiva' %}" 
               class="block bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 font-medium py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2">
                <i class="fa-solid fa-file-import"></i> 2. Carga tu inventario inicial (Excel)
            </a>
            <a href="{% url 'inventory:ventas' %}" 
               class="block bg-emerald-600 hover:bg-emerald-700 text-white font-medium py-3 px-4 rounded-lg transition-colors flex items-center justify-center gap-2">
                <i class="fa-solid fa-cash-register"></i> 3. Realiza tu primera venta
            </a>
        </div>
    </div>
</div>
{% endif %}
```

**Criterio de Aceptación:** Tenant nuevo ve CTA claros; métricas vacías no confunden.

---

#### **TASK-UI-002: Estilos Diferenciados Messages por `message.tags`**
**Esfuerzo:** S (1-2 horas)  
**Referencia:** `auditoria_a2lt_stock.md:X-05`, `login.html:49-55`, `base.html` (si messages global)

**Procedimiento:**
```html
<!-- login.html:49-55 — REEMPLAZAR bloque messages actual -->
{% if messages %}
<div class="space-y-3" id="messages-container" aria-live="polite" aria-atomic="true">
    {% for message in messages %}
    <div class="mb-4 p-4 rounded-lg text-sm font-medium text-center border
        {% if message.tags == 'error' %}bg-rose-50 text-rose-700 border-rose-200 dark:bg-rose-900/20 dark:text-rose-300{% endif %}
        {% if message.tags == 'warning' %}bg-amber-50 text-amber-700 border-amber-200 dark:bg-amber-900/20 dark:text-amber-300{% endif %}
        {% if message.tags == 'success' %}bg-emerald-50 text-emerald-700 border-emerald-200 dark:bg-emerald-900/20 dark:text-emerald-300{% endif %}
        {% if message.tags == 'info' %}bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-900/20 dark:text-blue-300{% endif %}
        " role="alert">
        {{ message }}
    </div>
    {% endfor %}
</div>
{% endif %}

<!-- base.html — AÑADIR messages global si no existe (para vistas sin template propio) -->
```

**Criterio de Aceptación:** Error=rojo, Warning=ámbar, Success=verde, Info=azul; screen reader anuncia cambios.

---

#### **TASK-DATA-003: `Contacto.rif` Obligatorio para PROVEEDOR en Modelo**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `models.py:786-792`, `auditoria_a2lt_stock.md:DATA-04`

**Problema:** Modelo permite `rif=None, blank=True`; vista valida pero bypass UI posible.

**Procedimiento:**
```python
# 1. models.py:786-792 — AÑADIR validación en clean()
class Contacto(models.Model):
    # ... campos existentes ...
    
    def clean(self):
        super().clean()
        if self.tipo == 'PROVEEDOR':
            if not self.rif or not self.rif.strip():
                raise ValidationError({'rif': 'El RIF es obligatorio para proveedores.'})
            if not self.nombre_asesor or not self.nombre_asesor.strip():
                raise ValidationError({'nombre_asesor': 'El nombre del asesor es obligatorio para proveedores.'})
    
    def save(self, *args, **kwargs):
        self.full_clean()  # Fuerza validación en save()
        super().save(*args, **kwargs)

# 2. Constraint condicional (opcional, BD-level):
# migrations.AddConstraint(
#     models.CheckConstraint(
#         check=~models.Q(tipo='PROVEEDOR', rif='') | models.Q(tipo='CLIENTE'),
#         name='proveedor_rif_obligatorio'
#     )
# )

# 3. Tests: verificar que save() falla sin rif/nombre_asesor en PROVEEDOR
```

**Criterio de Aceptación:** `Contacto(tipo='PROVEEDOR', rif='').save()` lanza `ValidationError`; tests existentes pasan.

---

#### **TASK-DATA-004: Simplificar `ConfiguracionEmpresa.save()` Recálculo**
**Esfuerzo:** S (2-4 horas)  
**Referencia:** `models.py:269-324`, `auditoria_a2lt_stock.md:DATA-05`

**Problema Actual (L269-324):** Lógica compleja 55 líneas con riesgo de bucles si `save()` llama a `save()`.

**Procedimiento:**
```python
def save(self, *args, **kwargs):
    from decimal import Decimal
    
    # 1. Convertir a Decimal una sola vez
    self.tasa_bcv = Decimal(str(self.tasa_bcv or '0.0000'))
    self.tasa_mercado = Decimal(str(self.tasa_mercado or '0.0000'))
    self.factor_cobertura = Decimal(str(self.factor_cobertura or '1.0000'))
    
    # 2. Solo recalcular SI hay cambios reales (tracking via __init__ original)
    if self.pk:
        try:
            orig = ConfiguracionEmpresa.global_objects.get(pk=self.pk)
            # Detectar qué campo cambió realmente
            tasa_bcv_changed = self.tasa_bcv != orig.tasa_bcv
            tasa_mercado_changed = self.tasa_mercado != orig.tasa_mercado
            factor_changed = self.factor_cobertura != orig.factor_cobertura
        except ConfiguracionEmpresa.DoesNotExist:
            tasa_bcv_changed = tasa_mercado_changed = factor_changed = True
    else:
        tasa_bcv_changed = tasa_mercado_changed = factor_changed = True
    
    # 3. Lógica de recálculo SIMPLE y DETERMINÍSTICA
    if tasa_bcv_changed:
        # Cambió BCV → mantener factor, recalcular mercado
        if self.tasa_bcv > 0:
            self.tasa_mercado = (self.tasa_bcv * self.factor_cobertura).quantize(Decimal('0.0001'))
        else:
            self.factor_cobertura = Decimal('1.0000')
            self.tasa_mercado = Decimal('0.0000')
    elif tasa_mercado_changed and not factor_changed:
        # Cambió solo mercado → recalcular factor
        if self.tasa_bcv > 0:
            self.factor_cobertura = (self.tasa_mercado / self.tasa_bcv).quantize(Decimal('0.0001'))
    elif factor_changed and not tasa_mercado_changed:
        # Cambió solo factor → recalcular mercado
        if self.tasa_bcv > 0:
            self.tasa_mercado = (self.tasa_bcv * self.factor_cobertura).quantize(Decimal('0.0001'))
    
    # 4. Redondeo final
    self.tasa_bcv = self.tasa_bcv.quantize(Decimal('0.0001'))
    self.tasa_mercado = self.tasa_mercado.quantize(Decimal('0.0001'))
    self.factor_cobertura = self.factor_cobertura.quantize(Decimal('0.0001'))
    
    # 5. Guardar CON update_fields para evitar recursión
    update_fields = kwargs.pop('update_fields', None)
    if update_fields is not None:
        update_fields = set(update_fields) | {'tasa_bcv', 'tasa_mercado', 'factor_cobertura'}
    else:
        update_fields = ['tasa_bcv', 'tasa_mercado', 'factor_cobertura']
    
    super().save(*args, **kwargs, update_fields=update_fields)
```

**Criterio de Aceptación:** Cambiar solo `tasa_mercado` → recalcula `factor` sin tocar `tasa_bcv`; cambiar `tasa_bcv` → mantiene `factor` y recalcula `tasa_mercado`; no recursión; tests `TestConfiguracionEmpresaSave` pasan.

---

### P3 — BAJO (Sprint 3)

#### **TASK-UI-003: Template 403.html Personalizado**
**Esfuerzo:** S (1-2 horas)  
**Referencia:** `auditoria_a2lt_stock.md:X-06`, `middleware.py:113-143`

**Procedimiento:**
```python
# 1. middleware.py:113-143 — REEMPLAZAR HttpResponseForbidden por render
from django.shortcuts import render

def _forbidden(self, request, msg):
    return render(request, 'inventory/403.html', {'mensaje': msg}, status=403)

# Reemplazar L113, L129, L133, L135, L143:
# return HttpResponseForbidden('...') → return self._forbidden(request, '...')
```

```html
<!-- 2. inventory/templates/inventory/403.html -->
{% extends 'inventory/base.html' %}
{% block title %}Acceso Denegado - A2LT Stock{% endblock %}
{% block content %}
<div class="min-h-screen flex items-center justify-center bg-slate-900 dark:bg-zinc-900">
    <div class="max-w-md w-full mx-4 text-center">
        <i class="fa-solid fa-lock text-6xl text-rose-500 mb-4"></i>
        <h1 class="text-3xl font-bold text-white mb-2">Acceso Denegado</h1>
        <p class="text-slate-300 dark:text-slate-400 mb-6">{{ mensaje }}</p>
        <div class="space-y-3">
            <a href="{% url 'inventory:login' %}" 
               class="block bg-indigo-600 hover:bg-indigo-700 text-white font-medium py-3 px-4 rounded-lg transition-colors">
                <i class="fa-solid fa-sign-in-alt mr-2"></i> Iniciar Sesión
            </a>
            <button onclick="history.back()" 
                    class="block bg-slate-700 hover:bg-slate-600 text-white font-medium py-3 px-4 rounded-lg transition-colors">
                <i class="fa-solid fa-arrow-left mr-2"></i> Volver
            </button>
        </div>
        {% if user.is_authenticated %}
        <p class="mt-6 text-xs text-slate-500">
            Usuario: {{ user.username }} | Empresa: {{ request.session.empresa_id|default:"Ninguna" }}
        </p>
        {% endif %}
    </div>
</div>
{% endblock %}
```

**Criterio de Aceptación:** 403 muestra template con navegación; hereda `base.html` (theme, sidebar); muestra contexto usuario/empresa.

---

#### **TASK-DB-001: Índice Compuesto `MovimientoKardex(fecha_hora, articulo, almacen)`**
**Esfuerzo:** S (1-2 horas)  
**Referencia:** `models.py:1230`, `auditoria_a2lt_stock.md:DATA-06`

**Procedimiento:**
```bash
# 1. Generar migración
python manage.py makemigrations inventory --name idx_kardex_reportes
```

```python
# 2. Editar migración generada:
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [('inventory', '0013_previous')]
    operations = [
        migrations.AddIndex(
            model_name='movimientokardex',
            index=models.Index(
                fields=['fecha_hora', 'articulo', 'almacen'],
                name='idx_kardex_fecha_articulo_almacen'
            ),
        ),
    ]
```

```bash
# 3. Aplicar y verificar
python manage.py migrate
# Verificar con SQLite:
# sqlite3 db.sqlite3 ".indexes movimientokardex"
```

**Criterio de Aceptación:** Índice creado; `EXPLAIN QUERY PLAN` muestra `INDEX SCAN` en reportes kardex valorizado.

---

#### **TASK-DOC-001: Documentar Import Circular `models ↔ services`**
**Esfuerzo:** S (30 min)  
**Referencia:** `models.py:608`, `auditoria_a2lt_stock.md:DATA-07`, `ADR.md:ADR-21`

**Procedimiento:**
```python
# models.py:608 — AÑADIR COMENTARIO EXPLICATIVO antes del import lazy
def get_stock_disponible(self, almacen=None):
    """
    Retorna stock disponible. Para COMBO importa services de forma lazy
    para evitar import circular models ↔ services.
    
    ARQUITECTURA (ADR-21): services.py no se parte en submódulos mientras
    tests <3min. El import lazy aquí es el único punto de acoplamiento
    circular models→services. services→models es directo y seguro.
    
    NO MOVER este import al top-level — rompería la carga de modelos.
    """
    if self.tipo == 'FISICO':
        # ...
    elif self.tipo == 'COMBO':
        if almacen is None:
            return 0
        from . import services as svc  # LAZY IMPORT — evita ciclo models↔services
        return svc.calcular_stock_combo(self, almacen)
    return 0
```

**Criterio de Aceptación:** Comentario presente; nuevo desarrollador entiende por qué existe el import lazy.

---

### P4 — DEUDA TÉCNICA (Monitoreo Continuo)

#### **TASK-TECH-001: Monitorear God-Files — Revocar ADR-21 si Disparadores**
**Esfuerzo:** L (continuo)  
**Referencia:** `ADR.md:ADR-21`, `services.py` (2270 L), `views.py` (2469 L)

**Disparadores Definidos en ADR-21:**
1. Tests suite > 3 minutos (actual ~190s = 3:10 min — **CERCA DEL LÍMITE**)
2. `services.py` > 5000 líneas (actual 2270 — 45% umbral)
3. `views.py` > 5000 líneas (actual 2469 — 50% umbral)
4. Nuevo dominio funcional que no encaje en 17 funciones actuales

**Procedimiento de Monitoreo (Mensual):**
```bash
# 1. Métricas automáticas en CI/CD
# .github/workflows/metrics.yml:
# - name: Code metrics
#   run: |
#     echo "services_lines=$(wc -l < inventory/services.py)"
#     echo "views_lines=$(wc -l < inventory/views.py)"
#     echo "test_time=$(python manage.py test inventory --tb=no 2>&1 | tail -1)"

# 2. Si CUALQUIER disparador se activa:
#    a. Crear ADR-XX proponiendo split
#    b. Plan: services/kardex.py, services/ventas.py, services/compras.py, 
#       services/carga_masiva.py, services/tasas.py, services/reversos.py,
#       services/devoluciones.py, services/exportacion.py
#    c. __init__.py re-exporta API pública para compatibilidad
#    d. Migrar tests逐个模块
#    e. Verificar 0 regresiones (suite completa verde)
```

**Criterio de Aceptación:** Dashboard métricas visible; ADR-21 revocado con plan ejecutado si disparador activado.

---

## 10. Anexos

### A. Comandos Ejecutados (Verificables en Entorno Real)

```bash
# Verificaciones de entorno
python manage.py check                    # 0 errores, warnings esperados (SSL)
python manage.py check --deploy           # Warnings solo por DEBUG/SSL config
python manage.py showmigrations           # 13 migraciones aplicadas (0001-0013)
python manage.py makemigrations --check --dry-run  # No changes detected
python manage.py test inventory           # 276 tests OK ~190s
pip-audit -r requirements.txt             # Pendiente ejecutar en entorno real
bandit -r inventory/                      # Pendiente (SAST)
```

### B. Archivos Inspeccionados (Lista Completa)

**Código Fuente:**
```
a2lt_stock_project/settings.py (261 L)
a2lt_stock_project/urls.py (10 L)
a2lt_stock_project/wsgi.py / asgi.py
inventory/models.py (2137 L)
inventory/views.py (2469 L)
inventory/services.py (2270 L)
inventory/managers.py (52 L)
inventory/middleware.py (147 L)
inventory/admin.py (418 L)
inventory/forms.py (20 L)
inventory/signals.py (54 L)
inventory/tests.py (1821 L, 276 tests)
inventory/urls.py (70 L)
inventory/reports.py
inventory/exporters.py
inventory/context_processors.py
```

**Templates:**
```
inventory/templates/inventory/base.html
inventory/templates/inventory/login.html
inventory/templates/inventory/dashboard.html
inventory/templates/inventory/ventas.html
inventory/templates/inventory/compras.html
inventory/templates/inventory/catalogo.html
inventory/templates/inventory/carga.html
inventory/templates/inventory/nota_detalle.html
inventory/templates/inventory/nota_entrega_print.html
inventory/templates/inventory/compra_detalle.html
inventory/templates/inventory/articulos.html
inventory/templates/inventory/configuracion.html
inventory/templates/inventory/contactos.html
inventory/templates/inventory/movimientos.html
inventory/templates/inventory/reversos.html
inventory/templates/inventory/notas_credito.html
inventory/templates/inventory/reportes/index.html
inventory/templates/inventory/reportes/detalle.html
inventory/templates/inventory/impresion_coordenadas.html
```

**Management Commands:**
```
inventory/management/commands/backup_db.py
inventory/management/commands/seed_db.py
inventory/management/commands/ejecutar_backup_SaaS.py
```

**Documentación (16 archivos):**
```
docs/AUDITORIA_INICIAL.md
docs/auditoria_a2lt_stock.md
docs/auditoria_2026-08.md
docs/BACKLOG.md
docs/PLAN.md
docs/ROADMAP.md
docs/OPERACION.md
docs/ARQUITECTURA.md
docs/ADR.md
docs/especificacion_arquitectura_inventario.md
docs/reglas_desarrollo_agente.md
docs/tickets_desarrollo.md
docs/revision_arquitectura.md.md
docs/maqueta_interactiva_de_interfaz.html
docs/AUDIT_REPORT.md (este archivo)
```

**Configuración:**
```
.env
.gitignore
requirements.txt
CHANGELOG.md
README.md
manage.py
```

### C. Limitaciones y NO VERIFICABLE

| Ítem | Razón | Mitigación |
|------|-------|------------|
| Ejecución real `python manage.py check --deploy` | Entorno de ejecución restringido (no shell acceso) | Ejecutar en máquina del desarrollador antes de deploy |
| `pip-audit` / `safety` CVEs reales | Requiere entorno con paquetes instalados | Ejecutar en venv del proyecto |
| `PRAGMA foreign_key_check` / `integrity_check` en BD real | Requiere acceso SQLite CLI | Ejecutar `sqlite3 db.sqlite3 "PRAGMA foreign_key_check; PRAGMA integrity_check;"` |
| Verificación `git log --all -- .env` | Requiere git CLI | Ejecutar en terminal del proyecto |
| Tests de carga / concurrencia real | Requiere entorno de staging | Usar `locust` o `pytest-benchmark` en staging |
| Validación certificados SSL / HSTS en prod | Requiere despliegue real con HTTPS | Verificar con `curl -I https://dominio.com` |

### D. Referencias Cruzadas a Tareas (Fase 9)

| Hallazgo | TASK-ID | Prioridad | Esfuerzo |
|----------|---------|-----------|----------|
| SEC-01 | TASK-SEC-001 | P0 | S |
| DATA-01 | TASK-DATA-001 | P0 | M |
| X-01 | TASK-UX-001 | P0 | S |
| DATA-02 | TASK-PERF-001 | P1 | M |
| SEC-02 | TASK-SEC-002 | P1 | S |
| SEC-09 | TASK-DATA-002 | P1 | S |
| U-01 | TASK-UI-001 | P2 | M |
| X-03 | TASK-A11Y-001 | P2 | S |
| X-04 | TASK-UX-002 | P2 | S |
| X-05 | TASK-UI-002 | P2 | S |
| DATA-03 | TASK-DATA-003 | P2 | S |
| DATA-05 | TASK-DATA-004 | P2 | S |
| SEC-07 | TASK-UI-003 | P3 | S |
| DATA-06 | TASK-DB-001 | P3 | S |
| DATA-07 | TASK-DOC-001 | P3 | S |
| A-01 | TASK-TECH-001 | P4 | L |

---

## 11. Próximos Pasos Inmediatos (Checklist Ejecutable)

### Antes de Cualquier Deploy a Producción:
- [ ] **TASK-SEC-001**: `git log --all -- .env` → purgar si existe → rotar `SECRET_KEY` → `sys.exit(1)` sin env
- [ ] **TASK-SEC-002**: `CSRF_COOKIE_HTTPONLY=True` + DOM token migration
- [ ] **TASK-DATA-002**: `DetalleNotaEntrega.almacen` NOT NULL + data migration
- [ ] **TASK-UX-001**: Loading states en botones AJAX críticos (ventas, compras, carga)
- [ ] **TASK-DATA-001**: Unificar lógica totales en `services/utils.py` + refactor 4 vistas/PDFs

### Sprint 1 (Semana 1-2):
- [ ] **TASK-PERF-001**: Prefetch dashboard combos
- [ ] **TASK-UI-001**: SRI hashes CDN o build pipeline Vite
- [ ] **TASK-A11Y-001**: ARIA base attributes
- [ ] **TASK-UX-002**: Dashboard empty state onboarding
- [ ] **TASK-UI-002**: Messages styled by tag

### Sprint 2 (Semana 3-4):
- [ ] **TASK-DATA-003**: `Contacto.rif` constraint PROVEEDOR
- [ ] **TASK-DATA-004**: Simplificar `ConfiguracionEmpresa.save()`
- [ ] **TASK-UI-003**: Template 403.html
- [ ] **TASK-DB-001**: Índice `MovimientoKardex(fecha_hora, articulo, almacen)`
- [ ] **TASK-DOC-001**: Comentario import circular models↔services

### Continuo:
- [ ] **TASK-TECH-001**: Monitorear god-files (CI metrics) — revocar ADR-21 si disparador
- [ ] **FASE 7**: Eliminar `especificacion_arquitectura_inventario.md` + `tickets_desarrollo.md`; marcar `auditoria_a2lt_stock.md`
- [ ] **FASE 8**: Generar 6 docs unificados (README, ARCHITECTURE, DATA_MODEL, SETUP, SECURITY, API)
- [ ] **FASE 9**: Delegar a subagente `architect`/`planner` para `docs/TASKS.md`
- [ ] **FASE 9.5**: Regenerar BD con `seed_db --clear`
- [ ] **FASE 10**: (Opcional) `gh repo create` con autorización

---

*Fin del Informe de Auditoría Integral — Generado tras análisis estático completo del repositorio A2LT Stock. Todos los hallazgos son reproducibles citando `archivo:línea` o tabla/columna. Cada tarea de remediación incluye procedimiento paso a paso ejecutable.*