# Guía de Pruebas Físicas Manuales — A2LT Stock

Auditoría: pruebas exhaustivas de cada módulo interactuando con la interfaz gráfica (navegador / Django server). Cada paso: navegación → datos → botón/submit → resultado visual esperado → verificación BD/state.

Ambiente: `python manage.py runserver` (`http://127.0.0.1:8000/`)
Superusuario existente: `angeldrk`
Referencia interfaz: `docs/maqueta_interactiva_de_interfaz.html`
Referencia seguridad: `docs/auditoria_2026-08.md`
Referencia servicios: `inventory/services.py` (Regla Sagrada)
Referencia modelos: `inventory/models.py`
Referencia middleware: `inventory/middleware.py` (`TenantMiddleware`)
Referencia managers: `inventory/managers.py` (`EmpresaManager`)

---

## Módulo: AUTENTICACIÓN / MULTI-TENANT

### Flujo 1 — Login básico
1. Navegar a `/` o `/login/`
2. Ingresar `username`: `angeldrk`, `password`: [clave]
3. Click "Iniciar sesión"
4. Resultado esperado: redirección a `/dashboard/` (200); barra muestra empresa activa
5. Verificación: `request.session.get('empresa_id')` corresponde a empresa activa del usuario

### Flujo 2 — Cambio de empresa
1. Autenticado; navegar `/contactos/`
2. Usar selector empresa (o modificar `session['empresa_id']` en `/contactos/`)
3. Resultado: datos filtrados por empresa; intentar `empresa_id=99999` → 403

### Flujo 3 — Usuario sin empresas_permitidas bloqueado
1. Crear usuario (`User` sin `PerfilUsuario.empresas_permitidas`)
2. Login con usuario; navegar `/dashboard/`, `/ventas/`, `/catalogo/`, `/carga/`, `/articulos/`
3. Resultado esperado: 403 en cada endpoint (`TenantMiddleware._authorize` rechaza paso 5)

---

## Módulo: DASHBOARD / PANEL DE CONTROL

### Flujo 5 — Dashboard carga métricas
1. Autenticado con empresa activa
2. `GET /dashboard/`
3. Verificar visible: valoración total (USD + VES), volumen ventas mes, notas mes, alertas críticas (`stock_disponible <= stock_minimo`), última sync tasas
4. Resultado: valores coherentes con BD

### Flujo 6 — Alertas de stock mínimo
1. Configurar `stock_minimo` > 0 en artículo
2. Dejar stock real < mínimo
3. Recargar `/dashboard/`
4. Resultado: `alertas_count` aumenta; alerta muestra SKU + nombre
5. Aumentar stock → alertas desaparecen

---

## Módulo: CATÁLOGO / INVENTARIO

### Flujo 7 — Catálogo básico
1. `GET /catalogo/`
2. Verificar paginación (`page_size` whitelist: 10, 25, 50, 75, 100), orden `nombre`
3. `GET ?categoria=HOGAR`: solo artículos HOGAR; `GET ?categoria=INEXISTENTE`: 400
4. `GET ?page_size=7`: 400; `GET ?page=0`: 400; `GET ?page=999`: 400

---

## Módulo: CARGA MASIVA (Ticket #3)

### Flujo 9 — Descarga plantilla
1. Autenticado; `GET /carga/`
2. Click "Descargar plantilla"
3. Resultado: `.xlsx` descargado con cabeceras exactas

### Flujo 10 — Carga exitosa
1. `POST /carga/` con archivo `.xlsx` (4 filas válidas)
2. Resultado JSON: `ok=True`, `filas_procesadas=4`, `filas_error=0`, `colisiones=0`, `lote_id` UUID válido, `reporte_txt` con lote
3. BD verificación: 4 artículos nuevos; movimientos `ENTRADA` (`CARGA_MASIVA_SUMA`)

### Flujo 11 — Error aislado
1. Archivo con 2 filas malas (`nombre=''`, `costo='-5.00'`)
2. Resultado: `filas_procesadas=4`, `filas_error=2`, artículos buenos creados, errores reportados con formato `Fila X [SKU]: Motivo`

