# Spec: Fixes P1 - SEC-02 + EST-03 + DATA-09 + DATA-10

## 1. Contexto y Alcance

### Proyecto
- **Framework**: Django 6.0.6 multi-tenant on-premise
- **Base de datos**: SQLite WAL mode
- **Python**: 3.14
- **OS**: Windows
- **Commit auditado**: `9a65224` (HEAD, post P0 fixes)
- **Suite de tests**: 368 tests OK (6 skipped)

### Fixes P1 a implementar

| ID | Título | Severidad | Archivo | Línea |
|----|--------|-----------|---------|-------|
| SEC-02 | CSRF_COOKIE_HTTPONLY=False + DEBUG=True en .env | ALTA | `a2lt_stock_project/settings.py`, `.env` | 246, 8 |
| EST-03 | Correlativos Max+1 sin lock + UniqueConstraint NotaCredito | ALTA | `inventory/models.py` | 1458-1489, 960-991, 1874-1888 |
| DATA-09 | Moneda.es_base constraint único por tenant | ALTA | `inventory/models.py` | 2051-2058 |
| DATA-10 | TasaCambio unique constraint | BAJA | `inventory/models.py` | 2096-2102 |

---

## 2. Requisitos Funcionales (EARS)

### SEC-02: CSRF_COOKIE_HTTPONLY=True + DEBUG controlado por entorno

**UBICACIÓN**: `a2lt_stock_project/settings.py:246`, `.env:8`

#### REQ-SEC02-01: CSRF_COOKIE_HTTPONLY habilitado
**CUANDO** la aplicación se ejecuta en cualquier entorno  
**ENTONCES** `CSRF_COOKIE_HTTPONLY` DEBE ser `True`  
**Y** el token CSRF NO DEBE ser accesible desde JavaScript via `document.cookie`

#### REQ-SEC02-02: Token CSRF disponible en DOM para JavaScript
**EL** template base DEBE incluir una meta tag con el token CSRF:  
`<meta name="csrf-token" content="{{ csrf_token }}">`  
**EL** JavaScript DEBE leer el token via:  
`document.querySelector('meta[name=csrf-token]').getAttribute('content')`

#### REQ-SEC02-03: DEBUG controlado exclusivamente por variable de entorno
**CUANDO** la variable de entorno `DEBUG` no está definida  
**ENTONCES** `DEBUG` DEBE ser `False` (default seguro)  
**CUANDO** `DEBUG=True` en `.env`  
**ENTONCES** solo aplica para desarrollo local explícito  
**EL** archivo `.env` de desarrollo PUEDE tener `DEBUG=True`  
**PERO** cualquier despliegue real DEBE tener `DEBUG=False` en variables de entorno

#### REQ-SEC02-04: Settings de seguridad coherentes con DEBUG=False
**CUANDO** `DEBUG=False`  
**ENTONCES** se activan automáticamente:  
- `SECURE_BROWSER_XSS_FILTER = True`  
- `SECURE_CONTENT_TYPE_NOSNIFF = True`  
- `X_FRAME_OPTIONS = 'DENY'`  
- `SESSION_COOKIE_SECURE = SECURE_SSL_REDIRECT`  
- `CSRF_COOKIE_SECURE = SECURE_SSL_REDIRECT`  
- HSTS si `SECURE_SSL_REDIRECT=True`

---

### EST-03: Correlativos con lock + UniqueConstraint en NotaCredito

**UBICACIÓN**: `inventory/models.py` — `NotaEntrega.save()` (1458-1489), `DocumentoCompra.save()` (960-991), `NotaCredito._next_correlativo()` (1874-1888), `NotaCredito.Meta` (1833-1844)

#### REQ-EST03-01: Eliminar race condition en correlativos (Max+1)
**EL** patrón `Max('numero') + 1` en `save()` DEBE ser reemplazado  
**LOS** servicios que crean documentos DEBEN usar `select_for_update()` sobre una tabla de correlativos  
**O** una tabla dedicada `Correlativo` con `select_for_update` por empresa + tipo de documento

#### REQ-EST03-02: Tabla Correlativo para gestión atómica
**SE** introduce modelo `Correlativo` con campos:  
- `empresa` (FK)  
- `tipo_documento` (CharField: 'NOTA_ENTREGA', 'FACTURA_COMPRA', 'NOTA_CREDITO')  
- `ultimo_numero` (PositiveIntegerField)  
- `UniqueConstraint(empresa, tipo_documento)`

