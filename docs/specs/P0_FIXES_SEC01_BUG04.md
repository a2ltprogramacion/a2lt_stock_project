# Spec: Fixes P0 - SEC-01 + BUG-04

## 1. Contexto y Alcance

### Proyecto
- **Framework**: Django 6.0.6 multi-tenant on-premise
- **Base de datos**: SQLite WAL mode
- **Python**: 3.14
- **OS**: Windows
- **Commit auditado**: `0585207` (HEAD)
- **Suite de tests**: 358 tests OK (6 skipped)

### Fixes P0 a implementar

| ID | Título | Severidad | Archivo | Línea |
|----|--------|-----------|---------|-------|
| SEC-01 | SECRET_KEY fallback inseguro | CRÍTICO | `a2lt_stock_project/settings.py` | 28 |
| BUG-04 | NameError en `DetalleCompraQuerySet.para_empresa` | CRÍTICO | `inventory/models.py` | 31, 34-40 |

---

## 2. Requisitos Funcionales (EARS)

### SEC-01: Eliminar fallback inseguro de SECRET_KEY

**UBICACIÓN**: `a2lt_stock_project/settings.py:28`

#### REQ-SEC01-01: Fallo explícito sin SECRET_KEY en entorno
**CUANDO** la variable de entorno `SECRET_KEY` no está definida  
**ENTONCES** el sistema DEBE lanzar `django.core.exceptions.ImproperlyConfigured` al iniciar  
**Y** el mensaje DEBE incluir instrucciones para generar una clave segura

#### REQ-SEC01-02: Sin fallback hardcodeado
**EL** código NO DEBE contener ningún valor por defecto para `SECRET_KEY`  
**EL** valor `dev-insecure-key-change-in-prod` DEBE ser eliminado completamente

#### REQ-SEC01-03: Comando de generación en mensaje de error
**EL** mensaje de error DEBE mostrar:
```
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

#### REQ-SEC01-04: Compatibilidad con desarrollo local
**CUANDO** se ejecuta en desarrollo local con archivo `.env`  
**ENTONCES** `SECRET_KEY` DEBE cargarse desde `.env` (ya configurado)  
**Y** NO DEBE haber cambios en el flujo de desarrollo

#### REQ-SEC01-05: Validación en `check --deploy`
**CUANDO** se ejecuta `python manage.py check --deploy`  
**ENTONCES** DEBE fallar si `SECRET_KEY` no está en variables de entorno  
**Y** DEBE mostrar el mensaje de error descriptivo

---

### BUG-04: Corregir NameError en DetalleCompraQuerySet.para_empresa

**UBICACIÓN**: `inventory/models.py:31` (import) + `inventory/models.py:34-40` (uso)

#### REQ-BUG04-01: Importar get_current_empresa
**EL** archivo `inventory/models.py` DEBE importar `get_current_empresa` desde `.managers` en la línea 31  
**ACTUAL**: `from .managers import EmpresaManager, EmpresaQuerySet`  
**ESPERADO**: `from .managers import EmpresaManager, EmpresaQuerySet, get_current_empresa`

#### REQ-BUG04-02: Funcionamiento correcto de para_empresa()
**CUANDO** se llama `DetalleDocumentoCompra.objects.para_empresa()`  
**ENTONCES** DEBE filtrar por `documento_compra__empresa_id` igual a la empresa activa del contexto  
**Y** SI no hay empresa activa en contexto, DEBE retornar queryset vacío (`.none()`)  
**Y** NO DEBE lanzar `NameError`

#### REQ-BUG04-03: Consistencia con EmpresaQuerySet.para_empresa()
**EL** comportamiento DEBE ser idéntico a `EmpresaQuerySet.para_empresa()` definido en `managers.py:25-30`  
**LA** lógica: obtener `empresa_id` del ContextVar, filtrar si existe, retornar `.none()` si es None

---

## 3. Criterios de Aceptación (Gherkin)

### Feature: SEC-01 - SECRET_KEY sin fallback inseguro

```gherkin
@SEC01 @P0 @security
Feature: SECRET_KEY debe requerir variable de entorno obligatoria

  Background:
    Given un proyecto Django configurado
    And el archivo settings.py tiene la línea SECRET_KEY

  @SEC01-01 @deploy-check
  Scenario: check --deploy falla sin SECRET_KEY en entorno
    When ejecuto "python manage.py check --deploy" sin SECRET_KEY en variables de entorno
    Then el comando falla con código de salida != 0
    And la salida contiene "ImproperlyConfigured"
    And la salida contiene "SECRET_KEY"
    And la salida contiene "python -c \"import secrets; print(secrets.token_urlsafe(64))\""

  @SEC01-02 @dev-env
  Scenario: Desarrollo local con .env funciona correctamente
    Given un archivo .env existe con SECRET_KEY=clave-desarrollo-local
    When ejecuto "python manage.py check"
    Then el comando termina exitosamente (código 0)
    And no hay errores de configuración

  @SEC01-03 @prod-env
  Scenario: Producción requiere SECRET_KEY en entorno
    Given no existe archivo .env
    And la variable de entorno SECRET_KEY no está definida
    When intento iniciar la aplicación (runserver, gunicorn, etc.)
    Then la aplicación falla al arrancar con ImproperlyConfigured
    And el mensaje explica cómo generar una clave segura

  @SEC01-04 @no-fallback
  Scenario: No existe fallback hardcodeado en código
    When inspecciono el código en settings.py línea 28
    Then no hay ningún valor por defecto en os.environ.get()
    And no aparece la cadena "dev-insecure-key-change-in-prod"
