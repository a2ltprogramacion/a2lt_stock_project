# Estructura de Directorios — A2LT Stock (Post-Ticket #20)

Mapa físico del repositorio reflejando la totalidad de la infraestructura construida hasta el Ticket #20 (Contrapartidas y Devoluciones).

---

## 1. Árbol Visual del Proyecto

```text
a2lt_stock_project/
│
├── manage.py                                         # Punto de entrada Django (runserver, migrate, test)
├── requirements.txt                                  # Dependencias: Django, openpyxl, requests
├── .gitignore                                        # Exclusión de .venv/, db.sqlite3, __pycache__/
│
├── a2lt_stock_project/                               # Configuración global del proyecto Django
│   ├── __init__.py
│   ├── settings.py                                   # SQLite, INSTALLED_APPS, MIDDLEWARE, templates
│   ├── urls.py                                       # Enrutador raíz → incluye inventory.urls
│   ├── wsgi.py                                       # Interfaz WSGI para servidores web
│   └── asgi.py                                       # Interfaz ASGI (compatibilidad futura)
│
├── inventory/                                        # Aplicación núcleo — motor de negocio SaaS
│   ├── __init__.py
│   ├── admin.py                                      # Registro de modelos y bloqueo de permisos de stock
│   ├── apps.py                                       # Config de la app (AppConfig)
│   ├── context_processors.py                         # Variables globales de contexto (empresa activa)
│   ├── forms.py                                      # Formularios Django (login, configuracion)
│   ├── managers.py                                   # EmpresaManager: aislamiento multi-tenant + contextvars
│   ├── middleware.py                                 # Inyección de empresa activa en request/DB
│   ├── models.py                                     # 18 modelos relacionales (Empresa → SerialArticulo)
│   ├── services.py                                   # Motor transaccional: Kárdex, F(), reversos, carga masiva
│   ├── signals.py                                    # post_save: crear PerfilUsuario al registrar User
│   ├── tests.py                                      # 58 tests unitarios de cobertura total
│   ├── urls.py                                       # 18 rutas: ventas, compras, reversos, APIs
│   ├── views.py                                      # Controladores: dashboard, POS, modales, exportación
│   │
│   ├── management/
│   │   └── commands/
│   │       └── ejecutar_backup_SaaS.py               # Comando Django: backup frío por tenant + telemetría
│   │
│   ├── migrations/                                   # Historial completo de migraciones (4 archivos)
│   │   ├── __init__.py
│   │   ├── 0001_normalizar_config.py
│   │   ├── 0002_perfil_usuario_rbac.py
│   │   ├── 0003_modelo_documento_compra.py
│   │   └── 0004_perfeccionar_reversos_trazables.py
│   │
│   ├── static/
│   │   └── inventory/
│   │       └── js/
│   │           └── admin_articulo.js                 # Widgets JS para el admin de artículos (combos, seriales)
│   │
│   └── templates/inventory/                          # Capa de presentación — 15 plantillas Slate-950
│       ├── base.html                                 # Layout raíz: sidebar, FOUC blocker, toggle tema
│       ├── login.html                                # Pantalla de autenticación de usuario
│       ├── dashboard.html                            # KPIs, valoración de inventario, alertas de stock
│       ├── catalogo.html                             # Catálogo de ventas con copia a clipboard y social selling
│       ├── ventas.html                               # Terminal POS: carrito, seriales, emisión de Nota de Entrega
│       ├── compras.html                              # Terminal simétrica de mostrador para ingresos por compra
│       ├── reversos.html                             # Interfaz de contrapartidas: anulación de ventas y compras
│       ├── contactos.html                            # Directorio unificado clientes/proveedores con pestañas
│       ├── articulos.html                            # CRUD de artículos, fichas técnicas, combos y recetas
│       ├── configuracion.html                        # Panel de tasas, márgenes, calibración de impresión
│       ├── carga.html                                # Zona drag & drop de importación masiva Excel
│       ├── movimientos.html                          # Kárdex analítico con filtros por almacén/tiempo
│       ├── nota_entrega_print.html                   # Formato de impresión física (blanco y negro, @media print)
│       └── impresion_coordenadas.html                # Impresión parametrizada por coordenadas libres (Ticket #12)
│
├── docs/                                             # Documentación técnica y planos de construcción
│   ├── BACKLOG.md                                    # Plan Maestro de Tickets (estado: hasta Ticket #20)
│   ├── arbol_directorios_a2lt.md                     # ← Este archivo: mapa topológico del repositorio
│   ├── especificacion_arquitectura_inventario.md      # SRS: fórmulas, reglas sagradas, ADRs
│   ├── maqueta_interactiva_de_interfaz.html           # Prototipo visual de la UI precargado
│   ├── reglas_desarrollo_agente.md                   # Convenciones y buenas prácticas para agentes AI
│   ├── tickets_desarrollo.md                         # Desglose narrativo de todos los tickets
│   └── revision_arquitectura.md.md                   # Auditoría arquitectónica cruzada
│
├── scratch/                                          # Sandbox de prototipado (no forma parte del sistema)
│   └── ...                                           # Fragmentos HTML/JS extraídos durante desarrollo
│
└── .venv/                                            # Entorno virtual Python (aislado, no versionado)
```

---

## 2. Índice de Responsabilidades por Archivo

### 2.1. Núcleo de la Aplicación (`inventory/`)

