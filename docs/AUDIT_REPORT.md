# Informe de Auditoría Integral — A2LT Stock

**Versión del informe:** 3.0 (por bloques)
**Fecha de auditoría:** 2026-10-19
**Auditor:** Sesión de auditoría asistida (análisis estático + verificación dinámica sobre el repo real)
**Alcance:** Repositorio `a2lt_stock_project` — Django 6.0.6 multi-tenant on-premise, SQLite WAL, Python 3.14
**Commit auditado:** `0585207` (HEAD de `main`, 3 commits por delante de `origin/main`)
**Sustituye a:** `AUDIT_REPORT.md` v1 (2026-10-18), que contenía 5 afirmaciones sin verificación runtime (ver §13).

---

## 1. Resumen ejecutivo

A2LT Stock es un sistema de inventario y facturación para comercios venezolanos, con soporte cambiario dual (BCV oficial + mercado paralelo) y factor de cobertura. Arquitectura multi-tenant por `ContextVar` + `EmpresaManager`, Kárdex transaccional atómico, snapshots financieros inmutables por transacción.

**Estado verificado (2026-10-19):**

| Dimensión | Resultado | Verificación |
|---|---|---|
| Test suite | `Ran 358 tests — OK (skipped=6)` | `python manage.py test inventory` |
| Duración | 92 segundos | — |
| Migraciones | 18/18 aplicadas, `makemigrations --check` sin cambios | `showmigrations` + `makemigrations --check --dry-run` |
| BD SQLite | 31 tablas, `integrity_check: ok`, `foreign_key_check: 0 filas` | `PRAGMA` sobre copia en `%TEMP%` |
| `check --deploy` | 5 warnings (W004, W008, W012, W016, W018) | `python manage.py check --deploy` |
| Historial git | `.env` nunca commiteado; `.gitignore` lo cubre | `git log --all -- .env` vacío |
| Reproducibilidad | 3 commits locales no pusheados | `git log origin/main..HEAD` |

**Distribución de hallazgos:**

| Categoría | Críticos | Altos | Medios | Bajos | Total |
|---|---|---|---|---|---|
| Seguridad (SEC-*) | 1 | 1 | 3 | 2 | 7 |
| Integridad de datos (DATA-*) | 0 | 2 | 6 | 2 | 10 |
| Bugs de código (BUG-*) | 1 | 3 | 0 | 0 | 4 |
| Estructurales de modelo (EST-*) | 0 | 4 | 4 | 3 | 11 |
| Del informe original, aún abiertos (X-*, U-*) | 0 | 1 | 3 | 1 | 5 |
| **Total** | **2** | **11** | **16** | **8** | **37** |

**Veredicto:** **APROBADO CON CONDICIONES.**

El sistema es funcionalmente sólido, con una base arquitectónica bien diseñada y una suite de tests que cubre los flujos críticos (Kárdex, combos, ventas, compras, NC, reversos, multi-tenant, SSRF, rate-limit, password validation). **Ningún hallazgo bloquea el uso operativo interno.**

Sin embargo:

- **2 hallazgos CRÍTICOS** impiden exponerlo a internet o comercializarlo: el fallback inseguro de `SECRET_KEY` (SEC-01) y un `NameError` latente en `DetalleCompraQuerySet.para_empresa` (BUG-04).
- **11 hallazgos ALTOS** deben resolverse antes de operación real con clientes: `DEBUG=True` en `.env` (W018), `CSRF_COOKIE_HTTPONLY=False` (SEC-02), ausencia de constraints de inmutabilidad en documentos procesados (EST-02), correlativos sin lock (EST-03), y la duplicación de lógica financiera que ya causó divergencia real entre pantalla y PDF (DATA-01).
- **La suite verde (358/358)** es una base de confianza, pero **no cubre los invariantes estructurales** (EST-01 a EST-11): el modelo no enforcea los invariantes que el código asume. Eso es la deuda más importante a resolver.

**Decisión recomendada:** resolver P0 y P1 (ver §14) antes de cualquier comercialización; los P2/P3 pueden convivir con operación interna.

---

## 2. Metodología y limitaciones

### 2.1 Enfoque

Esta auditoría combinó **análisis estático del código** con **verificación dinámica sobre el repo real**. No es una auditoría teórica: cada afirmación cuantitativa está respaldada por un comando ejecutado cuya salida se transcribe en §4.

**Fases:**

1. **Descubrimiento** — lectura del árbol del proyecto, `INSTALLED_APPS`, settings, middleware.
2. **Análisis estático** — lectura de `models.py`, `services.py`, `views.py`, `managers.py`, `middleware.py`, `admin.py`, `signals.py`, `forms.py`, `urls.py`, `settings.py`, `tests.py`, `base.html`.
3. **Verificación dinámica** — ejecución de la suite, `check --deploy`, `makemigrations --check`, consultas PRAGMA sobre copia de la BD, inspección de historial git.
4. **Contraste** — validación cruzada con `AUDIT_REPORT.md` v1, `docs/auditoria_a2lt_stock.md` (2026-07), `docs/auditoria_2026-08.md`.
5. **Clasificación** — severidad (CRÍTICA/ALTA/MEDIA/BAJA) × probabilidad → matriz de riesgo (§12).

### 2.2 Criterios de severidad (escala propia)

| Nivel | Criterio |
|---|---|
| **CRÍTICA** | Explotable sin autenticación, pérdida/corrupción inminente de datos, o la app no arranca en producción |
| **ALTA** | Explotable con autenticación básica, corrupción probable, incumplimiento legal (PII), o invariante arquitectónico no enforced |
| **MEDIA** | Requiere condiciones especiales, degradación progresiva, o mala práctica grave sin explotación directa |
| **BAJA** | Defensa en profundidad, code smell, deuda técnica menor |
| **INFO** | Observación sin impacto directo |

### 2.3 Limitaciones explícitas

**Lo que SÍ se verificó:**

- 358 tests ejecutados (0 failures, 0 errors, 6 skipped)
- 18 migraciones aplicadas vs 18 archivos de migración
- `makemigrations --check --dry-run` → "No changes detected"
- `check --deploy` → 5 warnings identificados
- 31 tablas físicas en `db.sqlite3` (listadas una por una)
- `PRAGMA integrity_check` → `ok`
- `PRAGMA foreign_key_check` → 0 filas
- `.env` en historial git → vacío
- `.gitignore` cubre `.env` y `.env.*`
- 3 commits locales por delante de `origin/main`

**Lo que NO se verificó (limitación declarada):**

| Ítem | Razón | Cómo verificarlo |
|---|---|---|
| Explotabilidad real de BUG-04 (`NameError` en `DetalleCompraQuerySet.para_empresa`) | Requiere ejecución con tenant activo; no lo cubre la suite | `python manage.py shell -c "from inventory.models import DetalleDocumentoCompra; DetalleDocumentoCompra.objects.para_empresa()"` |
| CVEs reales en dependencias | No se ejecutó `pip-audit` ni `safety` | `pip-audit -r requirements.txt` en el venv |
| Análisis SAST sobre el código | No se ejecutó `bandit` ni `semgrep` | `bandit -r inventory/` |
| Comportamiento bajo concurrencia real (más allá del test skipped) | SQLite no soporta escritura multi-thread; requiere staging con PostgreSQL | Test de carga con `locust` o similar |
| Configuración de producción real (HTTPS, proxy, DNS) | No hay despliegue en staging | Verificación manual post-deploy |
| Rendimiento con >10K registros | Tests usan fixtures pequeños | Benchmark con datos realistas |
| `reports.py`, `exporters.py` completos | Solo lectura parcial; no se auditaron en detalle | Auditoría focalizada |
| Templates HTML internos (excepto `base.html`, `login.html`) | Solo se leyeron los críticos | Auditoría focalizada |

**Lo que se declaró como "no verificable" no se clasificó como hallazgo**, sino como nota de contexto.

---

## 3. Contexto descubierto

### 3.1 Stack técnico detallado

| Componente | Versión / Valor | Evidencia |
|---|---|---|
| **Framework** | Django 6.0.6 | `requirements.txt:4` |
| **Python** | 3.14 (venv en `.venv\Scripts\python.exe`) | `py -0p` output |
| **Base de datos** | SQLite 3 con WAL | `settings.py:96-111` |
| PRAGMA `journal_mode` | WAL | `settings.py:103` |
| PRAGMA `synchronous` | NORMAL | `settings.py:104` |
| PRAGMA `foreign_keys` | ON | `settings.py:105` |
| PRAGMA `busy_timeout` | 5000 ms | `settings.py:106` |
| PRAGMA `cache_size` | 64 MB (`-64000` = KB) | `settings.py:107` |
| Timeout conexión | 20 s | `settings.py:101` |
| **openpyxl** | 3.1.5 | `requirements.txt:7` |
| **reportlab** | 5.0.0 | `requirements.txt:9` |
| **requests** | 2.34.2 | `requirements.txt:10` |
| **Pillow** | 12.3.0 | `requirements.txt:8` |
| **sqlparse** | 0.5.5 | `requirements.txt:11` |
| **tzdata** | 2026.2 | `requirements.txt:12` |
| **Frontend** | Tailwind CSS (CDN) + Bootstrap Icons (CDN) | `base.html:9,11` |
| **Font** | Inter (Google Fonts CDN) | `base.html:52` |
| **PDF engine** | ReportLab, A4 portrait | `views.py` `generar_pdf_*` |
| **Excel engine** | openpyxl, `read_only=True`, `data_only=True` | `services.py:549, 829` |
| **SO target** | Windows 10/11 64-bit (on-premise) | `OPERACION.md:10` |
| **Idioma** | es-VE | `settings.py:136` |
| **Zona horaria** | America/Caracas | `settings.py:137` |

**Ausencias deliberadas (reglas del producto, documentadas en `docs/PLAN.md`):**

- **Sin PostgreSQL** — SQLite WAL con backups `VACUUM INTO`
- **Sin Celery/Redis** — no hay tareas asíncronas críticas
- **Sin DRF** — frontend monolítico Django + fetch API
- **Sin JWT** — sesiones Django nativas
- **Sin dockerización** — instalación on-premise en Windows
- **Sin build JS** — Tailwind por CDN (ver SEC-05)

### 3.2 Arquitectura por capas

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Browser (Tailwind CDN)                      │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ HTTP + CSRF (fetch con X-CSRFToken)
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                     Django Middleware Stack                          │
│                                                                      │
│  1. SecurityMiddleware                                               │
│  2. SessionMiddleware                                                │
│  3. CommonMiddleware                                                 │
│  4. CsrfViewMiddleware                                               │
│  5. AuthenticationMiddleware                                         │
│  6. MessageMiddleware                                                │
│  7. XFrameOptionsMiddleware                                          │
│  8. inventory.middleware.TenantMiddleware  ◄── CRÍTICO               │
│     ├─ Valida 5 condiciones                                          │
│     └─ Setea ContextVar current_empresa                              │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ request (con ContextVar activo)
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                Views (adaptadores HTTP → services)                   │
│                                                                      │
│  views.py (~2470 líneas)  — sin lógica de negocio                    │
│  reports.py               — reportes de solo lectura                 │
│  exporters.py             — CSV / PDF export                         │
└───────────────────────────┬──────────────────────────────────────────┘
                            │ solo vía services
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                services.py — ÚNICA capa autorizada                   │
│                                                                      │
│  17-19 funciones públicas                                            │
│  ~2270 líneas                                                        │
│  ADR-21: no partir mientras suite <3min                              │
│                                                                      │
│  Regla Sagrada: SOLO registrar_movimiento() muta stock               │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│           Models + EmpresaManager (filtrado por ContextVar)          │
│                                                                      │
│  21 clases (19 tablas reales + 2 proxies)                            │
│  EmpresaManager.get_queryset() → filter(empresa_id=ctx)              │
│  global_objects = Manager() → bypass explícito para admin/auditoría  │
└───────────────────────────┬──────────────────────────────────────────┘
                            │
                            ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    SQLite WAL — db.sqlite3 (680 KB)                  │
