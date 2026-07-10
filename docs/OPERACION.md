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
| `/catalogo/` | Catálogo | Lista de artículos activos con precios en USD/Bs ajustados por factor de cobertura. |
| `/ventas/` | Notas de Entrega | Punto de venta. Emite NE correlativa única por empresa. |
| `/compras/` | Compras | Registro de compra a proveedor con snapshot de tasa. |
| `/reversos/` | Reversos | Listado de notas y compras; opción de anular con motivo. |
| `/articulos/` | Fichas | CRUD de artículos (FISICO/COMBO). |
| `/carga/` | Carga Masiva | Upload de Excel para inventario inicial o ajustes. |
| `/movimientos/` | Kardex Integrado | Listado de movimientos + registro manual de ajustes. |
| `/contactos/` | Clientes y Proveedores | CRUD unificado. |
| `/configuracion/` | Configuración | Tasa BCV, tasa mercado, factor cobertura, márgenes, API, cuarentena, cross-selling. |
| `/reportes/` | Reportes | Índice de 8 reportes con export CSV/PDF. |

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

La suite de 157 tests toma ~120s. Es esperable en SQLite WAL con 
migraciones completas cada vez. Para tests rápidos de un módulo:
```bash
python manage.py test inventory.tests.TestDashboardLiveData -v 2
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
   python manage.py test inventory  # ~2min
   ```