### Flujo 12 — Colisión 3 botones
1. Artículo existente con `seed_inventario(20)`; archivo con `COL-001` cantidad 15
2. Resultado: `colisiones=1`, `reporte_txt` menciona pendiente
3. Resolver `SUMAR` (`POST /resolucion/`): `ok=True`, 1 movimiento `ENTRADA`, stock final = 28
4. Resolver `SUSTITUIR`: exactamente 2 movimientos (`SALIDA` + `ENTRADA`), stock final = 15
5. Resolver `CANCELAR`: `movimientos=[]`, stock = 20, sin alteración

---

## Módulo: VENTAS (Ticket #5 / #6)

### Flujo 14 — Venta físico básico
1. Autenticado; cliente creado (`Contacto.CLIENTE`); artículo `FISICO`; `registrar_movimiento` `ENTRADA`
2. `GET /ventas/`; seleccionar artículo; agregar carrito
3. Click "Emitir Nota de Entrega"
4. Resultado: `NotaEntrega` creada (`tasa_bcv_aplicada` = tasa config, `factor_cobertura_aplicado` = factor config, detalles con `precio_ajustado_bcv` calculado)
5. BD: `InventarioAlmacen` actualizado; `MovimientoKardex.SALIDA` (`VENTA`)

### Flujo 15 — Venta con descuento global
1. Agregar artículo; ingresar descuento (ej: 10%)
2. Emitir nota
3. Resultado: `nota.descuento_global` = 10; subtotal e IVA con factor descuento aplicado

---

## Módulo: COMPRAS / PROVEEDORES (Ticket #9 / #19)

### Flujo 19 — Compra básica
1. Autenticado; proveedor (`PROVEEDOR`, `rif` obligatorio, `nombre_asesor` obligatorio)
2. `POST` datos (`numero_factura`, `fecha_compra`, `monto_total_usd`, `almacen_id`, `lista_items` con `sku`, `cantidad`, `costo_factura`)
3. Resultado: `DocumentoCompra` creado; `DetalleDocumentoCompra` con 4 snapshots; `MovimientoKardex.ENTRADA` (`COMPRA`); `InventarioAlmacen` actualizado

### Flujo 20 — Costo/ganancia actualizado
1. Compra con `costo_factura` diferente al artículo
2. Resultado: `Articulo.costo` actualizado; `precio_divisa` recalculado (`MARKUP`: costo * (1 + margen%); `MARGIN`: costo / (1 - margen%))
3. Verificar diferencia `MARKUP` vs `MARGIN` con `margen_ind` explícito

---

## Módulo: INVENTARIO / KARDEX

### Flujo 22 — Entrada manual
1. `svc.registrar_movimiento(articulo, almacen, 'ENTRADA', Decimal('...'), 'COMPRA')`
2. Resultado: `MovimientoKardex.ENTRADA`; `InventarioAlmacen` actualizado atomically (`F()`)

### Flujo 23 — Salida rollback (stock insuficiente)
1. `seed_inventario(10)`; `registrar_movimiento('SALIDA', 15)`
2. Resultado: `ValueError` "Stock insuficiente"; inventario = 10 (intacto); `MovimientoKardex` NO creado

---

## Módulo: NOTAS / FACTURACIÓN (Ticket #5)

### Flujo 29 — Emisión física con tasas
1. Configurar tasas (`tasa_bcv`, `factor_cobertura`); `GET /ventas/`
2. Agregar artículo físico; emitir nota
3. Resultado: `NotaEntrega.tasa_bcv_aplicada` = tasa; `precio_ajustado_bcv` = `precio_usd * tasa * factor`

### Flujo 30 — Devoluciones / Notas de crédito (Ticket #18)
1. Venta previa creada
2. `reversar_nota_entrega(empresa_pk, nota_pk, 'Reverso')`
3. Resultado: `NotaCredito` creada; `DetalleNotaCredito` con `costo_aplicado` histórico; `MovimientoKardex.ENTRADA` (`DEVOLUCION_VENTA`); seriales (`SerialArticulo`) a `DISPONIBLE`
4. Artículo defectuoso (`es_defectuoso=True`): `ENTRADA` + `SALIDA` (`MERMA_DEFECTUOSO`)
5. Doble reverso: `ValueError` "ya se encuentra anulada"; `MovimientoKardex` = solo 1; stock NO inflado

