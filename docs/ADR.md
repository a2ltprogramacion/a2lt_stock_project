# Decisiones de Arquitectura (ADRs)

**Última actualización:** 2026-07-26

Este archivo centraliza todas las Decisiones de Arquitectura (ADR – 
*Architecture Decision Records*) referenciadas en el código y la 
documentación del sistema A2LT Stock. Cada ADR describe una decisión 
tomada, su contexto y sus consecuencias.

---

## ADR-01: Esquema de Nota de Entrega como documento de salida

**Estado:** Aceptada  
**Contexto:** Necesidad de un documento correlativo único por empresa 
que registre toda salida de inventario al cliente, persistiendo el 
número correlativo y el estado operativo.  
**Decisión:** Modelo `NotaEntrega` con `unique_together = 
('empresa', 'numero')`, `numero` autogenerado por `save()`, estado 
`PROCESADO`/`ANULADO` con motivo de anulación.  
**Consecuencias:** El número correlativo se respeta por tenant; las 
anulaciones queden trazadas. `services.reversar_nota_entrega()` es la 
única vía autorizada para marcar ANULADO + generar contramovimientos.

## ADR-02: DecimalField para todas las cantidades y precios

**Estado:** Aceptada  
**Contexto:** El sector requiere unidades fraccionables (kits, 
fracciones de combos). `FloatField` introduce errores de 
redondeo acumulativos en reportes histórico.  
**Decisión:** Todos los campos de cantidad, costo y precio se 
declaran como `DecimalField` con `max_digits` adecuado (12-18, 2-6 
decimales).  
**Consecuencias:** Mayor uso de memoria y(storage) pero reportes 
determinísticos. `services.calcular_stock_combo` usa `Decimal //` 
floor division desde A12 (commit `29a09ec`).

## ADR-03: Soft-delete en Articulo

**Estado:** Aceptada  
**Contexto:** El kárdex inmutable referencia Articulo por FK. Si se 
borra un Articulo, el histórico del kardex queda huérfano.  
**Decisión:** Articulo tiene `activo = BooleanField(default=True)`. 
Los borrados lógicos solo desactivan. Las consultas por default 
filtran `activo=True`.  
**Consecuencias:** El admin y las vistas de negocio deben respetar 
`activo`; las consultas históricas que reportan movimientos pasados 
usan `global_objects` para no perder referencias.

## ADR-04: Configuración por inquilino (no Singleton global)

**Estado:** Aceptada (modificada en migración `0001_normalizar_config`)  
**Contexto:** Originalmente existía un Singleton global. En multi-tenant, 
cada empresa necesita su propia configuración de tasas, márgenes, API, 
cuarentena, etc.  
**Decisión:** Modelo `ConfiguracionEmpresa` con FK OneToOne hacia 
`Empresa`. Cada tenant tiene su propio registro.  
**Consecuencias:** El context processor `inject_config` usa 
`ConfiguracionEmpresa.objects.first()` que opera vía `EmpresaManager` 
(ContextVar), por lo que respeta al tenant activo.

## ADR-05: Contacto unificado (Clientes + Proveedores)

**Estado:** Aceptada  
**Contexto:** Los comercios necesitan gestionar clientes y proveedores 
con campos casi idénticos; mantener dos modelos duplica tablas.  
**Decisión:** Modelo único `Contacto` con campo `tipo = 
CLIENTE|PROVEEDOR`. Los proxy models `Cliente` y `Proveedor` exponen 
managers filtrados por tipo.  
**Consecuencias:** Tabla única en DB; los FK `cliente` y `proveedor` 
usan `limit_choices_to={'tipo': '...'}` para validar a nivel form.

## ADR-06: Empresa como entidad raíz multi-tenant

**Estado:** Aceptada  
**Contexto:** Necesidad de aislar datos entre comercios sin recurrir 
a PostgreSQL schemas (regla: solo SQLite) ni a `tenant_id` manual en 
cada consulta.  
**Decisión:** `Empresa` es el padre multi-tenant. Todos los modelos 
multi-tenant tienen FK a `Empresa` y usan `objects = EmpresaManager()`. 
**Consecuencias:** Ver ADR-17 — el manager filtra automáticamente.

## ADR-08: TransactionTestCase para tests de rollback

**Estado:** Aceptada  
**Contexto:** Los tests que verifican `@transaction.atomic` con 
rollback real no funcionan con `TestCase` (usa savepoints).  
**Decisión:** Tests de reversos, anular venta/compra, y rollback de 
carga masiva usan `TransactionTestCase`.  
**Consecuencias:** Suite más lenta (~30 segundos más) pero verificación 
real de atomicidad en BD.

## ADR-09: Colisiones de carga masiva via sesión Django

**Estado:** Aceptada  
**Contexto:** La carga masiva puede encontrar conflictos (SKU ya 
existe con datos distintos). Necesitamos un UX de resolución sin BD 
intermedia.  
**Decisión:** Las colisiones se persisten en `request.session` bajo 
la clave `carga_{lote_id}`. La vista `vista_resolver_colision` las 
lee y permite al operador elegir "sumar" o "sustituir".  
**Consecuencias:** Sin tabla de staging; ver `views.py:353`.

## ADR-10: Validación de formato Excel

**Estado:** Aceptada  
**Contexto:** Los operadores suben archivos que a veces son `.xls` 
viejos o con macros; necesitamos rechazo temprano y claro.  
**Decisión:** `validar_formato_excel()` en `services.py:378` valida 
extensión, magic bytes y estructura básica de `openpyxl`. Rechaza 
`.xls` (legacy) y exige `.xlsx`.  
**Consecuencias:** Mensaje claro al operador; `ProcesarCargaMasivaExcel` 
espera un `io.BytesIO` válido.

## ADR-11: Carga masiva atómica por lote

**Estado:** Aceptada  
**Contexto:** Una carga masiva con 100 filas no puede dejar 
resultados parciales si la fila 50 falla.  
**Decisión:** `procesar_carga_masiva()` envuelve todo en 
`@transaction.atomic`. Cualquier error hace rollback total y 
devuelve el lote_id + filas afectadas para diagnóstico.

## ADR-12: Fixtures Excel en memoria (sin disco)

