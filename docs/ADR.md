# Decisiones de Arquitectura (ADRs)

**Última actualización:** 2026-07-10

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
