# Arquitectura — A2LT Stock

**Versión:** 1.0 (julio 2026)

## Visión general

A2LT Stock es un sistema monolítico Django on-premise con patrón 
multi-tenant basado en **ContextVar** (no en schema separado ni en 
`tenant_id` manual). Esto aísla datos entre comercios con una sola 
instancia de SQLite WAL.

```
┌─────────────────────────────────────────────────────────┐
│                      Browser (Tailwind)                  │
└───────────────────┬─────────────────────────────────────┘
                    │ HTTP + CSRF
┌───────────────────▼─────────────────────────────────────┐
│  Django Middleware Stack                                 │
│  ┌────────────────────────────────────────────────────┐  │
│  │ TenantMiddleware (valida 5 condiciones y setea       │  │
│  │ ContextVar current_empresa)                          │  │
│  └────────────────────────────────────────────────────┘  │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│   Views (HTTP/JSON adapters; sin lógica de negocio)      │
│   views.py, reports.py, exporters.py                    │
└───────────────────┬─────────────────────────────────────┘
                    │ (only via services)
┌───────────────────▼─────────────────────────────────────┐
│   services.py — ÚNICA capa autorizada a mutar kardex     │
│   17 funciones públicas (kardex, ventas, compras, ...)  │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│  Models + EmpresaManager   ← filtrado automático por    │
│  23 clases (Empresa + 19 modelos + 4 managers)     ContextVar │
└───────────────────┬─────────────────────────────────────┘
                    │
┌───────────────────▼─────────────────────────────────────┐
│   SQLite WAL — un archivo db.sqlite3 compartido          │
│   backup_db genera snapshot atomic via VACUUM INTO       │
└─────────────────────────────────────────────────────────┘
```

## Multi-tenant: ContextVar

El patrón central. **`inventory/managers.py`** define:

```python
_current_empresa = contextvars.ContextVar('current_empresa', default=None)

def set_current_empresa(empresa_id): ...   # middleware invoca
def get_current_empresa(): ...              # vistas/services usan
def reset_current_empresa(token): ...      # middleware finally: restablece

class EmpresaManager(models.Manager):
    def get_queryset(self):
        qs = super().get_queryset()
        empresa_id = get_current_empresa()
        if empresa_id is not None:
            return qs.filter(empresa_id=empresa_id)
        return qs.none()   # ADR-17: SIEMPRE None → queryset vacío (no `all()`)
```

Todos los modelos multi-tenant declaran:

```python
class Articulo(models.Model):
    empresa = models.ForeignKey(Empresa, ...)
    objects = EmpresaManager()         # filtrado por ContextVar
    global_objects = models.Manager()  # manager bypass (uso admin).");
```

## TenantMiddleware — las 5 validaciones

`inventory/middleware.py` corre en cada request (excepto rutas exentas 
`/admin/`, `/login/`, `/static/`, `/favicon.ico`, `/`). Verifica:

1. `user.is_authenticated` ↔ si no, 403.
2. `user.perfil` existe (`PerfilUsuario` con M2M `empresas_permitidas`) ↔ si no, 403.
3. `request.session['empresa_id']` presente ↔ si no, 403.
4. Empresa existe y `activa=True` ↔ si no, 403.
5. Empresa está en `perfil.empresas_permitidas` ↔ si no, 403.

Después setea el ContextVar. El `@login_required` actúa en paralelo 
(defense-in-depth) redirigiendo con 302 a `/login/` si el usuario no 
está autenticado.

## Regla sagrada del kardex

**El único origen válido para modificar `InventarioAlmacen.cantidad_disponible` 
es `services.registrar_movimiento()`.**

Toda otra vía es bug crítico. `registrar_movimiento()`:
1. Bloque pesimista del `InventarioAlmacen` (`select_for_update`).
2. Crea `MovimientoKardex` con `tipo=ENTRADA|SALIDA`, `concepto`, 
   `cantidad`, `saldo_resultante`.
3. Actualiza `cantidad_disponible` atómicamente con `F()` expression 
   (no en Python) para evitar race conditions.