**Estado:** Aceptada  
**Contexto:** Tests repetitivos no pueden generar archivos temporales.  
**Decisión:** Los helpers de tests (`crear_excel_*` en `tests.py:453`) 
usan `openpyxl.Workbook` en `io.BytesIO`. Sin `NamedTemporaryFile`.

## ADR-13: Contrato de cabecera Excel para carga masiva

**Estado:** Aceptada  
**Contexto:** Un campo cambiado en la cabecera del Excel rompe toda 
la carga automáticamente sin mensaje claro.  
**Decisión:** Cabecera obligatoria documentada y validada por 
`procesar_carga_masiva_excel` (ver `services.py:469`). La orden de 
columnas también está validada.

## ADR-17: EmpresaManager + ContextVar multi-tenant

**Estado:** Aceptada  
**Contexto:** Reemplazo del patrón manual `filter(empresa=...)` por 
un mecanismo automático que filtre por el tenant activo sin que el 
código de negocio repita `filter(empresa_id=...)` en cada consulta.  
**Decisión:** 
- `contextvars.ContextVar('current_empresa')` en `inventory/managers.py`.
- `EmpresaManager(models.Manager)` sobreescribe `get_queryset()` 
  para filtrar por la empresa del contexto. Si `ContextVar` es None, 
  retorna queryset vacío (no `all()`) como defensa anti-fugas.
- `TenantMiddleware._authorize()` valida 5 condiciones y setea el 
  ContextVar en cada request.
- `global_objects = models.Manager()` se reserva para consultas 
  administrativas explícitas.

**Consecuencias:** Toda lectura/escritura multi-tenant pasa por 
`EmpresaManager` automáticamente. La única forma de bypassear es 
`global_objects` (auditable en code review).  
**Uso:** `get_current_empresa()` es la única forma de resolver el 
tenant activo desde servicios.

## ADR-18: Snapshots inmutables en NotaEntrega y DocumentoCompra

**Estado:** Aceptada  
**Contexto:** Las tasas de cambio cambian frecuentemente. Si los 
reportes históricos usan la config global, los totales del pasado 
varían con cada cambio de tasa.  
**Decisión:** 
- `DetalleNotaEntrega` graba `precio_unitario_usd`, 
  `precio_unitario_bs`, `costo_unitario_snapshot` al momento de la 
  venta (inmutables).
- `NotaEntrega` graba `tasa_bcv_aplicada` y 
  `factor_cobertura_aplicado`.
- `DocumentoCompra` graba `tasa_bcv_aplicada`, 
  `tasa_mercado_aplicada`, `factor_cobertura_aplicado`, 
  `fuente_tasa`, `monto_total_bs_snapshot`.
- `services.reversar_documento_compra` y 
  `reversar_nota_entrega` no modifican los snapshots; crean 
  contramovimientos del kárdex con el costo snapshot original.

**Consecuencias:** Los reportes históricos (Fase 4) son 
determinísticos; el test C15 valida inmutabilidad explícita.

## ADR-21: No partir services.py en submódulos

**Estado:** Aceptada  
**Contexto:** services.py tiene 2085+ líneas con 17 funciones 
públicas mezclando dominios (kardex, ventas, compras, devoluciones, 
carga masiva, reversos, tasas). Refactor natural: partirla en 
`services/kardex.py`, `services/ventas.py`, etc.  
**Decisión:** **No partir**. Se agrega un índice de secciones en 
el header del archivo (commit `5d5e45f`, Fase 5) que mapea cada 
dominio con el número de línea de su sección.  
**Motivos:** 
1. Riesgo de imports circulares (models ↔ services) — `Articulo.get_stock_disponible()` importa `services` de forma lazy.
2. Suite verde con 157 tests; un split puede romper imports 
   accidentalmente.
3. El índice en el header hace navegable el archivo sin 
   fragmentación.

**Consecuencias:** El archivo seguirá creciendo linea por linea 
pero el índice ayuda. Cuando los tests dejen de correr en <3 min 
o el archivo supere 5000 líneas, se podrá revocar este ADR.  
**Tests C18:** 2 tests protegen la API surface (17 funciones 
públicas deben estar presentes).

## ADR-22: Backups del sistema fuera del repositorio

**Estado:** Aceptada  
**Contexto:** El comando `backup_db` genera archivos SQLite en 
`backups/` que pueden pesar MBs y no aportan nada al repositorio.  
**Decisión:** `.gitignore` incluye `backups/` y `*.sqlite3` ya 
estaba. `logs/` y `*.log` también se excluyen.  
**Consecuencias:** Cada ambiente on-premise mantiene sus propios 
backups en disco; el repositorio queda limpio de artefactos.

---

## ADR-23: Emisión de Notas de Entrega y Facturas como un solo flujo (1.1.0)

**Estado:** Aceptada  
**Contexto:** El cliente opera PDV para clientes finales. 
Originalmente, la NotaEntrega era un documento interno. Se requirió 
emitir también Facturas con `numero_factura` único por empresa, 
sin romper el resto del flujo (kardex, snapshots, reversos).  
**Decisión:** Un solo modelo `NotaEntrega` con `tipo_documento` 
(`NOTA_ENTREGA` | `FACTURA`) y `numero_factura` opcional (NE) 
 u obligatorio (FACTURA), unique por empresa. El service 
`procesar_venta` mantiene una firma única, despachando internamente 
según `tipo_documento`. Correlativo por empresa via 
`ConfiguracionEmpresa.prefijo_nota_entrega` + 
`correlativo_inicial_nota`. `numero_nota` con formato 
`{prefijo}-{numero:08d}` auto-generado en `save()`.  
**Consecuencias:** Una sola tabla, una sola vista de detalle/PDF. 
El campo `iva_check` (calculated property: True si algún detalle 
tiene `iva_porcentaje>0`) reemplaza el toggle manual. La Validación 
UI (interlock: `confirm-sale-btn` deshabilitado si FACTURA sin 
`numero_factura`) se hace en `ventas.html` con `enableConfirmIfFacturaReady()`.  
**Tests:** C20 (modelos), C21 (UI interlock + PDF).

