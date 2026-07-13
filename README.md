# A2LT Stock

Sistema on-premise de control de inventario y punto de venta multi-tenant, 
dirigido al mercado venezolano de telecom/electrónica. Inspirado en el 
flujo operativo de Profit Plus 2K, modernizado con Django 6 y Tailwind CSS.

**Para Venezuela** — soporta BCV + tasa mercado + factor de cobertura 
cambiaria, con snapshots inmutables de tasas en cada transacción.

---

## Características principales

- **Multi-tenant seguro** — cada comercio (empresa) tiene sus propios 
  datos, filtrados via ContextVar (no por schema ni tenant_id manual).
- **Multi-moneda** — USD, VES y futuras. Cada compra/venta graba el 
  snapshot de la tasa aplicada para auditoría histírica.
- **Kardex inmutable** — toda modifica de stock pasa por 
  `services.registrar_movimiento()`; el costo_unitario_snapshot de cada 
  detalle de venta es inalterable.
- **Emisión de Notas de Entrega / Facturas** (1.1.0) — el servicio 
  `procesar_venta` soporta `tipo_documento` (`NOTA_ENTREGA` | `FACTURA`), 
  `numero_factura` único por empresa, `descuento_global` configurable, 
  `iva_porcentaje` **por línea** (1.1.1: cada ítem puede llevar su 
  propio 16 / 8 / 0 %) e `iva_check` automático. Cada 
  `DetalleNotaEntrega` guarda **4 snapshots de precio** (`precio_base`, 
  `precio_ajustado`, `precio_directo_bcv`, `precio_ajustado_bcv`) + 
  `iva_porcentaje` + `descuento_aplicado`. PDF A4 portrait con 
  reportlab. Vista detalle `/ventas/<id>/` + PDF descargable 
  `/ventas/<id>/pdf/`.
- **Módulo de Compras a proveedores** (1.1.0/1.1.1) — 
  `DocumentoCompra` con **3 tipos de documento** (1.1.1: 
  `FACTURA_COMPRA`, `NOTA_ENTREGA_PROVEEDOR`, `REGISTRO_MENOR`) y 
  correlativo automático por empresa vía signal + 
  `DetalleDocumentoCompra` con **4 snapshots de costo** + `iva_porcentaje` 
  **por línea** + `descuento_aplicado` + seriales. 
  `registrar_compra_proveedor` valida FKs multi-tenant; 
  `reversar_documento_compra` genera contramovimiento auditado. PDF + 
  vista detalle `/compras/<id>/` + `/compras/<id>/pdf/`.
- **Fichas de Artículos con tokens de precio** (1.1.0) — 4 variables 
  dinámicas para redactar mensajes de mercadeo en `social_quick` y 
  `social_cross` sin reescribir al cambiar precios/tasas: 
  `$[PRECIO_USD]`, `$[PRECIO_BCV]`, `$[PRECIO_BS_BASE]` (Bs. sin 
  factor, nuevo), `$[PRECIO_BS]` (Bs. con factor). Sustitución 
  automática al copiar texto en catálogo. Toolbar con 4 botones en 
  el formulario de artículos para insertar tokens en la posición del 
  cursor (JS `injectToken()`, sin llamada al servidor).
- **8 reportes operativos** — Kardex Valorizado, Inventario Valorizado, 
  Ventas por Período, Cuentas por Cobrar (CxC), Cuentas por Pagar (CxP), 
  Top Artículos Vendidos, Artículos Sin Movimiento (obsoletos), y 
  Estado de Resultados simple. Exportables a CSV (BOM utf-8 para Excel) 
  y PDF (A4 landscape con reportlab).
- **Dashboard con KPIs live** — valoración USD/VES del inventario, 
  volumen de ventas del mes, conteo de notas, alertas de reposición, 
  disponibilidad de combos virtuales calculada en tiempo real, ǧltima 
  sincronización de tasa persistida.
- **Backup atómico** — `manage.py backup_db` genera un snapshot 
  consistente via SQLite `VACUUM INTO` sin bloquear escrituras, con 
  opción de retención automática.
- **Combos virtuales** — stock calculado dinamicamente como 
  `min(floor(S(a_i)/q_i))` sobre los componentes físicos.
- **Reversos auditados** — anular NotaEntrega o DocumentoCompra 
  genera contramovimientos de kardex con motivo persistido.

## Stack

- **Backend:** Django 6.0.6 (Python 3.11+), SQLite WAL — sin PostgreSQL, 
  sin Celery, sin DRF (reglas del producto).
- **Frontend:** Tailwind CSS (CDN), Chart.js, FontAwesome. Sin build JS.
- **PDF:** reportlab 5.0.
- **Excel:** openpyxl 3.1.
- **Tests:** Django TestCase/TransactionTestCase — 247 tests verdes 
  en **~160s** (157 en 1.0.0 + 77 en 1.1.0 + 13 en 1.1.1).