4. Registra en `AuditoriaTasa` si la operación usa tasas.

Tests ADR-08 (TransactionTestCase) validan rollback real ante stock 
insuficiente o excepciones.

## Snapshots inmutables (ADR-18, ampliados ADR-24)

Cada transacción financiera graba el estado del mundo en ese 
instante. Estos campos son **inmutables** post-creación:

| Modelo | Campo snapshot | Set cuando |
|---|---|---|
| `NotaEntrega` | `tasa_bcv_aplicada`, `factor_cobertura_aplicado`, `tasa_mercado_aplicada` | Procesar venta (N1) |
| `DetalleNotaEntrega` | `precio_base`, `precio_ajustado`, `precio_directo_bcv`, `precio_ajustado_bcv`, `iva_porcentaje`, `descuento_aplicado` | Procesar venta (N1) |
| `DocumentoCompra` | `tasa_bcv_aplicada`, `tasa_mercado_aplicada`, `factor_cobertura_aplicado`, `fuente_tasa` | Registrar compra (C1) |
| `DetalleDocumentoCompra` | `costo_directo`, `costo_ajustado`, `costo_directo_bcv`, `costo_ajustado_bcv`, `iva_porcentaje`, `descuento_aplicado` | Registrar compra (C1) |
| `MovimientoKardex` | `cantidad`, `saldo_resultante`, `fecha_hora` (auto_now_add) | Cada movimiento |

Esto garantiza que los reportes históricos (Fase 4) sean 
determinísticos sin importar cambios posteriores en `ConfiguracionEmpresa`.

## Modelo de datos (29 clases en 1.1.0)

### Núcleo multi-tenant

- **Empresa** — raíz. Sin manager custom (es la entidad raíz).
- **ConfiguracionEmpresa** — OneToOne(Empresa). Tasas, márgenes, 
  API, cuarentena, cross-selling, offsets de impresión. En 1.1.0 añade 
  `prefijo_nota_entrega`, `correlativo_inicial_nota`, 
  `prefijo_nota_entrega`, `correlativo_inicial_compra`, 
  `ivas_disponibles` (lista JSON por defecto `[16, 8, 0]`).
- **PerfilUsuario** — OneToOne(User). M2M `empresas_permitidas`, 
  FK `empresa_activa`. Define a qué comercios accede el usuario.

### Inventario y catálogo

- **Almacen** — FK Empresa. `es_principal`, `activo`.
- **Articulo** — PK `sku` (CharField, ADR implícita: no migrar). 
  `tipo=FISICO|COMBO`, soft-delete `activo`. `iva_porcentaje` 
  (default 16), `descripcion`, `ficha_tecnica`, `social_quick`, 
  `social_cross` (TextField, literales con tokens `$[PRECIO_*]`).
- **InventarioAlmacen** — tabla intermedia (Articulo, Almacen). 
   `cantidad_disponible`, `stock_minimo`, `ubicacion_estante`. 
   **Regla sagrada**: solo se muta via `services.registrar_movimiento()`.
- **RecetaCombo** — define un `COMBO` con sus componentes físicos y 
  las cantidades requeridas. El stock del combo se calcula: 
  `min(floor(S(a_i)/q_i))` por componente en un almacén dado.
- **SerialArticulo** — trazabilidad por IMEI/serial único; estado 
  `DISPONIBLE|VENDIDO|ANULADO_COMPRA`.

### Contactos (ADR-05)

- **Contacto** — PK `identificacion` (CharField). `tipo=CLIENTE|PROVEEDOR`.
- **Cliente**, **Proveedor** — proxy models con managers filtrados.

### Transacciones de venta (Etapa N, 1.1.0)

- **NotaEntrega** — documento de venta. Número correlativo por 
  empresa (`unique_together` empresa+numero). Campo `numero_nota` 
  con formato `{prefijo}-{numero:08d}` (auto-generado). 
  `tipo_documento`=`NOTA_ENTREGA`|`FACTURA` (N2, **ADR-23**). 
  `numero_factura` (opcional para NE, obligatorio para FACTURA, 
  único por empresa). `iva_check` (auto si algún detalle tiene 
  `iva_porcentaje`>0), `iva_total`, `descuento_global` (0–100 %). 
  Estado `PROCESADO|ANULADO`.
