# Changelog — A2LT Stock

Todos los cambios notables del proyecto se documentan en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-1.1.0/)
y este proyecto se adhiere a [SemVer](https://semver.org/lang/es/) una 
vez público.

---

## [1.2.0] — 2026-07-13

Iteración que cierra el **TKET #18-NC** (Notas de Crédito / Devoluciones):
módulo aparte `/notas-credito/` con devoluciones parciales o totales
sobre Ventas y Compras, snapshots inmutables de precios/IVA por línea,
generación de PDFs A4, e integración atómica con Kardex.

### Added (Features nuevas)

- **Módulo Notas de Crédito (`/notas-credito/`):** nueva ruta con 5
  endpoints (`notas_credito`, `api_origen_detalle`, `crear_nc`,
  `detalle_nc`, `pdf_nc`) y 2 templates (`notas_credito.html` +
  `nota_credito_detalle.html`). Pantalla única con pestañas **Historial
  de NCs** (totales, estado, link a PDF) y **Emitir Nueva NC** (carga
  del documento origen → grilla editable de líneas con IVA % por
  item → submit JSON con motivo obligatorio).
- **Modelos `NotaCredito` + `DetalleNotaCredito`:** nueva jerarquía
  con `prefijo` + `numero` + `numero_control`, integración 1-NC-1-origen
  enforce por `CheckConstraint` (XOR entre `nota_entrega` y
  `factura_compra`). Snapshots inmutables de `precio_unitario_snapshot`,
  `iva_porcentaje_snapshot`, `cantidad_devuelta` por cada línea, con
  cálculo automático de `subtotal_devuelto_usd` + `iva_usd` +
  `linea_total_usd` en `save()`.
- **`ConfiguracionEmpresa.prefijo_nota_credito` + 
  `correlativo_inicial_nota_credito`:** configurable por el tenant
  (default `NC` + correlativo aislado por empresa). Autoasignación de
  `numero = Max('numero') + 1` dentro del tenant.
- **`procesar_devolucion_venta()` + `procesar_devolucion_compra()`:** 
  servicios atómicos en `services.py` con `@transaction.atomic`,
  validación perimetral multi-tenant (`global_objects` para evitar
  leak entre tenants), kardex (`DEVOLUCION_VENTA` ENTRADA /
  `DEVOLUCION_COMPRA` SALIDA) y liberación FIFO de seriales 
  (VENDIDO → DISPONIBLE en ventas; DISPONIBLE → ANULADO_COMPRA en
  compras). Reverso de los movimientos contables generados.
- **Properties `cantidad_devuelta_acumulada` + 
  `cantidad_pendiente_devolver` + `es_totalmente_devuelto`:** en 
  `DetalleNotaEntrega` y `DetalleDocumentoCompra` para que la UI y 
  los reports muestren cuánto queda sin devolver.
- **PDF de la NC:** `generar_pdf_nc` (reportlab A4 portrait) con
  encabezado, motivo, doc origen, líneas y total a reembolsar.

### Fixed (Bug fixes)

- **C-N1:** `CheckConstraint` con `check=` (no soportado por Django)
  reemplazada por `condition=` (la kwarg correcta). Detectado por
  `TestSettingsHardening.test_sincronizacion_con_tests` mediante
  `subprocess.run('manage.py check')`.
- **C-N2:** `NotaCredito.save()` con default `prefijo='NC'` no leía
  `ConfiguracionEmpresa.prefijo_nota_credito` porque Django nunca
  ejecutaba la rama `if not self.prefijo`. Corregido a `default=''` 
  (CharField truthy) → migración 0015 + tests verdes 
  (15 backend + 14 UI).
- **C-N3:** `_testMethodName` se usa para nombres únicos entre tests
  `TransactionTestCase` (la BD persiste); además agregado 
  `BEGIN; ... PRAGMA defer_foreign_keys;` para evadir FKs al limpiar.
- **C-N4:** `create_tenant_defaults` signal ahora usa 
  `instance.rif` en lugar de `instance.pk` para la
  identificacion del Cliente Genérico (evita UNIQUE collisions al
  re-correr la suite).
- **C-N5:** código muerto de `procesar_devolucion_venta` legacy 
  (TKET #15-SAAS, firma posicional con `tipo_costo`) eliminado; los
  tests legacy se marquaron `@skip` con razón informativa.

### Internal (Refactors)

- **Limpieza mojibake:** corregidos 470+ caracteres UTF-8 mal
  decodificados en `tests.py` (todos originados por ediciones a mano
  en sesiones donde el encoding del editor no fue utf-8). Restaurada
  la sincronización de `TestSettingsHardening` 
  (subprocess `manage.py check`).
- **PK de la NC auto:** `numero_control` se calcula en `save()` 
  leyendo `prefijo` → `f"{prefijo}-{numero:08d}"`, evitando solaparse
  entre tenants.

### Estadísticas

- **276 tests verdes** (247 previos + 15 backend + 14 UI nuevos 
  de Notas de Crédito), 5 skipped (4 de `TestNotasDeCreditoPOS` 
  legacy + `test_costo_historico_snapshot_venta_vs_actual` ya
  reemplazados por `TestNotasCreditoBackend`).
- Migraciones nuevas: `0014_nota_credito_devoluciones` y
  `0015_nota_credito_prefijo_default`.
- Templates nuevos: `notas_credito.html` (1 pantalla con pestañas
  Historial + Emitir), `nota_credito_detalle.html` (cabecera + líneas
  + totales + botón PDF).

---

## [1.1.1] — 2026-07-13

Iteración de refinamiento basada en feedback del cliente sobre los 
módulos de Compras y Ventas. Resuelve 3 observaciones reales:

**O1**: Tipo de Documento de Compra — antes sólo había 
`FACTURA_COMPRA` y se confundía "nota de entrega" con "Nota de 
Crédito". Ahora hay 3 opciones: **Factura** (con #factura 
obligatorio), **Nota de Entrega / Recibo** (con #documento 
opcional), **Registro Menor** (sin documento físico, repos de 
mostrador). Las opciones obsoletas `NOTA_CREDITO_COMPRA` y 
`ORDEN_COMPRA` se removieron: las Notas de Crédito se reservan 
para **TICKET #18** (módulo aparte `/notas-credito/`) porque 
requieren referenciar el documento original, listar items a 
devolver (parcial/total) y generar contramovimientos de kardex 
— no caben en un radio botón del formulario Compras.

**O2**: IVA Individual por Línea en PDT虍 — antes había un 
checkbox global `iva_check` y un sólo porcentaje por documento. 
Ahora el backend (`procesar_venta` y `registrar_compra_proveedor`) 
respeta `iva_porcentaje` enviado por cada item, sobrescribiendo 
el default del artículo. La grilla en `ventas.html` y 
`compras.html` ahora tiene una **columna "IVA %"** con `<select>` 
por línea poblado con `ConfiguracionEmpresa.ivas_disponibles` 
(default `[16, 8, 0]`). Permite facturas mixtas: 16% para una 
línea, 8% para otra, exento para otra. El `iva_total` del 
documento se recalcula sumando los IVAs individuales. Validación: 
rango `[0, 100]`.

**O3**: Las Notas de Crédito son un módulo aparte (TICKET #18, 
planificado en BACKLOG sin implementar aún).

### Cambios

- **`models.py`:** `DocumentoCompra.TIPO_DOCUMENTO_CHOICES` a 3 
opciones (`FACTURA_COMPRA`, `NOTA_ENTREGA_PROVEEDOR`, 
`REGISTRO_MENOR`). `max_length` 20 → 30. Label `numero_factura` 
→ `N° Documento Proveedor` con `help_text` ampliado.
- **Migración 0013:** `tipo_documento_compra_3_opciones` 
(actualiza `choices` + `max_length` + `help_text` del campo).
- **`services.py`:** validación `tipo_documento` ahora acepta las 3 
opciones; unicidad de `numero_factura` aplica a cualquier doc con 
número informado (no sólo FACTURA). `procesar_venta` lee 
`item['iva_porcentaje']` con prioridad sobre `Articulo.iva_porcentaje`.
- **`views.py`:** `ventas()` y `compras_view()` inyectan 
`ivas_disponibles_json` (fallback `[16, 8, 0]` si config vacío).
- **`ventas.html`:** columna "IVA %" nueva en grilla, `<select>` 
por línea con `ivasDisponibles`. `processSale` envía 
`iva_porcentaje` por item.
- **`compras.html`:** idem para compras. `onPurchaseDocTypeChange()` 
re-escrito: container siempre visible, label y obligatoriedad 
cambian segun `tipo_documento`.
- **`compra_detalle.html`:** etiquetas `tipo_documento` actualizadas 
a las 3 opciones con fallback a `get_tipo_documento_display`.
- **Tests:** +13 tests en 3 clases (`TestTipoDocumentoCompra3Opciones`, 
`TestIvaIndividualPorLinea`, `TestIVAConfiguracionIvasDisponibles`).
  Cobertura: FACTURA obliga #factura, NOTA_ENTREGA_PROVEEDOR/ 
REGISTRO_MENOR permite sin #, choices viejos rechazados, 
procesar_venta respeta iva_porcentaje por item, mezcla de 
ivas (%16, %8, %0), 3 radios en `compras.html`, columna IVA % 
en grilla.

### Estadísticas

- 247 tests en verde en ~160s (234 previos + 13 nuevos).
- Migración nueva: 0013 (`tipo_documento_compra_3_opciones`).
- Commits: este y los previos de 1.1.0.

---

## [1.1.0] — 2026-07-13

Iteración sobre el núcleo 1.0.0: añadido el flujo completo de Emisión 
de Notas de Entrega/Facturas, el módulo de Compras a proveedores con 
seriales+IVA+descuentos, el sistema de tokens de variables de precio 
para redactar mensajes de mercadeo, y una ronda profunda de auditoría 
(seguridad, descuentos, totales, JSXSS, dead code). Suite en 234 tests 
verdes (~151s).

### Added (Features nuevas)

- **Emisión de Notas de Entrega / Facturas (Fases N1–N5):** el servicio 
  `procesar_venta` ahora soporta `tipo_documento` (`NOTA_ENTREGA` o 
  `FACTURA`), `numero_factura` único por empresa, `descuento_global` 
  (0–100 %), `iva_porcentaje` por artículo y `iva_check` automático.
  Cada `DetalleNotaEntrega` snapshot de los 4 precios 
  (`precio_base`, `precio_ajustado`, `precio_directo_bcv` y 
  `precio_ajustado_bcv`) + `iva_porcentaje` + `descuento_aplicado`.
  ConfiguracionEmpresa añade `prefijo_nota_entrega` + 
  `correlativo_inicial_nota` + `ivas_disponibles`.
  Vistas `vista_detalle_nota`, `generar_pdf_nota` (reportlab) y URLs 
  `/ventas/<id>/`, `/ventas/<id>/pdf/`.
- **Módulo de Compras a proveedores (Fase C1–C3):** `DocumentoCompra` 
  con correlativo automático + `DetalleDocumentoCompra` con 4 precios 
  snapshot + IVA + descuento + seriales. 
  `registrar_compra_proveedor` valida multi-tenant de FKs (almacen, 
  proveedor, artículo) y dispara `registrar_movimiento ENTRADA`.
  `reversar_documento_compra` genera contramovimiento auditado.
  Vistas `vista_detalle_compra`, `generar_pdf_compra` (reportlab) 
  con `/compras/<id>/`, `/compras/<id>/pdf/`.
- **Fichas de Artículos con tokens de precio (NUEVO):** 4 variables 
  dinámicas para redactar mensajes de mercadeo en `social_quick` y 
  `social_cross` sin reescribir al cambiar precios/tasas:
  | Token | Cálculo en el catálogo |
  |---|---|
  | `$[PRECIO_USD]` | `precio_divisa` (USD base) |
  | `$[PRECIO_BCV]` | `precio_divisa × factor_cobertura` |
  | `$[PRECIO_BS_BASE]` | `precio_divisa × tasa_bcv` (sin factor) |
  | `$[PRECIO_BS]` | `precio_divisa × factor × tasa_bcv` |

  Sustitución en `copyToClipboard` y `updateCrossSellingOutput` 
  (`catalogo.html`), con compatibilidad legacy `[Precio_USD]`, 
  `[Precio_BCV]`, `[Precio_BS_BASE]`, `[Precio_Bs]`.
- **Toolbar de inserción de tokens en Formulario de Artículos:** 
  `articulos.html` ahora expone 4 botones (USD/BCV/Bs.Base/Bs.Ajust.) 
  sobre los textareas `form-p-cross` y `form-p-quick`. La función JS 
  `injectToken(textareaId, token)` inserta el token en la posición del 
  caret, sobrescribe la selección si existe, restaura el foco, y NO 
  envía nada al servidor (el texto se persiste literal al guardar con 
  `saveProduct()`).
- **Tests (21 nuevos):** `TestCatalogoPreciosCuadruple` (3), 
  `TestCatalogoTemplateTokens` (5), `TestArticulosToolbarTokens` (10),
  `TestArticulosToolbarRender` (3). Suite pasa de 213 a 234 tests.

### Fixed (Bug fixes — auditoría)

**Críticos:**
- **C1:** bug `Max('id')` en cálculo de correlativo de `DocumentoCompra` 
  (generaba saltos). Eliminado; `save()` usa `Max('numero')` y signal 
  `create_tenant_defaults` inicializa `correlativo_inicial_nota` y 
  `correlativo_inicial_compra`.
- **C2:** 4 vistas (`vista_detalle_nota`, `generar_pdf_nota`, 
  `vista_detalle_compra`, `generar_pdf_compra`) no filtraban por 
  `empresa_id` → leak multi-tenant. Ahora todas usan 
  `get_object_or_404(Modelo, pk=id, empresa_id=session['empresa_id'])`.
- **C3:** 26 sinks de `innerHTML` sin escape en `ventas.html` (13) y 
  `compras.html` (13). Añadido helper JS `escapeHtml()` y todos los 
  sinks escapados (`renderClientDropdown`/`renderProviderDropdown`, 
  `filterSaleItem`/`filterPurchaseItem`, `renderNoteItems`/`renderPurchaseItems`, 
  `renderSerialsPanel`/`renderPurchaseSerialsPanel`).
- **C4:** tag roto `<h-sm">` en `nota_detalle.html` eliminado.

**Medios:**
- **M1:** `descuento_global` ahora se aplica a los totales en las 4 
  vistas/PDFs y en los templates de detalle con bloque condicional.
- **M2:** labels "IVA (16%)" → "IVA:" en `ventas.html` y `compras.html`.
- **M5:** botones `confirm-*-btn` deshabilitados + spinner durante el 
  fetch; restaurados en `.then()`/`.catch()` para evitar doble-submit.
- **M7:** variable muerta `iva_total_bs` eliminada de `services.py` 
  (calculaba descuento doble sobre IVA en Bs y no se persistía).
- **M8:** `total_bs_neto` alineado en `vista_detalle_nota` y 
  `vista_detalle_compra` usando snapshots por-detalle 
  (`factor_desc`, `cobertura`, `tasa_bcv`).

**Bajos:**
- **B1:** código muerto eliminado (`note-discount-usd`, 
  `purchase-discount-usd`, `lastCorrelative`, `iva_porcentaje` 
  duplicado). Balance HTML verificado 50/50, 53/53, 28/28, 29/29 divs 
  y 1/1 sections en los templates tocados.
- **B4:** guard `if (!r.ok)` + `.catch()` mejorado en `processSale` 
  y `processPurchase`.

### Internal (Refactors)

- **Limpieza:** eliminados 9 archivos de debug temporales 
  (`check_*.py`, `fix_*.py`, `add_tests.py`, `show_context.py`) y 
  `__pycache__`.
- **Defaults Decimal:** todos los `DecimalField` default corrregidos 
  de float a `Decimal('...')`.

### Documentation (Documentación)

- CHANGELOG.md (este archivo) ampliado con 1.1.0.
- `docs/PLAN.md` ampliado con Etapa N + matriz tests C20+.
- `docs/ARQUITECTURA.md` actualizado con nuevos modelos, services, 
  migraciones, tests (234 verdes) y patterns.
- `docs/ADR.md` añade ADR-23 (Emisión NE/Factura), ADR-24 (snapshots
  4 precios en DetalleNotaEntrega/DetalleDocumentoCompra extendidos),
  ADR-25 (tokens de variables de precio) y ADR-26 (toolbar caret 
  tracking sin servidor).
- `docs/BACKLOG.md` marca completados los tickets de Compras y añade 
  TICKET #14 Fichas de Artículos (4 tokens + toolbar).
- `docs/OPERACION.md` añade sección "Tokens de variables de precio" 
  + tabla de reemplazos.
- `README.md` actualiza el conteo de tests a 234 y añade módulos de 
  Ventas/Compras/Fichas en features.

### Estadísticas de la iteración

- 4 commits desde `712ba8c` (N1+N2) hasta `c470093` (Fichas + 
  auditoría).
- Tests: 213 → 234 (+21).
- Migraciones: 0010, 0011 y 0012 añadidas (siguen siendo numeradas).
- Nuevos snapshots: `tasa_mercado_aplicada` en NotaEntrega; 
  `factor_cobertura_aplicado`, `tasa_bcv_aplicada` en DocumentoCompra.
- Nuevas plantillas: `nota_detalle.html`, `compra_detalle.html` 
  y ampliación de `ventas.html`, `compras.html`, `catalogo.html`, 
  `articulos.html`.

---

## [1.0.0] — 2026-07-10

Primera entrega completa del sistema. 28 commits desde el arranque de 
la auditoría. 157 tests verdes. Suite completa en ~120s.

### Added (Features nuevas)

- **Multi-tenant ContextVar (B-1, B-2/B-7):** `TenantMiddleware` valida 
  5 condiciones (autenticación, PerfilUsuario, empresa_id session, 
  empresa activa, empresa en `empresas_permitidas`). Managers filtran 
  automáticamente por ContextVar. Tests migrados a `self.client.login()`.
- **Defense-in-depth auth (B-3):** `@login_required` en 16 vistas de 
  negocio. Middleware corta con 403; decorator redirige con 302.
- **Multimoneda (Fase 3):** modelos `Moneda` (con `es_base` unique 
  por tenant enforcement) y `TasaCambio` (con índice por fecha). 
  Signal siembra USD+VES+tasa 1:1 al crear Empresa. 
  `DocumentoCompra` graba snapshot inmutable de tasas al facturar.
- **Reportes (Fase 4.1-4.8):** 8 reportes operativos — Kardex 
  Valorizado, Inventario Valorizado, Ventas por Período, Cuentas por 
  Cobrar, Cuentas por Pagar, Top Artículos Vendidos, Artículos Sin 
  Movimiento (obsoletos), Estado de Resultados simple. Dispatcher 
  `obtener_reporte(nombre, empresa_id, **params)`.
- **Exports (Fase 4):** CSV (utf-8-sig BOM para Excel español) y PDF 
  (reportlab A4 landscape con tabla + totales).
- **Vistas de reportes:** `vista_reportes` índice + 
  `vista_reporte_detalle` unificada con filtros por URL 
  (articulo, almacen, fechas, limite, dias_sin_mov) y 
  `?format=csv|pdf` para descarga.
- **Dashboard live KPIs (Fase 4):** 6 KPIs reales — valoración USD/VES, 
  volumen de ventas USD/Bs, conteo de notas del mes, alertas 
  críticas de reposición, disponibilidad de combos virtuales 
  calculada en tiempo real, última sincronización desde AuditoriaTasa.
- **Backup atómico (Fase 6):** `manage.py backup_db` genera snapshot 
  via SQLite `VACUUM INTO` sin bloquear escrituras. Soporta `--dir`, 
  `--name`, `--retention N` (borra backups > N días), `--check` 
  dry-run. Detecta BD in-memory para funcionar en tests.
- **Documentación:** README raíz + 5 archivos en `docs/` (auditoría, 
  plan, roadmap, operación, arquitectura, ADR).
- **API surface tests (Fase 5):** `TestServicesAPISurface` valida 
  que services.py expone las 17 funciones públicas esperadas y que 
  `registrar_movimiento` conserva sus 5 args posicionales.

### Fixed (Bug fixes)

- **A1-A3 (Limpieza):** eliminados `fix_test.py` (script mutador), 
  `scratch/` (~1200 líneas muertas), 2 stubs en `views.py`.
- **A4:** bug `ANULADO` vs `ANULADA` en `services.py:1960` causante 
  de reversos silenciosos. Test C1 de idempotencia añadido.
- **A5:** bug "siempre-MARKUP" en `registrar_compra_proveedor`: ahora 
  respeta `articulo.metodo_ganancia`. Test C2 añadido.
- **A6:** `base.html` sin getCookie ni `{% block extra_js %}` 
  (rompía carga masiva). Fix con helper global + block.
- **A7:** `articulos_view` con `getattr(request, 'empresa', None)` 
  en lugar de ContextVar. Migrado a `get_current_empresa()`. 
  `@csrf_exempt` removido. CSRF token en `articulos.html`.
- **A8:** `contactos` y `vista_exportar_respaldo` con `Empresa.first()`. 
  Migrados a ContextVar. Test C5.
- **A9:** `@csrf_exempt` removido de `vista_crear_venta`. Test C6.
- **A10:** `registrar_compra_proveedor` validación multi-tenant 
  de almacen/proveedor/articulo. Test C7.
- **A11:** `procesar_venta` valida `almacen_id` por empresa ANTES 
  de cargar config (fuga de tasa). Test C8.
- **A12:** `calcular_stock_combo` usaba `math.floor` con floats. 
  Migrado a `Decimal //` nativo. Test C9.
- **A13:** `compras.html` usaba `/ventas/validar_stock/` (endpoint 
  de venta). Cambiado a `/catalogo/buscar/`. Test C10.
- **A14:** `ventas.html` no ofrecía imprimir Nota tras alerta. 
  Agregado `window.open('/ventas/{id}/imprimir/')`. Test C11.
- **A15:** kardex manual endpoint inexistente. Creado 
  `/movimientos/registrar/` + vista + JS. Test C12.

### Security (Hardening)

- **A16:** `settings.py` production-ready — `SECRET_KEY`/`DEBUG`/`ALLOWED_HOSTS` 
  desde env. WAL PRAGMA + headers de seguridad + `LOGGING` 
  RotatingFileHandler + `STATIC_ROOT`/`MEDIA_ROOT`. 
  `CSRF_COOKIE_HTTPONLY=False` para que JS getCookie funcione.
- **Setup `.env`:** cargador `_load_dotenv()` en `manage.py`/`wsgi.py`/`asgi.py` 
  sin depender de `python-dotenv`. Stdlib puro.
- **Hardening final (F-DOCS):** `SECURE_HSTS_PRELOAD=True`, 
  `SECURE_SSL_REDIRECT` via env (default False para on-premise LAN), 
  `SECURE_HSTS_PRELOAD` silencia W021. Check --deploy en DEBUG=False: 
  solo 1 warning esperable (W008 sobre HTTPS redirect para LAN HTTP).
- **A7:** `@csrf_exempt` removido de vistas sensibles. CSRF token 
  disponible via `getCookie('csrftoken')` global en `base.html`. 
  Cada fetch AJAX debe incluirlo en `X-CSRFToken` header.

### Documentation (Documentación)

- `docs/AUDITORIA_INICIAL.md` — hallazgos pre-Fase A.
- `docs/PLAN.md` — matriz completa Etapas A, B y Fases 3-6 con 
  commits y estados.
- `docs/ROADMAP.md` — features post-100% pagos, factura Seniat, 
  bitácora auditoría, app móvil.
- `docs/OPERACION.md` — guía instalación, módulos, troubleshooting, 
  reglas operativas.
- `docs/ARQUITECTURA.md` — diagrama, multi-tenant, regla sagrada 
  kardex, snapshots, mapa de services, migraciones, tests.
- `docs/ADR.md` — 16 ADRs formales (01-22 con saltos).
- `README.md` raíz — instalación rápida + features + reglas sagradas.
- `CHANGELOG.md` (este archivo).

### Internal (Refactors)

- **Fase 5:** índice de secciones añadido al header de `services.py` 
  (mapea cada dominio a número de línea). ADR-21: se decide NO 
  partir services.py en submódulos — riesgo de imports circulares 
  (models↔services) supera el beneficio de legibilidad.

### Operation (Operación)

- **management command `backup_db`:** atomic snapshot via 
  `VACUUM INTO`. Soporta retención y dry-run.
- **`seed_db --clear`:** ya existente, ahora documentado en 
  `docs/OPERACION.md`.

---

### Estadísticas finales

- 28 commits (`b0f7c3d` inicial → `2ae033e` F-DOCS).
- 157 tests en ~120s.
- 9 migraciones numeradas (0001-0009).
- 23 clases en `models.py` (19 modelos + 4 managers/clases proxy).
- 17 funciones públicas en `services.py`.
- 8 reportes operativos.
- 0 errores críticos en `manage.py check --deploy` con DEBUG=False.