**EL** método para obtener siguiente número:  
```python
with transaction.atomic():
    corr = Correlativo.objects.select_for_update().get(empresa=empresa, tipo_documento=tipo)
    corr.ultimo_numero += 1
    corr.save()
    return corr.ultimo_numero
```

#### REQ-EST03-03: Retry con backoff exponencial en IntegrityError
**CUANDO** ocurre `IntegrityError` por duplicado de correlativo  
**ENTONCES** reintentar hasta 3 veces con backoff: 50ms, 100ms, 200ms  
**SI** falla tras 3 intentos, propagar excepción

#### REQ-EST03-04: UniqueConstraint en NotaCredito para (empresa, numero)
**EL** modelo `NotaCredito` DEBE tener:  
```python
constraints = [
    models.UniqueConstraint(
        fields=['empresa', 'numero'],
        name='unique_nota_credito_numero_per_empresa',
    ),
    models.UniqueConstraint(
        fields=['empresa', 'numero_control'],
        condition=~models.Q(numero_control=''),
        name='unique_nota_credito_numero_control_per_empresa',
    ),
    # CheckConstraint existente se mantiene
]
```

#### REQ-EST03-05: Migraciones generadas y aplicables
**LAS** migraciones DEBEN generarse con `makemigrations` sin conflictos  
**LA** migración DEBE ser reversible

---

### DATA-09: Moneda.es_base constraint único por tenant a nivel BD

**UBICACIÓN**: `inventory/models.py:2051-2058` (`Moneda.save()`), `Moneda.Meta` (2042-2046)

#### REQ-DATA09-01: UniqueConstraint condicional en BD
**EL** modelo `Moneda` DEBE tener en `Meta.constraints`:  
```python
models.UniqueConstraint(
    fields=['empresa'],
    condition=models.Q(es_base=True),
    name='una_moneda_base_por_empresa',
)
```

#### REQ-DATA09-02: Eliminar lógica de enforcamiento en save()
**EL** método `save()` actual que hace `qs.update(es_base=False)` DEBE ser eliminado  
**LA** integridad DEBE ser garantizada por la BD, no por código de aplicación  
**ESTO** elimina la race condition donde dos hilos concurrentes pueden dejar 2 monedas base

#### REQ-DATA09-03: unique_together existente se mantiene
**EL** `unique_together = [('empresa', 'codigo')]` DEBE mantenerse  
**EL** nuevo constraint es adicional, no sustitutivo

---

### DATA-10: TasaCambio unique constraint por (empresa, moneda_origen, moneda_destino, fecha)

**UBICACIÓN**: `inventory/models.py:2096-2102` (`TasaCambio.Meta`)

#### REQ-DATA10-01: UniqueConstraint en TasaCambio
**EL** modelo `TasaCambio` DEBE tener en `Meta.constraints`:  
```python
models.UniqueConstraint(
    fields=['empresa', 'moneda_origen', 'moneda_destino', 'fecha'],
    name='unique_tasa_par_fecha',
)
```

#### REQ-DATA10-02: Index existente se mantiene
**EL** `Index(fields=['empresa', 'moneda_origen', 'moneda_destino', '-fecha'])` DEBE mantenerse  
**EL** constraint es adicional para integridad; el index es para performance de consultas

---

## 3. Criterios de Aceptación (Gherkin)

### Feature: SEC-02 - CSRF_COOKIE_HTTPONLY y DEBUG seguro

