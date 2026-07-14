# Guía de Operación — A2LT Stock

**Versión:** 1.0 (julio 2026)  
**Para:** Operadores/comercios que instalarán el sistema on-premise.

## Instalación

### Requisitos

- Windows 10/11 64-bit (test primary) o Linux x86_64.
- Python 3.11+ (probado en 3.14).
- 512 MB RAM mínimo (1 GB recomendado).
- 100 MB disco para sistema + 50 MB/mes para BD típica.

### Paso a paso (desarrollo)

1. Clonar el repositorio:
   ```bash
   git clone <repo-url> a2lt_stock_project
   cd a2lt_stock_project
   ```

2. Crear y activar entorno virtual:
   ```bash
   python -m venv .venv
   .\.venv\Scripts\activate     # Windows
   source .venv/bin/activate    # Linux/macOS
   ```

3. Instalar dependencias:
   ```bash
   pip install -r requirements.txt
   ```

4. Crear `.env` (ver abajo) o copiar `.env.example` si existe:
   ```env
   SECRET_KEY=cambar-esto-por-una-clave-aleatoria-de-64-chars
   DEBUG=True
   ALLOWED_HOSTS=localhost,127.0.0.1
   ```

5. Migraciones + semilla:
   ```bash
   python manage.py migrate
   python manage.py seed_db
   ```

6. Crear superusuario:
   ```bash
   python manage.py createsuperuser
   ```

7. (Opcional) Semilla de datos de prueba:
   ```bash
   python manage.py seed_db --clear
   # Crea 2 empresas con compradores, articulos y movimientos.
   ```

8. Levantar servidor:
   ```bash
   python manage.py runserver
   ```

9. Abrir http://127.0.0.1:8000 — login con el superusuario creado.

### Para producción on-premise

- Nunca usar `manage.py runserver` en producción. Usar Gunicorn 
  (Linux) o WhiteNoise + IIS/Wfastcgi (Windows).
- En `.env`: `DEBUG=False`, `SECRET_KEY` aleatoria de 64+ chars, 
  `ALLOWED_HOSTS=dominio.com,IP_exacta`.
- Programar backup nocturno vía Programador de Tareas (Windows) o 
  cron (Linux):
  ```bash
  # diario a las 02:00, retiene 7 dias
  0 2 * * * cd /opt/a2lt_stock && .venv/bin/python manage.py backup_db --retention 7
  ```
  En Windows Programador de Tareas → ejecutar:
  `Y:\ruta\a2lt_stock\.venv\Scripts\python.exe manage.py backup_db --retention 7`

## Uso

### Login + cambio de empresa

- El usuario pertenece a una o más empresas (`PerfilUsuario.empresas_permitidas`).
- Al entrar, se carga la `empresa_activa` del perfil.
- Para cambiar: clic en selector de empresa del header → submit del 
  formulario `/cambiar-empresa/`.

### Módulos disponibles

