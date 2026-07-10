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

## Snapshots inmutables (ADR-18)

Cada transacción financiera graba el estado del mundo en ese 
instante. Estos campos son **inmutables** post-creación:

| Modelo | Campo snapshot | Set cuando |
|---|---|---|
| `NotaEntrega` | `tasa_bcv_aplicada`, `factor_cobertura_aplicado` | Procesar venta |
| `DetalleNotaEntrega` | `precio_unitario_usd`, `precio_unitario_bs`, `costo_unitario_snapshot` | Procesar venta |
| `DocumentoCompra` | `tasa_bcv_aplicada`, `tasa_mercado_aplicada`, `factor_cobertura_aplicado`, `fuente_tasa`, `monto_total_bs_snapshot` | Registrar compra |
| `MovimientoKardex` | `cantidad`, `saldo_resultante`, `fecha_hora` (auto_now_add) | Cada movimiento |

Esto garantiza que los reportes históricos (Fase 4) sean 
determinísticos sin importar cambios posteriores en `ConfiguracionEmpresa`.

## Modelo de datos (23 clases)

### Núcleo multi-tenant

- **Empresa** — raíz. Sin manager custom (es la entidad raíz).
- **ConfiguracionEmpresa** — OneToOne(Empresa). Tasas, márgenes, 
  API, cuarentena, cross-selling, offsets de impresión.
- **PerfilUsuario** — OneToOne(User). M2M `empresas_permitidas`, 
  FK `empresa_activa`. Define a qué comercios accede el usuario.

### Inventario y catálogo

- **Almacen** — FK Empresa. `es_principal`, `activo`.
- **Articulo** — PK `sku` (CharField, ADR implícita: no migrar). 
  `tipo=FISICO|COMBO`, soft-delete `activo`. 
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

### Transacciones

- **NotaEntrega** — documento de venta. Número correlativo por 
  empresa (`unique_together`). Estado `PROCESADO|ANULADO`.
- **DetalleNotaEntrega** — FK NotaEntrega. Contiene los snapshots 
  de precio/costo (ADR-18).
- **DocumentoCompra** — cabecera de compra a proveedor. 
  Snapshots de tasas (ADR-18).
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
| `procesar_venta` | 1119 | Emite NotaEntrega + descuenta kardex + graba snapshots. |
| `sincronizar_tasa_cambio` | ~1300 | Lee tasa de API externa (o simulada en Fase 5). |
| `reversar_nota_entrega` | ~1400 | Anula NE + genera contramovimientos del kardex. |
| `reversar_documento_compra` | ~1450 | Anula Compra + contramovimientos + seriales. |
| `transferir_mercancia` | ~1520 | Movimientos de SALIDA y ENTRADA entre almacenes. |
| `ejecutar_ajuste_manual` | ~1560 | Ajuste +/- manual con concepto. |
| `registrar_compra_proveedor` | 1623 | Compra con validación multi-tenant de FKs (A10). |
| `exportar_datos_tenant` | 1802 | Snapshot JSON de tenant para respaldo lógico. |
| `procesar_devolucion_venta` | 1869 | Nota de crédito + reingreso (normal o cuarentena). |

(Las líneas pueden variar ligeramente tras commits; ver index 
en `services.py` header para el mapa actualizado).

## Migraciones (9 numeradas)

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

**Política:** Toda migración nueva sigue el patrón `00NN_descripcion`. 
El nombre corresponde a un ticket/ADR o fase.

## Tests (157 verdes)

Codificados por **C-series** (criterio de validación):

| Cód | Etapa | Cobertura | Tests |e |
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

### Otras suites sin código C pero activas

- `TestMovimientosBasicos` — flujo ENTRADA/SALIDA básico.
- `TestRollbackAtomicidad` — ADR-08 rollback real.
- `TestVentaExitosa` — emisión nota + snapshots precios.
- `TestCoberturaCritica` — reversos notificados + correlativo por empresa.

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

- **Snapshot immutability** — ver ADR-18.
- **Multi-tenant via ContextVar** — ver ADR-17.
- **Defense-in-depth en auth** — `TenantMiddleware` + `@login_required` 
  validan independientemente.
- **Lazy import en models** — `Articulo.get_stock_disponible()` 
  importa `services` de forma lazy para evitar el ciclo 
  `models ↔ services`. ADR-21 cabe aquí.
- **EmpresaManager filtrado automaticamente** — el código de 
  negocio no repite `filter(empresa_id=...)` en ningún lado.
- **Vistas sin lógica de negocio** — `views.py` actúa como 
  adaptador HTTP → services, sin reglas propias.

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