```gherkin
@SEC02 @P1 @security
Feature: CSRF cookie HttpOnly y DEBUG controlado por entorno

  Background:
    Given un proyecto Django configurado
    And settings.py carga CSRF_COOKIE_HTTPONLY y DEBUG desde entorno

  @SEC02-01 @csrf-httponly
  Scenario: CSRF_COOKIE_HTTPONLY es True en todos los entornos
    When inspecciono settings.py
    Then CSRF_COOKIE_HTTPONLY == True

  @SEC02-02 @csrf-token-dom
  Scenario: Token CSRF disponible en meta tag del template base
    Given un template que extiende base.html
    When renderizo la página
    Then el HTML contiene <meta name="csrf-token" content="{{ csrf_token }}">

  @SEC02-03 @js-reads-csrf
  Scenario: JavaScript lee token CSRF desde meta tag
    Given una página renderizada con meta tag csrf-token
    When ejecuto document.querySelector('meta[name=csrf-token]').getAttribute('content')
    Then obtengo el token CSRF válido
    And no uso document.cookie para leerlo

  @SEC02-04 @debug-default-false
  Scenario: DEBUG default es False sin variable de entorno
    Given no existe variable de entorno DEBUG
    When cargo settings.py
    Then DEBUG == False

  @SEC02-05 @debug-env-override
  Scenario: DEBUG=True solo si variable de entorno lo establece explícitamente
    Given variable de entorno DEBUG=True
    When cargo settings.py
    Then DEBUG == True

  @SEC02-06 @security-headers-activated
  Scenario: Headers de seguridad se activan cuando DEBUG=False
    Given DEBUG=False
    When cargo settings.py
    Then SECURE_BROWSER_XSS_FILTER == True
    And SECURE_CONTENT_TYPE_NOSNIFF == True
    And X_FRAME_OPTIONS == 'DENY'
    And SESSION_COOKIE_SECURE == SECURE_SSL_REDIRECT
    And CSRF_COOKIE_SECURE == SECURE_SSL_REDIRECT

  @SEC02-07 @env-file-dev-only
  Scenario: Archivo .env de desarrollo puede tener DEBUG=True
    Given archivo .env contiene DEBUG=True
    And estoy en máquina de desarrollo
    When cargo settings.py
    Then DEBUG == True
    And esto NO afecta a producción (que usa variables de entorno reales)
```

### Feature: EST-03 - Correlativos atómicos y UniqueConstraint NotaCredito

```gherkin
@EST03 @P1 @data-integrity
Feature: Correlativos sin race condition y constraints únicos en NotaCredito

  Background:
    Given una empresa configurada
    And ConfiguracionEmpresa con correlativos iniciales definidos

  @EST03-01 @correlativo-atomic
  Scenario: Obtener siguiente correlativo es atómico con select_for_update
    Given modelo Correlativo existe con ultimo_numero=5 para NOTA_ENTREGA
    When dos hilos concurrentes llaman obtener_siguiente_correlativo(empresa, 'NOTA_ENTREGA')
    Then uno obtiene 6 y el otro obtiene 7
    And no hay duplicados
    And no hay IntegrityError por race condition

  @EST03-02 @correlivo-retry
  Scenario: Retry con backoff en IntegrityError
    Given una condición de carrera extrema causa IntegrityError
    When el código reintenta con backoff 50ms, 100ms, 200ms
    Then en el segundo intento tiene éxito
    And se registra log de reintento

  @EST03-03 @nota-credito-unique-numero
  Scenario: NotaCredito exige (empresa, numero) único
    Given existe NotaCredito(empresa=1, numero=1)
    When intento crear NotaCredito(empresa=1, numero=1)
    Then lanza IntegrityError
    And el mensaje referencia constraint 'unique_nota_credito_numero_per_empresa'

  @EST03-04 @nota-credito-unique-numero-control
  Scenario: NotaCredito exige (empresa, numero_control) único cuando no vacío
    Given existe NotaCredito(empresa=1, numero_control='NC-00000001')
    When intento crear NotaCredito(empresa=1, numero_control='NC-00000001')
    Then lanza IntegrityError
    And el mensaje referencia constraint 'unique_nota_credito_numero_control_per_empresa'

  @EST03-05 @nota-credito-empty-numero-control-allowed
  Scenario: numero_control vacío permite múltiples registros (condition)
    Given existe NotaCredito(empresa=1, numero_control='')
    When intento crear otra NotaCredito(empresa=1, numero_control='')
    Then NO lanza IntegrityError (condition ~Q(numero_control='') lo permite)
    # NOTA: numero_control se auto-genera en save(), así que este caso es teórico

  @EST03-06 @nota-entrega-correlativo-atomic
  Scenario: NotaEntrega usa Correlativo para generar numero
    Given Correlativo(empresa=1, tipo='NOTA_ENTREGA', ultimo_numero=10)
    When creo NotaEntrega via services.procesar_venta()
    Then numero = 11
    And Correlativo.ultimo_numero = 11

  @EST03-07 @documento-compra-correlativo-atomic
  Scenario: DocumentoCompra usa Correlativo para generar numero
    Given Correlativo(empresa=1, tipo='FACTURA_COMPRA', ultimo_numero=5)
    When creo DocumentoCompra via services.registrar_compra_proveedor()
    Then numero = 6
    And Correlativo.ultimo_numero = 6
```