| Archivo | Responsabilidad |
|---|---|
| `models.py` | 18 modelos: `Empresa`, `ConfiguracionEmpresa`, `PerfilUsuario`, `Almacen`, `Articulo`, `InventarioAlmacen`, `RecetaCombo`, `Contacto`, `DocumentoCompra`, `MovimientoKardex` (Regla Sagrada), `AuditoriaTasa`, `NotaEntrega`, `DetalleNotaEntrega` (costo_unitario_snapshot ADR-18), `SerialArticulo`, `NotaCredito`, `DetalleNotaCredito` |
| `services.py` | Motor transaccional: `registrar_movimiento()` con F(), `procesar_venta()` (snapshots cambiarios + combos + seriales), `registrar_compra_proveedor()` (recálculo de precios), `reversar_nota_entrega()`, `reversar_documento_compra()`, `procesar_carga_masiva()` (tolerante a fallos), `resolver_colision()`, `revertir_carga_masiva()`, `sincronizar_tasa_cambio()`, `exportar_datos_tenant()` |
| `views.py` | 20+ controladores: dashboard, ventas (POS + creación API), compras, reversos, carga masiva, catálogo, contacto, movimientos, artículos, configuración, sincronización de tasas, exportación, login |
| `managers.py` | `EmpresaManager`: aislamiento multi-tenant vía `contextvars`, `get_current_empresa()`, `none()` en modo inseguro |
| `middleware.py` | `EmpresaMiddleware`: extrae `empresa_id` de sesión, lo inyecta en `contextvars` y `request.empresa` |
| `admin.py` | Panel Django admin con bloqueo de creación/edición/borrado en `InventarioAlmacen` y `MovimientoKardex` |
| `context_processors.py` | Expone `empresa_activa` y `configuracion_empresa` a todas las plantillas |
| `forms.py` | `LoginForm`, `ConfiguracionForm` con validación cruzada de tasas |
| `signals.py` | `post_save` de `User` → creación automática de `PerfilUsuario` |
| `tests.py` | 58 tests: Kárdex, combos, carga masiva, colisiones, reversos, ventas, seriales, exportación, tasas, multi-tenant |
| `urls.py` | 18 rutas: 4 vistas generales, 3 de compras, 4 de ventas, 2 de reversos, 2 de carga, tasas, respaldo |

### 2.2. Capa de Presentación (`templates/inventory/`)

| Plantilla | Responsabilidad |
|---|---|
| `base.html` | Layout raíz con sidebar Slate, bloqueador FOUC, toggle Light/Dark persistente, enlaces activos |
| `login.html` | Formulario de inicio de sesión con selector de empresa |
| `dashboard.html` | KPIs financieros, valoración de inventario, volumen de ventas, alertas de stock mínimo y rupturas |
| `catalogo.html` | Catálogo de artículos con fichas técnicas, copia a clipboard para WhatsApp/Instagram |
| `ventas.html` | POS: carrito de compras, buscador de artículos, selección FIFO de seriales, calculadora cambiaria |
| `compras.html` | Terminal de ingresos: carga de factura, items con costo, inyección de seriales, procesamiento asíncrono |
| `reversos.html` | Contrapartidas: tabs Ventas/Compras, badges de estado, modal de motivo, Fetch API con repintado asíncrono |
| `contactos.html` | Directorio con pestañas Clientes/Proveedores, modal de registro con campos condicionales |
| `articulos.html` | CRUD de artículos: edición de fichas, configuración de combos y recetas |
| `configuracion.html` | Panel de tasas BCV/Mercado, márgenes, calibración de coordenadas de impresión, historial de auditoría |
| `carga.html` | Zona drag & drop Excel, modal de colisión con botones Sumar/Sustituir/Cancelar |
| `movimientos.html` | Kárdex analítico con filtros por almacén, SKU, tipo y rango de fechas |
| `nota_entrega_print.html` | Formato de impresión física @media print en B/N con estilo ticket |
| `impresion_coordenadas.html` | Impresión parametrizable con posicionamiento absoluto por coordenadas (mm) |

### 2.3. Infraestructura de Soporte

| Archivo | Ruta | Responsabilidad |
|---|---|---|
| `manage.py` | Raíz | CLI de Django para migraciones, tests, servidor de desarrollo |
| `settings.py` | `a2lt_stock_project/` | Config global: SQLite, apps instaladas, middleware, static/template dirs |
| `urls.py` (proyecto) | `a2lt_stock_project/` | Incluye `inventory.urls` con prefijo raíz |
| `ejecutar_backup_SaaS.py` | `management/commands/` | Comando personalizado: backup frío con `VACUUM INTO`, telemetría de disco |
| `admin_articulo.js` | `static/inventory/js/` | Mejora UI del admin Django para recetas de combo y seriales |

---

## 3. Estructura de Migraciones

```text
migrations/
├── __init__.py
├── 0001_normalizar_config.py            # Modelos iniciales + singleton ConfiguracionEmpresa
├── 0002_perfil_usuario_rbac.py          # PerfilUsuario + control de acceso RBAC
├── 0003_modelo_documento_compra.py      # DocumentoCompra + campos de anulación en NotaEntrega
└── 0004_perfeccionar_reversos_trazables.py  # SerialArticulo.compra_origen, NotaCredito, DetalleNotaCredito
```

---

## 4. Convenciones del Repositorio

- **Prohibido** modificar `cantidad_disponible` de `InventarioAlmacen` fuera de `services.py` (Regla Sagrada).
- **Prohibido** usar placeholders o `pass` en servicios críticos; toda función debe ser plug & play.
- **Tema visual**: Slate-950/900 fondos, Slate-100 textos, acentos índigo (acciones) y esmeralda (confirmaciones).
- **Tests**: `python manage.py test inventory.tests` — deben mantenerse en 58/58 verdes.

---

> Con este mapa, cualquier agente de software puede leer la carpeta `docs/`, comprender la totalidad de la arquitectura e implementar código sin vacíos ni alucinaciones.