```

### Feature: BUG-04 - NameError en DetalleCompraQuerySet.para_empresa

```gherkin
@BUG04 @P0 @bug
Feature: DetalleCompraQuerySet.para_empresa() funciona sin NameError

  Background:
    Given el modelo DetalleDocumentoCompra existe
    And el manager DetalleCompraManager está configurado
    And la función get_current_empresa existe en inventory.managers

  @BUG04-01 @import
  Scenario: Import de get_current_empresa está presente
    When inspecciono inventory/models.py línea 31
    Then la línea contiene "from .managers import EmpresaManager, EmpresaQuerySet, get_current_empresa"

  @BUG04-02 @funciona-con-empresa
  Scenario: para_empresa() filtra correctamente cuando hay empresa activa
    Given una empresa activa establecida en contexto via set_current_empresa(empresa_id)
    And existen DetalleDocumentoCompra para esa empresa y para otras
    When llamo DetalleDocumentoCompra.objects.para_empresa()
    Then retorna solo los detalles de la empresa activa
    And no lanza excepción

  @BUG04-03 @funciona-sin-empresa
  Scenario: para_empresa() retorna queryset vacío sin empresa activa
    Given no hay empresa activa en contexto (get_current_empresa() retorna None)
    When llamo DetalleDocumentoCompra.objects.para_empresa()
    Then retorna un queryset vacío (QuerySet.none())
    And no lanza NameError ni AttributeError

  @BUG04-04 @consistencia
  Scenario: Comportamiento idéntico a EmpresaQuerySet.para_empresa()
    Given los mismos datos de prueba
    When comparo Empresa.objects.para_empresa() vs DetalleDocumentoCompra.objects.para_empresa()
    Then ambos aplican la misma lógica de filtrado por empresa_id del contexto
    And ambos retornan .none() cuando no hay empresa en contexto