### Feature: DATA-09 - Moneda base única por tenant (constraint BD)

```gherkin
@DATA09 @P1 @data-integrity
Feature: Constraint único de moneda base por empresa a nivel de base de datos

  Background:
    Given una empresa configurada
    And modelo Moneda con constraint una_moneda_base_por_empresa

  @DATA09-01 @unique-base-currency
  Scenario: Solo una moneda con es_base=True por empresa
    Given existe Moneda(empresa=1, codigo='USD', es_base=True)
    When intento crear Moneda(empresa=1, codigo='VES', es_base=True)
    Then lanza IntegrityError
    And el mensaje referencia constraint 'una_moneda_base_por_empresa'

  @DATA09-02 @multiple-companies-independent
  Scenario: Empresas diferentes pueden tener su propia moneda base
    Given existe Moneda(empresa=1, codigo='USD', es_base=True)
    When creo Moneda(empresa=2, codigo='VES', es_base=True)
    Then se crea exitosamente
    And ambas empresas tienen su moneda base

  @DATA09-03 @non-base-currencies-unlimited
  Scenario: Múltiples monedas no-base permitidas por empresa
    Given existe Moneda(empresa=1, codigo='USD', es_base=True)
    When creo Moneda(empresa=1, codigo='VES', es_base=False)
    And creo Moneda(empresa=1, codigo='EUR', es_base=False)
    Then ambas se crean exitosamente

  @DATA09-04 @save-no-longer-enforces
  Scenario: Método save() ya no hace qs.update(es_base=False)
    When inspecciono Moneda.save()
    Then no hay lógica que desactive es_base en otras monedas
    And la integridad depende 100% del constraint de BD

  @DATA09-05 @concurrent-safe
  Scenario: Dos hilos concurrentes creando moneda base - BD decide
    Given no hay moneda base para empresa=1
    When hilo A crea Moneda(empresa=1, codigo='USD', es_base=True)
    And hilo B crea Moneda(empresa=1, codigo='VES', es_base=True) simultáneamente
    Then exactamente una tiene éxito
    And la otra lanza IntegrityError
    And no hay estado intermedio con dos monedas base
```

### Feature: DATA-10 - TasaCambio unique constraint

```gherkin
@DATA10 @P1 @data-integrity
Feature: TasaCambio único por (empresa, moneda_origen, moneda_destino, fecha)

  Background:
    Given una empresa configurada
    And monedas USD y VES creadas para la empresa
    And modelo TasaCambio con constraint unique_tasa_par_fecha

  @DATA10-01 @unique-rate-per-day
  Scenario: Una sola tasa por par de monedas por fecha por empresa
    Given existe TasaCambio(empresa=1, origen=USD, destino=VES, fecha='2026-10-19', tasa=36.5)
    When intento crear TasaCambio(empresa=1, origen=USD, destino=VES, fecha='2026-10-19', tasa=37.0)
    Then lanza IntegrityError
    And el mensaje referencia constraint 'unique_tasa_par_fecha'

  @DATA10-02 @different-date-allowed
  Scenario: Fechas diferentes permiten tasas diferentes
    Given existe TasaCambio(empresa=1, origen=USD, destino=VES, fecha='2026-10-19', tasa=36.5)
    When creo TasaCambio(empresa=1, origen=USD, destino=VES, fecha='2026-10-20', tasa=37.0)
    Then se crea exitosamente

  @DATA10-03 @different-pair-allowed
  Scenario: Pares de monedas diferentes permitidos en misma fecha
    Given existe TasaCambio(empresa=1, origen=USD, destino=VES, fecha='2026-10-19')
    When creo TasaCambio(empresa=1, origen=EUR, destino=VES, fecha='2026-10-19')
    Then se crea exitosamente

  @DATA10-04 @different-company-allowed
  Scenario: Empresas diferentes pueden tener misma tasa mismo día
    Given existe TasaCambio(empresa=1, origen=USD, destino=VES, fecha='2026-10-19', tasa=36.5)
    When creo TasaCambio(empresa=2, origen=USD, destino=VES, fecha='2026-10-19', tasa=37.0)
    Then se crea exitosamente

  @DATA10-05 @index-preserved
  Scenario: Index para consultas por fecha descendente se mantiene
    When inspecciono TasaCambio.Meta.indexes
    Then existe Index(fields=['empresa', 'moneda_origen', 'moneda_destino', '-fecha'])
```