## Instalación rápida

```bash
git clone <repo-url> a2lt_stock_project
cd a2lt_stock_project
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt

# Crear .env con SECRET_KEY y DEBUG
echo "SECRET_KEY=desarrollo-inseguro-cambiar-en-prod" > .env
echo "DEBUG=True" >> .env

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abrir http://127.0.0.1:8000

## Documentación

- `docs/AUDITORIA_INICIAL.md` — hallazgos previos a la Fase A.
- `docs/PLAN.md` — plan de estabilización completo (Etapas A, B, 
  Fases 3-6 **+ Etapas N (Emisión NE/Factura), C (Compras), 
  FA (Fichas Artículos)** y reglas de calidad) + matriz de tests 
  C1-C23 (234 verdes).
- `docs/ARQUITECTURA.md` — diagrama de capas, multi-tenant 
  ContextVar, regla sagrada del kardex, **snapshots inmutables 
  extendidos a 4 precios por detalle (ADR-24)**, mapa de 
  `services.py`, 12 migraciones numeradas, 29 modelos y tests C1-C23.
- `docs/ADR.md` — **20 Decisiones de Arquitectura** formales 
  (ADR-01 a ADR-26 con saltos; ADR-23 a ADR-26 añaden Emisión 
  NE/Factura, snapshots 4-precios, tokens de precio y toolbar 
  caret tracking).
- `docs/BACKLOG.md` — 30+ tickets de desarrollo con estado 
  (incluye tickets #14-#17 iteración 1.1.0).
- `docs/ROADMAP.md` — features post-100% (cuentas por cobrar/pagar, 
  factura electrónica Seniat, bitácora de auditoría).
- `docs/OPERACION.md` — guía de instalación detallada, módulos, 
  **tokens de variables de precio**, troubleshooting y reglas 
  operativas.
- `CHANGELOG.md` — registro de cambios por release (Keep a 
  Changelog). **1.1.0 (2026-07-13) cubre Emisión NE/Factura, 
  Compras Avanzadas, Fichas de Artículos y auditoría.**

## Producción

Para producción on-premise se recomienda:

1. Crear `.env` con `DEBUG=False` y `SECRET_KEY` aleatoria de 64+ chars.
2. Programar backup nocturno via Programador de Tareas (Windows) o 
   cron (Linux):
   ```bash
   0 2 * * * cd /opt/a2lt_stock && .venv/bin/python manage.py backup_db --retention 7
   ```
3. Servir con Gunicorn (Linux) o WhiteNoise + IIS (Windows). Ver 
   `docs/OPERACION.md` para detalles.

## Tests

```bash
python manage.py test inventory                  # suite completa (~2min)
python manage.py test inventory.tests.TestDashboardLiveData -v 2    # rápidos
```

## Reglas sagradas

1. **Stock**: solo se modifica via `services.registrar_movimiento()`. 
   Nunca UPDATE directo a `InventarioAlmacen.cantidad_disponible`.
2. **Tenant**: usar `get_current_empresa()` (ContextVar), nunca 
   `Empresa.objects.first()` ni `request.empresa`.
3. **Snapshots**: los campos `tasa_bcv_aplicada`, 
   `factor_cobertura_aplicado`, `tasa_mercado_aplicada` (1.1.0) y 
   **los 4 snapshots de precio/costo** (`precio_base`, 
   `precio_ajustado`, `precio_directo_bcv`, `precio_ajustado_bcv` — 
   o `_costo_` en compras) grabados en cada compra/venta son 
   inmutables post-factura (ADR-18 + ADR-24).
4. **@login_required**: defense-in-depth junto a `TenantMiddleware` 
   que valida 5 condiciones (autenticación, perfil, empresa_id en 
   sesión, empresa activa, empresa permitida para el usuario).
5. **Vistas detalle/PDF** (1.1.0, regla C2 — anti-leak multi-tenant): 
   `vista_detalle_nota`, `generar_pdf_nota`, `vista_detalle_compra`, 
   `generar_pdf_compra` deben hacer 
   `get_object_or_404(Modelo, pk=id, empresa_id=session['empresa_id'])` 
   — nunca simple `get_object_or_404(Modelo, pk=id)`.
6. **Tokens de precio** (1.1.0, ADR-25): los tokens `$[PRECIO_USD]`, 
   `$[PRECIO_BCV]`, `$[PRECIO_BS_BASE]`, `$[PRECIO_BS]` se persisten 
   como texto literal en `social_quick`/`social_cross`. La 
   sustitución ocurre solo en frontend (`catalogo.html`). La toolbar 
   de `articulos.html` NO envía datos al servidor: `injectToken()` 
   edita el texto localmente y `saveProduct()` persiste el token 
   literal al guardar.

## Licencia

Propietaria. © 2026 A2LT Soluciones (Ing. Angel Argenis León Torres).