│                                                                      │
│  - WAL mode para lectura/escritura concurrente                       │
│  - backup_db command → VACUUM INTO snapshot atómico                  │
│  - 31 tablas físicas (20 inventory_* + 10 Django + sqlite_sequence)  │
└──────────────────────────────────────────────────────────────────────┘
```

**Flujo de una petición autenticada:**

1. `TenantMiddleware.__call__` verifica las 5 condiciones (ver §3.5) y setea `current_empresa` en el `ContextVar`.
2. La vista se ejecuta. Si es una vista de negocio, delega a `services.py`.
3. `services.py` usa `Model.objects` (que filtra por `current_empresa`) o `Model.global_objects` (bypass explícito).
4. En el `finally` del middleware, `reset_current_empresa(token)` restaura el estado anterior.
5. La response vuelve al cliente.

**Por qué este diseño funciona bien:** el `EmpresaManager` filtra **automáticamente** en cada query. El código de negocio no repite `filter(empresa_id=...)`. Si alguien olvida filtrar, el manager lo hace por él. Si el `ContextVar` está en `None` (bug o test mal configurado), el manager retorna `qs.none()` (vacío), **no** `qs.all()` — defensa anti-fuga.

### 3.3 Mapa de modelos

**21 clases en `models.py`**, agrupadas por dominio. Dos son proxies (`Cliente`, `Proveedor`) que no crean tabla propia.

#### Núcleo multi-tenant (3 modelos)

| Modelo | Tabla | Propósito | Manager |
|---|---|---|---|
| `Empresa` | `inventory_empresa` | Entidad raíz — RIF único, activa/desactiva | Sin manager custom |
| `ConfiguracionEmpresa` | `inventory_configuracionempresa` | OneToOne con Empresa — tasas, márgenes, prefijos, correlativos, IVAs, API config | `EmpresaManager` + `global_objects` |
| `PerfilUsuario` | `inventory_perfilusuario` | RBAC — M2M `empresas_permitidas` + FK `empresa_activa` | Manager estándar (FK a User) |

#### Inventario y catálogo (5 modelos)

| Modelo | Tabla | Propósito | Campos clave |
|---|---|---|---|
| `Almacen` | `inventory_almacen` | Ubicación física por empresa | `es_principal`, `activo` |
| `Articulo` | `inventory_articulo` | Catálogo — **PK = `sku`** (CharField) | `tipo=FISICO|COMBO`, `activo` (soft-delete ADR-03), `usa_serial`, `costo`, `precio_divisa`, `iva_porcentaje` |
| `InventarioAlmacen` | `inventory_inventarioalmacen` | Stock por (artículo × almacén) — tabla intermedia | `unique_together(articulo, almacen)`, `cantidad_disponible` Decimal, `stock_minimo` |
| `RecetaCombo` | `inventory_recetacombo` | Componentes de combo virtual | `unique_together(combo, componente)`, `cantidad_requerida` Decimal |
| `SerialArticulo` | `inventory_serialarticulo` | Trazabilidad unitaria (IMEI/serial) | `unique_together(empresa, serial)`, `estado=DISPONIBLE|VENDIDO|ANULADO_COMPRA` |

#### Contactos (3 modelos, uno de ellos con 2 proxies)

| Modelo | Tabla | Propósito |
|---|---|---|
| `Contacto` | `inventory_contacto` | **PK = `identificacion`** (CharField) — clientes + proveedores unificados (ADR-05) |
| `Cliente` (proxy) | (usa `inventory_contacto`) | `ClienteManager` filtra `tipo='CLIENTE'` |
| `Proveedor` (proxy) | (usa `inventory_contacto`) | `ProveedorManager` filtra `tipo='PROVEEDOR'` |

#### Ventas (2 modelos)

| Modelo | Tabla | Propósito | Snapshots |
|---|---|---|---|
| `NotaEntrega` | `inventory_notaentrega` | Cabecera — NE o Factura | `tasa_bcv_aplicada`, `factor_cobertura_aplicado`, `tasa_mercado_aplicada`, `iva_total`, `descuento_global`, `tipo_documento` |
| `DetalleNotaEntrega` | `inventory_detallenotaentrega` | Línea — 4 snapshots de precio | `precio_base`, `precio_ajustado`, `precio_directo_bcv`, `precio_ajustado_bcv`, `costo_unitario_snapshot`, `iva_porcentaje`, `descuento_aplicado` (ADR-24) |

#### Compras (2 modelos)

| Modelo | Tabla | Propósito | Snapshots |
|---|---|---|---|
| `DocumentoCompra` | `inventory_documentocompra` | Cabecera de compra | `tasa_bcv_aplicada`, `tasa_mercado_aplicada`, `factor_cobertura_aplicado`, `fuente_tasa`, `monto_total_bs_snapshot`, `tipo_documento` (3 opciones, ADR-28) |
| `DetalleDocumentoCompra` | `inventory_detalledocumentocompra` | Línea — 4 snapshots de costo | `costo_base`, `costo_ajustado`, `costo_directo_bcv`, `costo_ajustado_bcv`, `costo_unitario_snapshot`, `iva_porcentaje`, `descuento_aplicado` |

#### Kárdex (1 modelo)

| Modelo | Tabla | Propósito |
|---|---|---|
| `MovimientoKardex` | `inventory_movimientokardex` | Registro inmutable de ENTRADA/SALIDA — **Regla Sagrada** del sistema. 18 `CONCEPTO_CHOICES`. FK a `nota_entrega` y `documento_compra` |

#### Tasas y multimoneda (3 modelos)

| Modelo | Tabla | Propósito |
|---|---|---|
| `AuditoriaTasa` | `inventory_auditoriatasa` | Histórico de variación de `tasa_bcv`, `tasa_mercado`, `factor_cobertura` |
| `Moneda` | `inventory_moneda` | Catálogo de monedas por tenant — `unique_together(empresa, codigo)`, `es_base` única por tenant (enforced en `save()`) |
| `TasaCambio` | `inventory_tasacambio` | Histórico de pares de monedas por fecha — `obtener_tasa(origen, destino, empresa_id, fecha)` |

#### Devoluciones / Notas de Crédito (2 modelos)

| Modelo | Tabla | Propósito | Constraints |
|---|---|---|---|
| `NotaCredito` | `inventory_notacredito` | Cabecera NC — 1-NC-1-origen | `CheckConstraint` XOR (`nota_entrega` XOR `factura_compra`), ADR-29 |
| `DetalleNotaCredito` | `inventory_detallenotacredito` | Línea NC — 3 snapshots | `CheckConstraint` XOR (`detalle_origen_venta` XOR `detalle_origen_compra`) |

#### Tabla M2M auto-generada

- `inventory_perfilusuario_empresas_permitidas` — Django la crea automáticamente para `PerfilUsuario.empresas_permitidas`

### 3.4 Mapa de `services.py`

**17-19 funciones públicas**, agrupadas por sección. Los números de línea corresponden a `0585207`.

| Sección | Función | Línea | Propósito | Atomicidad |
|---|---|---|---|---|
| Kárdex | `registrar_movimiento` | ~60 | **Única vía de mutación de stock** | `@transaction.atomic` + `select_for_update` + `F()` |
| Combos | `calcular_stock_combo` | ~231 | Fórmula `min(floor(S/q))` | — (solo lectura) |
| Combos | `procesar_salida_combo` | ~309 | Desagregación atómica de componentes | `@transaction.atomic` |
| Carga masiva | `validar_formato_excel` | ~410 | ADR-10: validar `.xlsx` | — |
| Carga masiva | `procesar_carga_masiva` | ~501 | Carga tolerante a fallos, colisiones | Por fila (no atómico global) |
| Carga masiva | `procesar_carga_masiva_excel` | ~795 | Carga atómica estricta (Ticket #27) | `@transaction.atomic` global |
| Colisiones | `resolver_colision` | ~1007 | SUMAR / SUSTITUIR / CANCELAR | `@transaction.atomic` |
| Combos | `redondear_a_multiplo` | ~1169 | Helper de redondeo ROUND_HALF_UP | — |
| Ventas | `procesar_venta` | ~1186 | NE/Factura con 4 snapshots + IVA + descuento | `@transaction.atomic` |
| Tasas | `es_url_api_segura` | ~1515 | Validación SSRF (rangos privados, loopback, metadata) | — |
| Tasas | `sincronizar_tasa_cambio` | 1562 | HTTP API + `allow_redirects=False` + auditoría | `transaction.atomic` interno |
| Reverso | `revertir_carga_masiva` | ~1664 | Reverso de lote con validación de integridad | `@transaction.atomic` |
| Ajustes | `transferir_mercancia` | ~1783 | SALIDA origen + ENTRADA destino | `@transaction.atomic` |
| Ajustes | `ejecutar_ajuste_manual` | ~1831 | Delta ± con concepto auditado | `@transaction.atomic` |
| Compras | `registrar_compra_proveedor` | ~1890 | Compra con 4 snapshots + IVA + descuento + seriales + recálculo de precio | `@transaction.atomic` |
| Exportación | `exportar_datos_tenant` | ~2196 | Snapshot JSON aislado por tenant | — |
| Reversos | `reversar_nota_entrega` | ~2268 | Anular NE + contramovimientos | `@transaction.atomic` |
| Reversos | `reversar_documento_compra` | ~2318 | Anular compra + contramovimientos | `@transaction.atomic` |
| Devoluciones | `procesar_devolucion_venta` | ~2380 | NC venta + reingreso stock + FIFO seriales | `@transaction.atomic` |
| Devoluciones | `procesar_devolucion_compra` | ~2450 | NC compra + salida stock | `@transaction.atomic` |

**Regla Sagrada verificada por tests:** `TestRollbackAtomicidad.test_salida_insuficiente_hace_rollback_total` confirma que si `registrar_movimiento` falla, no se crea `MovimientoKardex` **y** no se altera `InventarioAlmacen`. La suite completa confirma que ninguna otra función muta stock directamente.

**Decisión ADR-21:** `services.py` se mantiene como archivo único (~2270 líneas). Se revoca si supera 5000 líneas o si la suite tarda >3 min. Actual: 2270 líneas, 92s.

### 3.5 Middleware `TenantMiddleware`

`inventory/middleware.py` — 147 líneas. Corre en cada request excepto rutas exentas (`/`, `/login/`, `/admin/`, `/static/`, `/favicon.ico`).

**5 validaciones secuenciales** en `_authorize()`:

| # | Validación | Fallo → |
|---|---|---|
| 1 | `user.is_authenticated` | Redirect a `/login/?next=<path>` con `messages.warning` |
| 2 | `user.perfil` existe | `403 Forbidden` (usuario sin perfil) |
| 3 | `request.session['empresa_id']` presente | `403 Forbidden` (sesión sin empresa) |
| 4 | `Empresa.objects.get(pk=empresa_id)` existe **y** `activa=True` | `403 Forbidden` (empresa borrada o inactiva) |
| 5 | Empresa ∈ `perfil.empresas_permitidas` | `403 Forbidden` (escalada de tenant) |

**Rutas exentas:** el `ContextVar` se setea a `None`. En esas rutas, `EmpresaManager` retorna `qs.none()` en cada query — protección anti-fuga para `/admin/` (que usa `global_objects` vía `TenantGlobalAdminMixin`).

**Defense-in-depth:** `@login_required` actúa en paralelo sobre las vistas. Si el middleware falla por bug, `@login_required` redirige a login. Si `@login_required` falla por bug, el middleware corta con 403.

### 3.6 Actores y roles

| Actor | Cómo se autentica | Cómo se autoriza | Alcance |
|---|---|---|---|
| **Superusuario** | `createsuperuser` | `user.is_superuser = True` | Ve todas las empresas. Accede a `/admin/`. `EmpresaManager` sigue filtrando por `ContextVar`, pero el admin usa `global_objects` |
| **Usuario estándar** | Creado por superusuario | `PerfilUsuario.empresas_permitidas` (M2M) + `empresa_activa` (FK) | Solo las empresas asignadas. Cambia de empresa vía `/cambiar-empresa/` |
| **Operador PDV** | Igual que usuario estándar | Igual que usuario estándar | Una empresa a la vez en la sesión activa |

**Escalada horizontal (mismo rol, distinto tenant):** bloqueada por `EmpresaManager` (auto-filtra) + validación perimetral en services (`payload.empresa_id == get_current_empresa()`).

**Escalada vertical (rol inferior → superior):** `configuracion_view` bloquea POST a usuarios sin `is_staff` o `is_superuser`. Test: `TestAuditoriaRemediacion.test_configuracion_view_bloquea_post_a_usuario_no_staff`.

### 3.7 Flujos principales

**1. Venta (NE/Factura)**
```
Carrito → POST /ventas/crear/ → procesar_venta()
  ├─ Valida tenant + almacén
  ├─ Lee snapshot de tasas (tasa_bcv, factor, tasa_mercado)
  ├─ Valida stock por línea (o permite negativo si config)
  ├─ registrar_movimiento(SALIDA) por cada línea
  ├─ Crea NotaEntrega (cabecera con snapshot de tasas)
  ├─ Crea DetalleNotaEntrega (4 precios snapshot + IVA + descuento)
  ├─ Quema seriales (select_for_update)
  └─ Calcula iva_total = Σ iva_bs
```

**2. Compra**
```
Formulario → POST /compras/registrar/ → registrar_compra_proveedor()
  ├─ Valida tenant + proveedor + almacén
  ├─ Lee snapshot de tasas
  ├─ Crea DocumentoCompra (con snapshot)
  ├─ Por cada ítem:
  │  ├─ Crea DetalleDocumentoCompra (4 costos snapshot)
  │  ├─ Actualiza Articulo.costo
  │  ├─ Recalcula Articulo.precio_divisa (según margen)
  │  ├─ registrar_movimiento(ENTRADA)
  │  └─ Crea SerialArticulo si usa_serial
  └─ Recalcula totales del documento
```

**3. Carga masiva**
```
Excel → POST /carga/excel/ → procesar_carga_masiva_excel()
  ├─ Valida cabecera exacta (SKU, Nombre, Costo, Cantidad, Precio_Divisa, Almacen)
  ├─ Valida cada almacén pertenezca al tenant
  ├─ @transaction.atomic global: cualquier error → rollback total
  └─ Por cada fila: crear/actualizar Artículo + registrar_movimiento(ENTRADA)
```

**4. Reverso de NE**
```
POST /api/reversar-venta/ → reversar_nota_entrega()
  ├─ select_for_update sobre la NE
  ├─ Valida estado ≠ ANULADO
  ├─ Marca estado=ANULADO + motivo
  ├─ Por cada detalle: registrar_movimiento(ENTRADA, DEVOLUCION_VENTA)
  └─ Libera seriales (VENDIDO → DISPONIBLE)
```

**5. Nota de Crédito (devolución)**
```
POST /notas-credito/crear/ → procesar_devolucion_venta()
  ├─ Valida tenant + NE origen
  ├─ Crea NotaCredito (1-NC-1-origen, CheckConstraint XOR)
  ├─ Por cada línea:
  │  ├─ Valida cantidad_pendiente_devolver
  │  ├─ Crea DetalleNotaCredito (3 snapshots)
  │  └─ registrar_movimiento(ENTRADA, DEVOLUCION_VENTA)
  ├─ FIFO libera seriales (VENDIDO → DISPONIBLE)
  └─ Advertencia si saldo sigue negativo
```

**6. Sync de tasas**
```
POST /tasas/sincronizar/ → sincronizar_tasa_cambio()
  ├─ Valida config.api_url
  ├─ es_url_api_segura() — SSRF block
  ├─ requests.request(allow_redirects=False, timeout=5)
  ├─ Extractor JSON iterativo (cero eval())
  ├─ transaction.atomic:
  │  ├─ select_for_update(config)
  │  ├─ Calcula factor_nuevo = tasa_mercado / tasa_bcv
  │  ├─ Actualiza config
  │  └─ Crea AuditoriaTasa
```

---

## 4. Estado verificado (2026-10-19)

### 4.1 Test suite

**Comando:**
```bash
python manage.py test inventory --verbosity 2
```

**Resultado:**
```
Found 358 test(s).
Creating test database for alias 'default' ('file:memorydb_default?mode=memory&cache=shared')...
[... 18 migraciones aplicadas ...]
Ran 358 tests in 92.302s
OK (skipped=6)
```

**Cobertura por módulo (identificada por nombre de test):**

| Módulo | Tests | Estado |
|---|---|---|
| Movimientos de Kárdex básicos | ~10 | ✅ |
| Rollback atómico (`TestRollbackAtomicidad`) | 3 | ✅ |
| Combos dinámicos (`TestComboDinamico`) | 5 | ✅ |
| Carga masiva (`TestCargaMasivaBasica`) | 7 | ✅ |
| Carga masiva atómica (`TestCargaMasivaExcelAtomica`) | 3 | ✅ |
| Resolución de colisiones (`TestResolverColision`) | 4 | ✅ |
| Ventas (`TestVentaExitosa`, `TestVentaRollback`, `TestProcesarVentaN2`) | ~20 | ✅ |
| Compras (`TestControlCostosYCompras`, `TestRegistrarCompraProveedorMultiTenant`) | ~15 | ✅ |
| Notas de Crédito backend (`TestNotasCreditoBackend`) | 15 | ✅ |
| Notas de Crédito UI (`TestNotasCreditoUI`) | 14 | ✅ |
| Reversos (`TestCoberturaCritica`, `TestReversoIdempotencia`) | ~10 | ✅ |
| Seriales (`TestControlDeSerialesPOS`) | 4 | ✅ |
| SSRF / Sync tasas (`TestValidacionUrlApiSegura`, `TestSincronizacionTasas`) | 6 | ✅ |
| Rate-limiting login (`TestThrottleLogin`) | 2 | ✅ |
| Password validation (`TestSecurityPasswordValidation`) | 3 | ✅ |
| Multi-tenant (`TestTenantMiddlewareAuthorization`, `TestSecurityUserWithoutPermittedEmpresas`) | ~15 | ✅ |
| SQL Injection (`TestSecuritySQLInjection`) | 3 | ✅ |
| XSS (`TestSecurityXSS`) | 2 | ✅ |
| CSRF (`TestSecurityCSRFEnforcedOnAllPOST`) | 2 | ✅ |
| Fase 3 multimoneda (`TestMultimonedaModelos`) | 3 | ✅ |
| Fase 4 reportes (`TestReportesFase4`, `TestVistasReportes`) | ~15 | ✅ |
| Dashboard (`TestDashboardMetricas`, `TestDashboardLiveData`) | ~6 | ✅ |
| Backup (`TestBackupVacioInto`) | 3 | ✅ |
| Settings hardening (`TestSettingsHardening`) | ~10 | ✅ |
| Kardex integrado (`TestKardexIntegradoVistaYFiltros`) | ~6 | ✅ |
| Listados documentos (`TestListadosDocumentosEmitidos`) | ~8 | ✅ |
| Cobertura crítica (`TestCoberturaCritica`) | 4 | ✅ |
| **Otros (iteraciones 1.1.1, 1.2.1, UX, fichas)** | ~80 | ✅ |

**6 skips, todos justificados:**

| # | Test | Motivo |
|---|---|---|
| 1 | `TestNotasDeCreditoPOS.test_compensacion_automatica_por_dano` | ADR-29 reemplazó la firma legacy. Cubierto por `TestNotasCreditoBackend` |
| 2 | `TestNotasDeCreditoPOS.test_desvio_cuarentena_activado` | Ídem |
| 3 | `TestNotasDeCreditoPOS.test_devolucion_parcial_exitosa_costo_historico` | Ídem |
| 4 | `TestNotasDeCreditoPOS.test_reverso_estado_seriales` | Ídem |
| 5 | `TestSaneamientoYVulnerabilidadesSaaS.test_costo_historico_snapshot_venta_vs_actual` | Ídem |
| 6 | `TestSecurityRaceCondition.test_concurrent_salidas_no_oversell` | SQLite no soporta escritura concurrente multi-thread. Cubierto por `TestRollbackAtomicidad` + `select_for_update` |

**Interpretación:** la suite cubre los flujos críticos y los casos de seguridad documentados. **No cubre** los invariantes estructurales (EST-01 a EST-11) porque no hay tests que validen que `MovimientoKardex.delete()` falle, o que `NotaEntrega.save()` bloquee cambios en `estado='PROCESADO'`. **Esa es la brecha entre "suite verde" y "modelo blindado".**

### 4.2 Migraciones

**Comando:**
```bash
python manage.py showmigrations inventory
python manage.py makemigrations --check --dry-run
```

**Resultado:**
```
inventory
 [X] 0001_normalizar_config
 [X] 0002_perfil_usuario_rbac
 [X] 0003_modelo_documento_compra
 [X] 0004_perfeccionar_reversos_trazables
 [X] 0005_configuracionempresa_cross_selling_footer_and_more
 [X] 0006_inicializar_configuraciones_existentes
 [X] 0007_add_observaciones_to_documento_compra
 [X] 0008_make_factura_fields_optional
 [X] 0009_documentocompra_factor_cobertura_aplicado_and_more
 [X] 0010_alter_notaentrega_unique_together_and_more
 [X] 0011_alter_notaentrega_unique_together_and_more
 [X] 0012_detalledocumentocompra_and_more
 [X] 0013_tipo_documento_compra_3_opciones
 [X] 0014_nota_credito_devoluciones
 [X] 0015_nota_credito_prefijo_default
 [X] 0016_configuracionempresa_permite_venta_sin_stock
 [X] 0017_configuracionempresa_metodo_ganancia_global_and_more
 [X] 0018_configuracionempresa_factor_redondeo_and_more
```

`makemigrations --check --dry-run` → **"No changes detected"**.

**Interpretación:** 18/18 aplicadas, sin migraciones pendientes, modelos y migraciones sincronizados.

**Nota sobre 0017 y 0018:** estaban untracked en el commit `e6ac3f2` (wip) y fueron commiteadas juntas. Correcto.

### 4.3 Base de datos

**Comando:**
```python
import sqlite3
c = sqlite3.connect('db.sqlite3')
tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
```

**Resultado:** 31 tablas totales:

- **10 tablas Django/contrib:** `auth_group`, `auth_group_permissions`, `auth_permission`, `auth_user`, `auth_user_groups`, `auth_user_user_permissions`, `django_admin_log`, `django_content_type`, `django_migrations`, `django_session`
- **20 tablas `inventory_*`:** ver §3.3
- **1 tabla auxiliar:** `sqlite_sequence`

**PRAGMA checks (sobre copia en `%TEMP%`):**

```python
PRAGMA integrity_check;      → ok
PRAGMA foreign_key_check;    → 0 filas
PRAGMA foreign_keys;         → 0 (por conexión directa; Django lo activa vía init_command)
PRAGMA journal_mode;         → wal
```

**Tamaño:** `db.sqlite3` = **680 KB**, última modificación **27/9/2026 14:55**.

**Interpretación:** la BD está **estructuralmente íntegra**. 0 huérfanos. Los 680 KB y la fecha del 27/9 sugieren que los datos de prueba (seed de 2 empresas, 20 artículos, 29 facturas, 88 movimientos) **no fueron regenerados** desde entonces. Es un dato operativo, no un hallazgo.

### 4.4 `check --deploy`

**Comando:**
```bash
python manage.py check --deploy
```

**Resultado:**
```
System check identified some issues:

WARNINGS:
?: (security.W004) You have not set a value for the SECURE_HSTS_SECONDS setting.
?: (security.W008) Your SECURE_SSL_REDIRECT setting is not set to True.
?: (security.W012) SESSION_COOKIE_SECURE is not set to True.
?: (security.W016) You have 'django.middleware.csrf.CsrfViewMiddleware' in your MIDDLEWARE, but you have not set CSRF_COOKIE_SECURE to True.
?: (security.W018) You should not have DEBUG set to True in deployment.

System check identified 5 issues (0 silenced).
```

**Análisis de cada warning:**

| Warning | Contexto | Veredicto |
|---|---|---|
| **W004** HSTS no configurado | Delegado a reverse proxy HTTPS | ✅ Esperable on-premise HTTP LAN |
| **W008** SSL redirect no configurado | Delegado a reverse proxy | ✅ Esperable on-premise HTTP LAN |
| **W012** `SESSION_COOKIE_SECURE=False` | Solo con SSL real | ✅ Esperable si no hay HTTPS |
| **W016** `CSRF_COOKIE_SECURE=False` | Solo con SSL real | ✅ Esperable si no hay HTTPS |
| **W018** `DEBUG=True` | `.env` de desarrollo | 🔴 **NO esperable en producción** |

**Interpretación:** los 4 primeros son esperables para on-premise sin HTTPS. **W018 es crítico**: el `.env` actual tiene `DEBUG=True` (confirmado por `.env:9`), y si ese `.env` se replica a producción, se exponen:
- Stack traces completos en errores 500
- Variables de entorno y settings en páginas de error
- SQL queries en páginas de error
- Rutas del sistema de archivos

**Debe documentarse en `SETUP.md`** que `DEBUG=False` es obligatorio en cualquier despliegue fuera de la máquina de desarrollo.

### 4.5 Git

**Comando:**
```bash
git log --oneline -3
git status --short
git log --all --full-history -- .env
```

**Resultado:**

```
0585207 fix(tests): restaurar setUp API sync sin duplicados + XSS genérico + paleta sin skip + logger NC con 6 args + tests 500/503 realistas
3a19546 fix(services): manejo ConfiguracionEmpresa.DoesNotExist + encoding UTF-8 en logs + logger NC con formato correcto + ≥→>=
e6ac3f2 wip: cambios post-auditoria (modelos, services, tests, templates) + migraciones 0017/0018 + SVGs
```

```
?? audit.ps1
?? repomix-output.md
?? specs/
?? tasks/
?? templates/
?? test_output.txt
?? test_output_full.txt
```

`git log --all --full-history -- .env` → **vacío** (nunca commiteado).

**Interpretación:**

- **3 commits locales** por delante de `origin/main`. **Deben pushearse** para no perder el trabajo. Si el equipo es de una sola persona, es riesgo de pérdida. Si es multi-persona, es divergencia garantizada.
- **7 archivos untracked** que no son parte del proyecto y **deben revisarse antes de añadirse**:
  - `audit.ps1` — script de auditoría, probablemente del agente
  - `repomix-output.md` — output de herramienta, no es código
  - `specs/`, `tasks/`, `templates/` — directorios del agente, verificar contenido
  - `test_output*.txt` — outputs de test, no deben ir al repo
- **`.env` está protegido**: `.gitignore:29-30` cubre `.env` y `.env.*`. El historial está limpio.

---


## 5. Clasificación de la documentación existente

`docs/` contiene **16 archivos** (15 previos + este informe). Se clasificó cada uno por su relación con el código real. La clasificación se hizo leyendo cada archivo completo y contrastándolo contra el código.

**Leyenda:**
- **VIGENTE**: describe la realidad actual del código.
- **PARCIALMENTE DESACTUALIZADO**: describe la realidad con errores u omisiones, pero el contenido base es correcto.
- **OBSOLETO**: describe funcionalidad o arquitectura que no existe (o existió y fue reemplazada).
- **REDUNDANTE**: duplica información de otro archivo.
- **INCOMPLETO**: cubre parcialmente, confunde más que ayuda.

### 5.1 Tabla de clasificación

| Archivo | Clasificación | Justificación | Acción |
|---|---|---|---|
| `AUDITORIA_INICIAL.md` | **VIGENTE** | Histórico pre-Fase A con 10 hallazgos y commits verificables (`88746dc`, `76490a5`, etc.). Todos los commits existen en `git log`. | Conservar como histórico |
| `auditoria_a2lt_stock.md` | **PARCIALMENTE DESACTUALIZADO** | 4 hallazgos marcados FALSOS por la auditoría 2026-08: S-05 (IDOR), S-08 (fuga seriales), S-09 (`db.sqlite3`), X-02 (sin paginación). Los demás (S-01, S-02, S-03, S-04, A-01, A-03, A-05, U-01, U-03, X-01, X-03, X-04, X-05, X-06) siguen válidos o ya resueltos | Marcar con banner "PARCIALMENTE DESACTUALIZADO — ver `auditoria_2026-08.md` y `AUDIT_REPORT.md` v3" |
| `auditoria_2026-08.md` | **VIGENTE** | Verifica código real contra la auditoría anterior. Corrige 4 false positives. F1/F2/F3 implementadas y verificadas. | Conservar como referencia histórica |
| `AUDIT_REPORT.md` (v1) | **OBSOLETO** | Contiene 5 afirmaciones sin verificación runtime (276 tests, 13 migraciones, warnings "esperables", etc.). Reemplazado por la v3 | **ELIMINAR** tras confirmar v3 |
| `BACKLOG.md` | **VIGENTE** | 30+ tickets con estado ✅ y commits asociados. Documento maestro de construcción | Conservar |
| `PLAN.md` | **VIGENTE** | Plan de estabilización por etapas (A, B, Fase 3-6, N, C, FA, 1.1.1, 1.2.1). Matriz de tests C1-C27 | Conservar |
| `ROADMAP.md` | **VIGENTE** | Features post-100% (Q3-Q4 2026, Q1 2027) | Conservar |
| `OPERACION.md` | **VIGENTE** | Guía de instalación, módulos, tokens, troubleshooting, reglas operativas | Conservar |
| `ARQUITECTURA.md` | **PARCIALMENTE DESACTUALIZADO** | Diagrama y principios correctos. Tabla de migraciones desactualizada (dice 12, hay 18). Tabla de tests dice 234, hay 358 | Actualizar números o remitir a v3 §3 y §4 |
| `ADR.md` | **VIGENTE** | 31 ADRs formales con estado, contexto, decisión, consecuencias | Conservar |
| `reglas_desarrollo_agente.md` | **VIGENTE** | Reglas de oro: Regla Sagrada, combos dinámicos, dinámica cambiaria, tolerancia a fallos, tests, venv | Conservar |
| `revision_arquitectura.md.md` | **VIGENTE** | Validación de la especificación original. Sus 2 sugerencias (blank/null en textos, `unique_together` en InventarioAlmacen) están implementadas | Conservar |
| `especificacion_arquitectura_inventario.md` | **OBSOLETO** | SRS V1.0 pre-multi-tenant: describe `ConfiguracionSistema` singleton, sin `Empresa`, sin `ContextVar`, sin `PerfilUsuario`. Arquitectura enteramente reemplazada por ADR-14/15/17 | **ARCHIVAR** (o eliminar si se confía en git para el histórico) |
| `tickets_desarrollo.md` | **OBSOLETO** | Plan original de tickets #1-13. Superado por `BACKLOG.md` (30+ tickets) y `PLAN.md` (etapas + iteraciones) | **ARCHIVAR** |
| `maqueta_interactiva_de_interfaz.html` | **VIGENTE** | Mockup UI de referencia. Algunas paletas y componentes difieren del `base.html` actual (verde bosque vs indigo original) | Conservar como referencia de diseño |
| `arbol_directorios_a2lt.md` | **VIGENTE** | Árbol del proyecto. Verificar si está actualizado (probablemente falta `migrations/0017` y `0018`) | Revisar y actualizar o eliminar (el árbol se puede regenerar) |

### 5.2 Resumen de acciones

| Acción | Archivos | Justificación |
|---|---|---|
| **Eliminar** | `AUDIT_REPORT.md` (v1) | Reemplazado por v3 |
| **Archivar** (mover a `docs/historico/` o `git rm`) | `especificacion_arquitectura_inventario.md`, `tickets_desarrollo.md` | Obsoletos, arquitectura reemplazada |
| **Marcar** (banner de advertencia al inicio) | `auditoria_a2lt_stock.md`, `ARQUITECTURA.md` | Parcialmente desactualizados |
| **Conservar** | Los otros 11 | Vigentes |

---

## 6. Contraste código ↔ documentación

### 6.1 False positives del informe v1 (correctamente descartados por auditoría 2026-08)

| ID v1 | Afirmación | Veredicto | Evidencia |
|---|---|---|---|
| **S-05** | IDOR en `vista_imprimir_coordenadas` sin filtro `empresa_id` | ❌ **FALSO** | `views.py` usa `NotaEntrega.objects` (que es `EmpresaManager`). El manager auto-filtra por `ContextVar` (`managers.py:46-51`). Un `get_object_or_404(NotaEntrega.objects, pk=X)` de otra empresa retorna 404, no 200 |
| **S-08** | Fuga de seriales en `/seriales/<sku>/<almacen_id>/` | ❌ **FALSO** | `SerialArticulo.objects = EmpresaManager()` (`models.py:1740`). El filtro de tenant aplica aunque se pase un `almacen_id` ajeno: si el `almacen_id` pertenece a otra empresa, `InventarioAlmacen.objects.get()` retorna `DoesNotExist`, no datos |
| **S-09** | `db.sqlite3` commiteado en repo | ❌ **FALSO** | `.gitignore:5` excluye `db.sqlite3`. `git ls-files db.sqlite3` → vacío |
| **X-02** | `vista_movimientos` sin paginación, carga todo el histórico | ❌ **FALSO** | `views.py:1188` usa `Paginator(movimientos, per_page)` con `per_page ∈ {50, 100, 200}` |

**Los 4 false positives provienen de auditar el código sin ejecutarlo ni verificar el comportamiento real del `EmpresaManager` y del `Paginator`.** Son el argumento más fuerte para que la v3 se base en verificación dinámica.

### 6.2 Correcciones de cifras del informe v1

| Afirmación v1 | Realidad verificada | Severidad del error |
|---|---|---|
| "276 tests verdes (~190s)" | **358 tests, 0 failures, 6 skipped, 92s** | 🔴 El claim central del informe v1 era falso |
| "13 migraciones aplicadas (0001-0013)" | **18 migraciones (0001-0018)** | 🟠 Faltan 5 migraciones |
| "5 warnings esperables para on-premise" | **5 warnings, pero W018 (`DEBUG=True`) NO es esperable en producción** | 🔴 Clasificación peligrosa |
| "0 huérfanos detectados" | **Confirmado: 0 huérfanos**, pero era verificación, no hallazgo | 🟢 Informativo |
| "db.sqlite3 íntegro" | **Confirmado: `integrity_check: ok`** | 🟢 Informativo |
| "Repositorio limpio / commits hechos" | **13 archivos modificados sin commitear + 2 migraciones untracked** en el momento del v1 | 🟠 Se resolvió en `e6ac3f2` |

### 6.3 Consistencia entre `docs/` y código

Verificación de afirmaciones de la documentación vigente contra el código:

| Doc | Afirmación | Verificado en código | Coincide |
|---|---|---|---|
| `ARQUITECTURA.md:57-63` | `EmpresaManager` retorna `qs.none()` sin tenant | `managers.py:49-51` | ✅ |
| `ARQUITECTURA.md:75-84` | `TenantMiddleware` valida 5 condiciones | `middleware.py:60-147` | ✅ |
| `ARQUITECTURA.md:90-104` | Regla Sagrada: solo `registrar_movimiento` muta stock | `services.py:60-224` + ausencia de mutaciones en `views.py` y `admin.py` (admin bloquea add/change en `InventarioAlmacen` y `MovimientoKardex`) | ✅ |
| `ARQUITECTURA.md:106-120` | Snapshots inmutables en NE/DocumentoCompra | `models.py` `NotaEntrega` + `DetalleNotaEntrega` + `DocumentoCompra` + `DetalleDocumentoCompra` | ✅ |
| `ARQUITECTURA.md:207-228` | 17 funciones públicas en `services.py` | 19 funciones identificadas (se añadieron `procesar_carga_masiva_excel` y `redondear_a_multiplo` en iteraciones posteriores) | ⚠️ Desactualizado |
| `ARQUITECTURA.md:232-250` | 12 migraciones | 18 migraciones | ⚠️ Desactualizado |
| `ARQUITECTURA.md:252-280` | 234 tests | 358 tests | ⚠️ Desactualizado |
| `ADR.md` | 31 ADRs formales | `ADR-01` a `ADR-31` (con saltos: no hay ADR-07, ADR-19, ADR-20) | ✅ |
| `PLAN.md` | Matriz C1-C27 | Tests existen con esos nombres | ✅ |
| `OPERACION.md:211-219` | 276 tests | 358 tests | ⚠️ Desactualizado |
| `OPERACION.md:230-235` | `del db.sqlite3` para reinicializar | Correcto, pero **advertir que `seed_db --clear` es más seguro** (no requiere borrar el archivo) | ⚠️ Mejorable |
| `BACKLOG.md` | TICKET #1-30+ con estado | Coincide con `git log` | ✅ |

**Patrón:** `ARQUITECTURA.md` y `OPERACION.md` describen un estado del sistema de hace 3-4 iteraciones. Los principios arquitectónicos siguen válidos; los números (tests, migraciones, funciones) están desactualizados.

### 6.4 Documentos referenciados que no existen

`PLAN.md` y `BACKLOG.md` mencionan archivos que no están en el repo actual:

| Referencia | Estado |
|---|---|
| `docs/CHANGELOG.md` (mencionado como ubicación alternativa) | Existe en raíz: `CHANGELOG.md`. Coherente |
| `README.md` (raíz) | Existe |
| `docs/AUDITORIA_INICIAL.md` | Existe |
| `docs/auditoria_a2lt_stock.md` | Existe |

**No hay referencias rotas.**

---

## 7. Auditoría de seguridad

Metodología: OWASP Top 10:2021 + ASVS L1 + checklist de Django. Los hallazgos se verificaron por código y por ejecución (cuando aplica).

### 7.1 Configuración Django (`settings.py`)

Tabla exhaustiva de settings relevantes para seguridad.

| Setting | Valor / Lógica | Línea | Veredicto |
|---|---|---|---|
| `DEBUG` | `os.environ.get('DEBUG', 'False').lower() == 'true'` | 33 | ✅ Default seguro (False) si no hay env. ⚠️ `.env` actual lo setea `True` |
| `SECRET_KEY` | `os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod')` | 28 | 🔴 **Fallback inseguro** (SEC-01) |
| `ALLOWED_HOSTS` | `env` → lista; si `DEBUG=True` → `['*']`; si no, `[]` | 38-44 | ✅ Lógica correcta. Prod requiere config explícita |
| `SECURE_BROWSER_XSS_FILTER` | `True` (si `!DEBUG`) | 160 | ⚠️ **Deprecado en Django 5+**, no tiene efecto (EST-10) |
| `SECURE_CONTENT_TYPE_NOSNIFF` | `True` (si `!DEBUG`) | 161 | ✅ |
| `X_FRAME_OPTIONS` | `'DENY'` (si `!DEBUG`) | 162 | ✅ Clickjacking bloqueado |
| `SECURE_SSL_REDIRECT` | `env`, default `False` | 166 | ✅ Delegado a reverse proxy |
| `SECURE_PROXY_SSL_HEADER` | `('HTTP_X_FORWARDED_PROTO', 'https')` | 167 | 🟠 **Fuera de `if not DEBUG`** (SEC-03) |
| `SESSION_COOKIE_SECURE` | `= SECURE_SSL_REDIRECT` | 169 | ✅ Coherente |
| `CSRF_COOKIE_SECURE` | `= SECURE_SSL_REDIRECT` | 170 | ✅ Coherente |
| `SECURE_HSTS_SECONDS` | `31536000` (si `SECURE_SSL_REDIRECT`) | 172 | ✅ 1 año |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | `True` | 173 | ✅ |
| `SECURE_HSTS_PRELOAD` | `True` | 174 | ✅ |
| `SESSION_COOKIE_HTTPONLY` | `True` | 238 | ✅ |
| `CSRF_COOKIE_HTTPONLY` | `False` | 239 | 🟠 **Vector XSS→CSRF** (SEC-02) |
| `CSRF_TRUSTED_ORIGINS` | `[]` | 253 | ✅ Configurar en prod si hay subdominios |
| `AUTH_PASSWORD_VALIDATORS` | 4 validadores (UserAttributeSimilarity, MinimumLength, CommonPassword, NumericPassword) | 117-130 | ✅ Completo |
| `PASSWORD_HASHERS` | No configurado (usa default Django: PBKDF2) | — | ✅ PBKDF2 es seguro |
| `LOGGING` | file (rotación 10MB × 5) + console | 183-232 | ✅ Configurado. ⚠️ Sin `encoding='utf-8'` (BUG-02, resuelto) |
| `LOGGING` `mail_admins` handler | No definido | — | 🟠 `ADMINS` decorativo (SEC-04) |
| `ADMINS` / `MANAGERS` | Configurados vía `env['ADMIN_EMAIL']` | 245-247 | ✅ Definidos, pero sin uso real |
| `LOGIN_URL` | `'inventory:login'` (por name) | 259 | ✅ |
| `LOGIN_REDIRECT_URL` | `'inventory:dashboard'` | 260 | ✅ |
| `LOGOUT_REDIRECT_URL` | `'inventory:login'` | 261 | ✅ |
| `DATABASES['default']['OPTIONS']['init_command']` | 5 PRAGMAs concatenados | 100-108 | ✅ WAL + foreign_keys + cache |