---

## 4. Archivos Afectados

### SEC-02: CSRF + DEBUG

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `a2lt_stock_project/settings.py` | Línea 246: Cambiar `CSRF_COOKIE_HTTPONLY = False` → `True` | **Modificación** |
| `a2lt_stock_project/settings.py` | Verificar lógica DEBUG (línea 39) ya correcta: `os.environ.get('DEBUG', 'False').lower() == 'true'` | **Verificación** |
| `templates/base.html` | Agregar `<meta name="csrf-token" content="{{ csrf_token }}">` en `<head>` | **Modificación** |
| `static/js/` (archivos JS que usan CSRF) | Cambiar lectura de cookie a `document.querySelector('meta[name=csrf-token]').getAttribute('content')` | **Modificación** |
| `.env` | Línea 8: Cambiar `DEBUG=True` → `DEBUG=False` (documentar que dev local puede sobrescribir) | **Modificación** |
| `docs/SETUP.md` / `README.md` | Documentar que `DEBUG=False` es obligatorio en producción | **Documentación** |

### EST-03: Correlativos + NotaCredito constraints

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `inventory/models.py` | Agregar modelo `Correlativo` (nueva clase) | **Nuevo modelo** |
| `inventory/models.py` | `NotaEntrega.save()`: delegar a `Correlativo.get_next(empresa, 'NOTA_ENTREGA')` | **Modificación** |
| `inventory/models.py` | `DocumentoCompra.save()`: delegar a `Correlativo.get_next(empresa, 'FACTURA_COMPRA')` | **Modificación** |
| `inventory/models.py` | `NotaCredito._next_correlativo()`: delegar a `Correlativo.get_next(empresa, 'NOTA_CREDITO')` | **Modificación** |
| `inventory/models.py` | `NotaCredito.Meta.constraints`: agregar 2 UniqueConstraint | **Modificación** |
| `inventory/services.py` | Funciones `procesar_venta`, `registrar_compra_proveedor`, `procesar_devolucion_*` usan nuevo flujo | **Modificación** |
| `inventory/migrations/0019_*.py` | Migración auto-generada para Correlativo + constraints NotaCredito | **Migración** |

### DATA-09: Moneda constraint

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `inventory/models.py` | `Moneda.Meta.constraints`: agregar `UniqueConstraint` condicional | **Modificación** |
| `inventory/models.py` | `Moneda.save()`: eliminar lógica `qs.update(es_base=False)` (líneas 2051-2058) | **Eliminación** |
| `inventory/migrations/0020_*.py` | Migración para constraint condicional | **Migración** |

### DATA-10: TasaCambio constraint

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `inventory/models.py` | `TasaCambio.Meta.constraints`: agregar `UniqueConstraint` | **Modificación** |
| `inventory/migrations/0021_*.py` | Migración para constraint | **Migración** |

---

## 5. Plan de Tests (TDD)

### Tests para SEC-02

| Test ID | Archivo | Descripción |
|---------|---------|-------------|
| `test_sec02_csrf_cookie_httponly_true` | `tests/test_security.py` | `settings.CSRF_COOKIE_HTTPONLY == True` |
| `test_sec02_base_template_has_csrf_meta_tag` | `tests/test_security.py` | `base.html` contiene meta tag csrf-token |
| `test_sec02_js_reads_csrf_from_meta` | `tests/test_security.py` | Test E2E con Playwright: JS lee token desde meta |
| `test_sec02_debug_default_false` | `tests/test_security.py` | Sin env DEBUG → settings.DEBUG == False |
| `test_sec02_debug_env_override` | `tests/test_security.py` | Con DEBUG=True en env → settings.DEBUG == True |
| `test_sec02_security_headers_when_debug_false` | `tests/test_security.py` | Headers de seguridad activos con DEBUG=False |
| `test_sec02_env_file_debug_true_dev_only` | `tests/test_security.py` | `.env` local con DEBUG=True funciona en dev |

### Tests para EST-03