## ADR-24: 4 precios snapshot por detalle de venta y compra (1.1.0)

**Estado:** Aceptada  
**Contexto:** El sistema anterior sólo guardaba 2 precios 
(`precio_unitario_usd`, `precio_unitario_bs`). El cliente requiere 
tener precios con/sin factor de cobertura diferenciados para 
ambos USD y Bs. en cada detalle (post-pago, ajustes de inventarios, 
conciliaciones).  
**Decisión:** `DetalleNotaEntrega` y `DetalleDocumentoCompra` 
incluyen ahora 4 snapshots inmutables:
- `precio_base` / `costo_directo` = precio neto base (USD).
- `precio_ajustado` / `costo_ajustado` = base × factor (USD).
- `precio_directo_bcv` / `costo_directo_bcv` = base × tasa_bcv (Bs. sin factor).
- `precio_ajustado_bcv` / `costo_ajustado_bcv` = base × factor × tasa_bcv (Bs. con factor).

Más `iva_porcentaje` y `descuento_aplicado` (individual por línea) 
para que la línea sea reconstruible en el tiempo.  
**Implementación:** Set dentro de `procesar_venta` y 
`registrar_compra_proveedor`, atomic con el resto de la transacción.  
**Consecuencias:** Usuarios pueden ver el desglose en PDFs; los 
reportes históricos (Fase 4) quedan determinísticos. Tamaño de BD 
crece levemente (4 cols Decimal extra por detalle).  
**Tests:** C20 (creación de NE), C22 (creación de Compras).

## ADR-25: Tokens de variables de precio como literales de texto (1.1.0)

**Estado:** Aceptada  
**Contexto:** Los textos de mercadeo (`social_quick`, `social_cross`) 
se copian al portapapeles en el catálogo. Si el especialista 
hardcodea precios, cada cambio de tasa/precio exige reescribir todos 
los textos.  
**Decisión:** 4 tokens de sustitución dinámica, persistidos 
literalmente en BD:
- `$[PRECIO_USD]` = `precio_divisa` (USD base)
- `$[PRECIO_BCV]` = `precio_divisa × factor_cobertura` (USD ajustado)
- `$[PRECIO_BS_BASE]` = `precio_divisa × tasa_bcv` (Bs. sin factor; nuevo token)
- `$[PRECIO_BS]` = `precio_divisa × factor × tasa_bcv` (Bs. con factor)

La sustitución se hace en frontend (`catalogo.html`) por 
`copyToClipboard()` y `updateCrossSellingOutput()`, leyendo attrs 
`data-precio-base`, `data-precio-ajustado`, `data-precio-bs-base`, 
`data-precio-bs` ya presentes en la tarjeta. Compatibilidad legacy 
con `[Precio_USD]`, `[Precio_BCV]`, `[Precio_BS_BASE]`, `[Precio_Bs]`.  
**Consecuencias:** El especialista redacta una sola vez y los tokens 
se actualizan solos con cada modificación de config / precio. No se 
requiere ninguna migración (sólo un cálculo nuevo en 
`vista_catalogo`).  
**Tests:** C23 (4 precios cuádruples + atributos + sustitución).

## ADR-26: Toolbar de inserción de tokens con caret tracking sin servidor (1.1.0)

**Estado:** Aceptada  
**Contexto:** Insertar manualmente tokens en los textareas 
`social_quick` / `social_cross` es tedioso y propenso a errores.  
Se podría implementar un editor WYSIWYG, pero el perfil del producto 
no justifica añadir build JS ni dependencia pesada.  
**Decisión:** 4 botones encima de cada textarea de marketing en 
`articulos.html` (`#form-p-cross` y `#form-p-quick`). El JS 
`injectToken(textareaId, token)`:
1. Lee `selectionStart`/`selectionEnd` del textarea (caret position).
2. Reconstruye el valor: `texto[:start] + token + texto[end:]`.
   Esto sobrescribe la selección si existe (comportamiento estándar 
   de editores); si no, inserta en la posición del cursor.
3. Coloca el cursor justo después del token via 
   `setSelectionRange(start + token.length, ...)`.
4. Mantiene el foco y dispara `Event('input')` para frameworks que escuchan.

**Crucial:** `injectToken` NO hace fetch al servidor. El texto se 
persiste literal al guardar vía `saveProduct()` (con el token ya 
insertado). Cumple ADR-25: los tokens son literales.  
**Consecuencias:** Sin build JS, sin-state del lado del servidor 
para el editor. La `#form-p-ficha` (Ficha Técnica) NO tiene toolbar 
— es para datos técnicos del equipo, no incluye precios.  
**Tests:** C23 (toolbar presencia + 4 botones × 2 textareas + función 
`injectToken` definida + no-contiene-fetch + caret tracking).

---

## ADR-27: IVA individual por línea con override opcional (1.1.1 O2)

**Estado:** Aceptada  
**Contexto:** Una factura puede mezclar items con diferentes IVAs 
(16%, 8%, exento). El backend tenía un solo `iva_check` global y 
un único `iva_porcentaje` por artículo en `Articulo`. No había 
forma de cargar el PDT diferenciando por línea — problema real 
en operaciones cotidianas.  
**Decisión:**  
1. `procesar_venta` y `registrar_compra_proveedor` aceptan 
   `iva_porcentaje` por item en `lista_items[]`. Si viene, toma 
   precedencia sobre `Articulo.iva_porcentaje`; si no viene, cae 
   al default para compatibilidad hacia atrás.
2. `ConfiguracionEmpresa.ivas_disponibles` (JSONField) es la lista 
   de hasta 5 tasas permitidas que se inyecta como 
   `ivas_disponibles_json` (fallback `[16, 8, 0]`) en 
   `ventas.html` y `compras.html`, y se renderiza como `<select>` 
   por línea en la grilla de items.
3. Rango válido: `0 ≤ iva_porcentaje ≤ 100`. Fuera de rango → 
   `ValueError`.  
**Consecuencias:** Permite cargar PDT diferenciadas sin tocar la 
configuración de inventario. El `iva_total` de cabecera se calcula 
sumando los IVAs individuales de cada detalle. UI con `<select>` 
es nativo HTML, sin librerías JS.  
**Tests:** C24 (3 tipos de documento), C25 (IVA por línea en backend + UI), 
C26 (configuración por tenant).

