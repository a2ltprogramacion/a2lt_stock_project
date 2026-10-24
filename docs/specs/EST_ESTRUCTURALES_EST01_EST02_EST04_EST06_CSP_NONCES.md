# Spec: Estructurales EST-01 + EST-02 + EST-04 + EST-06 + Migración CSP a Nonces (SEC-02b)

**Fecha:** 2026-10-22
**Rama de trabajo:** `fix/seguridad-configuracion-2026-10` (PR #1 y #2 abiertos, sin merge)
**Precedida por:** `docs/specs/P0_FIXES_SEC01_BUG04.md` (aprobada), `docs/specs/P1_FIXES_SEC02_EST03_DATA09_DATA10.md` (aprobada — formato de referencia)
**Fuente de hallazgos:** `docs/AUDIT_REPORT.md` §10 (EST-01/02/04/05/06) y §7 (deuda CSP de SEC-02b)

---

## 1. Contexto y Alcance

### 1.1 Entorno (hechos verificados, no hipótesis)

| Componente | Valor | Evidencia |
|---|---|---|
| Framework | Django 6.0.6 | `requirements.txt:4` |
| Python | 3.14 | venv del proyecto |
| BD | SQLite 3 (WAL, foreign_keys=ON) | `settings.py:108-123` |
| Plataforma | Windows on-premise, es-VE, America/Caracas | `settings.py:148-150` |
| Suite | **485 tests OK (skipped=6)** | entorno de trabajo |
| Migraciones | Última aplicada: `0028` (las nuevas serán `0029+`) | `inventory/migrations/` |
| Multi-tenant | `EmpresaManager` retorna `.none()` fuera de request → en migraciones/scripts usar `global_objects` o `apps.get_model` | `managers.py:46-51` |
| Excepciones Django 6 | `RestrictedError` ya NO es subclase de `ProtectedError` (ambas hijas de `IntegrityError`) — constatado en runtime | `test_tenant_lifecycle.py:25-30` |
| Context processors | `django.template.context_processors.request` **activo** | `settings.py:93` |

### 1.2 Ya implementado (esta spec se apoya en ello, NO lo duplica)

- **DATA-01**: `inventory/calculos.py` — fuente ÚNICA de subtotales/IVA/descuento/totales (`calcular_totales_documento`). Usada por 5 vistas (`views.py:842, 947, 996, 1102, 1850`).
- **EST-03**: `inventory/correlativos.py` — correlativos atómicos (constraint + reintento); patrón `_correlativo_gestionado` como escape hatch interno de `save()`.
- **DATA-09/EST-11**: flip+constraint en `Moneda`/`Almacen`. **DATA-08**: CHECKs de rangos en detalles.
- **SEC-02b**: `CspMiddleware` propio (`inventory/middleware.py:161-181`) + `settings.CSP_POLICY` (env-overridable), ANTES de `TenantMiddleware` (cubrir los 403 early-return del tenant).
- **SEC-05**: Tailwind CDN con SRI pineado (base.html:24, impresion_coordenadas.html:7, login.html:10, nota_entrega_print.html:9).

### 1.3 Alcance

| ID | Título | Severidad / Prioridad | Ubicación |
|----|--------|----------------------|-----------|
| EST-01 | Invariantes de Kárdex no enforced (la "Regla Sagrada" es intención, no invariante) | ALTA / P1 | `models.py:1300-1428` |
| EST-02 | Inmutabilidad de documentos emitidos no enforced | ALTA / P1 | `NotaEntrega`, `DocumentoCompra`, `NotaCredito` + sus 3 `Detalle*` |
| EST-04 | `usuario` CharField(150) sin FK a `User` ni trazabilidad forense | ALTA / P1 | `MovimientoKardex.usuario` (models.py:1397), `NotaCredito.usuario` (models.py:2029) |
| EST-06 | `total_documento_bs` ignora `descuento_global` y miente por el nombre | MEDIA / P2 | `NotaEntrega` (models.py:1699) y `DocumentoCompra` (models.py:1185) |
| CSP nonces | Deuda aceptada de SEC-02b: eliminar `'unsafe-inline'` de script-src | MEDIA | `settings.py:196-214` + 14 plantillas |
| EST-05 (anexo opcional) | `AuditoriaTasa` sin campo `usuario` | MEDIA / P3 | `models.py:1435-1492` |

### 1.4 Correcciones a las premisas del auditor (verificadas contra Django 6.0.6 y el código)

1. **EST-01 — la remediación literal es defectuosa**: un override de `delete()` de instancia NO bloquea `QuerySet.delete()` (bulk), NI los borrados en cascada, NI cubre `.update()`. Doc oficial Django 6.0: *"The delete() method for an object is not necessarily called when deleting objects in bulk using a QuerySet or as a result of a cascading delete. To ensure customized delete logic gets executed, you can use pre_delete and/or post_delete signals."* y *"update() … does not call save() on models or emit pre_save/post_save signals."* (https://docs.djangoproject.com/en/6.0/ref/signals/#pre-delete · https://docs.djangoproject.com/en/6.0/ref/models/querysets/#update). Por eso esta spec exige **señal `pre_delete`** (se dispara para instancia, queryset y cascada) + **guard en `QuerySet.update()`**.
2. **EST-01 — el admin YA está cerrado hoy**: `MovimientoKardexAdmin` define `has_add/change/delete_permission = False` (`admin.py:338-348`); la acción "eliminar seleccionados" exige `has_delete_permission`. Los vectores reales son shell, scripts y querysets de código propio.
3. **CSP — existe una tercera opción no contemplada**: **Django 6.0 trae CSP nativo** (`ContentSecurityPolicyMiddleware`, settings `SECURE_CSP`/`SECURE_CSP_REPORT_ONLY` con constantes `CSP.SELF`/`CSP.NONCE`, context processor `csp` que expone `{{ csp_nonce }}`, Report-Only y decoradores por vista). Doc oficial: https://docs.djangoproject.com/en/6.0/ref/csp/ y https://docs.djangoproject.com/en/6.0/ref/middleware/#content-security-policy-middleware. El proyecto está pineado a 6.0.6 → la disyuntiva "django-csp vs extender nuestro middleware" queda superada por la opción nativa (ver REQ-CSP-01 y §6).
4. **Reversos — comportamiento confirmado (esperado)**: `reversar_nota_entrega`/`reversar_documento_compra` NO borran kárdex: hacen `save(update_fields=['estado','motivo_anulacion'])` (services.py:2348, 2386) e **INSERTAN movimientos compensatorios** (`DEVOLUCION_VENTA` entrada; `ANULACION_COMPRA` salida). No existe función `anular_compra`. Los guards deben permitir exactamente esas mutaciones.

### 1.5 Inventario de evidencia clave (recopilada con grep/read sobre el repo)

- **Kárdex — punto único de creación**: `services.registrar_movimiento` (services.py:210). Creaciones directas fuera del servicio: **solo 1 test** (`tests.py:1638`). `.update()` sobre kárdex: **solo 1 test** (`tests.py:1649`, envejece `fecha_hora` 8 meses para el filtro de `exportar_datos_tenant` con `meses_historico=6`).
- **Borrados legítimos de kárdex HOY (allowlist)**: `seed_db.py:499` (`--clear`) y cascada de `empresa.delete()` (FK `empresa` on_delete=CASCADE, models.py:1336). `test_tenant_lifecycle.py:98` borra tenants recién sembrados **sin filas de kárdex** → hoy no dispara nada; todo teardown real de tenant con datos sí necesitará el escape hatch.
- **Mutaciones legítimas de documentos emitidos HOY**: exactamente 4 sitios en services — `nota.save(update_fields=['estado','motivo_anulacion'])` (2348), `compra.save(...)` (2386), `nc.save(update_fields=['monto_total_reembolso'])` (2631, 2791). Además **código muerto**: `nc.delete() if nc.pk else None` dentro de `except` de funciones `@transaction.atomic` (services.py:2627, 2787) — no-op (el rollback ya deshace) que colisionaría con el guard de EST-02.
- **`.update()` sobre documentos**: 0 ocurrencias en services/views (grep). El bypass existe como *posibilidad*, no como práctica.
- **Admin — superficie de EST-02**: `NotaEntregaAdmin` (admin.py:373) permite editar `estado`, `motivo_anulacion`, `cliente`, `moneda_pago`, `descuento_global`, `observaciones` de documentos PROCESADO; `DetalleNotaEntregaInline` (367) editable con delete; `DetalleNotaEntregaAdmin` (386) con CRUD completo. No existe admin de `NotaCredito`.
- **Writers de `usuario` (string) — inventario completo**: 8 vistas (`views.py:469/486` carga masiva con `usuario` **por POST**; `548/554`; `611/630` colisión por POST; `759` venta fallback `'API'`; `1345` asiento manual; `2057` compra API; `2426/2434` NC fallback `'Sistema'`); `seed_db.py` `"seed_db"` (359, 421); `generate_demo_data.py` `'Demo Setup'`/`'Demo User'` (207, 338); tests ~60 literales (`'test'`, `'Admin'`, `'DevSys'`, `'data03'`, `'setUp'`, `'Thread-N'`, `'operador_audit'`…); `reversar_*` hardcodean `'Sistema'` (services.py:2360, 2400); `NotaCredito.usuario` `default='Sistema'`.
- **Consumidores de presentación de `usuario`**: solo `nota_credito_detalle.html:51` (`{{ nc.usuario|default:"Sistema" }}`). Kárdex no muestra usuario en templates; `exporters.py`/`reports.py` no lo referencian.
- **Property `total_documento_bs` — huérfana en producción**: sus ÚNICOS consumidores son 2 tests de existencia/valor-vacío (`tests.py:6231, 6240`). Ninguna vista/template/exporter la usa (DATA-01 las reemplazó). La de `DocumentoCompra` (models.py:1185) padece el mismo defecto.
- **CSP — scripts inline**: **16 bloques `<script>` inline en 14 plantillas** (base.html ×3: getCsrfToken L10-19, theme+`tailwind.config` L29-58, sidebar/utilidades L394+; articulos 226; impresion_coordenadas 106; compras 285; contactos 293; catalogo 215; configuracion 281; carga 129; login 13-16; notas_credito 183; reversos 144; reportes/detalle 117; movimientos 224; ventas 284). `getCsrfToken()` se define 1 vez (base.html:15) y se consume en **7 plantillas** (articulos 345, compras 406, carga 213/335, notas_credito 234/374, movimientos 244, ventas 418, reversos 198). Los 4 tags externos con SRI no se tocan (nonce solo aplica a inline).
- **CSP — tests existentes afectados**: `test_security_csp_403.py:301` (igualdad exacta `header == settings.CSP_POLICY` → romperá con nonce dinámico); `:253-269` (orígenes externos presentes → seguirá pasando); `:242-249` (CSP en el 403 del tenant → debe seguir pasando con el middleware nativo en la misma posición); `test_templates_sri.py` debe quedar verde.

---

## 2. Requisitos Funcionales (Notación EARS)

### 2.1 EST-01 — Kárdex inmutable a nivel de modelo

**UBICACIÓN**: `inventory/models.py:1300-1428` (`MovimientoKardex`), `inventory/services.py:62-225` (`registrar_movimiento`), `inventory/signals.py`.

**Decisión de diseño (ver §6.1)**: señales ORM (`pre_delete`/`pre_save`) + guard en `QuerySet.update()` + escape hatch contextual. Triggers SQL descartados como mecanismo base (ver §6.1 justificación).

#### REQ-EST01-01: Bloqueo de borrados por señal pre_delete
**MIENTRAS** no esté activo un contexto de bypass autorizado (REQ-EST01-03)  
**EL SISTEMA DEBE** bloquear todo borrado de filas de `MovimientoKardex` — `delete()` de instancia, `QuerySet.delete()` y borrados en cascada — mediante señal `pre_delete`, lanzando `KardexProtegidoError` (excepción dedicada, definida en `inventory`).

#### REQ-EST01-02: Bloqueo de .update() por QuerySet custom
**CUANDO** se invoque `.update()` sobre cualquier queryset de `MovimientoKardex` (`objects` o `global_objects`) fuera del bypass  
**ENTONCES** EL SISTEMA DEBE lanzar `KardexProtegidoError` mediante un `QuerySet` custom cableado a ambos managers (`EmpresaManager.from_queryset(...)` y `Manager.from_queryset(...)`), conservando el filtrado multi-tenant.

#### REQ-EST01-03: Escape hatch contextual (kardex_bypass)
**EL SISTEMA DEBE** proveer un context manager `kardex_bypass(motivo: str)` basado en `ContextVar` (reentrante, thread/async-safe) que habilite excepcionalmente DELETE/UPDATE/creación directa de kárdex, registrando `logger.warning` con el motivo.

#### REQ-EST01-04: Allowlist explícita de usos del bypass
**EL SISTEMA DEBE** restringir documentadamente el uso de `kardex_bypass` a la siguiente allowlist (codificada en ADR, no en código):
1. `seed_db.py --clear` (`_clear_all`, línea 499) — reseed de demo.
2. Teardown de tenant completo (`empresa.delete()` con kárdex/documentos — cascada).
3. Tests que envejecen `fecha_hora` (`tests.py:1649`) y crean kárdex directo como fixture (`tests.py:1638`).
**SI** aparece un cuarto uso en código de negocio (services/views/admin) **ENTONCES** eso es un defecto de diseño, no un caso del bypass.

#### REQ-EST01-05: Guard de creación (Regla Sagrada bidireccional)
**CUANDO** se intente crear un `MovimientoKardex` por fuera de `registrar_movimiento` y sin bypass  
**ENTONCES** EL SISTEMA DEBE bloquear vía señal `pre_save` exigiendo un contexto de escritura autorizada que `registrar_movimiento` activa internamente (solo 2 sitios de creación existen hoy: services.py:210 legítimo; tests.py:1638 fixture).

#### REQ-EST01-06: Cero regresiones en el camino legítimo
**CUANDO** `registrar_movimiento` cree el registro dentro de su contexto autorizado  
**EL SISTEMA DEBE** comportarse exactamente igual que hoy (los 485 tests existentes no requieren cambios por el camino legítimo).

#### REQ-EST01-07: Migraciones exentas
**MIENTRAS** se ejecuten migraciones (modelos históricos vía `apps.get_model`)  
**EL SISTEMA DEBE** permitir las operaciones de datos sin activar los guards (los receivers se conectan con `sender=Modelo real`; las señales de clases históricas no los alcanzan). **Verificación obligatoria paso 0** antes de confiar en esta exención.

#### REQ-EST01-08: Observabilidad del bloqueo
**CUANDO** un guard bloquee una operación  
**EL SISTEMA DEBE** loguear `ERROR` con modelo, operación, pk si existe y traceback, antes de lanzar la excepción.

#### REQ-EST01-09: No invasión del admin
**MIENTRAS** `MovimientoKardexAdmin` mantenga `has_add/change/delete_permission=False`  
**EL SISTEMA DEBE** seguir presentando el kárdex en el admin como solo lectura, sin que los guards cambien esa superficie.

**Verificación EST-01**: `python manage.py test inventory` verde (485 + ~8 tests nuevos en `test_cases/test_kardex_inmutable.py`: delete instancia/queryset, update, create directo, bypass positivo, cascada tenant, reversos intactos).

---

### 2.2 EST-02 — Inmutabilidad de documentos emitidos

**UBICACIÓN**: `NotaEntrega` (models.py:1498), `DetalleNotaEntrega` (1708), `DocumentoCompra` (1032), `DetalleDocumentoCompra` (1194), `NotaCredito` (1957), `DetalleNotaCredito` (2106); `services.py`; `admin.py`.

**Matriz EXACTA de campos mutables tras emisión** (derivada de los 4 únicos `save()` legítimos, §1.5):

| Modelo | Campos mutables tras creación | Condición |
|---|---|---|
| `NotaEntrega` | `estado`, `motivo_anulacion` | solo transición `PROCESADO → ANULADO` |
| `DocumentoCompra` | `estado`, `motivo_anulacion` | solo transición `PROCESADO → ANULADO` |
| `NotaCredito` | `estado`, `motivo_anulacion` | solo transición `PROCESADO → ANULADO` |
| `DetalleNotaEntrega` | **ninguno** | matriz vacía |
| `DetalleDocumentoCompra` | **ninguno** | matriz vacía |
| `DetalleNotaCredito` | **ninguno** | matriz vacía (su `save()` recalcula derivados de entradas idénticas → sin diff → permitido) |

#### REQ-EST02-01: Inmutabilidad de cabeceras vía pre_save
**MIENTRAS** una `NotaEntrega`/`DocumentoCompra`/`NotaCredito` existente esté en estado `PROCESADO`  
**EL SISTEMA DEBE** permitir en `save()` únicamente la matriz de campos de la tabla anterior; cualquier otro campo modificado DEBE lanzar `DocumentoInmutableError` (subclase de la misma base que `KardexProtegidoError`) con mensaje que indique el servicio legítimo a usar.

#### REQ-EST02-02: Transición única y documentos cerrados
**SI** el estado original es `ANULADO` **ENTONCES** EL SISTEMA DEBE bloquear toda mutación posterior (documento histórico cerrado); **SI** el nuevo estado no es `ANULADO` o el original no es `PROCESADO` **ENTONCES** el cambio de `estado` DEBE bloquearse.

#### REQ-EST02-03: Inmutabilidad de detalles
**MIENTRAS** un `Detalle*` exista **EL SISTEMA DEBE** bloquear vía `pre_save` cualquier modificación de sus campos tras la creación (matriz vacía), permitiendo el re-save idempotente con valores idénticos.

#### REQ-EST02-04: Bloqueo de borrados
**CUANDO** se intente borrar (instancia, queryset o cascada) cualquiera de los 6 modelos fuera del bypass de EST-01 (reutilizado)  
**ENTONCES** EL SISTEMA DEBE bloquear vía `pre_delete`.

#### REQ-EST02-05: Eliminación del código muerto nc.delete()
**EL SISTEMA DEBE** eliminar `nc.delete() if nc.pk else None` de `procesar_devolucion_venta` (services.py:2627) y `procesar_devolucion_compra` (2787): es no-op dentro de `@transaction.atomic` y su `pre_delete` enmascararía la excepción original bajo los nuevos guards.

#### REQ-EST02-06: NotaCredito inmutable desde su nacimiento
**EL SISTEMA DEBE** refactorizar `procesar_devolucion_venta`/`procesar_devolucion_compra` para computar `monto_total_reembolso` **antes** del `create` de la cabecera (doble pasada: validar+cálculo, luego persistir), eliminando el `nc.save(update_fields=['monto_total_reembolso'])` post-creación (2631, 2791). Alternativa (allowlist del campo) solo si el usuario la elige en §6.5.

#### REQ-EST02-07: Mecanismo compartido
**EL SISTEMA DEBE** implementar la matriz con señales `pre_save`/`pre_delete` y un helper único de comparación contra original (cubre instance save, admin, forms). **El bypass `.update()` de queryset queda fuera de fase 1** y documentado como riesgo residual aceptado (§5); fase 2 opcional en §6.3.

#### REQ-EST02-08: Admin solo lectura para documentos emitidos
**MIENTRAS** un documento emitido (cualquier estado ≠ creación) se muestre en el admin  
**EL SISTEMA DEBE** presentarlo íntegramente como solo lectura (`get_readonly_fields` dinámico con todos los campos; `DetalleNotaEntregaInline.can_delete=False`; `DetalleNotaEntregaAdmin` sin permisos de edición) para evitar 500s del guard y cerrar el vector "anular sin reversar stock" que hoy permite editar `estado` a mano.

#### REQ-EST02-09: Camino legítimo intacto
**CUANDO** `reversar_nota_entrega`/`reversar_documento_compra` anulen un documento (update_fields permitidos por la matriz)  
**EL SISTEMA DEBE** funcionar sin cambios, incluyendo los INSERT compensatorios de kárdex y la liberación/anulación de seriales.

#### REQ-EST02-10: Anulación por devolución preservada
**CUANDO** `procesar_devolucion_*` cree una NC sobre un documento `PROCESADO`  
**EL SISTEMA DEBE** seguir permitiéndolo (la creación de NC nueva no muta el origen; el reingreso de stock va por kárdex compensatorio).

**Verificación EST-02**: `python manage.py test inventory` verde (485 + ~10 tests nuevos en `test_cases/test_inmutabilidad_documentos.py`: matriz por modelo, transición válida/inválida, delete bloqueado, admin readonly, reversos/devoluciones intactos, NC creada con monto definitivo).

---

### 2.3 EST-04 — `usuario`: FK a User + snapshot

**UBICACIÓN**: `MovimientoKardex.usuario` (models.py:1397-1401), `NotaCredito.usuario` (2029-2032), services (firmas), views (8 sitios), migración `0029`.

#### REQ-EST04-01: Esquema — renombrar y añadir FK (MovimientoKardex)
**EL SISTEMA DEBE** renombrar `MovimientoKardex.usuario` → `usuario_nombre` (`RenameField`, datos preservados) y añadir FK `usuario → User` (`on_delete=SET_NULL`, `null=True`, `blank=True`) con `related_name` que **no colisione** con `Empresa.movimientos_kardex` (usado por la FK empresa, models.py:1336) — p. ej. `kardex_registrado_por`.

#### REQ-EST04-02: Esquema — NotaCredito
**EL SISTEMA DEBE** aplicar el mismo tratamiento a `NotaCredito` (el `default='Sistema'` pasa al snapshot `usuario_nombre`; la FK nace `NULL`-able).

#### REQ-EST04-03: Backfill con match de username
**CUANDO** se ejecute la migración de datos (`0029`)  
**EL SISTEMA DEBE** resolver la FK por match exacto `username → auth_user`; **SI** no hay match **ENTONCES** la FK queda `NULL` preservando `usuario_nombre` (los valores `'seed_db'`, `'Sistema'`, `'Demo Setup'`, `'data03'`… no matchean por diseño — el snapshot es la trazabilidad). La migración usa modelos históricos con manager plano (`EmpresaManager` no define `use_in_migrations`) — verificación paso 0.

#### REQ-EST04-04: Auditoría previa de usernames
**CUANDO** se aplique la migración sobre la BD real  
**EL SISTEMA DEBE** ejecutar antes una auditoría `SELECT DISTINCT usuario … vs auth_user` registrando el % de match esperado (paso operativo documentado, no bloqueante).

#### REQ-EST04-05: Servicios aceptan str | User (backward-compat)
**LOS** servicios que reciben `usuario` (`registrar_movimiento`, `procesar_venta`, `registrar_compra_proveedor`, `procesar_carga_masiva*`, `procesar_devolucion_*`, `revertir_carga_masiva`, `transferir_mercancia`, `ejecutar_ajuste_manual`) **DEBEN** aceptar `str | User` y resolver internamente con un helper único: instancia `User` → FK + `usuario_nombre=user.username`; string con usuario existente → FK resuelta + snapshot; string sin match o vacío → FK `NULL` + snapshot preservado. **Las ~60 llamadas de tests con literales NO se tocan** (quedan como snapshot + FK NULL, comportamiento correcto y verificable).

#### REQ-EST04-06: Vistas pasan request.user
**LAS** 8 vistas escritoras **DEBEN** pasar `request.user` (instancia) en lugar de `request.user.username`, y el parámetro `usuario` recibido por POST en `vista_carga_masiva` (views.py:469) y `vista_resolver_colision` (611) **DEBE** deprecase (ignorado + `logger.warning`): el operador autenticado es la fuente de verdad forense, no un campo del formulario.

#### REQ-EST04-07: Trazabilidad de reversos
**LOS** servicios `reversar_nota_entrega`/`reversar_documento_compra` **DEBEN** aceptar `usuario: str | User = 'Sistema'` (parámetro nuevo opcional; las vistas `api_reversar_*` pasan `request.user`) para dejar de hardcodear `'Sistema'` (services.py:2360, 2400).

#### REQ-EST04-08: Multi-tenant declarado
**EL SISTEMA DEBE** documentar que la FK a `User` es **global** (los usuarios NO son per-empresa; `PerfilUsuario` gobierna el acceso por empresa): el kárdex/NC registra qué humano operó, no a qué tenant pertenece.

#### REQ-EST04-09: Presentación por snapshot
**EL** template `nota_credito_detalle.html:51` **DEBE** mostrar `nc.usuario_nombre|default:"Sistema"` (snapshot determinista) en lugar de la FK (que puede ser `None`); el filtro `|default` existente se conserva.

**Verificación EST-04**: `python manage.py makemigrations --check` limpio tras `0029`; `python manage.py migrate` + reversibilidad (`migrate 0028`); `python manage.py test inventory` verde con los ~60 call-sites de tests intactos; ~7 tests nuevos (`test_cases/test_usuario_fk.py`): resolución str/User, backfill match/no-match, SET_NULL preserva snapshot, view pasa instancia.

---

### 2.4 EST-06 — Totales honestos vía fuente única

**UBICACIÓN**: `NotaEntrega.total_documento_bs` (models.py:1699-1701), `DocumentoCompra.total_documento_bs` (1185-1187), `inventory/calculos.py`.

**Hecho clave**: ambas properties están **huérfanas en producción** (solo tests.py:6231/6240 las referencian; DATA-01 movió los totales reales a `calculos.calcular_totales_documento`, usada por las 5 vistas). Su semántica real es **bruto**: `subtotal_bs + total_iva_bs` NO aplica `descuento_global` — el nombre promete "total del documento" y miente.

#### REQ-EST06-01: Prohibición de fórmula duplicada
**EL SISTEMA DEBE** eliminar la fórmula `subtotal_bs + total_iva_bs` de `models.py`; ninguna property de totales puede computar importes por su cuenta (fuente única DATA-01).

#### REQ-EST06-02: Renombrado con semántica honesta + delegación
**SI** se conserva una property de conveniencia **ENTONCES** DEBE llamarse `total_bs_bruto` y **DELEGAR** en `calculos.calcular_totales_documento(self.detalles, self.descuento_global)` (claves `subtotal_bs_bruto + total_iva_bs_bruto`), en ambos modelos. El nombre `total_documento_bs` **DEBE** desaparecer (sin alias deprecado: un alias con la misma firma y distinto valor sería una trampa silenciosa).

#### REQ-EST06-03: Total neto sigue viniendo de calculos
**CUANDO** pantallas/PDF muestren totales de documento **EL SISTEMA DEBE** seguir usando `calculos.calcular_totales_documento` (`total_bs_neto`/`total_usd_neto`) — las 5 vistas no se tocan.

#### REQ-EST06-04: Contrato de tests actualizado
**LOS** tests `tests.py:6222-6240` **DEBEN** actualizarse al nuevo contrato: `hasattr(nota, 'total_documento_bs')` → `False`; `total_bs_bruto == 0` con detalles vacíos; con `descuento_global=10`, `total_bs_bruto ≠ total_bs_neto` (par bruto/neto distinguible).

**Verificación EST-06**: `python manage.py test inventory` verde; test de inspección de fuente (patrón ya usado en `test_calculos.py:264`): `models.py` no contiene la fórmula duplicada.

---

### 2.5 CSP — Migración a nonces (deuda SEC-02b)

**UBICACIÓN**: `settings.py:196-214`, `inventory/middleware.py:161-181`, 14 plantillas, `test_security_csp_403.py`.

**Meta**: eliminar `'unsafe-inline'` de **script-src**. **style-src lo conserva** mientras se use Tailwind CDN JIT (injecta `<style>` en runtime) — deuda documentada hasta que exista build de Tailwind (SEC-05 mantiene el CDN).

#### REQ-CSP-01: Adopción del CSP nativo de Django 6.0
**EL SISTEMA DEBE** adoptar el CSP nativo de Django 6.0 (`django.middleware.security.ContentSecurityPolicyMiddleware` + `SECURE_CSP` en formato dict con `django.utils.csp.CSP` + context processor `django.template.context_processors.csp`) en lugar de extender `CspMiddleware` propio o añadir `django-csp` (justificación en §6.8; verificación paso 0: `python -c "from django.middleware.security import ContentSecurityPolicyMiddleware; from django.utils.csp import CSP"` — el venv no fue inspeccionable desde las herramientas de esta sesión).

#### REQ-CSP-02: Posición del middleware preservada
**EL SISTEMA DEBE** reemplazar `inventory.middleware.CspMiddleware` por `ContentSecurityPolicyMiddleware` **en la misma posición** (antes de `TenantMiddleware`, settings.py:80-81) para que los 403 early-return del tenant también reciban la CSP (comportamiento hoy garantizado por `test_sec02b_csp_header_en_403_del_middleware`).

#### REQ-CSP-03: Política con nonce en script-src
**EL SISTEMA DEBE** definir `SECURE_CSP` equivalente a la política actual, con `script-src = [CSP.SELF, CSP.NONCE, 'https://cdn.tailwindcss.com']` (sin `'unsafe-inline'`) y `style-src` conservándolo. Nota CSP3: con nonce presente, los navegadores ignoran `'unsafe-inline'` en esa directiva — la eliminación es efectiva, no cosmética.

#### REQ-CSP-04: Nonce en los 16 scripts inline
**LOS** 16 bloques `<script>` inline de las 14 plantillas (§1.5) **DEBEN** llevar `nonce="{{ csp_nonce }}"`; el context processor `csp` se añade a `TEMPLATES` (el `request` processor ya está activo). Los 4 tags externos con SRI no se modifican.

#### REQ-CSP-05: Gate anti-regresión de plantillas
**EL SISTEMA DEBE** incluir un test estático que falle si alguna plantilla contiene `<script>` sin `src` y sin `nonce=` (grep sobre `inventory/templates/`), evitando que una plantilla nueva rompa el JS silenciosamente.

#### REQ-CSP-06: Report-Only previo y rollback por entorno
**EL SISTEMA DEBE** soportar un periodo de adopción con `CSP_REPORT_ONLY` (env): con `CSP_REPORT_ONLY=true` la política se emite como `Content-Security-Policy-Report-Only` (no bloqueante); el flip a enforcing y el rollback de emergencia se hacen por variable de entorno, sin cambios de código.

#### REQ-CSP-07: Deprecación documentada de CSP_POLICY
**LA** variable `CSP_POLICY` (string crudo por env, settings.py:202) **DEBE** marcarse deprecada y documentarse su retirada; la configuración canónica pasa a ser `SECURE_CSP` (dict). Documentar en `docs/OPERACION.md` el nuevo knob `CSP_REPORT_ONLY`.

#### REQ-CSP-08: Rework de la suite CSP
**LA** suite `test_security_csp_403.py` **DEBE** re-trabajarse: (a) el unit test del middleware propio (277-301) se adapta al middleware nativo; (b) la igualdad exacta de header (301) pasa a verificar estructura (presencia de `nonce-`, orígenes permitidos); (c) los orígenes externos (253-269) y el 403 con CSP (242-249) siguen pasando; (d) nuevo test: nonces distintos entre dos requests. `test_templates_sri.py` debe permanecer verde.

#### REQ-CSP-09: Sin caching de páginas
**MIENTRAS** el proyecto no cacheé páginas HTML **EL SISTEMA DEBE** documentar que el nonce por request es seguro; **SI** en el futuro se añade caching de respuestas **ENTONCES** deberá excluirse el header/nonce de las páginas cacheadas (advertencia del how-to oficial de CSP).

**Verificación CSP**: `python manage.py test inventory` verde; navegación manual de las 7 vistas con JS activo (ventas, compras, carga, notas_credito, movimientos, reversos, articulos) con la política enforcing — sin errores de consola CSP.

---

### 2.6 Anexo opcional — EST-05: `AuditoriaTasa.usuario`

**UBICACIÓN**: `models.py:1435-1492`. Writers actuales: `services.sincronizar_tasa_cambio` (services.py:1713) y `views.configuracion_view` (views.py:1702) — ambos con `request.user`/usuario disponible.

#### REQ-EST05-A1: Mismo patrón EST-04
**SI** el usuario aprueba el anexo **ENTONCES** `AuditoriaTasa` **DEBE** recibir FK `usuario → User` (SET_NULL) + snapshot `usuario_nombre`, con backfill idéntico (migración `0030`) y resolución `str | User` en sus 2 writers.

**Verificación EST-05**: idéntica a EST-04, ~3 tests.

---

## 3. Criterios de Aceptación (Gherkin)

### Feature: EST-01 — Kárdex inmutable

```gherkin
@EST01 @P1 @data-integrity
Feature: El kárdex solo muta vía registrar_movimiento; DELETE/UPDATE/direct-INSERT quedan bloqueados

  Background:
    Given una empresa activa con tenant en sesión
    And un artículo FISICO con stock 10 en un almacén
    And el guard de kárdex activo (señales pre_delete/pre_save + QuerySet.update)

  @EST01-01 @happy
  Scenario: registrar_movimiento crea el registro y muta stock (camino legítimo intacto)
    When llamo registrar_movimiento(articulo, almacen, "ENTRADA", 5, "AJUSTE_ENTRADA", usuario="op")
    Then se crea exactamente 1 MovimientoKardex
    And el stock pasa de 10 a 15
    And no se lanza KardexProtegidoError

  @EST01-02 @negative
  Scenario: QuerySet.delete() desde shell queda bloqueado
    When ejecuto MovimientoKardex.objects.all().delete()
    Then lanza KardexProtegidoError
    And el conteo de movimientos no cambia

  @EST01-03 @negative
  Scenario: delete() de instancia queda bloqueado
    When ejecuto movimiento.delete() sobre una fila existente
    Then lanza KardexProtegidoError

  @EST01-04 @negative
  Scenario: .update(cantidad=999) queda bloqueado
    When ejecuto MovimientoKardex.objects.filter(pk=X).update(cantidad=999)
    Then lanza KardexProtegidoError
    And la cantidad persistida sigue siendo la original

  @EST01-05 @negative
  Scenario: .update() por global_objects también queda bloqueado
    When ejecuto MovimientoKardex.global_objects.filter(empresa_id=E).update(detalle_adicional="x")
    Then lanza KardexProtegidoError

  @EST01-06 @negative
  Scenario: Creación directa fuera del servicio queda bloqueada
    When ejecuto MovimientoKardex.objects.create(...) sin bypass y sin pasar por services
    Then lanza KardexProtegidoError
    And no queda fila huérfana sin contraparte en InventarioAlmacen

  @EST01-07 @edge
  Scenario: Escape hatch habilita el fixture de test que envejece fecha_hora
    When entro en with kardex_bypass(motivo="fixture export"):
      And ejecuto MovimientoKardex.objects.filter(pk=X).update(fecha_hora=hace_8_meses)
    Then la fecha queda actualizada
    And existe un log WARNING con el motivo

  @EST01-08 @edge
  Scenario: Teardown de tenant con kárdex requiere bypass explícito
    Given un tenant con movimientos de kárdex
    When ejecuto empresa.delete() sin bypass
    Then lanza KardexProtegidoError
    When ejecuto empresa.delete() dentro de kardex_bypass(motivo="teardown tenant")
    Then el tenant y su kárdex se eliminan por cascada

  @EST01-09 @edge
  Scenario: Migraciones con modelos históricos no activan los guards
    When ejecuto una RunPython sobre apps.get_model("inventory", "MovimientoKardex")
    Then la operación de datos completa sin KardexProtegidoError

  @EST01-10 @negative
  Scenario: El reverso de una venta no borra kárdex (solo INSERT compensatorio)
    When llamo reversar_nota_entrega(empresa_id, nota_id, "motivo")
    Then la nota queda ANULADA
    And no se lanza KardexProtegidoError
    And existen N+1 movimientos (los originales + compensatorios)
```

### Feature: EST-02 — Documentos emitidos inmutables

```gherkin
@EST02 @P1 @data-integrity
Feature: Facturas/NE/NC emitidas no se editan ni se borran; solo la transición a ANULADO vía services

  Background:
    Given una empresa activa
    And una NotaEntrega PROCESADO con 2 detalles creada via procesar_venta
    And el guard de inmutabilidad activo (pre_save/pre_delete con matriz)

  @EST02-01 @happy
  Scenario: Anulación vía reversar_nota_entrega funciona igual que hoy
    When llamo reversar_nota_entrega(empresa_id, nota_id, "error de carga")
    Then la nota queda estado=ANULADO y motivo_anulacion="error de carga"
    And se registran movimientos compensatorios DEVOLUCION_VENTA
    And ningún otro campo de la nota cambió

  @EST02-02 @negative
  Scenario: Cambiar precio de un detalle de una nota PROCESADA queda bloqueado
    When hago detalle.precio_base = 999 y detalle.save()
    Then lanza DocumentoInmutableError
    And el mensaje referencia reversar_nota_entrega como vía legítima

  @EST02-03 @negative
  Scenario: Borrar detalles de una nota emitida queda bloqueado
    When ejecuto nota.detalles.all().delete()
    Then lanza DocumentoInmutableError
    And los detalles persisten

  @EST02-04 @negative
  Scenario: Reactivar una nota ANULADA queda bloqueada (documento cerrado)
    Given una nota ANULADA
    When hago nota.estado = "PROCESADO" y nota.save()
    Then lanza DocumentoInmutableError

  @EST02-05 @negative
  Scenario: Cambiar moneda_pago de una nota PROCESADA queda bloqueado
    When hago nota.moneda_pago = "BS_EFECTIVO" y nota.save()
    Then lanza DocumentoInmutableError

  @EST02-06 @edge
  Scenario: Re-save idempotente sin cambios queda permitido
    When guardo la nota sin modificar ningún campo
    Then no lanza excepción

  @EST02-07 @happy
  Scenario: NotaCredito nace con monto definitivo (refactor)
    When llamo procesar_devolucion_venta(...) con 1 item
    Then la NC se crea una sola vez con monto_total_reembolso definitivo
    And no existe nc.save() posterior al create
    And el kárdex registra DEVOLUCION_VENTA

  @EST02-08 @edge
  Scenario: DetalleNotaCredito recalcula derivados idénticos sin bloqueo
    When guardo un DetalleNotaCredito existente sin cambiar sus entradas
    Then el save completa (los derivados recalculados son iguales)

  @EST02-09 @edge
  Scenario: seed_db --clear sigue funcionando con bypass
    When ejecuto seed_db --clear envuelto en kardex_bypass
    Then la base queda limpia y resembrada

  @EST02-10 @negative
  Scenario: Admin no permite editar un documento emitido
    When un superusuario abre la NotaEntrega PROCESADA en /admin/
    Then todos los campos se muestran solo lectura
    And el inline de detalles no ofrece borrar
```

---

### Feature: EST-04 — usuario como FK + snapshot forense

```gherkin
@EST04 @P1 @forensics
Feature: Kárdex y Notas de Crédito referencian al usuario real con snapshot tolerante a bajas

  Background:
    Given un usuario "operador" existente en auth_user
    And una empresa activa con tenant en sesión
    And el esquema migrado: usuario_nombre (snapshot) + usuario (FK SET_NULL)

  @EST04-01 @happy
  Scenario: Service recibe instancia User y llena FK + snapshot
    When llamo procesar_venta(..., usuario=<User operador>)
    Then el movimiento de kárdex tiene usuario_id=operador.pk
    And usuario_nombre == "operador"

  @EST04-02 @happy
  Scenario: Service recibe string con usuario existente y resuelve la FK
    When llamo registrar_movimiento(..., usuario="operador")
    Then el movimiento tiene usuario_id=operador.pk
    And usuario_nombre == "operador"

  @EST04-03 @edge
  Scenario: String sin usuario correspondiente queda como snapshot con FK NULL
    When llamo registrar_movimiento(..., usuario="data03")
    Then el movimiento tiene usuario_id NULL
    And usuario_nombre == "data03"

  @EST04-04 @edge
  Scenario: Los ~60 call-sites de tests con literales siguen pasando sin cambios
    When ejecuto la suite completa
    Then los tests que pasan usuario="Admin"/"Test"/"DevSys" siguen en verde
    And cada movimiento conserva su snapshot de usuario

  @EST04-05 @negative
  Scenario: Baja del usuario preserva la trazabilidad (SET_NULL)
    Given un movimiento creado por <User operador>
    When el usuario operador es borrado
    Then el movimiento persiste con usuario_id NULL
    And usuario_nombre == "operador"

  @EST04-06 @edge
  Scenario: Backfill de migración hace match por username
    Given kárdex histórico con usuario_nombre="operador" (CharField renombrado)
    When ejecuto la migración 0029
    Then usuario_id apunta a operador.pk
    And las filas con "seed_db"/"Sistema" quedan con FK NULL y snapshot intacto

  @EST04-07 @negative
  Scenario: Vistas dejan de confiar en usuario por POST
    When hago POST a carga masiva con usuario="cualquiera" en el body
    Then el kárdex se registra contra request.user (usuario autenticado)
    And el valor del POST queda ignorado con logger.warning

  @EST04-08 @happy
  Scenario: Reversos registran quién anuló
    When llamo reversar_nota_entrega(empresa_id, nota_id, "motivo", usuario=<User admin>)
    Then los movimientos compensatorios llevan usuario_id=admin.pk
    And usuario_nombre == "admin"
```

### Feature: EST-06 — Totales con semántica honesta

```gherkin
@EST06 @P2 @single-source
Feature: La property engañosa desaparece; los totales viven solo en calculos.py

  Background:
    Given una NotaEntrega con 2 detalles y descuento_global=10
    And un DocumentoCompra con 1 detalle y descuento_global=5

  @EST06-01 @happy
  Scenario: total_bs_bruto delega en calculos y refleja el bruto
    When consulto nota.total_bs_bruto
    Then el valor == subtotal_bs_bruto + total_iva_bs_bruto de calcular_totales_documento
    And NO aplica descuento_global (es bruto, el nombre lo dice)

  @EST06-02 @happy
  Scenario: El total neto del documento sigue viniendo de calculos
    When la vista de detalle/PDF calcula totales
    Then usa calcular_totales_documento(...).total_bs_neto (con descuento aplicado)
    And el valor mostrado difiere del bruto cuando hay descuento_global > 0

  @EST06-03 @negative
  Scenario: La property antigua desaparece sin alias
    When evaluo hasattr(nota, "total_documento_bs")
    Then es False
    And no existe alias deprecado que devuelva otro valor con el nombre antiguo

  @EST06-04 @edge
  Scenario: DocumentoCompra recibe el mismo tratamiento
    When consulto compra.total_bs_bruto
    Then delega en calcular_totales_documento con el descuento de la compra

  @EST06-05 @negative
  Scenario: models.py no contiene fórmula duplicada
    When inspecciono el fuente de inventory/models.py
    Then no existe "subtotal_bs + self.total_iva_bs" como fórmula de property
```

### Feature: CSP — Nonces sin unsafe-inline en script-src

```gherkin
@CSP @SEC02b @security
Feature: script-src sin 'unsafe-inline'; cada script inline autorizado por nonce por request

  Background:
    Given Django 6.0.6 con ContentSecurityPolicyMiddleware antes de TenantMiddleware
    And SECURE_CSP con script-src [SELF, NONCE, cdn.tailwindcss.com]
    And style-src conserva 'unsafe-inline' (deuda Tailwind JIT documentada)

  @CSP-01 @happy
  Scenario: La respuesta lleva CSP con nonce y sin unsafe-inline en script-src
    When hago GET a /dashboard/
    Then el header Content-Security-Policy contiene "nonce-"
    And script-src NO contiene 'unsafe-inline'
    And script-src contiene https://cdn.tailwindcss.com

  @CSP-02 @happy
  Scenario: Los 16 scripts inline llevan el nonce del request
    When renderizo cualquier de las 14 plantillas con scripts inline
    Then cada <script> sin src lleva nonce="<valor>"
    And el valor coincide con el nonce del header
    And getCsrfToken() sigue funcional

  @CSP-03 @edge
  Scenario: Dos requests reciben nonces distintos
    When hago dos GET consecutivos a /ventas/
    Then los nonces de ambos headers son diferentes

  @CSP-04 @edge
  Scenario: El 403 del tenant también lleva CSP
    When un usuario autenticado sin empresa en sesión accede a /dashboard/
    Then la respuesta 403 incluye Content-Security-Policy

  @CSP-05 @edge
  Scenario: Modo Report-Only durante la adopción
    Given CSP_REPORT_ONLY=true en el entorno
    When hago GET a cualquier página
    Then el header es Content-Security-Policy-Report-Only
    And el navegador no bloquea scripts

  @CSP-06 @negative
  Scenario: Un script inline nuevo sin nonce queda detectado por el gate
    Given una plantilla nueva con <script> sin nonce
    When ejecuto el test estático de gate
    Then falla con el nombre de la plantilla y la línea

  @CSP-07 @negative
  Scenario: SRI de los recursos externos intacto
    When inspecciono los 4 tags externos (Tailwind CDN en base/login/print/impresion)
    Then conservan integrity y crossorigin sin cambios
```

---

## 4. Archivos Afectados

### 4.1 EST-01 + EST-02 (comparten escape hatch y señales)

| Archivo | Cambio | Tipo |
|---|---|---|
| `inventory/models.py` | Definir excepciones (`KardexProtegidoError`, `DocumentoInmutableError` con base común); QuerySet custom + managers de `MovimientoKardex` (`objects`/`global_objects` con `.update()` bloqueado) | **Modificación** |
| `inventory/kardex_guard.py` (nuevo) o `signals.py` | ContextVar de bypass + `kardex_bypass(motivo)` + receivers `pre_delete`/`pre_save` de kárdex y de los 6 modelos de documento con helper de matriz | **Nuevo** |
| `inventory/apps.py` | `ready()`: conectar señales | **Modificación** |
| `inventory/services.py` | `registrar_movimiento` envuelve su `create` en contexto autorizado; **eliminar `nc.delete()` muerto (2627, 2787)**; refactor NC pre-create (2631/2791 → antes del create) | **Modificación** |
| `inventory/admin.py` | `NotaEntregaAdmin.get_readonly_fields` dinámico (todo readonly si existe obj); `DetalleNotaEntregaInline.can_delete=False`; `DetalleNotaEntregaAdmin` solo lectura | **Modificación** |
| `inventory/management/commands/seed_db.py` | `_clear_all` envuelto en `kardex_bypass("seed_db --clear")` (líneas 499-510) | **Modificación** |
| `inventory/tests.py` | `tests.py:1649` y `:1638` envueltos en bypass (fixtures legítimos) | **Modificación** |
| `inventory/test_cases/test_kardex_inmutable.py`, `test_inmutabilidad_documentos.py` (nuevos) | ~18 tests nuevos | **Nuevo** |
| `docs/ADR.md` | ADR: allowlist del bypass + matriz de inmutabilidad + bypass `.update()` documentado | **Documentación** |

### 4.2 EST-04 (+ anexo EST-05 si se aprueba)

| Archivo | Cambio | Tipo |
|---|---|---|
| `inventory/models.py` | `MovimientoKardex`: RenameField `usuario→usuario_nombre` + FK `usuario` (SET_NULL, related_name `kardex_registrado_por`); `NotaCredito`: ídem (`notas_credito_emitidas`) | **Modificación** |
| `inventory/migrations/0029_usuario_fk_kardex_nc.py` (nuevo) | RenameField + AddField + RunPython backfill (match username → FK; no-match → NULL) | **Migración** |
| `inventory/services.py` | Helper `resolver_usuario(str|User)` único; firmas `str|User`; `reversar_*` aceptan `usuario` opcional (fin del hardcoded `'Sistema'`) | **Modificación** |
| `inventory/views.py` | 8 sitios: pasar `request.user`; deprecar `usuario` por POST en carga masiva (469) y colisión (611) | **Modificación** |
| `inventory/templates/inventory/nota_credito_detalle.html` | Línea 51: `nc.usuario_nombre|default:"Sistema"` | **Modificación** |
| `inventory/test_cases/test_usuario_fk.py` (nuevo) | ~7 tests de resolución/backfill/SET_NULL | **Nuevo** |
| (anexo EST-05) `models.py` + `migrations/0030` + 2 writers (services.py:1713, views.py:1702) | FK + snapshot en `AuditoriaTasa` | **Modificación** |

### 4.3 EST-06

| Archivo | Cambio | Tipo |
|---|---|---|
| `inventory/models.py` | Eliminar `total_documento_bs` en `NotaEntrega` (1699) y `DocumentoCompra` (1185); añadir `total_bs_bruto` delegando en `calculos` | **Modificación** |
| `inventory/tests.py` | Actualizar 6222-6240 al contrato nuevo | **Modificación** |

### 4.4 CSP nonces

| Archivo | Cambio | Tipo |
|---|---|---|
| `a2lt_stock_project/settings.py` | MIDDLEWARE: `inventory.middleware.CspMiddleware` → `django.middleware.security.ContentSecurityPolicyMiddleware` (misma posición); `SECURE_CSP` dict con `CSP.NONCE`; context processor `csp`; env `CSP_REPORT_ONLY`; deprecar `CSP_POLICY` (196-214) | **Modificación** |
| `inventory/middleware.py` | Eliminar `CspMiddleware` (161-181); `TenantMiddleware` se conserva | **Eliminación** |
| 14 plantillas (16 tags inline) | `nonce="{{ csp_nonce }}"` en cada `<script>` sin src: base (×3), articulos, impresion_coordenadas, compras, contactos, catalogo, configuracion, carga, login, notas_credito, reversos, reportes/detalle, movimientos, ventas | **Modificación** |
| `inventory/test_cases/test_security_csp_403.py` | Rework: middleware nativo, igualdad de header → estructura con nonce, test nonces distintos, gate de plantillas | **Modificación** |
| `inventory/test_cases/test_templates_sri.py` | Verificar que sigue verde (SRI no se toca) | **Verificación** |
| `docs/OPERACION.md` | Documentar `CSP_REPORT_ONLY` y el rollback por entorno | **Documentación** |

---

## 5. Riesgos y Mitigaciones

### 5.1 EST-01

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| **Tests que harán ruido (confirmados)**: `tests.py:1649` (`.update(fecha_hora)`) y `:1638` (create directo) rompen al activarse los guards | Cierta | Medio | Migrar ambos al bypass `kardex_bypass(motivo="fixture")` — uso legítimo documentado en la allowlist (REQ-EST01-04). Son los ÚNICOS call-sites (grep completo). |
| `seed_db --clear` (499) bloqueado por `pre_delete` | Cierta | Medio | Envolver `_clear_all` en bypass (REQ-EST01-04). |
| Cascada de `empresa.delete()` con kárdex/documentos bloquea teardowns futuros | Media | Medio | Bypass documentado para teardown; `test_tenant_lifecycle` hoy no tiene kárdex y sigue verde sin cambios. |
| Señales disparándose en cascadas no anticipadas (p. ej. flush de BD de tests) | Baja | Alto | La suite usa rollback transaccional (TestCase), no deletes ORM; verificación: suite completa verde. |
| `pre_save` de modelos históricos en migraciones | Baja | Alto | REQ-EST01-07 + verificación paso 0 (receiver con sender=clase real no recibe señales de históricas). |
| Guard de INSERT rompe un flujo legítimo desconocido | Baja | Alto | Solo existen 2 sitios de creación (verificados); periodo de observación con logs ERROR antes de considerar el guard estable. |

### 5.2 EST-02

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| `nc.delete()` muerto (2627/2787) lanza `pre_delete` y enmascara la excepción original en devoluciones fallidas | Cierta | Alto | Eliminar el código muerto ANTES de conectar los guards (REQ-EST02-05); es no-op dentro de `@transaction.atomic`. |
| Refactor NC pre-create altera los montos de `monto_total_reembolso` | Media | Alto | Cobertura existente: `TestNotasCreditoBackend` (15) + `TestNotasCreditoUI` (14) + test nuevo de igualdad de valores pre/post refactor. |
| Admin: editar un PROCESADO lanza 500 en vez de mensaje amable | Media | Bajo | REQ-EST02-08: readonly dinámico ANTES de conectar guards (el guard es backstop, el admin es UX). |
| Superusuario pierde la capacidad de "arreglar a mano" un documento | Cierta | Medio | Decisión deliberada (invariante fiscal); el escape hatch existe pero queda fuera del admin por diseño. Documentar en ADR. |
| `.update()` sobre documentos no queda cubierto en fase 1 | — | Medio | **Bypass aceptado y documentado** (0 usos hoy en services/views; superficie: shell). Fase 2 opcional (§6.3). |
| Tests que re-saven documentos PROCESADO sin cambios | Baja | Bajo | El guard compara contra original: saves idempotentes pasan (REQ-EST02-03). |

### 5.3 EST-04

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Backfill con usernames que no matchean (`'seed_db'`, `'Sistema'`, ~60 literales de tests) | Cierta | Bajo | Es el comportamiento ESPECIFICADO (FK NULL + snapshot); REQ-EST04-04 audita el % real antes de migrar. |
| `related_name` colisiona con `Empresa.movimientos_kardex` (models.py:1336) | Cierta si se ignora | Medio | REQ-EST04-01 fija nombres distintos (`kardex_registrado_por`, `notas_credito_emitidas`). |
| Rotura de firmas en los ~60 call-sites de tests | Media | Alto | REQ-EST04-05: resolución `str|User` con compatibilidad total — ningún test se toca. |
| Migración no reversible | Baja | Alto | `RenameField` es reversible; el backfill RunPython lleva `reverse_code` que limpia la FK (el snapshot nunca se toca al volver atrás). |
| Vista de NC muestra `None` tras renombrar | Cierta si se ignora | Bajo | REQ-EST04-09: template pasa a `usuario_nombre|default:"Sistema"`. |

### 5.4 EST-06

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Un consumidor oculto de la property (eval dinámico, template remoto) | Baja | Bajo | Grep exhaustivo: solo 2 tests (6231/6240) — huérfana confirmada. |
| Regresión en los 5 call-sites de calculos por touch accidental | Baja | Medio | Esta spec NO toca `calculos.py`; tests de vista existentes cubren pantalla/PDF. |

### 5.5 CSP

| Riesgo | Prob. | Impacto | Mitigación |
|---|---|---|---|
| Un `<script>` inline sin nonce rompe el JS de esa página al activar enforcing | Media | Alto | Gate estático (REQ-CSP-05) + ventana Report-Only (REQ-CSP-06) + navegación manual de las 7 vistas con JS. |
| `test_security_csp_403.py:301` (igualdad exacta) rompe | Cierta | Bajo | Rework planificado (REQ-CSP-08). |
| Alguien depende de `CSP_POLICY` por env en un despliegue | Baja | Medio | Deprecación documentada (REQ-CSP-07) + knob `CSP_REPORT_ONLY` como palanca nueva. |
| Tailwind CDN JIT necesita style-inline | Cierta | — | style-src conserva `'unsafe-inline'` (deuda documentada hasta build de Tailwind). |
| Caching futuro publica nonces repetidos | Baja | Medio | REQ-CSP-09: advertencia documentada; hoy no hay caching de páginas. |
| Middleware nativo no disponible en el 6.0.6 instalado | Baja | Alto | Verificación paso 0 (import en venv real) ANTES de tareas de plantillas; fallback: extender `CspMiddleware` propio (opción original (a)). |

---

## 6. Preguntas Abiertas / Decisiones que Exige el Usuario

Disyuntivas de diseño que NO se cierran con evidencia técnica sola (la evidencia se incluye; la decisión es del usuario). **Recomendación del arquitecto** en cada una.

### 6.1 EST-01 — Dureza del enforcement: señales vs triggers SQL vs mixto
- **(a) Señales + guard de QuerySet (RECOMENDADO)**: `pre_delete` cubre instancia+bulk+cascada (doc oficial); el QuerySet custom cierra `.update()`; el escape hatch habilita la allowlist. Todo vive en Python, testeable, 0 migraciones.
- **(b) Triggers SQL SQLite (`CREATE TRIGGER ... RAISE(ABORT)`)**: máxima dureza (bloquea hasta SQL crudo), pero exige migración `RunSQL`, complica el teardown legítimo de tenants y los tests, y el proyecto tiene 0 SQL crudo (el vector que cierra no existe). Complejidad de test alta.
- **(c) Mixto**: señales ahora + triggers como fase futura si aparece SQL crudo.
- **Evidencia**: docs.djangoproject.com/en/6.0 (señales en bulk/cascada; `.update()` sin señales); grep: 0 usos de `.raw()`/`.extra()`/`cursor.execute` en el proyecto.

### 6.2 EST-01 — ¿Incluir el guard de creación (INSERT directo)?
- **Sí (RECOMENDADO)**: completa la Regla Sagrada en ambas direcciones; solo 2 sitios de creación existen hoy (1 legítimo + 1 fixture), el ruido es mínimo.
- **No**: limita EST-01 a DELETE/UPDATE (lo que el informe audita literalmente); el INSERT directo queda como hueco documentado.

### 6.3 EST-02 — ¿Fase 2 (guard `.update()` en los 6 modelos de documento)?
- **Diferir (RECOMENDADO)**: 0 usos de `.update()` sobre documentos en el código; fase 1 (señales) + bypass documentado + admin cerrado cubre los vectores reales. La fase 2 puede añadirse después con el mismo patrón EST-01 si aparece el vector.
- **Incluir ahora**: +2-3h, cierre total del bypass con coste de tocar los managers de 6 modelos.

### 6.4 EST-02 — ¿Admin totalmente readonly para documentos emitidos?
- **Sí (RECOMENDADO)**: hoy un superusuario puede "anular" una NE desde el admin SIN reversar stock (corrupción silenciosa de kárdex). El guard hará 500 si se intenta; el readonly es la UX correcta.
- **No**: mantener `estado`/`motivo_anulacion` editables en admin (requeriría eximir el par en el guard y aceptar anulaciones sin contramovimientos).

### 6.5 EST-02 — ¿Refactor NC pre-create o allowlist de `monto_total_reembolso`?
- **Refactor (RECOMENDADO)**: la NC queda inmutable desde su nacimiento; matriz homogénea; ~30-60 min de refactor con 29 tests NC existentes como red de seguridad.
- **Allowlist**: la matriz de `NotaCredito` gana el campo (hueco documentado: el monto de reembolso sería editable con `.save()`).

### 6.6 EST-06 — ¿Renombrar+delegar o eliminar la property?
- **Renombrar a `total_bs_bruto` + delegar (RECOMENDADO)**: conserva una API de conveniedad honesta; cumple el mandato de fuente única (DATA-01).
- **Eliminar del todo**: es huérfana (solo 2 tests); menos superficie. Ambas son honestas; eliminar es más drástico.

### 6.7 EST-04 — ¿Deprecar `usuario` por POST y añadirlo a `reversar_*`?
- **Ambos SÍ (RECOMENDADO)**: un campo de formulario no puede ser fuente forense (cualquiera escribe "admin"); los reversos deben registrar quién anuló (hoy hardcodean `'Sistema'`).
- **Alternativa**: mantener el POST (compatibilidad con operadores que registran a un tercero) — en ese caso el valor del POST va al snapshot, nunca a la FK.

### 6.8 CSP — ¿Django nativo vs django-csp vs extender el middleware propio?
- **Django 6.0 nativo (RECOMENDADO)**: trae middleware, nonces, Report-Only y context processor; cero dependencias nuevas (regla del producto); reemplaza código propio por soporte upstream. Verificado en doc oficial 6.0 (§8).
- **django-csp**: dependencia nueva; ⚠️ no está indexado en context7; aporta lo mismo que el nativo en 6.0 — no hay razón para añadirlo.
- **Extender `CspMiddleware` propio**: viable pero reimplementa (nonce por request con `secrets`, inyección en header, context processor manual) lo que Django 6.0 ya resuelve; más código propio que mantener.

### 6.9 CSP — ¿Ventana Report-Only antes de enforcing?
- **Sí (RECOMENDADO)**: knob `CSP_REPORT_ONLY` por entorno; flip a enforcing tras navegación manual de las 7 vistas con JS; rollback = revertir el env.
- **No**: enforcing directo (más rápido, riesgo de JS roto en producción interna).

### 6.10 EST-05 — ¿Incluir el anexo ahora?
- **Incluirlo (RECOMENDADO)**: mismo patrón que EST-04 ya implementado, 2 writers, ~2h, cierra el último hueco forense (quién movió la tasa que fija precios).
- **Diferir**: queda en el backlog P3 del auditor.

---

## 7. Estimación de Esfuerzo y Orden de Implementación

### 7.1 Estimación por fix

| Fix | Esfuerzo | Migraciones | Tests nuevos (aprox.) |
|---|---|---|---|
| EST-06 | S — 1-2 h | 0 | 3 |
| CSP nonces | M — 6-8 h | 0 | 6 (rework de 4 + gate) |
| EST-04 | M — 6-8 h | `0029` | 7 |
| EST-01 | M — 4-6 h | 0 | 8 |
| EST-02 | M-L — 8-12 h | 0 | 10 |
| Anexo EST-05 (si se aprueba) | S — 2 h | `0030` | 3 |
| **Total** | **25-36 h** (+2 h anexo) | 1-2 | ~34-37 |

### 7.2 Orden sugerido y dependencias

```
1. EST-06 (warmup, sin dependencias, riesgo nulo)
2. CSP nonces (independiente: settings + plantillas; verificación paso 0 del middleware nativo)
3. EST-04 (esquema de kárdex ANTES de los guards)
4. EST-01 (guards sobre el kárdex ya migrado; introduce el escape hatch reutilizable)
   └─ (4b) Anexo EST-05 inmediatamente después, si se aprueba (reutiliza el patrón 3/4)
5. EST-02 (patrón de señales ya probado en 4; dead code + admin + refactor NC)
```

**Convivencia EST-01 ↔ EST-04 (por qué EST-04 va primero)**: ambos tocan `MovimientoKardex`. EST-04 cambia el esquema (`usuario` → FK + snapshot) y las firmas de `registrar_movimiento`; EST-01 añade el `pre_save` que intercepta la creación del servicio. Hacer EST-01 primero obligaría a re-trabajar el contexto autorizado del guard con el esquema nuevo (doble rework de los mismos tests). EST-04 primero deja el esquema estable; EST-01 entonces cablea el guard una sola vez.

**El escape hatch de EST-01 es la pieza compartida**: EST-02 lo reutiliza para `seed_db --clear` y teardowns (mismo bypass, misma allowlist) — se diseña una vez en EST-01.

**Regla de integración por fix** (verificabilidad inmediata): cada fix termina con `python manage.py test inventory` verde y `makemigrations --check` limpio; ningún fix se mezcla en la rama con tests rojos.

---

## 8. Referencias de Documentación (context7 — evidencia de las decisiones)

1. **Señales en bulk delete / bypass de update()** — Django 6.0 oficial:
   - https://docs.djangoproject.com/en/6.0/ref/signals/#pre-delete — *"Sent at the beginning of a model's delete() method and a queryset's delete() method."*
   - https://docs.djangoproject.com/en/6.0/ref/models/querysets/#update — *"…applied instantly and does not call save() on models or emit pre_save/post_save signals."*
   - https://docs.djangoproject.com/en/6.0/topics/db/models — *"The delete() method for an object is not necessarily called when deleting objects in bulk using a QuerySet or as a result of a cascading delete. To ensure customized delete logic gets executed, you can use pre_delete and/or post_delete signals."*
2. **CSP nativo de Django 6.0** — decisión §6.8:
   - https://docs.djangoproject.com/en/6.0/releases/6.0/ — *"…headers are added via the ContentSecurityPolicyMiddleware, nonces are supported through the csp() context processor, and policies are configured using the SECURE_CSP and SECURE_CSP_REPORT_ONLY settings."*
   - https://docs.djangoproject.com/en/6.0/ref/csp/ — *"Django supports nonces as a secure way to allow specific inline <script> or <style> elements to execute without relying on 'unsafe-inline'."*
3. **django-csp** — ⚠️ no indexado en context7; evaluado con conocimiento previo (nonce middleware + settings `CSP_SCRIPT_SRC`); descartado frente al nativo de 6.0.

---

## Gate G1: Aprobación Requerida

> **⚠️ ESTE SPEC REQUIERE APROBACIÓN EXPLÍCITA ANTES DE CONTINUAR** con `/gherkin`, `/plan` y `/tasks`.
>
> **Decisiones que exige el usuario antes de aprobar** (ver §6, resumen):
> 1. Dureza EST-01: señales+QuerySet (rec.) / triggers SQL / mixto — §6.1
> 2. Guard de INSERT directo en kárdex: sí (rec.) / no — §6.2
> 3. EST-02 fase 2 (`.update()` en documentos): diferir (rec.) / incluir — §6.3
> 4. Admin readonly total de documentos emitidos: sí (rec.) / no — §6.4
> 5. NC: refactor pre-create (rec.) / allowlist monto — §6.5
> 6. EST-06: renombrar+delegar (rec.) / eliminar — §6.6
> 7. EST-04: deprecar usuario por POST + usuario en reversos (rec.) — §6.7
> 8. CSP: Django 6 nativo (rec.) / django-csp / middleware propio — §6.8
> 9. CSP: ventana Report-Only (rec.) / enforcing directo — §6.9
> 10. Anexo EST-05: incluir (rec., +2 h) / diferir — §6.10
>
> Una vez revisado, responda con **"APROBADO"** (o indique los cambios por pregunta: "APROBADO con 6.3 incluir, 6.10 diferir…").