| Test ID | Archivo | Descripción |
|---------|---------|-------------|
| `test_est03_correlativo_model_exists` | `tests/test_models_correlativo.py` | Modelo Correlativo creado con campos correctos |
| `test_est03_correlativo_unique_constraint` | `tests/test_models_correlativo.py` | UniqueConstraint(empresa, tipo_documento) funciona |
| `test_est03_get_next_correlativo_atomic` | `tests/test_models_correlativo.py` | `Correlativo.get_next()` usa select_for_update |
| `test_est03_concurrent_correlativo_no_duplicates` | `tests/test_models_correlativo.py` | Simular concurrencia: no duplicados (test skipped en SQLite, documentado) |
| `test_est03_retry_backoff_on_integrity_error` | `tests/test_models_correlativo.py` | Retry 3 veces con backoff 50/100/200ms |
| `test_est03_nota_entrega_uses_correlativo` | `tests/test_services_ventas.py` | `procesar_venta` genera numero via Correlativo |
| `test_est03_documento_compra_uses_correlativo` | `tests/test_services_compras.py` | `registrar_compra_proveedor` usa Correlativo |
| `test_est03_nota_credito_uses_correlativo` | `tests/test_services_notas_credito.py` | `procesar_devolucion_*` usa Correlativo |
| `test_est03_nota_credito_unique_numero` | `tests/test_models_nota_credito.py` | Constraint unique_nota_credito_numero_per_empresa |
| `test_est03_nota_credito_unique_numero_control` | `tests/test_models_nota_credito.py` | Constraint unique_nota_credito_numero_control_per_empresa |
| `test_est03_nota_credito_empty_numero_control_condition` | `tests/test_models_nota_credito.py` | Condition ~Q(numero_control='') permite vacíos |

### Tests para DATA-09

| Test ID | Archivo | Descripción |
|---------|---------|-------------|
| `test_data09_moneda_unique_base_constraint` | `tests/test_models_moneda.py` | Constraint una_moneda_base_por_empresa existe |
| `test_data09_only_one_base_per_empresa` | `tests/test_models_moneda.py` | IntegrityError al crear 2da moneda base misma empresa |
| `test_data09_different_empresas_independent` | `tests/test_models_moneda.py` | Empresas distintas pueden tener base propia |
| `test_data09_non_base_unlimited` | `tests/test_models_moneda.py` | Múltiples monedas no-base permitidas |
| `test_data09_save_no_longer_enforces` | `tests/test_models_moneda.py` | `Moneda.save()` no tiene lógica qs.update |
| `test_data09_concurrent_base_creation_db_decides` | `tests/test_models_moneda.py` | Concurrencia: BD decide ganador (test skipped en SQLite) |

### Tests para DATA-10

| Test ID | Archivo | Descripción |
|---------|---------|-------------|
| `test_data10_tasacambio_unique_constraint` | `tests/test_models_tasacambio.py` | Constraint unique_tasa_par_fecha existe |
| `test_data10_unique_per_pair_per_date` | `tests/test_models_tasacambio.py` | IntegrityError duplicado mismo par misma fecha |
| `test_data10_different_date_allowed` | `tests/test_models_tasacambio.py` | Fechas distintas OK |
| `test_data10_different_pair_allowed` | `tests/test_models_tasacambio.py` | Pares distintos misma fecha OK |
| `test_data10_different_empresa_allowed` | `tests/test_models_tasacambio.py` | Empresas distintas OK |
| `test_data10_index_preserved` | `tests/test_models_tasacambio.py` | Index para consultas descendentes se mantiene |

### Cobertura mínima requerida
- **SEC-02**: 100% ramas (config + template + JS)
- **EST-03**: 100% ramas Correlativo (éxito, retry, fallo tras 3) + 100% constraints NotaCredito
- **DATA-09**: 100% constraint BD + verificación eliminación código save()
- **DATA-10**: 100% constraint combinaciones válidas/inválidas
- **Global**: Mantener ≥ 80% cobertura del proyecto (actual ~85% estimado)

---