- **DetalleNotaEntrega** — FK NotaEntrega. En 1.1.0 (ADR-24) contiene 
  **4 snapshots de precio**: `precio_base`, `precio_ajustado`, 
  `precio_directo_bcv`, `precio_ajustado_bcv` — inmutables post-creación. 
  Más `iva_porcentaje` y `descuento_aplicado` (individual por línea).

### Transacciones de compra (Etapa C, 1.1.0)

- **DocumentoCompra** — cabecera de compra a proveedor. 
 _correlativo automático por empresa via signal `create_tenant_defaults` 
  en `signals.py`. Snapshots de tasas (ADR-18). `tipo_documento` 
  (FACTURA/NOTA_ENTREGA/Otros) + `observaciones` textuales. 
  `reversar_documento_compra` marca estado `ANULADO` y produce 
  contramovimientos de kardex.
- **DetalleDocumentoCompra** — FK DocumentoCompra. En 1.1.0 (ADR-24) 
  añade **4 snapshots de costo**: `costo_directo`, `costo_ajustado`, 
  `costo_directo_bcv`, `costo_ajustado_bcv`, `iva_porcentaje`, 
  `descuento_aplicado`. Soporta `cantidad` fraccional (Decimal).

### Otros

- **MovimientoKardex** — registro inmutable de cada 
  ENTRADA/SALIDA. Referencia el `almacen` y el `articulo` afectados. 
   `concepto` es una lista cerrada (COMPRA, VENTA, AJUSTE_ENTRADA, 
   AJUSTE_SALIDA, TRANSFERENCIA_ENTRADA, TRANSFERENCIA_SALIDA, 
   DEVOLUCION, ANULACION_COMPRA, MERMA_DEFECTUOSO, REVERSO_*, etc.).
- **AuditoriaTasa** — historial de variación de tasas. Usado por 
  el dashboard para mostrar "última sincronización".

### Devoluciones (ticket #15)

- **NotaCredito** — cabecera. FK NotaEntrega original.
- **DetalleNotaCredito** — artículos reingresados con su costo.

### Multimoneda (Fase 3)

- **Moneda** — catálogo por tenant. `codigo` ISO 4217, `es_base` 
  (única true por empresa, enforced en `save()`).
- **TasaCambio** — histórico de tasas por par de monedas y fecha. 
  `obtener_tasa(origen, destino, empresa_id, fecha=None)` busca la 
  más reciente <= fecha.

## services.py — mapa de funciones

