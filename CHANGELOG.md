# Changelog — A2LT Stock

Todos los cambios notables del proyecto se documentan en este archivo.

El formato está basado en [Keep a Changelog](https://keepachangelog.com/es-1.1.0/)
y este proyecto se adhiere a [SemVer](https://semver.org/lang/es/) una 
vez público.

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