| URL | Módulo | Descripción |
|-----|--------|-------------|
| `/dashboard/` | Dashboard | KPIs live: valoración USD/VES, alertas de reposición, combos, notas del mes, última sincronización de tasa. |
| `/catalogo/` | Catálogo | Lista de artículos activos con **4 precios calculados** (USD base, USD ajustado, Bs. base, Bs. ajustado). Botones para copiar `social_quick`, `social_cross` y `ficha_tecnica` con sustitución automática de tokens. |
| `/ventas/` | Notas de Entrega / Facturas (1.1.0) | Punto de venta. Emite `NOTA_ENTREGA` o `FACTURA` (con `numero_factura` único por empresa). Soporta `descuento_global` (0-100 %) e `iva_porcentaje` por artículo. PDF descargable. |
| `/ventas/<id>/` | Detalle NE/Factura (1.1.0) | Vista detallada de nota con desglose de 4 precios por líneas, IVA y descuento. |
| `/ventas/<id>/pdf/` | PDF NE/Factura (1.1.0) | Descarga PDF A4 portrait con reportlab. |
| `/compras/` | Compras a Proveedor (1.1.0/1.1.1) | Registro de compra con **3 tipos de documento** (Factura obligatoria, Nota Entrega/Recibo opcional, Registro Menor sin doc), **IVA individual por línea** (1.1.1), 4 snapshots de costo + descuento + seriales por artículo. |
| `/compras/<id>/` | Detalle Compra (1.1.0) | Vista detallada con desglose de 4 costos por líneas. |
| `/compras/<id>/pdf/` | PDF Compra (1.1.0) | Descarga PDF A4 portrait. |
| `/reversos/` | Reversos | Listado de notas y compras; opción de anular con motivo. |
| `/notas-credito/` | Notas de Crédito (1.2.0 TICKET #18-NC) | **Módulo nuevo.** Pantalla única con 2 pestañas (Historial de NCs + Emitir Nueva NC). Devoluciones parciales o totales sobre ventas (`NotaEntrega`) o compras (`DocumentoCompra`) con kardex `DEVOLUCION_VENTA` (ENTRADA) o `DEVOLUCION_COMPRA` (SALIDA) y liberación FIFO de seriales. Diseño 1-NC-1-origen (ADR-29). |
| `/notas-credito/<id>/` | Detalle NC (1.2.0) | Vista de la NC con motivo, doc. origen, líneas con IVA y total a reembolsar. |
| `/notas-credito/<id>/pdf/` | PDF NC (1.2.0) | Descarga PDF A4 portrait con reportlab (encabezado, motivo, líneas). |
| `/articulos/` | Fichas (1.1.0) | CRUD de artículos. **Toolbar con 4 botones** sobre `social_quick` y `social_cross` para insertar tokens de precio en la posición del cursor. |
| `/carga/` | Carga Masiva | Upload de Excel para inventario inicial o ajustes. |
| `/movimientos/` | Kardex Integrado | Listado de movimientos + registro manual de ajustes. |
| `/contactos/` | Clientes y Proveedores | CRUD unificado. |
| `/configuracion/` | Configuración | Tasa BCV, tasa mercado, factor cobertura, márgenes, API, cuarentena, cross-selling, **ivas disponibles**, **prefijos y correlativos iniciales** para NE/Compras. |
| `/reportes/` | Reportes | Índice de 8 reportes con export CSV/PDF. |

### Tokens de variables de precio (1.1.0)

Para redactar mensajes de mercadeo (WhatsApp, Instagram, Facebook) sin 
reescribir cada vez que cambia el precio o la tasa cambiaria, los 
textos `social_quick` (Respuesta Rápida Redes) y `social_cross` 
(Mensaje de Cross-Selling) en **Fichas de Artículos** admiten 4 
tokens que se sustituyen automáticamente al copiar el texto en el 
catálogo:

| Token | Significado | Fórmula (con `precio_divisa=10`, `factor=1.5`, `tasa_bcv=40`) |
|---|---|---|
| `$[PRECIO_USD]` | Precio en divisas (USD base) | `10.00` |
| `$[PRECIO_BCV]` | USD ajustado (con factor de cobertura) | `15.00` |
| `$[PRECIO_BS_BASE]` | Bs. base (sin factor) | `400.00` |
| `$[PRECIO_BS]` | Bs. ajustado (con factor) | `600.00` |

**Compatibilidad legacy:** se aceptan también los formatos antiguos 
`[Precio_USD]`, `[Precio_BCV]`, `[Precio_BS_BASE]`, `[Precio_Bs]`.

**Forma de uso:**
1. En **Fichas de Artículos** → editar artículo.
2. Sobre los textareas `Mensaje de Cross-Selling` y 
   `Respuesta Rápida Completa` aparece una toolbar con 4 botones 
   (USD, BCV, Bs.Base, Bs.Ajust.).
3. Click en el botón inserta el token en la posición del cursor. 
   Si hay texto seleccionado, se reemplaza; si no, se inserta en el 
   caret. El foco se mantiene en el textarea.
4. Guardar el artículo. El token se persiste como literal — el 
   mensaje se ve igual en la BD.
5. En **Catálogo**, los botones de copia sustituyen el token por el 
   valor actual calculado con `tasa_bcv` y `factor_cobertura` del 
   `ConfiguracionEmpresa` vigente. Cada modificación de tasas o 
   precios se refleja al copiar sin editar el mensaje.

**ADR-25** (Tokens de precio literales) y **ADR-26** (Toolbar caret 
tracking sin servidor) formalizan el diseño.

### Reportes (Fase 4)

| Reporte | URL | Filtros soportados |
|---------|-----|--------------------|
| Kardex valorizado | `/reportes/kardex/` | Artículo, almacén, rango fechas |
| Inventario valorizado | `/reportes/inventario/` | Almacén |
| Ventas por período | `/reportes/ventas/` | Rango fechas |
| Cuentas por cobrar | `/reportes/cxc/` | — |
| Cuentas por pagar | `/reportes/cxp/` | — |
| Top artículos vendidos | `/reportes/top_vendidos/` | Rango fechas, top N |
| Artículos obsoletos | `/reportes/obsoletos/` | Días sin movimiento |
| Estado de resultados | `/reportes/estado_resultados/` | Rango fechas |

Cada reporte soporta `?format=csv` (Excel-ready con BOM utf-8) y 
`?format=pdf` (A4 landscape con tabular).

### Backup

```bash
# Backup inmediato
python manage.py backup_db

# Backup en directorio custom
python manage.py backup_db --dir D:\backups\a2lt

# Backup con retención 7 días (borra backups > 7 días)
python manage.py backup_db --retention 7

# Dry-run (valida sin generar)
python manage.py backup_db --check

# Nombre custom
python manage.py backup_db --name cierre_mensual_202607
```

El backup usa `VACUUM INTO` de SQLite que genera un snapshot atómico 
consistente sin bloquear escrituras. El archivo generado es un SQLite 
válido e independiente (se puede abrir con cualquier cliente SQLite, 
incluso DB Browser for SQLite).

## Troubleshooting

### "Acceso Denegado: requiere sesión de usuario"

El middleware cortó porque no hay login. Cerrar sesión y volver a 
entrar en /login/.

### "Acceso Denegado: no se encontro empresa asociada en la sesión"

La sesión perdió `empresa_id`. Usualmente por timeout o cierre manual. 
Logout + login de nuevo (se re-asigna empresa automáticamente).

### "Cannot VACUUM from within a transaction"

Si aparece al correr `backup_db` manualmente fuera del command 
(por ejemplo, en shell raw Django): usar `connection.set_autocommit(True)` 
antes del `VACUUM INTO`, o invocar solo vía `manage.py backup_db` 
que ya gestiona esto.

### Tests lentos en Windows

La suite de **276 tests toma ~190s** (1.2.0: 247 previos + 15 backend
NC + 14 UI NC). Es esperable en SQLite WAL con migraciones completas
cada vez. Para tests rápidos de un módulo:
```bash
python manage.py test inventory.tests.TestDashboardLiveData -v 2
python manage.py test inventory.tests.TestArticulosToolbarTokens -v 2  # Fichas (rápidos)
python manage.py test inventory.tests.TestIvaIndividualPorLinea -v 2   # 1.1.1 IVA por línea (rápido)
python manage.py test inventory.tests.TestNotasCreditoUI -v 2         # 1.2.0 UI Notas de Crédito
python manage.py test inventory.tests.TestNotasCreditoBackend -v 2    # 1.2.0 backend Notas de Crédito
```

### BD corrupta / backup inválido

Restaurar desde el último `backups/db_backup_*.sqlite3` (copiarlo a 
`db.sqlite3`). El backup es una BD sqlite válida, sólo reemplazar.

### Cómo reinicializar todo (pérdida de datos)

```bash
del db.sqlite3
del backups\*.sqlite3
python manage.py migrate
python manage.py seed_db --clear
python manage.py createsuperuser
```

⚠ Esto borra TODOS los datos del sistema.

## Logs

- Aplicación: `logs/a2lt_stock.log` (rotación 5MB, 5 backups).
- Backups: `backups/` (excluido de git).

## Reglas operativas

1. **NUNCA editar** `InventarioAlmacen.cantidad_disponible` directamente 
   (SQL o admin). Toda alteración via `services.registrar_movimiento()`.
2. **NUNCA anular** NotaEntrega o DocumentoCompra con UPDATE SQL. 
   Usar los botones de anulación en `/reversos/` (invoca 
   `reversar_nota_entrega` o `reversar_documento_compra` que generan 
   los contramovimientos de kardex).
3. **Antes de cualquier cambio en producción**, correr:
   ```bash
   python manage.py backup_db
   python manage.py test inventory  # ~2.5min (234 tests)
   ```
4. **Vistas detalle y PDF de documentos** (NE, Factura, Compra) 
   DEBEN filtrar por `empresa_id=request.session.get('empresa_id')` 
   en el `get_object_or_404()`. Esto evita leak multi-tenant 
   (hallazgo C2 de la auditoría 1.1.0). Si se añade una nueva vista 
   de detalle, respetar este patrón.
5. **Tokens de precio** (`$[PRECIO_USD]`, `$[PRECIO_BCV]`, 
   `$[PRECIO_BS_BASE]`, `$[PRECIO_BS]`) son literales en BD. Al 
   actualizar precios o tasas vía `/configuracion/`, los mensajes 
   ya redactados en `social_quick`/`social_cross` se actualizan 
   automáticamente al copiar en `/catalogo/`. No requieren 
   reescritura.
6. **FACTURA** requiere `numero_factura` único por empresa (ADR-23). 
   La UI deshabilita el botón "Confirmar Venta" si el tipo FACTURA 
   está seleccionado pero el campo está vacío (interlock N4).
7. **Tipos de documento de Compra** (1.1.1 O1): 3 opciones en el 
   radio: Factura (obligatorio #factura), Nota Entrega / Recibo 
   (opcional el #documento), Registro Menor (sin documento físico). 
   Las viejas `NOTA_CREDITO_COMPRA` y `ORDEN_COMPRA` fueron 
   removidas — Notas de Crédito se reservan para TICKET #18 
   (módulo aparte `/notas-credito/`).
8. **IVA individual por línea** (1.1.1 O2): cada ítem en 
   `/ventas/` y `/compras/` puede tener su propio `iva_porcentaje` 
   (default 16 desde `Articulo.iva_porcentaje`; override desde 
   `<select>` de la grilla). Rango `[0, 100]`. `iva_total` del 
   documento se recalcula sumando IVAs individuales.