| Función | Línea | Descripción |
|---|---|---|
| `registrar_movimiento` | ~85 | Transacción atómica ENTRADA/SALIDA (Ticket #2). Única vía para mutar stock. |
| `calcular_stock_combo` | ~275 | Fórmula `min(floor(S(a_i)/q_i))` (Ticket #2). |
| `procesar_salida_combo` | ~320 | Desagregación atómica de componentes (Ticket #2). |
| `validar_formato_excel` | 378 | ADR-10: validar cabecera/extensión. |
| `procesar_carga_masiva` | 469 | ADR-11: carga atómica con resolución de colisiones. |
| `procesar_carga_masiva_excel` | 469 | ADR-13: wrapper que parsea Excel y delega al anterior. |
| `resolver_colision` | ~700 | Resuelve una colisión específica de carga (suma/sustituye). |
| `revertir_carga_masiva` | ~750 | Reverso de lote completo (genera contramovimientos). |
| `procesar_venta` | ~1158 | En 1.1.0 ampliado con `tipo_documento` (NE/FACTURA), `numero_factura` unique, `descuento_global` (0-100), `iva_porcentaje` por artículo y `iva_check` automático. 4 snapshots de precio por detalle (ADR-24). |
| `sincronizar_tasa_cambio` | ~1450 | Lee tasa de API externa (o simulada en Fase 5). |
| `reversar_nota_entrega` | ~2237 | Anula NE + genera contramovimientos del kardex. |
| `reversar_documento_compra` | ~2270 | Anula DocumentoCompra + contramovimientos + seriales. |
| `transferir_mercancia` | ~1520 | Movimientos de SALIDA y ENTRADA entre almacenes. |
| `ejecutar_ajuste_manual` | ~1560 | Ajuste +/- manual con concepto. |
| `registrar_compra_proveedor` | ~1720 | En 1.1.0 ampliado con 4 snapshots de costo + IVA + descuento + seriales + multi-tenant FKs validation. DetalleDocumentoCompra. |
| `exportar_datos_tenant` | 1802 | Snapshot JSON de tenant para respaldo lógico. |
| `procesar_devolucion_venta` | 1869 | Nota de crédito + reingreso (normal o cuarentena). |

(Las líneas pueden variar ligeramente tras commits; ver index 
en `services.py` header para el mapa actualizado).

## Migraciones (12 numeradas en 1.1.0)

| # | Nombre | Descripción |
|---|---|---|
| 0001 | `normalizar_config` | Schema inicial (Empresa, Articulo, InventarioAlmacen, MovimientoKardex, etc.) + `costo_unitario_snapshot` (ADR-18). |
| 0002 | `perfil_usuario_rbac` | PerfilUsuario + M2M empresas_permitidas. |
| 0003 | `modelo_documento_compra` | DocumentoCompra cabecera. |
| 0004 | `perfeccionar_reversos_trazables` | Trazabilidad de reversos (motivo, fecha). |
| 0005 | `configuracionempresa_cross_selling_footer_and_more` | Campos de cross-selling, offsets impresión. |
| 0006 | `inicializar_configuraciones_existentes` | Seed para empresas pre-existentes. |
| 0007 | `add_observaciones_to_documento_compra` | Observaciones text en DocumentoCompra. |
| 0008 | `make_factura_fields_optional` | `numero_factura` y `fecha_compra` nullable (cargas retroactivas). |
| 0009 | `documentocompra_factor_cobertura_aplicado_and_more` | **Fase 3**: snapshots de tasas en DocumentoCompra + Moneda + TasaCambio. |
| 0010 | `alter_notaentrega_unique_together_and_more` | **Etapa N1**: NotaEntrega/DetalleNotaEntrega con 4 precios snapshot, IVA, descuento; ConfiguracionEmpresa con prefijo/correlativo/ivas. |
| 0011 | `detallecompra_iva_porcentaje_descuento_and_more` | **Etapa C1**: DetalleDocumentoCompra extendido con 4 snapshots de costo + IVA + descuento. |
| 0012 | `documento_compra_serials_and_more` | **Etapa C2/C3**: serial Nikon trazabilidad + soporte PDFs. |

**Política:** Toda migración nueva sigue el patrón `00NN_descripcion`. 
El nombre corresponde a un ticket/ADR o fase.

## Tests (234 verdes en 1.1.0)

Codificados por **C-series** (criterio de validación):

| Cód | Etapa | Cobertura | Tests |
|---|---|---|---|
| C1 | A4 | Reverso idempotente de NotaEntrega | 1 |
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
| C20 | Etapa N1-N2 | Modelos + servicio Emisión NE/Factura (4 snapshots, IVA, descuento) | 17 |
| C21 | Etapa N3-N5 | Template ventas + interlock UI + vista detalle + PDF | 6 |
| C22 | Etapa C | Módulo Compras: vistas detalle/PDF + templates + multi-tenant + snapshots | 18 |
| C23 | Etapa FA | Fichas Artículos: 4 precios cuádruple + 4to token + toolbar + JS injectToken | 21 |

### Otras suites sin código C pero activas

- `TestMovimientosBasicos` — flujo ENTRADA/SALIDA básico.
- `TestRollbackAtomicidad` — ADR-08 rollback real.
- `TestVentaExitosa` — emisión nota + snapshots precios.
- `TestCoberturaCritica` — reversos notificados + correlativo por empresa.
- `TestProcesarVentaN2`, `TestNotaEntregaFaseN3`, `TestInterlockFacturaN4`, 
  `TestNotaEntregaFaseN5` — pipeline completo de emisión.
- `TestCatalogoPreciosCuadruple`, `TestCatalogoTemplateTokens`, 
  `TestArticulosToolbarTokens`, `TestArticulosToolbarRender` — Fichas.

## Componentes externos

| Nombre | Versión | Uso |
|---|---|---|
| Django | 6.0.6 | Framework web. |
| openpyxl | 3.1.5 | Carga masiva Excel. |
| reportlab | 5.0.0 | Export PDF de reportes (A4 landscape). |
| Pillow | 12.3.0 | Dep de reportlab. |
| requests | 2.34.2 | API de tasas (simulada en Fase 3). |
| Tailwind CSS | CDN | Estilos sin build JS. |
| FontAwesome | CDN | Iconos. |
| Chart.js | CDN | (aun no usado; reservado para Fase 4 dashboard grafos). |

## Patrones clave

- **Snapshot immutability** — ver ADR-18 (1.0.0) y ADR-24 (1.1.0) 
  para extensión 4-precios en DetalleNotaEntrega/DetalleDocumentoCompra.
- **Multi-tenant via ContextVar** — ver ADR-17.
- **Defense-in-depth en auth** — `TenantMiddleware` + `@login_required` 
  validan independientemente.
- **Filtro multi-tenant en vistas detalle/PDF** — 
  `get_object_or_404(Modelo, pk=id, empresa_id=session['empresa_id'])` 
  (regla 7 de PLAN.md, anti-leak C2).
- **Emisión NE/Factura unificada (ADR-23)** — un solo modelo 
  `NotaEntrega` con `tipo_documento` despacha ambos casos desde 
  `procesar_venta`. Evita modelo/tablas/vistas duplicadas.
- **Lazy import en models** — `Articulo.get_stock_disponible()` 
  importa `services` de forma lazy para evitar el ciclo 
  `models ↔ services`. ADR-21 cabe aquí.
- **EmpresaManager filtrado automaticamente** — el código de 
  negocio no repite `filter(empresa_id=...)` en ningún lado.
- **Vistas sin lógica de negocio** — `views.py` actúa como 
  adaptador HTTP → services, sin reglas propias.
- **Tokens de precio literales (ADR-25, 1.1.0)** — los tokens 
  `$[PRECIO_USD]`, `$[PRECIO_BCV]`, `$[PRECIO_BS_BASE]`, `$[PRECIO_BS]` 
  se guardan en BD como texto literal en `social_quick`/`social_cross`. 
  La sustitución ocurre en frontend (`catalogo.html`) al mostrar/copiar.
- **Toolbar caret tracking sin servidor (ADR-26, 1.1.0)** — la 
  toolbar de `articulos.html` inserta el token en la posición del 
  caret vía JS `injectToken()`. No hay llamada fetch al servidor; 
  el texto se persiste literal al guardar.
- **Correlativos automáticos via signal (1.1.0)** — al crear 
  una Empresa, `create_tenant_defaults` siembra ConfiguracionEmpresa 
  con defaults para NE/Compras; al guardar DocumentoCompra, 
  `Max('numero')+1` calcula el siguiente correlativo por empresa.

## Limitaciones aceptadas

- SQLite WAL — no partición ni shards (regla no negociable del 
  producto). Sirve hasta ~10 GB sin issues.
- No DecimalField🕔 en lookup — algunos queries en reportes 
  ordenados por DecimalField terminan como str.
- API BCV/Binance simulada — `sincronizar_tasa_cambio` usa seed 
  values; la integración real está en ROADMAP.md (Q4-2026).
- No módulo de Pagos — Fase 4 marca CxC/CxP como "todo PROCESADO 
  ≡ pendiente"; registrar pago/cierre quedaaxterizado en ROADMAP.
- `Articulo.sku` es CharField PK — no migrar a AutoField.