### Flujo 31 — Factura requiere número
1. `tipo_documento='FACTURA'` sin `numero_factura`: falla (`ValueError`)
2. `tipo_documento='FACTURA'` con `numero_factura='FACT-001'`: `NotaEntrega` creada; `numero_factura` único por empresa (constraint `unique_together`)

---

## Módulo: COMBOS

### Flujo 27 — Cálculo dinámico
1. `calcular_stock_combo(combo, almacen)`
2. Formula: `min(floor(stock_componente / cantidad_requerida))`
3. Resultado: entero; 0 si algún componente sin inventario

### Flujo 28 — Venta combo (rollback)
1. `procesar_salida_combo(combo, almacen, cantidad_combos=Decimal('2'))`
2. Resultado: `MovimientoKardex.SALIDA` por componente; inventario actualizado
3. Intentar vender > disponible: `ValueError`; rollback total; inventario intacto

---

## Módulo: TASAS DE CAMBIO

### Flujo 32 — Sincronización exitosa
1. Configurar `api_url`, `http_method`, `response_selector`
2. `sincronizar_tasa_cambio()` con mock (`status_code=200`, JSON con `tasa_paralela=50.00`)
3. Resultado: `ok=True`, `tasa_mercado=50.0000`, `factor_cobertura=1.25`, `AuditoriaTasa` creada, `ConfiguracionEmpresa.tasa_mercado` actualizado

---

## Módulo: REPORTES / RESPALDO

### Flujo 38 — Backup aislado por tenant
1. `GET /respaldo/` (autenticado + empresa activa)
2. Resultado: JSON con datos solo de empresa activa (`metadata.empresa_rif`, artículos, almacenes activos, movimientos últimos 6 meses, sin datos de empresa B)
3. `Content-Type: application/json`, `Content-Disposition` con nombre archivo
4. Sin empresa activa: 302 (login) o 403 (middleware)

---

## Módulo: CONTACTOS

### Flujo 39 — Creación proveedor con validación
1. `POST /contactos/` con `tipo='PROVEEDOR'`, `rif=''`: bloqueado (`ValidationError`); contacto NO creado
2. `POST /contactos/` con `rif='J-...'`, `nombre_asesor='Asesor Real'`: creado
3. `POST` con `tipo='CLIENTE'`: `tipo` auto-seteado a `CLIENTE`

---

## Módulo: SERIAL / POS

### Flujo 36 — Venta con serial
1. Artículo `usa_serial=True`; `SerialArticulo` creada (`DISPONIBLE`)
2. `procesar_venta` con `seriales=['IMEI-...']`
3. Resultado: `SerialArticulo` actualizado (`VENDIDO`, `detalle_nota` = detalle PK); `NotaEntrega` con detalle; `MovimientoKardex` registrado
4. Serial ya vendido: `ValueError` "ya no está DISPONIBLE" (race condition prevenido con `select_for_update` + `estado`)
5. Cantidad serial discordante (`cantidad=2`, `seriales=['IMEI-111']`): `ValueError` "requiere exactamente 2 seriales"

---

## Módulo: MULTI-MONEDA / IMPRESIÓN / MULTI-TENANT / CARGA EXCEL ATÓMICA / REVERSO LOTES

### Flujo 40 — Multi-moneda
1. Configurar tasas; catálogo (`/catalogo/`): `precio_divisa`, `precio_usd_ajustado`, `precio_bs_base`, `precio_bs_bcv`

### Flujo 41 — Impresión parametrizada
1. Configurar coordenadas (`print_offset_x`, `y`, `row_spacing`); `GET /ventas/{nota_id}/imprimir-coordenadas/`
2. Resultado: HTML renderizado con coordenadas, `NE-{numero}`

### Flujo 42 — Multi-tenant (contextvar)
1. `test_vista_usa_get_current_empresa` confirma código usa `get_current_empresa()` no `Empresa.objects.first()`
2. `articulos_view` NO tiene `csrf_exempt`
3. `contactos` usa `ContextVar` no `request.empresa`
4. `vista_exportar_respaldo` usa `ContextVar`