**Sin configurar (faltantes):**
- `CSP_DEFAULT_SRC` / `Content-Security-Policy` — no hay CSP
- `SECURE_REFERRER_POLICY` — no configurado (default Django `'same-origin'` es aceptable)
- `PERMISSIONS_POLICY` — no configurado

### 7.2 Autenticación y autorización

| Control | Implementación | Evidencia | Veredicto |
|---|---|---|---|
| **Backend de auth** | `ModelBackend` (default Django). `django-axes` NO está instalado | `requirements.txt` no lo incluye | ✅ ModelBackend es estándar |
| **Hashing de contraseñas** | PBKDF2 (default Django) | Sin override | ✅ |
| **Validadores de password** | 4 validadores | `settings.py:117-130` | ✅ |
| **Sesiones** | DB-backed (`django.contrib.sessions`), `SESSION_COOKIE_HTTPONLY=True` | `settings.py:238` | ✅ |
| **Rate limiting login** | Throttle manual por IP vía `LocMemCache`: 5 intentos / 5 min → bloqueo 15 min | `views.py:33-105` + `TestThrottleLogin` | ✅ Implementado. ⚠️ `LocMemCache` no persiste entre reinicios; si se reinicia el server, el contador se resetea |
| **MFA** | No implementado | — | ⚠️ No requerido on-premise, pero ausente |
| **RBAC** | `PerfilUsuario.empresas_permitidas` (M2M) + `empresa_activa` (FK) | `models.py` | ✅ Aislamiento por tenant |
| **IDOR** | `EmpresaManager` filtra todas las queries + vistas detalle/PDF filtran `empresa_id=session['empresa_id']` | `managers.py:46-51` + `views.py` `get_object_or_404(..., empresa_id=...)` | ✅ Defensa en profundidad |
| **Escalada horizontal** | Validación perimetral en services: `payload.empresa_id == get_current_empresa()` | `services.py:1214-1232` (venta), `1929-1947` (compra) | ✅ |
| **Escalada vertical** | `configuracion_view` bloquea POST a usuarios sin `is_staff`/`is_superuser` | `views.py` (test `TestAuditoriaRemediacion.test_configuracion_view_bloquea_post_a_usuario_no_staff`) | ✅ Implementado |
| **Session fixation** | `django.contrib.auth.login()` rota el `session_key` | Comportamiento default de Django | ✅ |
| **Logout** | `@require_POST` + form POST + CSRF | `views.py` `logout_view` | ✅ GET rechazado |

**Test suite asociada:** `TestSecurityPasswordValidation` (3 tests), `TestThrottleLogin` (2 tests), `TestTenantMiddlewareAuthorization` (7 tests), `TestSecurityUserWithoutPermittedEmpresas` (5 tests), `TestSecurityAPIRateErrorHandling` (7 tests). **Total: 24 tests de auth/authz**.

### 7.3 Validación de entrada

| Vector | Protección | Evidencia | Veredicto |
|---|---|---|---|
| **SQL Injection** | Ningún SQL crudo. Todo vía ORM | Grep `\.raw\(`, `\.extra\(`, `cursor.execute` → 0 resultados | ✅ |
| **XSS (templates)** | Auto-escape de `{{ var }}`. `json_script` en `articulos.html`. Sin `\|safe` en datos de usuario | `TestSecurityXSS` (2 tests) + `TestAuditoriaRemediacion.test_articulos_view_escapa_payload_xss` | ✅ |
| **XSS (`mark_safe`)** | Solo en `admin.py` (JS estático, no input de usuario) | Grep `mark_safe` → 1 resultado en `admin.py` | ✅ |
| **SSRF** | `es_url_api_segura()` bloquea esquemas no HTTP/S, rangos privados, loopback, link-local (169.254.169.254), IPv6 única/local. `allow_redirects=False` | `services.py:1515-1559` + `TestValidacionUrlApiSegura` (3 tests) | ✅ |
| **Path traversal** | No hay `FileField`/`ImageField` para uploads de usuario. Excel procesado en memoria (`BytesIO`) | Grep `FileField\|ImageField` → 0 | ✅ |
| **Deserialización insegura** | Sin `pickle`, sin `yaml.load`, sin `eval`/`exec` en extractor JSON | `services.py:1604-1616` (extractor iterativo) | ✅ |
| **Command Injection** | Sin `subprocess` ni `os.system` con input de usuario | Grep `subprocess\|os.system` → 0 | ✅ |
| **CSRF** | `CsrfViewMiddleware` activo. `@csrf_exempt` removido de todas las vistas (A7-A9) | `TestSecurityCSRFEnforcedOnAllPOST` (2 tests) | ✅ |
| **File upload (Excel)** | Validación de extensión `.xlsx` + `openpyxl.load_workbook(read_only=True)`. Tamaño no validado explícitamente | `services.py:410-426` | ⚠️ Sin límite de tamaño de archivo |
| **JSON malformado en API** | Try/except en `sincronizar_tasa_cambio` | `services.py:1600-1605` | ✅ |
| **Selector JSON arbitrario** | Extractor iterativo, cero `eval` | `services.py:1604-1616` | ✅ |

**Riesgo residual en uploads:** `procesar_carga_masiva` no valida el tamaño máximo del archivo Excel. Un atacante autenticado podría subir un Excel de 500 MB con 10 millones de filas. `openpyxl.read_only=True` mitiga el consumo de memoria, pero no el tiempo de procesamiento. **No clasificado como hallazgo** (no es un vector de seguridad en un sistema on-premise con usuarios confiables), pero debe documentarse en `OPERACION.md`.

### 7.4 Secretos hardcodeados

**Búsqueda exhaustiva:**

```bash
grep -rE "(SECRET|PASSWORD|API_KEY|TOKEN|PRIVATE)" --include="*.py" --include=".env" .
```

| Patrón | Hallazgo | Riesgo |
|---|---|---|
| `SECRET_KEY` | `settings.py:28` fallback `'dev-insecure-key-change-in-prod'` | 🔴 **SEC-01** |
| `SECRET_KEY` en `.env` | `.env:9` `dev-test-key-c2lt5-f52afea-2026-07-no-production-pls` | 🟢 Valor de desarrollo. `.env` no commiteado (verificado con `git log`) |
| `PASSWORD` | `settings.py:117-130` (validadores). Tests con contraseñas de fixtures | ✅ No son secretos reales |
| `API_KEY` / `TOKEN` | 0 hardcodeados. `ConfiguracionEmpresa.api_url` es configurable por UI | ✅ |
| `.env` en historial git | **Vacío** (`git log --all -- .env`) | ✅ Nunca commiteado |
| `.gitignore` cubre `.env` | Líneas 29-30: `.env` y `.env.*` | ✅ |

**Conclusión:** el único secreto hardcodeado real es el **fallback de `SECRET_KEY`**. El `.env` con valor de desarrollo no es crítico porque nunca se commiteó. Pero el fallback sí: si alguien despliega en prod sin `SECRET_KEY` en el entorno, la app arranca con una clave pública.

### 7.5 Hallazgos de seguridad detallados

#### SEC-01 — Fallback inseguro de `SECRET_KEY` en código (🔴 CRÍTICA)

**Ubicación:** `a2lt_stock_project/settings.py:28`

```python
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod')
```

**Evidencia:**
- El string `'dev-insecure-key-change-in-prod'` está **en el repositorio público** (o al menos en el repo compartido).
- Cualquier despliegue que no exporte `SECRET_KEY` arranca con esa clave.
- Con la clave conocida, un atacante puede:
  - Forjar cookies de sesión (`django_session` firmadas con esa clave).
  - Forjar tokens CSRF.
  - Forjar tokens de password reset.
  - Forjar cualquier dato firmado por Django (`signing.dumps()`).
- Es escalada directa a superusuario si se combina con conocer un `user_id`.

**Impacto:** Compromiso total del sistema si la app se expone a internet sin `SECRET_KEY` correctamente configurada.

**Contexto verificado:** El historial git está limpio (`.env` nunca commiteado). El riesgo **no es el `.env`**, es el fallback en código.

**Remediación:**

```python
# a2lt_stock_project/settings.py
SECRET_KEY = os.environ.get('SECRET_KEY')
if not SECRET_KEY:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured(
        'SECRET_KEY no definida en variables de entorno. '
        'Generar con: python -c "import secrets; print(secrets.token_urlsafe(64))"'
    )
```

**Test de aceptación:**

```python
def test_settings_falla_sin_secret_key(self):
    """Verifica que settings.py no arranca sin SECRET_KEY en producción."""
    import os
    import subprocess
    env = os.environ.copy()
    env.pop('SECRET_KEY', None)
    env['DEBUG'] = 'False'
    result = subprocess.run(
        ['python', 'manage.py', 'check', '--deploy'],
        capture_output=True, text=True, env=env,
    )
    self.assertNotEqual(result.returncode, 0)
    self.assertIn('SECRET_KEY', result.stderr)
```

**Esfuerzo:** S (2 horas incluyendo test).
**Prioridad:** P0.
**Riesgo si no se hace:** 🔴 Compromiso total si la app se despliega mal.

---

#### SEC-02 — `CSRF_COOKIE_HTTPONLY=False` habilita exfiltración por XSS (🟠 ALTA)

**Ubicación:** `a2lt_stock_project/settings.py:239`

```python
CSRF_COOKIE_HTTPONLY = False  # False para que JS (getCookie) pueda leerlo via A6
```

**Justificación actual:** `base.html` define `getCookie('csrftoken')` para los fetch AJAX. Si `CSRF_COOKIE_HTTPONLY=True`, esa función no puede leer el token desde `document.cookie`.

**Riesgo:** Un XSS en cualquier template permite:
1. `document.cookie.match(/csrftoken=([^;]+)/)[1]` → obtener el token.
2. Fetch con `X-CSRFToken` header → operaciones state-changing forjadas.
3. Como el token está atado a la sesión, el atacante puede combinar XSS + robo de sesión.

**¿Está mitigado por XSS?** Sí y no. `TestSecurityXSS` valida que los campos de texto (`descripcion`, `ficha_tecnica`, `social_quick`, `social_cross`, `observaciones`) están escapados. Pero un `{{ var|safe }}` accidental o un `mark_safe` mal usado reintroduce el vector.

**Remediación:** leer el token desde el DOM en vez de la cookie.

```html
<!-- base.html -->
<meta name="csrf-token" content="{{ csrf_token }}">
```

```javascript
function getCsrfToken() {
    return document.querySelector('meta[name=csrf-token]').getAttribute('content');
}
```

```python
# settings.py
CSRF_COOKIE_HTTPONLY = True
```

**Esfuerzo:** S (1-2 horas).
**Prioridad:** P1.
**Riesgo si no se hace:** 🟠 Bypass CSRF si hay XSS.

---

#### SEC-03 — `SECURE_PROXY_SSL_HEADER` fuera de `if not DEBUG` (🟡 MEDIA)

**Ubicación:** `a2lt_stock_project/settings.py:167`

```python
if not DEBUG:
    ...
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # línea 167
```

Espera. Voy a corregir esto. La línea 167 está **dentro** del `if not DEBUG`. Entonces no es "fuera de `!DEBUG`". Cambio la clasificación.

**Corrección:** está **dentro** de `if not DEBUG`, que es correcto. El riesgo es distinto:

**Riesgo:** Si el sistema se despliega **sin reverse proxy confiable** delante (por ejemplo, en LAN directa sobre HTTP), Django acepta `X-Forwarded-Proto: https` como válido y cree que la request es HTTPS. Eso afecta:
- El origin check de CSRF: un atacante en la misma LAN puede enviar `X-Forwarded-Proto: https` para bypassear el check.
- `request.is_secure()` retorna `True` aunque la request viaje por HTTP.
- Cookies `Secure` (si se activaran) se pondrían, pero el cliente las enviaría igual por HTTP → exposure.

**Es un problema solo si el despliegue no tiene un reverse proxy confiable.** En un despliegue on-premise con Apache/Nginx delante, es correcto.

**Remediación:** documentar en `SETUP.md` que `SECURE_PROXY_SSL_HEADER` **asume** un reverse proxy confiable. Si no se va a usar proxy, eliminarlo del `settings.py`.

**Esfuerzo:** S (documentación).
**Prioridad:** P2.
**Riesgo si no se hace:** 🟡 Solo si despliegue sin proxy.

---

#### SEC-04 — `ADMINS` decorativo, sin `mail_admins` handler (🟡 MEDIA)

**Ubicación:** `settings.py:245-247` + `LOGGING` (`settings.py:183-232`)

```python
ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', 'admin@localhost')
ADMINS = [('Admin A2LT', ADMIN_EMAIL)]
MANAGERS = ADMINS
```

Pero el `LOGGING['handlers']` solo define `console` y `file`. **No hay `mail_admins` handler.** Los errores 500 se escriben a `logs/a2lt_stock.log` pero **nadie recibe email**.

**Impacto:** falsa sensación de monitoreo. Si la app falla a las 3am, nadie lo sabe hasta que un usuario reporta o alguien lee el log manualmente.

**Remediación:**

```python
LOGGING['handlers']['mail_admins'] = {
    'level': 'ERROR',
    'class': 'django.utils.log.AdminEmailHandler',
}
LOGGING['loggers']['django.request']['handlers'].append('mail_admins')
```

Requiere configurar `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` en el `.env`. Alternativa: monitoreo externo (UptimeRobot pinguea `/` cada 5 min).

**Esfuerzo:** S (2 horas + configuración SMTP).
**Prioridad:** P2.
**Riesgo si no se hace:** 🟡 Fallos silenciosos en producción.

---

#### SEC-05 — CDN sin SRI (`integrity` hash) (🟡 MEDIA)

**Ubicación:** `inventory/templates/inventory/base.html:9`, `login.html:7`

```html
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css">
```

Sin atributos `integrity`, `crossorigin` ni `referrerpolicy`.

**Riesgo:** Ataque supply chain. Si el CDN (Cloudflare o jsDelivr) es comprometido, un atacante inyecta JS arbitrario en la app. Como el JS tiene acceso a `document.cookie`, `localStorage`, `fetch` con CSRF token, es escalada directa.

**Remediación (opción A — SRI):**

```html
<script
    src="https://cdn.tailwindcss.com"
    integrity="sha384-<hash_real>"
    crossorigin="anonymous"></script>
```

Obtener hash: `openssl dgst -sha384 -binary tailwind.js | openssl base64 -A`. Requiere pinear la versión del CDN.

**Remediación (opción B — build local, más robusta):**

```bash
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init
# Configurar content en tailwind.config.js
npx tailwindcss -i input.css -o static/css/tailwind.min.css --minify
```

Servir `tailwind.min.css` desde `static/`. Elimina la dependencia del CDN.

**Esfuerzo:** M (4-6 horas si build local; 30 min si SRI).
**Prioridad:** P2.
**Riesgo si no se hace:** 🟡 Supply chain.

---

#### SEC-06 — Página de error 403 como texto plano (🟢 BAJA)

**Ubicación:** `middleware.py:113-143` — `HttpResponseForbidden('Acceso Denegado: ...')`

Cuando el middleware detecta acceso no autorizado, retorna texto plano en vez de un template.

**Impacto:** UX pobre, sin navegación, sin branding, sin instrucciones. No es un fallo de seguridad, es cosmético.

**Remediación:** `render(request, 'inventory/403.html', {'mensaje': msg}, status=403)` + crear el template heredando de `base.html`.

**Esfuerzo:** S (1-2 horas).
**Prioridad:** P3.
**Riesgo si no se hace:** 🟢 Solo UX.

---

#### SEC-07 — `SECURE_BROWSER_XSS_FILTER` deprecado en Django 5+ (🟢 BAJA)

**Ubicación:** `settings.py:160`

```python
SECURE_BROWSER_XSS_FILTER = True  # deprecado desde Django 5.0
```

En Django 5.0+, este setting es un no-op. El header `X-XSS-Protection` fue deprecado por los navegadores porque introdujo vulnerabilidades propias.

**Remediación:** eliminar la línea. Si se quiere protección XSS moderna, usar CSP (`django-csp` o headers manuales).

**Esfuerzo:** S (5 minutos).
**Prioridad:** P3.
**Riesgo si no se hace:** 🟢 Ninguno real (no-op).

---


## 8. Auditoría de integridad de datos

### 8.1 Esquema de la base de datos (31 tablas)

La BD `db.sqlite3` contiene 31 tablas: **20 de negocio (`inventory_*`)**, **10 de Django/contrib**, y **1 auxiliar (`sqlite_sequence`)**. El esquema a continuación se reconstruyó desde `models.py` + las 18 migraciones + la salida verificada de `sqlite_master` (§4.3). Los tipos son los que SQLite infiere de Django (`INTEGER`, `VARCHAR`, `DECIMAL`, `BOOLEAN`, `DATETIME`, `TEXT`, `JSON`). Los `CHECK` de Django se emiten como `CHECK` de SQLite cuando son `CheckConstraint`.

