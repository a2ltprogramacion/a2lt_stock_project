# TDD Task Plan: Fixes P0 - SEC-01 + BUG-04

## Metadatos
- Spec: `docs/specs/P0_FIXES_SEC01_BUG04.md`
- Commit base: `0585207`
- Rama sugerida: `fix/p0-sec01-bug04`

## Tareas SEC-01 (SECRET_KEY) - Orden TDD

### TASK-SEC01-01: Test check --deploy falla sin SECRET_KEY
- **Archivo test**: `inventory/tests/test_security.py`
- **Test**: `test_sec01_check_deploy_fails_without_secret_key`
- **RED**: Escribir test que falle (check --deploy pasa sin SECRET_KEY)
- **GREEN**: Implementar fix en settings.py
- **REFACTOR**: Limpiar código, verificar mensaje

### TASK-SEC01-02: Test mensaje error incluye comando generación
- **Test**: `test_sec01_error_message_contains_generation_command`
- Verificar que mensaje incluye `python -c "import secrets; print(secrets.token_urlsafe(64))"`

### TASK-SEC01-03: Test desarrollo local con .env funciona
- **Test**: `test_sec01_dev_env_works_with_dotenv`
- Con `.env` local, `manage.py check` pasa

### TASK-SEC01-04: Test no fallback hardcodeado
- **Test**: `test_sec01_no_hardcoded_fallback_in_code`
- Grep confirma ausencia de "dev-insecure-key-change-in-prod"

### TASK-SEC01-05: Test ImproperlyConfigured lanzada
- **Test**: `test_sec01_improperly_configured_raised`
- Importar settings sin SECRET_KEY lanza ImproperlyConfigured

---

## Tareas BUG-04 (NameError) - Orden TDD

### TASK-BUG04-01: Test import get_current_empresa
- **Archivo test**: `inventory/tests/test_models_managers.py`
- **Test**: `test_bug04_import_get_current_empresa`
- Verificar import en models.py línea 31

### TASK-BUG04-02: Test para_empresa filtra con empresa activa
- **Test**: `test_bug04_para_empresa_filters_by_active_empresa`
- Con empresa activa en contexto, filtra correctamente

### TASK-BUG04-03: Test para_empresa retorna .none() sin contexto
- **Test**: `test_bug04_para_empresa_returns_none_when_no_context`
- Sin empresa en contexto, retorna `.none()`

### TASK-BUG04-04: Test no NameError
- **Test**: `test_bug04_no_nameerror`
- Llamada no lanza NameError

### TASK-BUG04-05: Test consistencia con EmpresaQuerySet
- **Test**: `test_bug04_consistent_with_empresa_queryset`
- Mismo comportamiento que `EmpresaQuerySet.para_empresa()`

---

## Definition of Done Global
- [ ] 10 tests nuevos pasando (5 SEC-01 + 5 BUG-04)
- [ ] Suite completa: 368 tests OK (358 + 10)
- [ ] `python manage.py check --deploy` pasa con SECRET_KEY
- [ ] `python manage.py check --deploy` falla sin SECRET_KEY
- [ ] `git diff` muestra solo cambios en settings.py + models.py
- [ ] Commit atómico por fix (2 commits totales)

---

### Gate G3: Aprobación para implementar
> **¿APROBADO para proceder con implementación TDD?**
> Responder "APROBADO" para que el developer inicie TASK-SEC01-01.