```

---

## 4. Archivos Afectados

### SEC-01: SECRET_KEY

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `a2lt_stock_project/settings.py` | Línea 28: Reemplazar `os.environ.get('SECRET_KEY', 'dev-insecure-key-change-in-prod')` por lógica que lanza `ImproperlyConfigured` si no existe | **Modificación** |
| `.env.example` (si existe) | Verificar que documenta `SECRET_KEY` como obligatorio | **Verificación** |
| `README.md` / docs (si aplica) | Actualizar instrucciones de despliegue si mencionan el fallback | **Verificación** |

### BUG-04: NameError en managers

| Archivo | Cambio | Tipo |
|---------|--------|------|
| `inventory/models.py` | Línea 31: Agregar `get_current_empresa` al import desde `.managers` | **Modificación** |
| `inventory/models.py` | Líneas 34-40: `DetalleCompraQuerySet.para_empresa()` ya usa `get_current_empresa()` correctamente tras el import | **Sin cambio en lógica** |

---

## 5. Plan de Tests (TDD)

### Tests para SEC-01

| Test ID | Archivo | Descripción |
|---------|---------|-------------|
| `test_sec01_check_deploy_fails_without_secret_key` | `tests/test_security.py` | `check --deploy` falla sin SECRET_KEY en env |
| `test_sec01_error_message_contains_generation_command` | `tests/test_security.py` | Mensaje incluye comando `secrets.token_urlsafe(64)` |
| `test_sec01_dev_env_works_with_dotenv` | `tests/test_security.py` | Con `.env` local, `check` pasa |
| `test_sec01_no_hardcoded_fallback_in_code` | `tests/test_security.py` | Grep confirma ausencia de fallback hardcodeado |
| `test_sec01_improperly_configured_raised` | `tests/test_security.py` | Importar settings sin SECRET_KEY lanza ImproperlyConfigured |

### Tests para BUG-04

| Test ID | Archivo | Descripción |
|---------|---------|-------------|
| `test_bug04_import_get_current_empresa` | `tests/test_models_managers.py` | Import en models.py incluye get_current_empresa |
| `test_bug04_para_empresa_filters_by_active_empresa` | `tests/test_models_managers.py` | Con empresa activa, filtra correctamente |
| `test_bug04_para_empresa_returns_none_when_no_context` | `tests/test_models_managers.py` | Sin empresa en contexto, retorna `.none()` |
| `test_bug04_no_nameerror` | `tests/test_models_managers.py` | Llamada no lanza NameError |
| `test_bug04_consistent_with_empresa_queryset` | `tests/test_models_managers.py` | Mismo comportamiento que `EmpresaQuerySet.para_empresa()` |

### Cobertura mínima requerida
- **SEC-01**: 100% de las ramas del nuevo código (fallo vs éxito)
- **BUG-04**: 100% de las ramas de `para_empresa()` (con empresa / sin empresa)
- **Total**: Mantener ≥ 80% cobertura global del proyecto

---

## 6. Riesgos y Mitigación

| Riesgo | Probabilidad | Impacto | Mitigación |
|--------|--------------|---------|------------|
| **SEC-01**: Despliegues existentes fallen por falta de SECRET_KEY en entorno | Alta | Crítico | Documentar claramente en CHANGELOG y README; verificar CI/CD tiene SECRET_KEY configurado |
| **SEC-01**: Desarrolladores olviden configurar .env local | Media | Medio | `.env.example` ya existe; script de onboarding verifica |
| **BUG-04**: Otros QuerySet personalizados tengan el mismo bug | Baja | Medio | Grepear `get_current_empresa` en todo `models.py` para verificar imports |
| **BUG-04**: Regresión en tests existentes de multi-tenancy | Baja | Alto | Ejecutar suite completa (358 tests) antes y después |
| **Ambos**: Cambios rompan `python manage.py check` en CI | Baja | Alto | Ejecutar `check --deploy` localmente antes de commit |

---

## 7. Definition of Done

- [ ] **SEC-01**: `settings.py` lanza `ImproperlyConfigured` sin `SECRET_KEY` en entorno
- [ ] **SEC-01**: Mensaje de error incluye comando de generación `secrets.token_urlsafe(64)`
- [ ] **SEC-01**: `check --deploy` falla apropiadamente
- [ ] **SEC-01**: Desarrollo local con `.env` sigue funcionando
- [ ] **SEC-01**: Tests de seguridad pasan (5 tests nuevos)
- [ ] **BUG-04**: Import de `get_current_empresa` agregado en `models.py:31`
- [ ] **BUG-04**: `DetalleCompraQuerySet.para_empresa()` funciona sin NameError
- [ ] **BUG-04**: Filtra correctamente por empresa activa
- [ ] **BUG-04**: Retorna `.none()` sin empresa en contexto
- [ ] **BUG-04**: Tests de managers pasan (5 tests nuevos)
- [ ] **Suite completa**: 358 tests existentes + 10 nuevos = 368 tests OK
- [ ] **Sin regresiones**: `python manage.py check --deploy` pasa en entorno con SECRET_KEY

---

## Gate G1: Aprobación Requerida

> **⚠️ ESTE SPEC REQUIERE APROBACIÓN EXPLÍCITA ANTES DE CONTINUAR**
> 
> Una vez revisado, responda con **"APROBADO"** para proceder al plan de tareas (TDD Task Plan).
> Si requiere cambios, indíquelos específicamente.