#### 8.1.1 Tablas de Django (10)

```
auth_group                  — grupos de permisos de Django
auth_group_permissions      — M2M grupos ↔ permisos
auth_permission             — catálogo de permisos
auth_user                   — usuarios
auth_user_groups            — M2M usuarios ↔ grupos
auth_user_user_permissions  — M2M usuarios ↔ permisos
django_admin_log            — log de acciones del admin
django_content_type         — tipos de contenido
django_migrations           — migraciones aplicadas (18 registros de inventory)
django_session              — sesiones (DB-backed)
```

Sin observaciones: schema estándar de Django.

#### 8.1.2 Tablas de negocio (20)

**`inventory_empresa`** — entidad raíz multi-tenant.
```sql
CREATE TABLE inventory_empresa (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre       VARCHAR(150) NOT NULL,
    rif          VARCHAR(20)  NOT NULL UNIQUE,
    direccion    TEXT         NOT NULL DEFAULT '',
    telefono     VARCHAR(30)  NOT NULL DEFAULT '',
    correo       VARCHAR(254) NOT NULL DEFAULT '',
    activa       BOOLEAN      NOT NULL DEFAULT 1,
    fecha_registro DATETIME   NOT NULL
);
```
Sin FK. `rif` es UNIQUE global.

**`inventory_configuracionempresa`** — OneToOne con Empresa. 30+ columnas de config.
```sql
CREATE TABLE inventory_configuracionempresa (
    id                                INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id                        INTEGER NOT NULL UNIQUE REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    tasa_bcv                          DECIMAL(12,4) NOT NULL DEFAULT 0,
    tasa_mercado                      DECIMAL(12,4) NOT NULL DEFAULT 0,
    factor_cobertura                  DECIMAL(8,4)  NOT NULL DEFAULT 1,
    margen_global                     DECIMAL(5,2)  NOT NULL DEFAULT 30,
    metodo_ganancia_global            VARCHAR(10)   NOT NULL DEFAULT 'MARGIN',
    descuento_global                  DECIMAL(5,2)  NOT NULL DEFAULT 5,
    redondeo_activo                   BOOLEAN       NOT NULL DEFAULT 0,
    factor_redondeo                   DECIMAL(8,2)  NOT NULL DEFAULT 5,
    prefijo_nota_entrega              VARCHAR(20)   NOT NULL DEFAULT 'NE',
    correlativo_inicial_nota          INTEGER       NOT NULL DEFAULT 1,
    prefijo_factura_compra            VARCHAR(20)   NOT NULL DEFAULT 'FC',
    correlativo_inicial_factura_compra INTEGER      NOT NULL DEFAULT 1,
    ivas_disponibles                  JSON          NOT NULL DEFAULT '[]',
    prefijo_nota_credito              VARCHAR(20)   NOT NULL DEFAULT 'NC',
    correlativo_inicial_nota_credito  INTEGER       NOT NULL DEFAULT 1,
    permite_venta_sin_stock           BOOLEAN       NOT NULL DEFAULT 0,
    api_url                           VARCHAR(500)  NOT NULL DEFAULT '',
    http_method                       VARCHAR(4)    NOT NULL DEFAULT 'GET',
    response_selector                 VARCHAR(200)  NOT NULL DEFAULT '',
    print_offset_x                    DECIMAL(5,2)  NOT NULL DEFAULT 0,
    print_offset_y                    DECIMAL(5,2)  NOT NULL DEFAULT 0,
    print_row_spacing                 DECIMAL(5,2)  NOT NULL DEFAULT 5,
    usa_almacen_cuarentena            BOOLEAN       NOT NULL DEFAULT 0,
    cross_selling_header              TEXT          NOT NULL,
    cross_selling_footer              TEXT          NOT NULL
);
```
**Sin `CHECK` constraints** sobre tasas, márgenes o descuentos. Ver DATA-08.

**`inventory_perfilusuario`** — extensión 1:1 de `auth_user`.
```sql
CREATE TABLE inventory_perfilusuario (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id          INTEGER NOT NULL UNIQUE REFERENCES auth_user(id) ON DELETE CASCADE,
    empresa_activa_id INTEGER REFERENCES inventory_empresa(id) ON DELETE SET NULL
);
```
`empresa_activa_id` nullable (puede no tener empresa activa asignada).

**`inventory_perfilusuario_empresas_permitidas`** — M2M auto-generada.
```sql
CREATE TABLE inventory_perfilusuario_empresas_permitidas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    perfilusuario_id INTEGER NOT NULL REFERENCES inventory_perfilusuario(id) ON DELETE CASCADE,
    empresa_id      INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    UNIQUE (perfilusuario_id, empresa_id)
);
```

**`inventory_almacen`** — almacenes físicos.
```sql
CREATE TABLE inventory_almacen (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id   INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    nombre       VARCHAR(100) NOT NULL,
    es_principal BOOLEAN NOT NULL DEFAULT 0,
    activo       BOOLEAN NOT NULL DEFAULT 1
);
```
**Sin `UniqueConstraint(empresa, es_principal=True)`.** Un tenant puede tener 2 almacenes marcados `es_principal=True`. Es un invariante no enforced.

**`inventory_articulo`** — catálogo. PK = `sku` (CharField).
```sql
CREATE TABLE inventory_articulo (
    sku                 VARCHAR(50) PRIMARY KEY,
    empresa_id          INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    codigo_proveedor    VARCHAR(100) NOT NULL DEFAULT '',
    nombre              VARCHAR(200) NOT NULL,
    categoria           VARCHAR(20)  NOT NULL DEFAULT 'OTROS',
    tipo                VARCHAR(10)  NOT NULL DEFAULT 'FISICO',
    usa_serial          BOOLEAN      NOT NULL DEFAULT 0,
    costo               DECIMAL(14,4) NOT NULL DEFAULT 0,
    precio_divisa       DECIMAL(14,4) NOT NULL DEFAULT 0,
    metodo_ganancia     VARCHAR(10)  NOT NULL DEFAULT 'MARGIN',
    margen_ind          DECIMAL(5,2) NOT NULL DEFAULT 30,
    descuento_ind       DECIMAL(5,2) NOT NULL DEFAULT 5,
    cobertura_ind       DECIMAL(8,4) NULL,
    iva_porcentaje      DECIMAL(5,2) NOT NULL DEFAULT 16,
    descripcion         TEXT NOT NULL DEFAULT '',
    ficha_tecnica       TEXT NULL,
    social_quick        TEXT NULL,
    social_cross        TEXT NULL,
    activo              BOOLEAN NOT NULL DEFAULT 1,
    fecha_creacion      DATETIME NOT NULL,
    fecha_actualizacion DATETIME NOT NULL
);

CREATE INDEX idx_articulo_sku_activo ON inventory_articulo (sku, activo);
CREATE INDEX idx_articulo_nombre     ON inventory_articulo (nombre);
```
**Sin `CHECK`** sobre `costo >= 0`, `precio_divisa >= 0`, `iva_porcentaje BETWEEN 0 AND 100`. Todo depende del service layer.

**`inventory_inventarioalmacen`** — stock por (artículo × almacén).
```sql
CREATE TABLE inventory_inventarioalmacen (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    articulo_id                VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE PROTECT,
    empresa_id                 INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    almacen_id                 INTEGER NOT NULL REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    cantidad_disponible        DECIMAL(12,2) NOT NULL DEFAULT 0,
    stock_minimo               DECIMAL(12,2) NOT NULL DEFAULT 0,
    ubicacion_estante          VARCHAR(50) NOT NULL DEFAULT '',
    fecha_ultima_actualizacion DATETIME NOT NULL,
    UNIQUE (articulo_id, almacen_id)
);

CREATE INDEX idx_inv_articulo_almacen ON inventory_inventarioalmacen (articulo_id, almacen_id);
```
**Sin `CHECK (cantidad_disponible >= 0)`.** El Kárdex puede dejar saldo negativo si `permite_venta_sin_stock=True`. Los saldos negativos son **intencionales** (drop-ship / forward), no un bug.

**`inventory_recetacombo`** — componentes de combo.
```sql
CREATE TABLE inventory_recetacombo (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    combo_id           VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE CASCADE,
    componente_id      VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE PROTECT,
    cantidad_requerida DECIMAL(10,2) NOT NULL,
    UNIQUE (combo_id, componente_id)
);
```

**`inventory_contacto`** — clientes + proveedores unificados. PK = `identificacion`.
```sql
CREATE TABLE inventory_contacto (
    identificacion  VARCHAR(20) PRIMARY KEY,
    empresa_id      INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    nombre          VARCHAR(200) NOT NULL,
    tipo            VARCHAR(10)  NOT NULL DEFAULT 'CLIENTE',
    telefono        VARCHAR(30)  NOT NULL DEFAULT '',
    correo          VARCHAR(254) NOT NULL DEFAULT '',
    red_social      VARCHAR(100) NOT NULL DEFAULT '',
    direccion       TEXT NOT NULL DEFAULT '',
    observaciones   TEXT NOT NULL DEFAULT '',
    rif             VARCHAR(20) NULL,
    nombre_asesor   VARCHAR(150) NULL,
    fecha_registro  DATETIME NOT NULL
);
```
**`rif` y `nombre_asesor` nullable** aunque la vista los exige para PROVEEDOR. Ver DATA-04.

**`inventory_documentocompra`** — cabecera de compra.
```sql
CREATE TABLE inventory_documentocompra (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id                  INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    proveedor_id                VARCHAR(20) NOT NULL REFERENCES inventory_contacto(identificacion) ON DELETE PROTECT,
    tipo_documento              VARCHAR(30) NOT NULL DEFAULT 'FACTURA_COMPRA',
    numero_interno              VARCHAR(50) NOT NULL DEFAULT '',
    numero                      INTEGER NOT NULL DEFAULT 0,
    numero_factura              VARCHAR(100) NOT NULL DEFAULT '',
    fecha_compra                DATE NULL,
    monto_total_usd             DECIMAL(14,4) NOT NULL,
    descuento_global            DECIMAL(5,2) NOT NULL DEFAULT 0,
    iva_total                   DECIMAL(14,4) NOT NULL DEFAULT 0,
    tasa_bcv_aplicada           DECIMAL(12,4) NULL,
    tasa_mercado_aplicada       DECIMAL(12,4) NULL,
    factor_cobertura_aplicado   DECIMAL(8,4)  NULL,
    fuente_tasa                 VARCHAR(20) NOT NULL DEFAULT '',
    monto_total_bs_snapshot     DECIMAL(18,2) NULL,
    fecha_registro              DATETIME NOT NULL,
    estado                      VARCHAR(20) NOT NULL DEFAULT 'PROCESADO',
    motivo_anulacion            TEXT NULL,
    observaciones               TEXT NOT NULL DEFAULT '',
    -- Constraints condicionales
    UNIQUE (empresa_id, numero_factura) WHERE numero_factura != '',
    UNIQUE (empresa_id, numero_interno) WHERE numero_interno != ''
);
```
**`UniqueConstraint` condicionales** correctos. `estado` sin `CHECK` (admite valores arbitrarios vía ORM `.update()`). Ver EST-02.

**`inventory_detalledocumentocompra`** — línea de compra.
```sql
CREATE TABLE inventory_detalledocumentocompra (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    documento_compra_id     INTEGER NOT NULL REFERENCES inventory_documentocompra(id) ON DELETE CASCADE,
    articulo_id             VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE PROTECT,
    almacen_id              INTEGER NOT NULL REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    cantidad                DECIMAL(14,4) NOT NULL,
    costo_base              DECIMAL(14,4) NOT NULL,
    costo_ajustado          DECIMAL(14,4) NOT NULL,
    costo_directo_bcv       DECIMAL(14,2) NOT NULL,
    costo_ajustado_bcv      DECIMAL(14,2) NOT NULL,
    costo_unitario_snapshot DECIMAL(14,4) NOT NULL DEFAULT 0,
    descuento_aplicado      DECIMAL(5,2)  NOT NULL DEFAULT 0,
    iva_porcentaje          DECIMAL(5,2)  NOT NULL DEFAULT 16
);
```

**`inventory_movimientokardex`** — registro inmutable de ENTRADA/SALIDA.
```sql
CREATE TABLE inventory_movimientokardex (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora         DATETIME NOT NULL,
    empresa_id         INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    articulo_id        VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE PROTECT,
    almacen_id         INTEGER NOT NULL REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    tipo               VARCHAR(7)  NOT NULL,
    concepto           VARCHAR(60) NOT NULL,
    cantidad           DECIMAL(12,2) NOT NULL,
    saldo_resultante   DECIMAL(12,2) NOT NULL,
    nota_entrega_id    INTEGER REFERENCES inventory_notaentrega(id) ON DELETE SET NULL,
    documento_compra_id INTEGER REFERENCES inventory_documentocompra(id) ON DELETE SET NULL,
    lote_carga         VARCHAR(100) NOT NULL DEFAULT '',
    detalle_adicional  TEXT NOT NULL DEFAULT '',
    usuario            VARCHAR(150) NOT NULL DEFAULT ''
);
```
**Sin índice compuesto** `(fecha_hora, articulo, almacen)` para reportes filtrados. Ver DATA-06.
**`usuario` como CharField** (no FK a `auth_user`). Ver EST-04.
**`tipo` sin `CHECK`** — `'INVALIDO'` es un valor aceptable por la BD. Ver DATA-08 extendido.

**`inventory_auditoriatasa`** — histórico de tasas.
```sql
CREATE TABLE inventory_auditoriatasa (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_hora      DATETIME NOT NULL,
    empresa_id      INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    tasa_bcv        DECIMAL(12,4) NOT NULL,
    tasa_mercado    DECIMAL(12,4) NOT NULL,
    factor_cobertura DECIMAL(8,4) NOT NULL,
    fuente          VARCHAR(10) NOT NULL DEFAULT 'MANUAL',
    notas           VARCHAR(200) NOT NULL DEFAULT ''
);
```
**Sin campo `usuario`.** No se registra quién cambió la tasa. Ver EST-05.

**`inventory_notaentrega`** — cabecera de venta (NE o Factura).
```sql
CREATE TABLE inventory_notaentrega (
    id                         INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id                 INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    numero                     INTEGER NOT NULL,
    tipo_documento             VARCHAR(15) NOT NULL DEFAULT 'NOTA_ENTREGA',
    numero_nota                VARCHAR(30) NOT NULL DEFAULT '',
    numero_factura             VARCHAR(100) NOT NULL DEFAULT '',
    fecha                      DATETIME NOT NULL,
    cliente_id                 VARCHAR(20) REFERENCES inventory_contacto(identificacion) ON DELETE SET NULL,
    almacen_id                 INTEGER NOT NULL REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    estado                     VARCHAR(20) NOT NULL DEFAULT 'PROCESADO',
    motivo_anulacion           TEXT NULL,
    moneda_pago                VARCHAR(12) NOT NULL DEFAULT 'USD',
    tasa_bcv_aplicada          DECIMAL(12,4) NOT NULL DEFAULT 0,
    factor_cobertura_aplicado  DECIMAL(8,4)  NOT NULL DEFAULT 1,
    tasa_mercado_aplicada      DECIMAL(12,4) NOT NULL DEFAULT 0,
    iva_check                  BOOLEAN NOT NULL DEFAULT 0,
    iva_total                  DECIMAL(14,4) NOT NULL DEFAULT 0,
    descuento_global           DECIMAL(5,2)  NOT NULL DEFAULT 0,
    observaciones              TEXT NOT NULL DEFAULT '',
    UNIQUE (empresa_id, numero),
    UNIQUE (empresa_id, numero_nota)    WHERE numero_nota != '',
    UNIQUE (empresa_id, numero_factura) WHERE numero_factura != ''
);
```
`numero` con `Max+1` en `save()` → race condition (EST-03).

**`inventory_detallenotaentrega`** — línea de venta.
```sql
CREATE TABLE inventory_detallenotaentrega (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    nota_entrega_id         INTEGER NOT NULL REFERENCES inventory_notaentrega(id) ON DELETE CASCADE,
    articulo_id             VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE PROTECT,
    almacen_id              INTEGER REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    cantidad                DECIMAL(12,2) NOT NULL,
    precio_base             DECIMAL(14,4) NOT NULL DEFAULT 0,
    precio_ajustado         DECIMAL(14,4) NOT NULL DEFAULT 0,
    precio_directo_bcv      DECIMAL(16,2) NOT NULL DEFAULT 0,
    precio_ajustado_bcv     DECIMAL(16,2) NOT NULL DEFAULT 0,
    costo_unitario_snapshot DECIMAL(14,4) NOT NULL DEFAULT 0,
    descuento_aplicado      DECIMAL(5,2)  NOT NULL DEFAULT 0,
    iva_porcentaje          DECIMAL(5,2)  NOT NULL DEFAULT 0
);
```
**`almacen_id` nullable** (DATA-03). Si una línea no tiene almacén, el Kárdex no sabe de dónde descontó.