### Flujo 43 — Reverso lote carga masiva
1. `revertir_carga_masiva(lote_id, usuario='Admin')`
2. Resultado: `reversos_ejecutados=2`, `ok=True`, inventario vuelve a 0; bloqueado si hay `SALIDA` posterior (`ValidationError` "reverso bloqueado")

---

## VERIFICACIÓN DE SEGURIDAD (Auditoría Confirmada)

- **SSRF**: `es_url_api_segura('http://localhost/tasa')` → False; `https://198.51.100.10/tasa` → True
- **Rate Limiting**: `test_bloqueo_tras_intentos_fallidos`: 5 fallidos → `login_fail:127.0.0.1` = 5; 6º intento bloqueado; login exitoso limpia contador
- **Rollback Atómico**: `test_salida_insuficiente_hace_rollback_total`: `TransactionTestCase`, inventario intacto (`10.00`), `MovimientoKardex` = 0 nuevo
- **Multi-Tenant Aislamiento**: `EmpresaManager.get_queryset()` retorna `.none()` si `empresa_id` = None; `articulos_view` usa `get_current_empresa()`; `contactos` usa `ContextVar`
- **Serial Race Condition**: `test_error_race_condition_serial_ya_vendido`: `select_for_update` + `estado='DISPONIBLE'` previene doble venta del mismo serial
- **CSRF**: `TestSecurityCSRFEnforcedOnAllPOST` confirma que endpoints POST NO tienen `csrf_exempt`
- **XSS Escapado**: `TestSecurityXSS` confirma `descripcion`, `ficha_tecnica`, `social_quick`, `social_cross`, `observaciones` se renderizan escapados
- **SQL Injection**: `TestSecuritySQLInjection`: filtros `sku__icontains` y `nombre__icontains` con payloads `' OR '1'='1`, `'; DROP ...`, `UNION SELECT ...` NO retornan datos de otros tenants
- **Contraseña**: `TestSecurityPasswordValidation`: `validate_password('1234567')` lanza `ValidationError`; `CommonPasswordValidator` rechaza contraseñas comunes
- **Serial Único**: `TestSecuritySerialUniqueConstraint`: duplicado en misma empresa → `IntegrityError`; mismo serial en empresa diferente → permitido (`unique_together = ['empresa', 'serial']`)
- **Sesión Expirada**: `TestSecuritySessionExpiration`: empresa inactiva (`False`) → 403; empresa inexistente (`99999`) → 403; usuario removido de `empresas_permitidas` → 403

---

## ARCHIVOS CLAVE PARA MANIPULACIÓN FÍSICA
- `manage.py`: `runserver`, `shell`, `createsuperuser`, `test`, `migrate`
- `.env`: `DEBUG=True`, `SECRET_KEY`, `ALLOWED_HOSTS`
- `inventory/services.py`: `registrar_movimiento()`, `calcular_stock_combo()`, `procesar_salida_combo()`, `procesar_carga_masiva()`, `resolver_colision()`, `procesar_venta()`, `registrar_compra_proveedor()`, `revertir_carga_masiva()`, `reversar_nota_entrega()`, `reversar_documento_compra()`, `transferir_mercancia()`, `ejecutar_ajuste_manual()`
- `inventory/models.py`: todos los modelos (`Empresa`, `ConfiguracionEmpresa`, `PerfilUsuario`, `Articulo`, `InventarioAlmacen`, `RecetaCombo`, `MovimientoKardex`, `NotaEntrega`, `DetalleNotaEntrega`, `DocumentoCompra`, `DetalleDocumentoCompra`, `Contacto`, `SerialArticulo`, `NotaCredito`, `DetalleNotaCredito`)
- `inventory/middleware.py`: `TenantMiddleware` (autorización multi-tenant: auth → perfil → empresa activa → empresa permitida)
- `inventory/managers.py`: `EmpresaQuerySet.para_empresa()`, `EmpresaManager.get_queryset()` (retorna `.none()` sin contexto)
- `inventory/forms.py`: formularios para carga masiva, ventas, compras
- `docs/auditoria_2026-08.md`: resultados auditoría inicial
- `docs/especificacion_arquitectura_inventario.md`: especificación técnica completa
- `docs/maqueta_interactiva_de_interfaz.html`: maqueta UI interactiva