## 6. Riesgos y Mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **SEC-02**: JS existente rompe al cambiar lectura de CSRF | Media | Alto | Inventariar todos los `getCookie('csrftoken')` en código JS antes; migrar todos en mismo PR |
| **SEC-02**: DEBUG=True en .env se replica a producción por error | Alta | Crítico | Documentar prominentemente en SETUP.md; CI/CD debe validar DEBUG=False en stage/prod |
| **EST-03**: Migración de correlativos existentes a tabla Correlativo | Media | Alto | Data migration: poblar Correlativo con Max(numero) actual por empresa+tipo antes de switch |
| **EST-03**: Servicios que crean documentos directamente (no via services.py) | Baja | Medio | Grepear `NotaEntrega.objects.create`, `DocumentoCompra.objects.create`, `NotaCredito.objects.create` |
| **EST-03**: SQLite no soporta SELECT FOR UPDATE real (solo serializado) | Cierta | Medio | Tests de concurrencia marcados `@skipUnlessDBFeature('select_for_update_nowait')`; documentar limitación |
| **DATA-09**: Datos existentes con 2 monedas base por empresa | Baja | Alto | Verificar `Moneda.objects.filter(es_base=True).values('empresa').annotate(c=Count('id')).filter(c__gt=1)` antes de migrar |
| **DATA-09**: Eliminar save() rompe tests que esperan auto-desactivación | Media | Medio | Actualizar tests para esperar IntegrityError en lugar de auto-desactivación |
| **DATA-10**: Datos existentes con tasas duplicadas | Baja | Alto | Verificar `TasaCambio.objects.values('empresa','moneda_origen','moneda_destino','fecha').annotate(c=Count('id')).filter(c__gt=1)` antes de migrar |
| **Todos**: Migraciones no reversibles (constraints) | Baja | Alto | Probar `migrate --plan` y `migrate 0018` para rollback antes de commit |

---

## 7. Definition of Done

- [ ] **SEC-02**: `CSRF_COOKIE_HTTPONLY = True` en settings.py
- [ ] **SEC-02**: `base.html` incluye `<meta name="csrf-token" content="{{ csrf_token }}">`
- [ ] **SEC-02**: Todo JavaScript lee CSRF desde meta tag (no cookie)
- [ ] **SEC-02**: `.env` tiene `DEBUG=False` (desarrollo local usa override local)
- [ ] **SEC-02**: Settings de seguridad activan correctamente con DEBUG=False
- [ ] **SEC-02**: Tests de seguridad pasan (7 tests nuevos)
- [ ] **EST-03**: Modelo `Correlativo` creado con UniqueConstraint(empresa, tipo_documento)
- [ ] **EST-03**: `Correlativo.get_next()` usa `select_for_update()` + retry backoff
- [ ] **EST-03**: `NotaEntrega`, `DocumentoCompra`, `NotaCredito` delegan a Correlativo
- [ ] **EST-03**: `NotaCredito.Meta` tiene 2 UniqueConstraint (numero + numero_control)
- [ ] **EST-03**: Migración 0019 creada y aplicable (incluye data migration poblar Correlativo)
- [ ] **EST-03**: Tests de correlativos y constraints pasan (11 tests nuevos)
- [ ] **DATA-09**: `Moneda.Meta.constraints` incluye `UniqueConstraint` condicional `una_moneda_base_por_empresa`
- [ ] **DATA-09**: `Moneda.save()` NO tiene lógica `qs.update(es_base=False)`
- [ ] **DATA-09**: Migración 0020 creada y aplicable
- [ ] **DATA-09**: Tests de constraint moneda base pasan (6 tests nuevos)
- [ ] **DATA-10**: `TasaCambio.Meta.constraints` incluye `UniqueConstraint` `unique_tasa_par_fecha`
- [ ] **DATA-10**: Migración 0021 creada y aplicable
- [ ] **DATA-10**: Tests de constraint tasa cambio pasan (6 tests nuevos)
- [ ] **Suite completa**: 368 tests existentes + 30 nuevos = 398 tests OK
- [ ] **Sin regresiones**: `python manage.py check --deploy` pasa (warnings esperables on-premise)
- [ ] **Migraciones**: `makemigrations --check --dry-run` → "No changes detected"
- [ ] **CHANGELOG.md**: Entrada para v1.x.x con todos los fixes P1

---

## Gate G1: Aprobación Requerida

> **⚠️ ESTE SPEC REQUIERE APROBACIÓN EXPLÍCITA ANTES DE CONTINUAR**
> 
> Una vez revisado, responda con **"APROBADO"** para proceder al plan de tareas (TDD Task Plan).
> Si requiere cambios, indíquelos específicamente.