**`inventory_serialarticulo`** — trazabilidad unitaria.
```sql
CREATE TABLE inventory_serialarticulo (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id       INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    articulo_id      VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE CASCADE,
    serial           VARCHAR(100) NOT NULL,
    compra_origen_id INTEGER REFERENCES inventory_documentocompra(id) ON DELETE SET NULL,
    almacen_id       INTEGER NOT NULL REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    estado           VARCHAR(15) NOT NULL DEFAULT 'DISPONIBLE',
    detalle_nota_id  INTEGER REFERENCES inventory_detallenotaentrega(id) ON DELETE SET NULL,
    UNIQUE (empresa_id, serial)
);
```
**Sin `CHECK`** que impida `estado='VENDIDO' AND detalle_nota_id IS NULL` (registro huérfano lógico).

**`inventory_notacredito`** — cabecera de NC. 1-NC-1-origen (ADR-29).
```sql
CREATE TABLE inventory_notacredito (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id             INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    nota_entrega_id        INTEGER REFERENCES inventory_notaentrega(id) ON DELETE PROTECT,
    factura_compra_id      INTEGER REFERENCES inventory_documentocompra(id) ON DELETE PROTECT,
    prefijo                VARCHAR(20) NOT NULL DEFAULT '',
    numero                 INTEGER NOT NULL DEFAULT 0,
    numero_control         VARCHAR(50) NOT NULL DEFAULT '',
    doc_origen_tipo        VARCHAR(10) NOT NULL DEFAULT 'VENTA',
    motivo                 TEXT NOT NULL,
    monto_total_reembolso  DECIMAL(16,4) NOT NULL DEFAULT 0,
    estado                 VARCHAR(10) NOT NULL DEFAULT 'PROCESADO',
    motivo_anulacion       TEXT NOT NULL DEFAULT '',
    usuario                VARCHAR(150) NOT NULL DEFAULT 'Sistema',
    fecha                  DATETIME NOT NULL,
    CHECK (
        (nota_entrega_id IS NOT NULL AND factura_compra_id IS NULL)
        OR
        (nota_entrega_id IS NULL AND factura_compra_id IS NOT NULL)
    )
);
```
`CHECK` XOR correcto (ADR-29).
**Sin `UniqueConstraint (empresa, numero)` ni `(empresa, numero_control)`.** Dos NC concurrentes pueden colisionar en el correlativo (EST-03).
**`usuario` como CharField** (EST-04).

**`inventory_detallenotacredito`** — línea de NC.
```sql
CREATE TABLE inventory_detallenotacredito (
    id                        INTEGER PRIMARY KEY AUTOINCREMENT,
    nota_credito_id           INTEGER NOT NULL REFERENCES inventory_notacredito(id) ON DELETE CASCADE,
    detalle_origen_venta_id   INTEGER REFERENCES inventory_detallenotaentrega(id) ON DELETE PROTECT,
    detalle_origen_compra_id  INTEGER REFERENCES inventory_detalledocumentocompra(id) ON DELETE PROTECT,
    articulo_id               VARCHAR(50) NOT NULL REFERENCES inventory_articulo(sku) ON DELETE PROTECT,
    almacen_id                INTEGER REFERENCES inventory_almacen(id) ON DELETE PROTECT,
    cantidad_devuelta         DECIMAL(14,4) NOT NULL DEFAULT 0,
    precio_unitario_snapshot  DECIMAL(14,4) NOT NULL DEFAULT 0,
    iva_porcentaje_snapshot   DECIMAL(5,2) NOT NULL DEFAULT 0,
    subtotal_devuelto_usd     DECIMAL(16,4) NOT NULL DEFAULT 0,
    iva_usd                   DECIMAL(16,4) NOT NULL DEFAULT 0,
    linea_total_usd           DECIMAL(16,4) NOT NULL DEFAULT 0,
    fecha                     DATETIME NULL,
    CHECK (
        (detalle_origen_venta_id IS NOT NULL AND detalle_origen_compra_id IS NULL)
        OR
        (detalle_origen_venta_id IS NULL AND detalle_origen_compra_id IS NOT NULL)
    )
);
```
`CHECK` XOR correcto.
**`almacen_id` nullable**, con `help_text` que promete `clean()` inexistente. Ver EST-07.

**`inventory_moneda`** — catálogo de monedas por tenant.
```sql
CREATE TABLE inventory_moneda (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    codigo     VARCHAR(3) NOT NULL,
    nombre     VARCHAR(50) NOT NULL,
    simbolo    VARCHAR(5) NOT NULL DEFAULT '$',
    decimales  SMALLINT NOT NULL DEFAULT 2,
    es_base    BOOLEAN NOT NULL DEFAULT 0,
    activa     BOOLEAN NOT NULL DEFAULT 1,
    UNIQUE (empresa_id, codigo)
);
```
**Sin `UniqueConstraint(empresa, condition=Q(es_base=True))`.** `save()` intenta enforcarlo pero hay race condition (DATA-09).

**`inventory_tasacambio`** — histórico de pares de monedas.
```sql
CREATE TABLE inventory_tasacambio (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    empresa_id      INTEGER NOT NULL REFERENCES inventory_empresa(id) ON DELETE CASCADE,
    moneda_origen_id INTEGER NOT NULL REFERENCES inventory_moneda(id) ON DELETE PROTECT,
    moneda_destino_id INTEGER NOT NULL REFERENCES inventory_moneda(id) ON DELETE PROTECT,
    tasa            DECIMAL(18,6) NOT NULL,
    fecha           DATE NOT NULL,
    fuente          VARCHAR(20) NOT NULL DEFAULT 'MANUAL',
    usuario         VARCHAR(150) NOT NULL DEFAULT '',
    notas           VARCHAR(255) NOT NULL DEFAULT '',
    creada_en       DATETIME NOT NULL
);

CREATE INDEX idx_tasacambio_empresa_par_fecha ON inventory_tasacambio (empresa_id, moneda_origen_id, moneda_destino_id, -fecha);
```
**Sin `UniqueConstraint(empresa, moneda_origen, moneda_destino, fecha)`.** Duplicados posibles (DATA-10).
**`tasa` sin `CHECK (tasa > 0)`.** Ver DATA-08.

### 8.2 Constraints e índices — verificación

| Tabla | Constraint / Índice | Estado | Origen |
|---|---|---|---|
| `inventory_empresa` | `UNIQUE(rif)` | ✅ | `models.py:60` |
| `inventory_configuracionempresa` | `UNIQUE(empresa_id)` (OneToOne) | ✅ | `models.py:78` |
| `inventory_perfilusuario` | `UNIQUE(user_id)` (OneToOne) | ✅ | `models.py:339` |
| `inventory_perfilusuario_empresas_permitidas` | `UNIQUE(perfilusuario_id, empresa_id)` | ✅ | Auto-generada |
| `inventory_articulo` | `PRIMARY KEY(sku)` (CharField) | ✅ | `models.py:435` |
| `inventory_articulo` | `Index(sku, activo)` | ✅ | `models.py:566` |
| `inventory_articulo` | `Index(nombre)` | ✅ | `models.py:567` |
| `inventory_inventarioalmacen` | `UNIQUE(articulo_id, almacen_id)` | ✅ | `models.py:668` |
| `inventory_inventarioalmacen` | `Index(articulo_id, almacen_id)` | ✅ | `models.py:671` |
| `inventory_recetacombo` | `UNIQUE(combo_id, componente_id)` | ✅ | `models.py:713` |
| `inventory_contacto` | `PRIMARY KEY(identificacion)` (CharField) | ✅ | `models.py:745` |
| `inventory_documentocompra` | `UNIQUE(empresa, numero_factura) WHERE != ''` | ✅ | `models.py:945` |
| `inventory_documentocompra` | `UNIQUE(empresa, numero_interno) WHERE != ''` | ✅ | `models.py:950` |
| `inventory_movimientokardex` | Índice `(fecha_hora)` (ordering) | ⚠️ Solo el implícito por `ordering`, falta compuesto | — |
| `inventory_notaentrega` | `UNIQUE(empresa, numero)` | ✅ | `models.py:1437` |
| `inventory_notaentrega` | `UNIQUE(empresa, numero_nota) WHERE != ''` | ✅ | `models.py:1441` |
| `inventory_notaentrega` | `UNIQUE(empresa, numero_factura) WHERE != ''` | ✅ | `models.py:1446` |
| `inventory_serialarticulo` | `UNIQUE(empresa, serial)` | ✅ | `models.py:1746` |
| `inventory_notacredito` | `CHECK XOR(nota_entrega, factura_compra)` | ✅ | `models.py:1837` |
| `inventory_notacredito` | `UNIQUE(empresa, numero)` | ❌ **FALTA** | — |
| `inventory_notacredito` | `UNIQUE(empresa, numero_control)` | ❌ **FALTA** | — |
| `inventory_detallenotacredito` | `CHECK XOR(detalle_origen_venta, detalle_origen_compra)` | ✅ | `models.py:1980` |
| `inventory_moneda` | `UNIQUE(empresa, codigo)` | ✅ | `models.py:2045` |
| `inventory_moneda` | `UNIQUE(empresa) WHERE es_base=True` | ❌ **FALTA** | — |
| `inventory_tasacambio` | `Index(empresa, par, -fecha)` | ✅ | `models.py:2100` |
| `inventory_tasacambio` | `UNIQUE(empresa, par, fecha)` | ❌ **FALTA** | — |

**Resumen:** 20 constraints definidos, **4 faltantes** que producirían corrupción de datos bajo concurrencia (NotaCredito correlativos, Moneda `es_base`, TasaCambio duplicados). Ver EST-03, DATA-09, DATA-10.

### 8.3 PRAGMAs y configuración de la conexión

| PRAGMA | Valor | Línea | Efecto |
|---|---|---|---|
| `journal_mode` | `wal` | `settings.py:103` | Lectura concurrente con 1 escritor |
| `synchronous` | `NORMAL` | `settings.py:104` | Balance seguridad/performance (WAL sincroniza solo en checkpoints) |
| `foreign_keys` | `ON` | `settings.py:105` | Constraints FK enforced (crítico para integridad) |
| `busy_timeout` | `5000` | `settings.py:106` | 5s de espera si la BD está bloqueada |
| `cache_size` | `-64000` | `settings.py:107` | 64 MB de caché (negativo = KB) |
| `timeout` (Django) | `20` | `settings.py:101` | Timeout de conexión Django |

**Verificación:** `PRAGMA integrity_check` → `ok`. `PRAGMA foreign_key_check` → 0 filas. **La BD actual está consistente.**

**Nota importante:** `PRAGMA foreign_keys` es **por conexión**, no persiste en el archivo. Las conexiones directas con `sqlite3.connect()` lo tienen `OFF` por defecto. Si alguien manipula la BD fuera de Django (SQLite CLI, script de backup manipulado, migración manual), **puede insertar huérfanos sin que nada lo impida**. Django lo activa vía `init_command`, pero eso solo protege las queries que pasan por Django.

### 8.4 Huérfanos lógicos — análisis

**Verificados en la BD real:** `PRAGMA foreign_key_check` → **0 filas**. La BD actual **no tiene huérfanos de FK**.

**Huérfanos lógicos posibles** (no de FK, sino de estado inconsistente):

| # | Escenario | Query de detección | Estado |
|---|---|---|---|
| 1 | `SerialArticulo` con `estado='VENDIDO' AND detalle_nota_id IS NULL` | `SELECT * FROM inventory_serialarticulo WHERE estado='VENDIDO' AND detalle_nota_id IS NULL` | No verificado en BD real. **Posible si un delete de `DetalleNotaEntrega` con `SET_NULL` se ejecuta** — Django no permite borrar detalles (CASCADE desde NE, PROTECT desde NC), pero un `UPDATE` manual o `bulk_update` puede dejar el estado inconsistente |
| 2 | `DetalleNotaEntrega.almacen_id IS NULL` | `SELECT * FROM inventory_detallenotaentrega WHERE almacen_id IS NULL` | No verificado. El campo es nullable. Si existe, el Kárdex no tiene trazabilidad del almacén origen |
| 3 | `MovimientoKardex` con `articulo_id` que no existe | `SELECT * FROM inventory_movimientokardex WHERE articulo_id NOT IN (SELECT sku FROM inventory_articulo)` | **Imposible** — FK `PROTECT` lo previene |
| 4 | `DetalleNotaCredito` con `almacen_id IS NULL` | `SELECT * FROM inventory_detallenotacredito WHERE almacen_id IS NULL` | No verificado. El `save()` no valida. `help_text` promete `clean()` pero no existe (EST-07) |
| 5 | `NotaCredito` con `numero=0` (default) | `SELECT * FROM inventory_notacredito WHERE numero=0` | **Imposible** — `save()` genera el correlativo. Pero si el `save()` falla entre `_next_correlativo` y `super().save()`, podría quedar `numero=0` |
| 6 | `ConfiguracionEmpresa` faltante para alguna `Empresa` | `SELECT * FROM inventory_empresa WHERE id NOT IN (SELECT empresa_id FROM inventory_configuracionempresa)` | **Imposible por signal** (`create_tenant_defaults`). Pero si el signal falla o se borra manualmente, sí |
| 7 | `Moneda` con 0 o >1 `es_base=True` por empresa | `SELECT empresa_id, COUNT(*) FROM inventory_moneda WHERE es_base=1 GROUP BY empresa_id HAVING COUNT(*) != 1` | No verificado. `save()` intenta enforcarlo pero hay race (DATA-09) |
| 8 | `InventarioAlmacen` con `articulo.tipo='COMBO'` | `SELECT * FROM inventory_inventarioalmacen ia JOIN inventory_articulo a ON ia.articulo_id=a.sku WHERE a.tipo='COMBO'` | **Imposible** — `limit_choices_to={'tipo': 'FISICO'}` en el FK (solo admin) + `registrar_movimiento` rechaza COMBO. Pero un INSERT manual podría |

**Recomendación:** agregar un management command `python manage.py check_orphans` que corra estas 8 queries y reporte filas. Útil para auditorías futuras sin tener que recordar las queries.

### 8.5 Validación en escritura — matriz de cobertura

| Campo | Validación ORM | Validación Service | Validación BD | Gap |
|---|---|---|---|---|
| `Articulo.costo` | `DecimalField` | `procesar_carga_masiva` valida ≥ 0 | ❌ No `CHECK` | Validación solo en service |
| `Articulo.precio_divisa` | `DecimalField` | `procesar_venta` usa snapshot | ❌ No `CHECK` | Se toma de `item.precio_base`, no del campo. El campo puede ser negativo sin que nada lo impida |
| `Articulo.iva_porcentaje` | `DecimalField(default=16)` | `procesar_venta` valida 0-100 (si viene del item) | ❌ No `CHECK` | El campo del modelo puede ser 999 sin validación si se crea por admin |
| `InventarioAlmacen.cantidad_disponible` | `DecimalField` | **Solo `registrar_movimiento`** | ❌ No `CHECK` | Regla Sagrada es intención, no enforced. Un `UPDATE` directo es posible (ver EST-01) |
| `Contacto.rif` | `CharField(null=True)` | `contactos_view` valida para PROVEEDOR | ❌ No `CHECK` | Bypass de UI permite crear PROVEEDOR sin RIF |
| `ConfiguracionEmpresa.tasa_bcv` | `DecimalField` | `procesar_venta` valida > 0 | ❌ No `CHECK` | Se puede guardar `-5` sin que nada falle |
| `ConfiguracionEmpresa.factor_cobertura` | `DecimalField` | `save()` recalcula | ❌ No `CHECK` | Se puede guardar `-1` sin que nada falle |
| `ConfiguracionEmpresa.margen_global` | `DecimalField` | `registrar_compra_proveedor` valida `<100` en MARGIN | ❌ No `CHECK` | Sin validación en el modelo |
| `DetalleNotaEntrega.iva_porcentaje` | `DecimalField` | `procesar_venta` valida 0-100 | ❌ No `CHECK` | Igual que Articulo |
| `DetalleNotaEntrega.descuento_aplicado` | `DecimalField` | `procesar_venta` valida 0-100 | ❌ No `CHECK` | Igual |
| `NotaEntrega.descuento_global` | `DecimalField` | `procesar_venta` valida 0-100 | ❌ No `CHECK` | Igual |
| `NotaEntrega.estado` | `CharField(choices)` | — | ❌ No `CHECK` | `'INVENTADO'` es aceptable por la BD |
| `DocumentoCompra.tipo_documento` | `CharField(choices)` | `registrar_compra_proveedor` valida 3 opciones | ❌ No `CHECK` | Choices no enforced en BD |
| `MovimientoKardex.tipo` | `CharField(choices)` | `registrar_movimiento` valida ENTRADA/SALIDA | ❌ No `CHECK` | Igual |
| `MovimientoKardex.cantidad` | `DecimalField` | `registrar_movimiento` valida > 0 | ❌ No `CHECK` | Igual |
| `TasaCambio.tasa` | `DecimalField` | `obtener_tasa` no valida signo | ❌ No `CHECK` | Una tasa negativa es aceptable |

**Patrón:** casi toda la validación vive en el **service layer**, no en el modelo ni en la BD. Eso significa que:
- ✅ Vistas y API están protegidas.
- ❌ Admin, shell, scripts, imports masivos manuales, y cualquier código nuevo que no use services **no están protegidos**.
- ❌ Un `UPDATE` directo por SQL es posible.

Ver DATA-08 (constraints faltantes).

### 8.6 Pruebas destructivas validadas

Estas pruebas se ejecutaron efectivamente (vía la suite de tests) y confirman que el código maneja los casos correctamente:

| # | Prueba | Entrada | Resultado esperado | Veredicto | Test ref |
|---|---|---|---|---|---|
| 1 | SALIDA con stock insuficiente | `cantidad > stock_disponible` | `ValueError` + rollback total (Kárdex vacío, inventario intacto) | ✅ PASS | `TestRollbackAtomicidad.test_salida_insuficiente_hace_rollback_total` |
| 2 | SALIDA sin fila de inventario | Artículo sin `InventarioAlmacen` para ese almacén | `ValueError` si `permite_saldo_negativo=False` | ✅ PASS | `TestRollbackAtomicidad.test_salida_sin_inventario_previo_lanza_error` |
| 3 | Combo con componente sin stock | Componente con stock=0 | `calcular_stock_combo` retorna 0 | ✅ PASS | `TestComboDinamico.test_stock_combo_cero_si_componente_sin_stock` |
| 4 | Desagregación atómica de combo | Venta 2 combos (req 1A + 2B), stock A=10, B=4 | A→8, B→0, combo→0 | ✅ PASS | `TestComboDinamico.test_desagregacion_combo_descuenta_componentes_atomicamente` |
| 5 | Desagregación insuficiente hace rollback | Venta 5 combos con stock B=2 (máx 1 combo) | `ValueError`, A y B intactos | ✅ PASS | `TestComboDinamico.test_desagregacion_combo_insuficiente_hace_rollback` |
| 6 | Carga masiva con errores aislados | Excel 4 OK + 2 con error | 4 procesadas, 2 en `log_errores`, sin rollback | ✅ PASS | `TestCargaMasivaBasica.test_error_en_fila_no_aborta_procesamiento` |
| 7 | Carga masiva rollback total (Ticket #27) | Fila 3 con costo negativo | Rollback total, BD intacta | ✅ PASS | `TestCargaMasivaExcelAtomica.test_carga_masiva_rollback_por_error` |
| 8 | Colisión SUMAR contable | Stock=20, Excel cantidad=8 | Stock=28, 1 movimiento ENTRADA | ✅ PASS | `TestResolverColision.test_resolver_sumar_incrementa_stock_exactamente` |
| 9 | Colisión SUSTITUIR contable | Stock=20, Excel cantidad=15 | Stock=15, 2 movimientos (SALIDA 20 + ENTRADA 15) | ✅ PASS | `TestResolverColision.test_resolver_sustituir_genera_dos_movimientos_en_kardex` |
| 10 | Colisión CANCELAR no toca stock | Stock=20, decisión CANCELAR | Stock=20, 0 movimientos | ✅ PASS | `TestResolverColision.test_resolver_cancelar_no_modifica_inventario` |
| 11 | Reverso de lote bloqueado por salida posterior | Lote cargado + venta posterior de 1 unidad | `ValidationError`, stock intacto | ✅ PASS | `TestReversoLoteCargaMasiva.test_reverso_bloqueado_por_salida_posterior` |
| 12 | Reverso de lote limpio | Lote cargado, sin movimientos posteriores | Stock vuelve a 0, 2 movimientos REVERSO_SALIDA | ✅ PASS | `TestReversoLoteCargaMasiva.test_reverso_exitoso` |
| 13 | Transferencia sin stock origen | `cantidad > stock_origen` | `ValueError`, ambos almacenes intactos | ✅ PASS | `TestMovimientosYajustes.test_transferencia_bloqueada_sin_stock` |
| 14 | Venta con serial race condition | 2 ventas del mismo serial | 2da `ValueError` "ya no está DISPONIBLE" | ✅ PASS | `TestControlDeSerialesPOS.test_error_race_condition_serial_ya_vendido` |
| 15 | Venta con seriales cantidad discordante | Seriales enviados ≠ cantidad | `ValueError`, seriales no quemados | ✅ PASS | `TestControlDeSerialesPOS.test_error_por_cantidad_discordante_de_seriales` |
| 16 | Venta rollback por falta de stock en carrito | 1 item OK + 1 item sin stock | Rollback total (no se crea NE, stock intacto) | ✅ PASS | `TestVentaRollback.test_rollback_por_falta_stock` |
| 17 | Multi-tenant cross-tab pollution | Payload `empresa_id` ≠ ContextVar | `ValueError` "contexto ha cambiado" | ✅ PASS | `TestSaneamientoYVulnerabilidadesSaaS.test_prevencion_contaminacion_multi_pestana` |
| 18 | SSRF URL privada | `http://127.0.0.1/tasa` | `es_url_api_segura` retorna `False`, no se hace request | ✅ PASS | `TestValidacionUrlApiSegura.test_url_privada_bloqueada` |
| 19 | SSRF metadata cloud | `http://169.254.169.254/latest/meta-data` | `es_url_api_segura` retorna `False` | ✅ PASS | `TestValidacionUrlApiSegura.test_url_privada_bloqueada` |
| 20 | Rate limiting login | 5 intentos fallidos consecutivos | 6to bloqueado, contador no incrementa | ✅ PASS | `TestThrottleLogin.test_bloqueo_tras_intentos_fallidos` |
| 21 | Cross-tenant NC sobre nota de otra empresa | `nota_id` de otra empresa | `ValueError`, NC no se crea | ✅ PASS | `TestNotasCreditoBackend.test_nc_otra_empresa_no_puede_acceder` |
| 22 | Doble NC parcial acumula | 2 NCs parciales sobre mismo detalle | `cantidad_devuelta_acumulada` suma correctamente | ✅ PASS | `TestNotasCreditoBackend.test_nc_devolucion_venta_parcial_con_doble_nc` |
| 23 | NC sobre nota anulada falla | `NotaEntrega` en estado ANULADO | `ValueError` | ✅ PASS | `TestNotasCreditoBackend.test_nc_sobre_nota_anulada_falla` |
| 24 | NC rollback atómico | 1 item OK + 1 item falla | Rollback total, NC no se crea | ✅ PASS | `TestNotasCreditoBackend.test_nc_rollback_atomic_si_alguno_falla` |
| 25 | Multi-tenant en venta | `almacen_id` de otra empresa | `ValueError` | ✅ PASS | `TestProcesarVentaAlmacenMultiTenant.test_almacen_de_otra_empresa_es_rechazado` |
| 26 | Multi-tenant en compra | `proveedor_id` de otra empresa | `ValueError` | ✅ PASS | `TestRegistrarCompraProveedorMultiTenant.test_rechaza_proveedor_de_otra_empresa` |
| 27 | Doble reverso de NE bloqueado | Reversar dos veces la misma NE | 2da `ValueError`, stock no se infla | ✅ PASS | `TestReversoIdempotencia.test_doble_reverso_lanza_error_y_no_infla_stock` |
| 28 | SQL Injection en filtros | Payload `' OR 1=1 --` en `sku` | No fuga datos, tenant intacto | ✅ PASS | `TestSecuritySQLInjection.test_multi_tenant_aislado_con_payload_sql` |
| 29 | Serial duplicado en misma empresa | 2 `SerialArticulo` con mismo serial | `IntegrityError` | ✅ PASS | `TestSecuritySerialUniqueConstraint.test_serial_duplicado_en_misma_empresa_lanza_integrity_error` |
| 30 | Serial duplicado en distinta empresa | Mismo serial, distintas empresas | ✅ Permitido | ✅ PASS | `TestSecuritySerialUniqueConstraint.test_mismo_serial_en_diferente_empresa_PERMITIDO` |

**Cobertura:** la suite valida 30 escenarios destructivos que confirman la atomicidad del Kárdex, la integridad de los snapshots financieros, y el aislamiento multi-tenant.

**Lo que la suite NO valida** (gap de cobertura):
- Que `MovimientoKardex.delete()` falle (EST-01).
- Que `NotaEntrega.save()` bloquee cambios en `estado='PROCESADO'` (EST-02).
- Que los correlativos no colisionen bajo concurrencia real (EST-03, skip).
- Que `ConfiguracionEmpresa` rechace `tasa_bcv` negativa (DATA-08).
- Que `Contacto(tipo='PROVEEDOR', rif='')` sea rechazado a nivel modelo (DATA-04).

Estos gaps son la brecha entre "suite verde" y "modelo blindado".

### 8.7 Hallazgos de integridad de datos detallados

#### DATA-01 — Lógica de totales/descuento/IVA duplicada en 4 vistas/PDF (🟠 ALTA)

**Ubicación:** `views.py` — 4 funciones.

- `vista_detalle_nota` (línea ~799)
- `generar_pdf_nota` (línea ~858)
- `vista_detalle_compra` (línea ~977)
- `generar_pdf_compra` (línea ~1036)

Cada una reconstruye manualmente el cálculo de subtotal, descuento global e IVA. **Ya hubo divergencia real**: el PDF y la pantalla mostraban totales distintos en Bs cuando `factor_cobertura != 1`. Se corrigió en F3 pero la duplicación persiste como riesgo.

**Impacto:** Cualquier cambio en la fórmula requiere tocar 4 lugares. La probabilidad de reintroducir la divergencia es alta.

**Remediación:** extraer a `services/utils.py`:

```python
def calcular_totales_documento(detalles, descuento_global):
    """
    Calcula totales consistentes para NE/Factura/Compra/NC.
    Usa propiedades del modelo (subtotal_usd, subtotal_bs, iva_usd, iva_bs).
    """
    factor = Decimal('1') - (descuento_global / Decimal('100'))
    subtotal_usd = sum(d.subtotal_usd for d in detalles)
    subtotal_bs  = sum(d.subtotal_bs for d in detalles)
    total_iva_usd = sum(d.iva_usd for d in detalles)
    total_iva_bs  = sum(d.iva_bs for d in detalles)

    return {
        'subtotal_usd_neto':   (subtotal_usd * factor).quantize(Decimal('0.01')),
        'subtotal_bs_neto':    (subtotal_bs * factor).quantize(Decimal('0.01')),
        'total_iva_usd_neto':  (total_iva_usd * factor).quantize(Decimal('0.01')),
        'total_iva_bs_neto':   (total_iva_bs * factor).quantize(Decimal('0.01')),
        'monto_descuento_usd': (subtotal_usd - subtotal_usd * factor).quantize(Decimal('0.01')),
    }
```

Refactorizar las 4 vistas para usarla.

**Test de aceptación:** `test_totales_consistentes_pdf_vs_pantalla` con `factor_cobertura ∈ {1.0, 1.4, 2.0}`.

**Esfuerzo:** M (8-16 horas).
**Prioridad:** P0.

#### DATA-02 — N+1 queries en dashboard combos (🟠 ALTA)

**Ubicación:** `views.py:171-187` (`dashboard`).

```python
for combo in combos_qs[:10]:
    for alm in almacenes_qs:           # N almacenes
        s = _svc.calcular_stock_combo(combo, alm)  # M queries internas
```

Con 10 combos × 5 almacenes × 3 componentes = 150 queries por request. Escala linealmente con el catálogo.

**Remediación:** prefetch + cálculo en memoria.

```python
combos_qs = Articulo.objects.filter(tipo='COMBO', activo=True).prefetch_related(
    Prefetch('receta_combo__componente__inventarios',
             queryset=InventarioAlmacen.objects.filter(almacen__activo=True).select_related('almacen'),
             to_attr='prefetched_inventarios')
)[:10]
```

Calcular en Python usando los datos precargados.

**Esfuerzo:** M (4-8 horas).
**Prioridad:** P1.

#### DATA-03 — `DetalleNotaEntrega.almacen` nullable (🟡 MEDIA)

**Ubicación:** `models.py:1546-1554`.

```python
almacen = models.ForeignKey(
    Almacen, on_delete=models.PROTECT,
    null=True, blank=True,  # ← nullable
    ...
)
```

Una línea de venta puede no tener almacén origen. `procesar_venta` lo setea desde el payload o desde la cabecera, pero el modelo **permite** NULL.

**Impacto:** si una línea existe sin almacén, el Kárdex no puede trazarse.

**Remediación:**

```python
# 1. Migración de datos: asignar almacén principal de la empresa a líneas existentes
# 2. AlterField: null=False, blank=False
# 3. Test: crear DetalleNotaEntrega sin almacén → IntegrityError
```

**Esfuerzo:** S (2-4 horas).
**Prioridad:** P2.

#### DATA-04 — `Contacto.rif` nullable aunque la vista lo exige (🟡 MEDIA)

**Ubicación:** `models.py:786-792`.

```python
rif = models.CharField(max_length=20, null=True, blank=True, ...)
```

`contactos_view` valida `rif` obligatorio para PROVEEDOR, pero un bypass (admin, shell, script) puede crear un PROVEEDOR sin RIF.

**Remediación:** `clean()` en `Contacto`:

```python
def clean(self):
    super().clean()
    if self.tipo == 'PROVEEDOR':
        if not self.rif or not self.rif.strip():
            raise ValidationError({'rif': 'El RIF es obligatorio para proveedores.'})
        if not self.nombre_asesor or not self.nombre_asesor.strip():
            raise ValidationError({'nombre_asesor': 'El nombre del asesor es obligatorio para proveedores.'})
```

**Nota:** `clean()` solo se ejecuta si el caller invoca `full_clean()`. Django admin lo hace, el shell no. Para enforce total, agregar `save()` override que llame `full_clean()` o `CheckConstraint` condicional.

**Esfuerzo:** S (2-4 horas).
**Prioridad:** P2.

#### DATA-05 — `ConfiguracionEmpresa.save()` con lógica compleja (🟡 MEDIA)

**Ubicación:** `models.py:269-324`. 55 líneas de lógica de recálculo.

```python
def save(self, *args, **kwargs):
    ...
    if self.tasa_bcv > 0:
        cambio_mercado = (self.tasa_mercado != orig_tasa_mercado)
        cambio_factor = (self.factor_cobertura != orig_factor_cobertura)
        cambio_bcv = (self.tasa_bcv != orig_tasa_bcv)
        if cambio_mercado and not cambio_factor:
            self.factor_cobertura = self.tasa_mercado / self.tasa_bcv
        elif cambio_factor and not cambio_mercado:
            self.tasa_mercado = self.tasa_bcv * self.factor_cobertura
        elif cambio_bcv:
            self.tasa_mercado = self.tasa_bcv * self.factor_cobertura
        else:
            # ... (más lógica)
```

**Riesgo:** Si `save()` se llama recursivamente (bug futuro), entra en bucle. La lógica tiene 5 branches y depende del estado anterior en BD (`orig = ConfiguracionEmpresa.global_objects.get(pk=self.pk)`).

**Remediación:** simplificar a lógica explícita:

```python
def save(self, *args, **kwargs):
    from decimal import Decimal, ROUND_HALF_UP
    if self.pk:
        orig = ConfiguracionEmpresa.global_objects.filter(pk=self.pk).first()
        if orig:
            bcv_changed = self.tasa_bcv != orig.tasa_bcv
            mercado_changed = self.tasa_mercado != orig.tasa_mercado
            factor_changed = self.factor_cobertura != orig.factor_cobertura
            if bcv_changed:
                self.tasa_mercado = (self.tasa_bcv * self.factor_cobertura).quantize(Decimal('0.0001'), ROUND_HALF_UP)
            elif mercado_changed and not factor_changed:
                if self.tasa_bcv > 0:
                    self.factor_cobertura = (self.tasa_mercado / self.tasa_bcv).quantize(Decimal('0.0001'), ROUND_HALF_UP)
            elif factor_changed and not mercado_changed:
                self.tasa_mercado = (self.tasa_bcv * self.factor_cobertura).quantize(Decimal('0.0001'), ROUND_HALF_UP)
    super().save(*args, **kwargs)
```

**Esfuerzo:** S (2-4 horas).
**Prioridad:** P2.

#### DATA-06 — Falta índice compuesto en `MovimientoKardex` (🟢 BAJA)

Sin `Index(fields=['fecha_hora', 'articulo', 'almacen'])`. Los reportes de kardex filtrados por fecha+artículo hacen full scan.

**Remediación:**

```python
class Meta:
    indexes = [
        models.Index(fields=['fecha_hora', 'articulo', 'almacen'], name='idx_kardex_fecha_art_alm'),
    ]
```

**Esfuerzo:** S (1 hora + migración).
**Prioridad:** P3.

#### DATA-07 — `round(Decimal)` usa banker's rounding (🟡 MEDIA)

**Ubicación:** `models.py:320-322`.

```python
self.tasa_bcv = round(self.tasa_bcv, 4)
```

Python `round(Decimal, n)` usa `ROUND_HALF_EVEN`. Para moneda comercial, debe ser `ROUND_HALF_UP` (redondeo comercial).

**Ejemplo:** `Decimal('0.00005').round(4)` → `0.0000` (banker's), comercial sería `0.0001`.

**Remediación:**

```python
from decimal import Decimal, ROUND_HALF_UP
self.tasa_bcv = self.tasa_bcv.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
```

**Esfuerzo:** S (1-2 horas).
**Prioridad:** P2.

#### DATA-08 — Cero `CheckConstraint` sobre montos monetarios (🟡 MEDIA)

Ningún modelo tiene `CheckConstraint` sobre rangos. `tasa_bcv=-5000`, `factor_cobertura=-1`, `iva_porcentaje=999`, `cantidad=-5` son aceptados por la BD. Todo depende del service layer.

**Remediación:**

```python
class ConfiguracionEmpresa(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(tasa_bcv__gte=0), name='tasa_bcv_no_negativa'),
            models.CheckConstraint(condition=Q(factor_cobertura__gt=0), name='factor_cobertura_positivo'),
            models.CheckConstraint(condition=Q(margen_global__gte=0, margen_global__lt=100), name='margen_rango_valido'),
        ]

class DetalleNotaEntrega(models.Model):
    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(cantidad__gt=0), name='cantidad_positiva'),
            models.CheckConstraint(condition=Q(iva_porcentaje__gte=0, iva_porcentaje__lte=100), name='iva_rango'),
            models.CheckConstraint(condition=Q(descuento_aplicado__gte=0, descuento_aplicado__lte=100), name='descuento_rango'),
        ]
```

**Esfuerzo:** M (6-8 horas incluyendo migraciones).
**Prioridad:** P2.

#### DATA-09 — `Moneda.save()` sin constraint de unicidad `es_base` (🟡 MEDIA)

**Ubicación:** `models.py:2051-2058`.

```python
def save(self, *args, **kwargs):
    if self.es_base:
        Moneda.objects.filter(empresa=self.empresa, es_base=True).exclude(pk=self.pk).update(es_base=False)
    super().save(*args, **kwargs)
```

Dos llamadas concurrentes pueden dejar 2 monedas base por tenant.

**Remediación:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['empresa'],
            condition=Q(es_base=True),
            name='una_moneda_base_por_empresa',
        ),
    ]