## ADR-28: Tipo de Documento de Compra separado en 3 opciones (1.1.1 O1)

**Estado:** Aceptada  
**Contexto:** `DocumentoCompra.TIPO_DOCUMENTO_CHOICES` mezclaba 
`FACTURA_COMPRA`, `NOTA_CREDITO_COMPRA` y `ORDEN_COMPRA`. Las 
Notas de Crédito son devoluciones (diferente flujo), y la "Orden 
de Compra" no debería tocar inventario hasta ser aprobada 
(flujo pendiente de implementar). La opción clásica `NOTA_ENTREGA` 
del proveedor (recibos sin factura) no estaba soportada.  
**Decisión:**  
1. Choices reducidos a 3: `FACTURA_COMPRA` (con #factura obligatorio), 
   `NOTA_ENTREGA_PROVEEDOR` (con #documento opcional), `REGISTRO_MENOR` 
   (sin doc. físico — repos de mostrador).
2. Migración 0013 (`tipo_documento_compra_3_opciones`).
3. Las Notas de Crédito se reservan como **módulo aparte** 
   (`/notas-credito/`, TICKET #18-NC), fuera del formulario de 
   Compras, porque requieren referenciar un documento origen, listar 
   items a devolver (parcial/total) y generar contramovimientos 
   de kardex — no caben en un radio button.
4. La unicidad de `numero_factura` aplica a cualquier doc con número 
   informado (no sólo FACTURA_COMPRA).  
**Consecuencias:** El usuario puede cargar compras con recibos/notas 
del proveedor sin complejidad. Las Notas de Crédito ganan su propio 
módulo con trazabilidad desde el doc. original.  
**Tests:** C24 (5 tests: 3 opciones + 2 choices viejos fallan).

## ADR-30: Captura de seriales inline por fila (1.2.1)

**Estado:** Aceptada (2026-07-26). Iteración UX.

**Contexto:**

El formulario de Compras (`compras.html`) implementaba la captura de 
seriales (TKET #14-SAAS, Fase C1) con un **panel inferior** 
(`#purchase-seriales-panel-container`) que listaba los seriales 
DISPONIBLES ya existentes en el inventario, permitiendo al operador 
"seleccionar" cuáles añadir. El frontend cargaba el panel vía 
`loadSerialesForPurchaseItem()` hasta 3 llamadas AJAX, mantenía un 
cache `serialesCache`, y `togglePurchaseSerial()` hacía add/remove 
de cada IMEI.

El problema: **las comprasregistran seriales NUEVOS que llegan en 
la factura del proveedor**, no existentes. El panel de "selección desde 
stock" era conceptualmente incorrecto y obligaba al operador a 
trabajar dos veces: parsear la factura a mano afuera y luego hacer 
click en cada serial uno por uno. Inusable para artículos con alta 
rotación (AURI-001, antenas con IMEI).

**Decisión:**

- Remover el panel HTML + los 3 funciones JS 
  (`loadSerialesForPurchaseItem`, `renderPurchaseSerialesPanel`, 
  `togglePurchaseSerial`) + `serialesCache`.
- Cada fila de item con `usa_serial=true` en la grilla de Compras 
  muestra un `<input type="text">` inline para que el operador pegue 
  / escriba los seriales que llegan en la factura, separados por 
  `,`, `;` o saltos de línea. Útil para pegar listas de IMEIs desde 
  el PDF o el correo del proveedor.
- `parseSerialInput(str)` se encarga de normalizar (split por 
  delimitadores, `.trim()`, dedupe, descarta vacíos) generando un 
  array `seriales_parsed`.
- Contador live `X/N` en el input: gris si 0, ámber si 
  incompleto, verde si parseado == `qty`.
- `processPurchase()` valida antesde enviar: si el item tiene 
  `usa_serial=true`, `seriales_parsed.length` debe ser exactamente 
  igual a `qty`. Si no, alerta y hace `focus()` al input.
- El backend NO cambia: `registrar_compra_proveedor` en `services.py` 
  ya esperaba `lista_items[].seriales: [...]` desde 1.1.0 y ya validaba 
  `len(seriales) == cantidad` + `bulk_create` as `DISPONIBLE` + 
  `compra_origen=documento`.
- Para VENTAS el wizard de selección FIFO de seriales persiste 
  intacto (ahí sí se elige desde stock DISPONIBLE).

**Consecuencias:**

- Menos clicks para registrar una compra con seriales: el operador 
  pega la lista y continúa. No hay ida-vuelta al servidor para 
  "cargar" seriales existentes.
- Compatibilidad con el backend asegurada sin migración: 
  el contrato `lista_items[].seriales: [str]` se respeta.
- La UI de Ventas no se toca: su flujo FIFO de selección de 
  seriales DISPONIBLES es correcto (los seriales ya están en stock a 
  esa altura), no requiere cambio.
- El bug C2 (multi-tenant leak en `vista_buscar_seriales_articulo`) 
  sigue mitigado desde 1.1.0; no se reintroduce.

**Tests:** sin tests nuevos. El contrato `seriales: [str]` en 
`registrar_compra_proveedor` ya está cubierto por tests C22 desde 1.1.0. 
Backend sin cambios.

---

## ADR-31: Sidebar colapsable con persistencia en localStorage (1.2.1)

**Estado:** Aceptada (2026-07-26). Iteración UX.

**Contexto:**

El sidebar fijo en `base.html` ocupa 256 px de ancho permanente. En 
pantallas 1366×768 (comunes en comercios venezolanos, electrodomésticos 
reciclados como POS), esto deja ~1100 px para la zona de trabajo, 
restándole张家空间 a las tablas largas (Compras, Ventas, Kardex) y a 
los formularios de captura.

**Decisión:**

- Añadir `id="app-sidebar"` al `<aside>` y `id="main-content"` al 
  `<main>` para anclar por JS.
- CSS `.sidebar-collapsed` en el `<aside>` (`w-16`, hide text labels) 
  + `.sidebar-collapsed + #main-content` hereda el anchoMayor 
  automáticamente (sm:ml-64 → sm:ml-16).
- Botón en el header (icono `fa-bars` / `fa-angles-left` según estado) 
  invoca `toggleSidebar()`.
- `localStorage` clave `a2lt_sidebar_collapsed` (boolean) persiste 
  entre sesiones.
- Script **anti-flash** inyectado en el `<head>` antes del render 
  del body: lee `localStorage` y agrega la clase `sidebar-collapsed` 
  al `<html>` tag si corresponde, para que el primer paint ya muestre 
  el sidebar colapsado/expandido correcto y evitar FOUC.
- Los 14 enlaces del menú envuelven su texto en 
  `<span class="nav-label">`. CSS 
  `.sidebar-collapsed .nav-label { display: none }` oculta el texto 
  cuando colapsa, dejando sólo iconos.
- El título de sección del sidebar y los datos del perfil del usuario 
  también colapsan (clase `sidebar-section-title` en el span de 
  título, clase `profile-text` en el div de datos del usuario).

**Consecuencias:**

- Cliente + operador recuperan ~192 px de ancho de trabajo en tablas 
  y formularios. La captura de Compras en 1366×768 ahora es viable 
  sin scroll horizontal en la grilla.
- Estado persistente entre pestañas y recargas (no se reinicia al 
  navegar).
- Compatible con dark mode: el script anti-flash no toca el 
  `localStorage` del tema, son ortogonales.
- Sin cambios en backend, sin vistas nuevas. Cambio puramente UI 
  en `base.html`.

**Tests:** sin tests nuevos. El `base.html` ya se cubre por tests C3 
(getCookie + block extra_js) y la mayoría de pruebas de render que 
verifican el layout base.

---

## ADR-32: CSP nativa de Django 6 con nonces por request

**Estado:** Aceptada (2026-10-24). Remediación SEC-02b / REQ-CSP-01..09 del
Capítulo 2 de `docs/plans/EST_ESTRUCTURALES_PLAN_Y_TAREAS.md`.

**Contexto:**

La política CSP previa la construía un middleware propio
(`inventory.middleware.CspMiddleware`) serializando el string crudo
`CSP_POLICY` de settings.py. Sin nonces, los 16 bloques `<script>`
inline repartidos en 14 plantillas exigían `'unsafe-inline'` en
script-src: cualquier script inyectado en una plantilla ejecutaba sin
restricción (mitigación XSS nula para inline). Django 6.0 incorporó CSP
nativa: `SECURE_CSP` / `SECURE_CSP_REPORT_ONLY` (dicts de directivas),
`django.middleware.csp.ContentSecurityPolicyMiddleware` (MiddlewareMixin
que setea `request._csp_nonce` en process_request y aplica el header en
process_response) y el context processor
`django.template.context_processors.csp` que expone `{{ csp_nonce }}`
(LazyNonce: header y plantilla comparten el MISMO valor por request).

**Decisión:**

1. **Adoptar el stack nativo y eliminar el propio.** MIDDLEWARE usa
   `django.middleware.csp.ContentSecurityPolicyMiddleware` en la MISMA
   posición que ocupaba el nuestro: inmediatamente ANTES de
   `TenantMiddleware` (el tenant retorna sus 403 con early return sin
   invocar `get_response`; por ser MiddlewareMixin, el nativo ya fijó el
   nonce en la bajada y aplica el header al subir, así los 403 del
   tenant también quedan cubiertos). Se eliminan el string `CSP_POLICY`
   (settings.py) y `class CspMiddleware` (middleware.py) sin alias
   deprecado; `TenantMiddleware` se conserva intacto.
2. **Política como dict único `_CSP_DICT`** con constantes
   `django.utils.csp.CSP`: `script-src` = self + NONCE +
   `cdn.tailwindcss.com` SIN `'unsafe-inline'` (con nonce, CSP3 lo
   ignoraría de todos modos — eliminación efectiva); `object-src
   'none'`; `frame-ancestors 'none'`; `style-src` CONSERVA
   `'unsafe-inline'` (deuda, ver Consecuencias). Los 16 scripts inline
   llevan `nonce="{{ csp_nonce }}"`; los 4 tags CDN externos con SRI no
   se tocan (el nonce solo autoriza inline).
3. **Knob `CSP_MODE`** (solo variable de entorno, sin duplicar la
   política): `'report'` (default) → `SECURE_CSP_REPORT_ONLY =
   _CSP_DICT` → header `Content-Security-Policy-Report-Only` (no
   bloqueante, ventana de adopción); `'enforce'` → `SECURE_CSP =
   _CSP_DICT` → header bloqueante. Valor fuera de `report|enforce` →
   `ImproperlyConfigured` en arranque (fail-fast, no fail-silent).
   Flip a enforcing y rollback de emergencia = env var + restart, cero
   código.

**Consecuencias:**

- `script-src` queda SIN `'unsafe-inline'`: un script inline solo
  ejecuta si lleva el nonce del request. El gate estático
  `test_csp_gate_estatico_scripts_inline_con_nonce` impide añadir
  plantillas con `<script>` inline sin nonce.
- **Deuda declarada:** `'unsafe-inline'` en `style-src` NO es removable
  mientras exista el Tailwind CDN JIT (inyecta `<style>` en runtime;
  SEC-05 mantiene el CDN hasta que exista un build de Tailwind).
- Report-Only sin `report-uri`: las violaciones solo se ven en la
  consola del navegador; suficiente para la LAN. El flip definitivo
  exige navegación manual de las 7 vistas con JS (spec §2.5).
- Hoy no hay caching de HTML → nonce-per-request seguro (REQ-CSP-09).
  Si algún día se cachean páginas, excluir header/nonce del cache
  (documentado en `docs/OPERACION.md`).
- El middleware nativo respeta headers CSP pre-existentes y valida el
  dict en `manage.py check` (E026).

**Tests:** `inventory/test_cases/test_security_csp_403.py` reworkado al
contrato nativo (15 tests: helper `csp_de()` modo-agnóstico, 5 sec02b
reworkados y 6 nuevos — gate estático, nonce header==scripts, nonces
distintos, default report-only, flip enforce, eliminaciones
estructurales). `test_templates_sri.py` intacto.

---

## ADR-33: Usuario forense: FK global a User + snapshot usuario_nombre
en kárdex y notas de crédito

**Estado:** Aceptada (2026-10-24). Remediación EST-04 /
REQ-EST04-01..08 del Capítulo 3 de
`docs/plans/EST_ESTRUCTURALES_PLAN_Y_TAREAS.md`.

**Contexto:**

`MovimientoKardex.usuario` y `NotaCredito.usuario` eran
`CharField(150)`: la "trazabilidad" era un string libre sin
integridad referencial — cualquiera podía escribir `'admin'` desde
el shell o un POST, sin que ningún constraint lo vinculase con
`auth_user` (hallazgo EST-04). Auditoría del backfill sobre la BD
real: 195 kárdex existentes, solo 8 con username existente
(`angeldrk` → FK resuelta); los literales de demo/semilla
(`'Demo Setup'` ×66, `'Demo User'` ×29, `'Sistema'` ×4, `''` ×88)
no existen como usuarios y quedan FK NULL con el snapshot
preservado. `NotaCredito`: 0 filas históricas.

**Decisión:**

1. Renombrar `usuario` → `usuario_nombre` como snapshot inmutable
   de presentación (`RenameField`: el histórico se preserva).
2. FK nueva `usuario` → `User` con `SET_NULL` — la trazabilidad
   degrada, no se pierde: la baja de un usuario deja la FK en NULL
   y el snapshot conserva el nombre.
3. Helper único `services.resolver_usuario` acepta
   `str | User | None`: instancia `User` → FK + `user.username`;
   string con username existente → FK resuelta (match exacto por
   `username`); sin match → FK NULL + snapshot con el string.
   Solo los 3 sitios de persistencia resuelven (create de
   `registrar_movimiento` y los `NotaCredito.objects.create` de
   `procesar_devolucion_{venta,compra}`); los writers
   intermedios reenvían el kwarg.
4. Las vistas llenan la FK desde `request.user` (operador
   autenticado); el `usuario` que llega por POST/JSON queda
   **DEPRECADO**: se ignora con `logger.warning` y puede tocar,
   como mucho, el snapshot de presentación — NUNCA la FK. La
   identidad forense sale SIEMPRE del autenticado.
5. Los `reversar_*` dejan de hardcodear `'Sistema'` y registran
   el usuario real; el default `'Sistema'` se conserva sólo para
   backward-compat.

**Decisión de multi-tenant** (el punto clave del ADR,
REQ-EST04-08): la FK es GLOBAL a la tabla `auth_user` — los
usuarios NO son per-empresa; el aislamiento por tenant lo gobierna
`PerfilUsuario` (`empresas_permitidas`/`empresa_activa`) en la
capa de acceso, NO en la FK. Una FK filtrada por tenant no es
viable sin un esquema de usuarios por empresa. El mismo usuario
real puede figurar en el kárdex de varias empresas y la FK sigue
resolviendo.

**Consecuencias:**

- `on_delete=SET_NULL`: borrar un `User` no borra historia (kárdex
  y NC quedan con FK NULL + snapshot intacto).
- El snapshot es la fuente de presentación: listados y PDF usan
  `usuario_nombre` (el PDF de NC en `views.py` y
  `nota_credito_detalle.html` renderizan `usuario_nombre` con
  fallback `'Sistema'`; la FK puede ser None).
- Migración `0029_usuario_fk_kardex_nc` escrita a mano porque
  `makemigrations` autogenera `AddField`+`AlterField` destructivo
  en SQLite (drop de columna = pérdida de datos); idempotente
  (2ª pasada del backfill es no-op) y reversible (el reverse pone
  la FK a NULL, el snapshot NUNCA se toca).
- El kwarg de servicio sigue llamándose `usuario` (distinto del
  campo): los ~60 call-sites de tests no se tocan.

**Tests:** `inventory/test_cases/test_usuario_fk.py` (7): backfill
match / sin match / idempotencia; resolución `str|User|None`;
`reversar_*` con usuario (y backward-compat sin arg); vistas con
`request.user` + `logger.warning` del POST `usuario` deprecado.

---

## ADR-34: Kárdex inmutable: guards de señal + QuerySet + escape
hatch con allowlist (EST-01)

**Estado:** Aceptada (2026-10-24). Remediación EST-01 /
REQ-EST01-01..09 del Capítulo 4 de
`docs/plans/EST_ESTRUCTURALES_PLAN_Y_TAREAS.md`.

**Contexto:**

La "REGLA SAGRADA" (solo `services.registrar_movimiento` muta stock
vía kárdex) era una intención del código, no un invariante: un
`.delete()` de queryset, un `.update(cantidad=...)`, un script de
shell o un `INSERT` directo la saltaban sin dejar rastro — borrando
la trazabilidad forense que la propia regla prometía (hallazgo
EST-01, spec §2.1).

Corrección al plan: un override de `delete()` a nivel de instancia
NO cubre los borrados bulk ni `.update()` (que además no emite
señales); esa vía se descarta y se documenta.

**Decisión:**

1. **Señales `pre_save` + `pre_delete` con `sender=clase real`**
   (`inventory/kardex_guard.py`, conectadas en `apps.ready()`):
   cubren instancia, bulk y cascada — el collector de Django envía
   TODAS las `pre_delete` antes de ejecutar un solo DELETE SQL, por
   lo que el raise aborta la operación completa sin borrados
   parciales. Los modelos históricos de migraciones
   (reconstruidos por `ModelState`: id distinto, sin relación de
   subclase) NO disparan estos receivers — las `RunPython` quedan
   exentas por diseño (probado con el roundtrip de la `0029`:
   `migrate inventory 0028 && migrate inventory` completa el
   backfill `fila.save()` sobre históricos sin
   `KardexProtegidoError`).
2. **`KardexQuerySet`** bloquea `.update()` y `bulk_create()` —
   las dos vías de mutación masiva que NO emiten señales — cableado
   a AMBOS managers de `MovimientoKardex`: `objects` vía
   `EmpresaManager.from_queryset(KardexQuerySet)()` (conserva el
   filtro de tenant: el `get_queryset()` de `managers.py` aplica
   `.none()`/`.filter` SOBRE un KardexQuerySet) y `global_objects`
   vía `as_manager()` (sin filtro de tenant, mismo bloqueo).
   Ningún otro modelo hereda el bloqueo.
3. **Escape hatch `kardex_bypass(motivo)`**: `ContextVar` con
   CONTADOR apilable (reentrante; thread/async-safe), log WARNING
   con el motivo al entrar. El service usa el contexto INTERNO
   `escritura_kardex_autorizada` (mismo contador, log INFO): el
   camino legítimo no genera ruido de WARNING. El `finally` con
   `reset(token)` impide fugas de contexto ante excepciones.
4. **Excepción `KardexProtegidoError`** (subclase de
   `IntegridadDocumentalError` → `PermissionDenied`): semántica de
   "operación no permitida" — un camino HTTP respondería 403, no
   500.

**Divergencia documentada vs el plan (crítica):** el plan esperaba
que el bypass hiciera pasable la cascada de `Empresa.delete()`. En
Django 6 los FK PROTECT preexistentes
(`MovimientoKardex.articulo/almacen`, `InventarioAlmacen.*`) lanzan
`ProtectedError` durante `collect()` ANTES de que exista señal
alguna — con o sin bypass. La primera excepción real de
`Empresa.delete()` en un tenant con kárdex es `ProtectedError`;
`KardexProtegidoError` queda como backstop del borrado directo de
kárdex. Por eso `services.eliminar_tenant(empresa, motivo)` —
única vía autorizada de teardown, motivo obligatorio (`ValueError`
si viene vacío), WARNING auditable al log — hace teardown
EXPLÍCITO en orden de dependencias scoped al tenant: kárdex →
seriales → NC (detalles+cabeceras) → notas (detalles+cabeceras) →
inventarios → compras (detalles+cabeceras) → recetas → contactos →
artículos → almacenes → config → `empresa.delete()` final (barrido
CASCADE/SET_NULL/RESTRICT del resto: correlativo, monedas, tasas,
auditoría). Viable SIN migraciones nuevas.

**Allowlist** (REQ-EST01-04; auditable por grep: un 4º uso del
bypass en services/views/admin es defecto de diseño, no un caso):

| Sitio | Uso del bypass |
|-------|----------------|
| `services.registrar_movimiento` | No usa el bypass público: contexto interno `escritura_kardex_autorizada` (el único punto donde nace kárdex legítimo) |
| `seed_db --clear` (`seed_db.py:503`) | Reseed demo: bulk delete global del kárdex dentro del bypass |
| Fixture export SaaS (`tests.py:1641`) | Crea kárdex directo y envejece su `fecha_hora` (create 1642 / `.update()` 1653; fixture declarado, no relajación) |
| `TestBackfillUsuarioFK` (`test_cases/test_usuario_fk.py`) | Fixtures del cap. 3: kárdex histórico pre-FK para el backfill de la `0029` |
| `services.eliminar_tenant` | Única vía de teardown de tenant (divergencia arriba) |
| `generate_demo_data` | **NO necesita bypass**: crea kárdex vía `registrar_compra_proveedor` (service) |
| Migraciones 0029/0030 | **Exentas por sender** (modelos históricos; REQ-EST01-07) |

**Consecuencias:**

- En producción el raise de `pre_delete` ocurre DENTRO del
  `transaction.atomic(savepoint=False)` del collector: envenena la
  transacción del caller (marca `needs_rollback`) — que ES el
  rollback total deseado, nada queda medio borrado. Los tests lo
  aíslan con un savepoint propio para poder seguir consultando.
- El bypass es el mecanismo COMPARTIDO que reutilizará EST-02
  (`seed_db --clear` y teardowns: mismo ContextVar, misma
  allowlist, auditable por grep en UN solo módulo).
- Las cascadas `SET_NULL` de la baja de usuarios (Gherkin
  EST04-05) no disparan el guard por diseño: el collector las
  resuelve con el `_base_manager` plano sobre `UpdateQuery` crudo
  (sin señales) y la fila de kárdex persiste con FK NULL +
  snapshot.
- `makemigrations --check` limpio: el wiring de managers no toca
  el estado del esquema (`use_in_migrations` inactivo).

**Tests:** `inventory/test_cases/test_kardex_inmutable.py` (8):
delete bloqueado en instancia/queryset/`global_objects`; `create`
directo y `bulk_create` bloqueados; `.update()` bloqueado en ambos
managers; bypass apilable con WARNING; `Empresa.delete()` con
kárdex bloqueado con rollback total; `eliminar_tenant` teardown
completo + motivo obligatorio; reverso N+1 (solo INSERT
compensatorio); receivers cableados solo a la clase real.

---

## ADRs no implementadas / candidatas

Las siguientes ADRs aparecen referenciadas en código pero no tienen 
desarrollo formal en este archivo:

- **ADR-06**: ya cubierta por ADR-17 (ContextVar). Se conserva la 
  referencia histórica en `models.py:7`.
- **ADR-19, ADR-20**: reservadas para futuras decisiones (sin uso 
  actual).

---

## Mapa de ADRs por componente

| ADR | Afecta a | Implementado en |
|-----|----------|-----------------|
| 01 | NotaEntrega | `models.NotaEntrega`, `services.reversar_nota_entrega` |
| 02 | Cantidades/precios Decimal | todos los modelos con DecimalField |
| 03 | Soft-delete Articulo | `models.Articulo.activo` |
| 04 | ConfiguracionEmpresa OneToOne | `models.ConfiguracionEmpresa` |
| 05 | Contacto unificado | `models.Contacto`, `Cliente`, `Proveedor` |
| 06 | Empresa raíz multi-tenant | `models.Empresa` |
| 08 | TransactionTestCase | `tests.TestRollbackAtomicidad`, etc. |
| 09 | Carga masiva via sesión | `views.py:353` |
| 10 | Validación Excel | `services.validar_formato_excel` |
| 11 | Carga atómica | `services.procesar_carga_masiva` |
| 12 | Fixtures en memoria | `tests.crear_excel_*` |
| 13 | Contrato cabecera Excel | `services.procesar_carga_masiva_excel` |
| 17 | EmpresaManager ContextVar | `managers.py`, `middleware.py` |
| 18 | Snapshots inmutables | `DetalleNotaEntrega`, `DocumentoCompra` |
| 21 | No partir services.py | `services.py` header + tests C18 |
| 22 | Backups excluidos git | `.gitignore` |
| 23 | Emisión NE/Factura unificada | `models.NotaEntrega.tipo_documento`, `services.procesar_venta`, `views.ventas` |
| 24 | 4 precios snapshot por detalle | `DetalleNotaEntrega`, `DetalleDocumentoCompra`, migraciones 0010/0011 |
| 25 | Tokens de precio literales | `Articulo.social_quick/social_cross`, `catalogo.html` JS |
| 26 | Toolbar caret tracking sin servidor | `articulos.html` JS `injectToken()` |
| 27 | IVA individual por línea con override (1.1.1) | `procesar_venta`, `registrar_compra_proveedor`, `ivas_disponibles_json` |
| 28 | Tipo de Documento Compra 3 opciones (1.1.1) | `DocumentoCompra.TIPO_DOCUMENTO_CHOICES`, migración 0013 |
| 29 | Notas de Crédito como módulo aparte 1-NC-1-origen (1.2.0 / TKET #18-NC) | `NotaCredito`/`DetalleNotaCredito`, `procesar_devolucion_{venta,compra}`, ruta `/notas-credito/` |
| 30 | Captura de seriales inline por fila en Compras (1.2.1) | `compras.html` (`parseSerialInput`, `updatePurchaseSerial`, contador live) |
| 31 | Sidebar colapsable con persistencia localStorage (1.2.1) | `base.html` (`toggleSidebar`, script anti-flash, CSS `.sidebar-collapsed`) |

## ADR-29: Notas de Crédito con diseño 1-NC-1-origen (1.2.0 / TKET #18-NC)

**Estado:** Aceptado (2026-07-13). Implementado y validado por
`TestNotasCreditoBackend` (15 tests) + `TestNotasCreditoUI` (14 tests) +
suite completa 276 ✓ en ~190s.

**Contexto:**

La versión anterior del módulo de Notas de Crédito (TKET #15-SAAS)
implementaba un modelo flexible pero con problemas de diseño:

1. La función `procesar_devolucion_venta()` recibía parámetros
   posicionales (`nota_id, items, tipo_costo`) en lugar de kwargs.
2. Soportaba tres modos ortogonales (`tipo_costo` ∈ {HISTORICO, ACTUAL},
   `es_defectuoso`, `usa_almacen_cuarentena`) que interactuaban
   generando una explosión combinatoria de casos a probar.
3. El servicio determinaba el destino del stock mediante un campo en
   `ConfiguracionEmpresa`, lo que abortaba el flujo offline si la
   configuración cambiaba.
4. La NC se identificaba con un sello de tiempo (`int(time.time())`)
   que podía colisionar entre tenants.

**Decisión:**

Para la iteración 1.2.0 reemplazamos el módulo entero con un diseño
**1-NC-1-origen**:

- Cada nota de crédito se apega exclusivamente a **un** documento de
  origen: o una `NotaEntrega` (devolución de venta) **o** un
  `DocumentoCompra` (devolución a proveedor). Esto se enforce a nivel
  de BD con `models.CheckConstraint(condition=…)` (XOR entre los dos
  campos FK).
- Cada línea tiene su propio `detalle_origen_venta` o
  `detalle_origen_compra` (también XOR).
- El `numero_control` se calcula en el `save()` de la NC, leyendo
  `ConfiguracionEmpresa.prefijo_nota_credito` (default `NC`) y
  `numero = Max('numero') + 1` **filtrado por empresa**. Resultado: 
  formato `NC-00000001` por tenant.
- Cada ítem de la NC persiste **3 snapshots** inmutables:
  `precio_unitario_snapshot`, `iva_porcentaje_snapshot` y
  `cantidad_devuelta`. Aunque el `Articulo` cambie después, la NC
  sigue mostrando el precio con que se vendió/compró.
- Cardinalidad: múltiples NC pueden existir sobre el mismo
  `DetalleNotaEntrega`/`DetalleDocumentoCompra`; cada una respeta el
  tope `cantidad_pendiente_devolver` que es propiedad agregada de la
  línea, **no** de la NC.
- Kardex: la devolución genera **un único movimiento** por línea de
  NC: `DEVOLUCION_VENTA`/`DEVOLUCION_COMPRA`. La liberación de
  seriales es FIFO (`VENDIDO → DISPONIBLE` en ventas; 
  `DISPONIBLE → ANULADO_COMPRA` en compras).
- Servicios `procesar_devolucion_venta()` y
  `procesar_devolucion_compra()` comparten firma kwargs: 
  `(empresa_id, nota/compra_id, items_devueltos, motivo, usuario)`.
  Validación multi-tenant **perimetral** con `global_objects` (evita
  leak entre tenants vía contextvars del `EmpresaManager`).

**Consecuencias:**

- ✅ Auditoría más limpia: cada NC está asociada 1:1 con un único doc
  origen, sin enumerar varios en la cabecera. Kardex tiene un solo
  registro por línea.
- ✅ UI simplificada: una sola pantalla con pestañas (historial +
  emisión) en lugar del wizard multi-paso de la versión previa.
- ✅ Multi-tenant estricto: services pasan por validación
  perimetral `global_objects` aislada del `EmpresaManager.transitivo`
  para que las FKs (FK to origen) no salten de tenant.
- ✅ Snapshots robustos: cambio de precio en `Articulo` no afecta
  histórico de NCs ya emitidas (C-N2).
- ⚠️ Funcionalidades removidas del sistema anterior: talla複数
  simultánea (`HISTORICO`/`ACTUAL` mezcladas en una misma emisión),
  merma automática desafect, cuarentena automática. Estas se podrán
  readicionar en ADR futura si el cliente las pide. Tests legacy
  (`TestNotasDeCreditoPOS`, 4 tests + 1 de
  `TestSaneamientoYVulnerabilidadesSaaS.test_costo_historico_*`) 
  marcados con `@skip` por incompatibilidad de contrato.