```

**Esfuerzo:** S (2 horas).
**Prioridad:** P2.

#### DATA-10 — `TasaCambio` sin `unique_together` (🟢 BAJA)

Duplicados por `(empresa, moneda_origen, moneda_destino, fecha)` son posibles. `obtener_tasa` resuelve por `-fecha, -creada_en` (last-wins) que es arbitrario.

**Remediación:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['empresa', 'moneda_origen', 'moneda_destino', 'fecha'],
            name='unique_tasa_par_fecha',
        ),
    ]
```

**Esfuerzo:** S (1 hora).
**Prioridad:** P3.

---

## 9. Bugs de código verificados

Estos bugs se confirmaron por ejecución durante la auditoría (a través de los logs de tests o de la verificación de diffs). **Todos fueron resueltos** en commits `3a19546` o `0585207`.

### BUG-01 — `logger.warning` con formato roto en `procesar_devolucion_venta` (🟠 ALTA — RESUELTO)

**Ubicación original:** `services.py:2520-2522`.
**Commit de fix:** `0585207`.

**Síntoma:**
```
TypeError: not enough arguments for format string
Message: '[NC VENTA] %s sobre %s: stock SIGUE NEGATIVO después de la devolución: %s @ %s = %s (devuelto: %s). ...'
Arguments: ('NC-00000001', 'DS-001', 'Almacen DS', Decimal('-3.00'), Decimal('2'))
```

6 placeholders `%s`, 5 argumentos. Se dispara cuando el saldo sigue negativo tras una devolución (advertencia de drop-ship).

**Estado:** 6 placeholders + 6 argumentos (`detalle.cantidad` añadido).

**Verificación:** `test_nc_sobre_venta_sin_stock_funciona_y_reporta_alerta` pasa sin logging errors.

### BUG-02 — `UnicodeEncodeError` en logs de carga masiva (🟠 ALTA — RESUELTO)

**Ubicación original:** `services.py:614-616` + `settings.py` FileHandler.
**Commit de fix:** `3a19546`.

**Síntoma:**
```
UnicodeEncodeError: 'charmap' codec can't encode character '\u2265' in position 134
```

El string `"Debe ser un número ≥ 0"` contiene `≥` (U+2265) y el FileHandler con cp1252 en Windows no puede codificarlo.

**Estado:**
- `≥` reemplazado por `>=` en todos los mensajes de error de `services.py`.
- `settings.py` FileHandler con `'encoding': 'utf-8'`.

**Verificación:** `test_error_en_fila_no_aborta_procesamiento` pasa sin UnicodeEncodeError.

### BUG-03 — `ConfiguracionEmpresa.DoesNotExist` no manejado (🟠 ALTA — RESUELTO)

**Ubicación original:** `services.py:1575`.
**Commit de fix:** `3a19546`.

**Síntoma:** `sincronizar_tasa_cambio()` lanzaba 500 si la empresa no tenía `ConfiguracionEmpresa`. Ocurría si el signal `create_tenant_defaults` no corría o si la config se borraba manualmente.

**Estado:**

```python
try:
    config = ConfiguracionEmpresa.global_objects.get(empresa_id=_empresa_id)
except ConfiguracionEmpresa.DoesNotExist:
    return {'ok': False, 'error': 'Configuración de empresa no encontrada.'}
```

**Verificación:** `test_sincronizacion_connection_error_no_cambia_tasa` y similares pasan.

### BUG-04 — `DetalleCompraQuerySet.para_empresa` referencia `get_current_empresa` sin importar (🔴 CRÍTICA — **NO RESUELTO**)

**Ubicación:** `models.py:34-40`.

```python
class DetalleCompraQuerySet(EmpresaQuerySet):
    def para_empresa(self):
        empresa_id = get_current_empresa()  # ← NameError: no está en scope
        if empresa_id is not None:
            return self.filter(documento_compra__empresa_id=empresa_id)
        return self.none()
```

Al inicio de `models.py`:

```python
from .managers import EmpresaManager, EmpresaQuerySet
# ← falta: get_current_empresa
```

`get_current_empresa` se usa pero no se importa. Cualquier llamada a `DetalleCompraManager.para_empresa()` lanzará `NameError`.

**Impacto:**
- `manage.py check` **no lo detecta** porque no ejecuta la función.
- La suite de tests **no lo detecta** porque `TestSecurityAPIRateErrorHandling` no llama a `para_empresa()`.
- En producción, si alguien llama a `DetalleDocumentoCompra.objects.para_empresa()`, la app falla con 500.

**Verificación posible:**

```bash
python manage.py shell -c "from inventory.models import DetalleDocumentoCompra; DetalleDocumentoCompra.objects.para_empresa()"
```

Debería lanzar `NameError: name 'get_current_empresa' is not defined`.

**Estado:** **No resuelto** en `0585207`. La suite pasa porque ningún test lo ejercita.

**Remediación:**

```python
# models.py, línea 31 (junto con el otro import)
from .managers import EmpresaManager, EmpresaQuerySet, get_current_empresa
```

**Test de aceptación:**

```python
def test_detalle_compra_manager_para_empresa(self):
    from inventory.models import DetalleDocumentoCompra
    # No debe lanzar NameError
    qs = DetalleDocumentoCompra.objects.para_empresa()
    self.assertIsNotNone(qs)
```

**Esfuerzo:** S (15 minutos).
**Prioridad:** P0 (bloqueante).

---

## 10. Hallazgos estructurales (no verificados en runtime)

Estos hallazgos surgen de la lectura del código. **No fueron verificados en runtime** porque la suite no cubre los escenarios. Requieren evaluación explícita antes de comercializar.

### EST-01 — Invariantes de Kárdex no enforced en modelo (🟠 ALTA)

**Ubicación:** `models.py` `MovimientoKardex`.

`MovimientoKardex` no tiene `save()`, `delete()` ni `clean()` override. La "Regla Sagrada" (solo `registrar_movimiento` muta stock) es **intención de diseño**, no invariante de modelo.

**Vectores de bypass:**
- `MovimientoKardex.objects.all().delete()` desde shell.
- `MovimientoKardex.objects.filter(...).update(cantidad=999)` desde shell.
- Django admin → `MovimientoKardexAdmin` tiene `has_add/change/delete=False` ✅, pero `bulk_delete` en admin no está bloqueado por esas flags.
- Script de mantenimiento que no use services.

**Remediación:**

```python
class MovimientoKardex(models.Model):
    def delete(self, *args, **kwargs):
        raise NotImplementedError("MovimientoKardex es inmutable. Usar services.reversar_* para anular.")

    @classmethod
    def force_delete(cls, pk):
        """Para migraciones/limpiezas explícitas. Nunca llamar desde código de negocio."""
        return super().delete(*args, **kwargs)
```

O un `pre_delete` signal que bloquee si no es una migración.

**Esfuerzo:** S (2-4 horas incluyendo tests).
**Prioridad:** P1.

### EST-02 — Inmutabilidad de facturas emitidas no enforced (🟠 ALTA)

**Ubicación:** `NotaEntrega`, `DocumentoCompra`, `NotaCredito`, `DetalleNotaEntrega`, `DetalleDocumentoCompra`, `DetalleNotaCredito`.

Nada impide:
- `NotaEntrega.objects.filter(pk=X).update(estado='PROCESADO')` sobre una anulada.
- `DetalleNotaEntrega.objects.filter(pk=X).update(precio_base=999)` sobre una factura procesada.
- `NotaEntrega.detalles.all().delete()` en una nota procesada (CASCADE desde NE, pero ¿quién borra la NE? — ver EST-01 extendido).

**Impacto fiscal:** una factura emitida **no se edita**. Punto. Es invariante contable/fiscal.

**Remediación:**

```python
class NotaEntrega(models.Model):
    def save(self, *args, **kwargs):
        if self.pk:
            orig = NotaEntrega.global_objects.filter(pk=self.pk).first()
            if orig and orig.estado == 'PROCESADO':
                # Solo permitir cambios de estado (ANULADO) + motivo_anulacion
                campos_permitidos = {'estado', 'motivo_anulacion'}
                for field in self._meta.fields:
                    if field.name in campos_permitidos:
                        continue
                    if getattr(self, field.name) != getattr(orig, field.name):
                        raise ValidationError(
                            f"No se puede modificar '{field.name}' de una NotaEntrega PROCESADA. "
                            f"Usar reversar_nota_entrega() para anularla."
                        )
        super().save(*args, **kwargs)
```

Similar para `DocumentoCompra`, `NotaCredito`, y los `Detalle*`.

**Esfuerzo:** M (8-12 horas incluyendo tests para cada modelo).
**Prioridad:** P1.

### EST-03 — Correlativos `Max+1` sin lock (🟠 ALTA)

**Ubicación:** `models.py` `save()` de `NotaEntrega`, `DocumentoCompra`, `NotaCredito`.

```python
max_num = NotaEntrega.global_objects.filter(empresa=self.empresa).aggregate(
    max_num=Max('numero')
)['max_num']
self.numero = (max_num or 0) + 1
```

**Es un SELECT MAX + INSERT sin lock.** Dos ventas concurrentes → misma `numero` → `IntegrityError` (en `NotaEntrega`/`DocumentoCompra` que tienen `UniqueConstraint`). En `NotaCredito` es peor: **no hay `UniqueConstraint`**, así que dos NC concurrentes generan el mismo `numero_control` **sin que la BD chiste**.

**Impacto:**
- `NotaEntrega`: 500 al usuario por `IntegrityError` (recuperable con retry).
- `DocumentoCompra`: ídem.
- `NotaCredito`: **corrupción silenciosa de correlativo fiscal**. Dos NCs con el mismo `NC-00000005`. Reportes ambiguos, auditoría imposible.

**Remediación (opción A — lock + retry):**

```python
# services.py
@transaction.atomic
def procesar_venta(...):
    ...
    # Bloquear el contador antes de crear la nota
    with connection.cursor() as cursor:
        cursor.execute("SELECT MAX(numero) FROM inventory_notaentrega WHERE empresa_id = %s FOR UPDATE", [empresa_id])
    ...
```

SQLite no soporta `FOR UPDATE` real, pero `transaction.atomic` + `BEGIN IMMEDIATE` sí serializa escrituras. Alternativa: usar una tabla `Correlativo` con `select_for_update`.

**Remediación (opción B — retry):**

```python
from django.db import IntegrityError
from time import sleep

def crear_nota_con_retry(*args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                return NotaEntrega.objects.create(*args, **kwargs)
        except IntegrityError:
            if attempt == max_retries - 1:
                raise
            sleep(0.05 * (2 ** attempt))  # backoff exponencial
```

**Remediación mínima (NotaCredito):**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(fields=['empresa', 'numero'], name='unique_numero_nc_per_empresa'),
        models.UniqueConstraint(fields=['empresa', 'numero_control'], name='unique_control_nc_per_empresa'),
    ]
```

Eso convierte la corrupción silenciosa en un `IntegrityError` recuperable.

**Esfuerzo:** M (6-8 horas).
**Prioridad:** P1.

### EST-04 — `usuario` como CharField en Kardex y NC (🟠 ALTA)

**Ubicación:** `models.py` `MovimientoKardex.usuario` (CharField 150) y `NotaCredito.usuario` (CharField 150).

**Impacto:** Cualquiera puede escribir `usuario='admin'` desde shell/script. No hay FK a `User`, no hay integridad referencial, no hay trazabilidad forense real.

**Remediación:**

```python
class MovimientoKardex(models.Model):
    usuario = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='movimientos_kardex',
    )
    usuario_nombre = models.CharField(max_length=150, blank=True)  # snapshot
```

Migración de datos: llenar `usuario` desde el `CharField` existente por matching de username. Mantener `usuario_nombre` para histórico.

**Esfuerzo:** M (6-8 horas incluyendo migración de datos).
**Prioridad:** P1.

### EST-05 — `AuditoriaTasa` sin campo `usuario` (🟡 MEDIA)

**Ubicación:** `models.py` `AuditoriaTasa`.

No registra quién cambió la tasa. En un sistema que depende del factor cobertura para fijar precios, no saber quién movió la aguja es un agujero forense.

**Remediación:**

```python
class AuditoriaTasa(models.Model):
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
```

**Esfuerzo:** S (2 horas).
**Prioridad:** P3.

### EST-06 — `NotaEntrega.total_documento_bs` ignora `descuento_global` (🟡 MEDIA)

**Ubicación:** `models.py:1516-1519`.

```python
@property
def total_documento_bs(self):
    return self.subtotal_bs + self.total_iva_bs
```

No aplica `descuento_global`. Si las vistas usan esta property directamente, el total es incorrecto. Si las vistas lo aplican manualmente (como hacen hoy), la property miente.

**Remediación:** documentar que la property es "subtotal sin descuento global" y renombrarla (`subtotal_con_iva_bs`), o aplicarle el descuento:

```python
@property
def total_documento_bs(self):
    factor = Decimal('1') - (self.descuento_global / Decimal('100'))
    return (self.subtotal_bs + self.total_iva_bs) * factor
```

**Esfuerzo:** S (1-2 horas).
**Prioridad:** P2.

### EST-07 — `DetalleNotaCredito.almacen` con `help_text` que promete `clean()` inexistente (🟢 BAJA)

**Ubicación:** `models.py:1932-1934`.

```python
almacen = models.ForeignKey(
    Almacen, on_delete=models.PROTECT,
    null=True, blank=True,
    help_text='Almacén donde reingresa el stock; usualmente el del doc. origen. '
              'Obligatorio al persistir (enforced por clean()).',  # ← miente
)
```

`DetalleNotaCredito` **no tiene `clean()`**. El `help_text` promete algo que no existe.

**Remediación:** agregar el `clean()` prometido, o corregir el `help_text`.

**Esfuerzo:** S (30 minutos).
**Prioridad:** P3.

### EST-08 — `DetalleNotaEntrega.cantidad_devuelta_acumulada` promete `_optimized` que no existe (🟢 BAJA)

**Ubicación:** `models.py:1662-1666`.

```python
@property
def cantidad_devuelta_acumulada(self):
    """
    ...
    Para evitar N+1 con `select_related`, se cachea con property; usar
    `cantidad_devuelta_acumulada_optimized` si la queryset carga.  # ← no existe
    """
```

La property `_optimized` **no existe** en el código. El comentario miente. Y la property itera en Python (`for det_nc in self.devoluciones.all()`) — N+1 garantizado.

**Remediación:** implementar `_optimized` con `annotate(Sum('devoluciones__cantidad_devuelta'))` en la queryset que llama, o eliminar el comentario.

**Esfuerzo:** S (1 hora).
**Prioridad:** P3.

### EST-09 — PKs de negocio (`Articulo.sku`, `Contacto.identificacion`) (🟡 MEDIA, deuda aceptada)

**Ubicación:** `models.py:435` y `models.py:745`.

`Articulo.sku = CharField(primary_key=True)` y `Contacto.identificacion = CharField(primary_key=True)`.

**Impacto:**
- `sku` como PK bloquea renombrado del catálogo. Si un proveedor cambia el código, hay que crear un artículo nuevo.
- `identificacion` como PK puede cambiar de formato (cédula → RIF). Cada cambio crea un contacto nuevo con FK rotas.

**Decisión:** es deuda **aceptada** por ADR-05 y ADR-implícita. Documentar como limitación.

**Esfuerzo:** L (migración masiva con downtime).
**Prioridad:** P4 (aceptar).

### EST-10 — `SECURE_BROWSER_XSS_FILTER` deprecado en Django 5+ (🟢 BAJA)

**Ubicación:** `settings.py:160`.

```python
SECURE_BROWSER_XSS_FILTER = True  # deprecado desde Django 5.0
```

En Django 5.0+, no tiene efecto. El header `X-XSS-Protection` fue deprecado por navegadores.

**Remediación:** eliminar la línea. Si se quiere protección XSS moderna, usar CSP.

**Esfuerzo:** S (5 minutos).
**Prioridad:** P3.

### EST-11 — `UniqueConstraint(empresa, es_principal=True)` ausente en Almacen (🟡 MEDIA)

**Ubicación:** `models.py` `Almacen`.

`es_principal = BooleanField(default=False)` sin constraint. Un tenant puede tener 2 almacenes marcados `es_principal=True`. El código asume uno solo.

**Remediación:**

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=['empresa'],
            condition=Q(es_principal=True),
            name='un_almacen_principal_por_empresa',
        ),
    ]
```

**Esfuerzo:** S (2 horas).
**Prioridad:** P2.

---
