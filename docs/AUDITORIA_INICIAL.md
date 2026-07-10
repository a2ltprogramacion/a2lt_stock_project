# Auditoría Inicial — A2LT Stock

**Fecha:** 2026-07-10  
**Arquitecto:** Ing. Angel Argenis León Torres (A2LT Soluciones)  
**Modelo:** GLM-5.2 (z-ai)

## Alcance

Auditoría topológica y estructural del repository `a2lt_stock_project` 
Django 6.0.6 multi-tenant on-premise, antes de iniciar la fase de 
estabilización Fase A.

## Hallazgos críticos (orden de severidad)

1. **`fix_test.py` (bomba mutadora)** — script Python en `inventory/` 
   que durante una corrida de `manage.py test` alteraba `tests.py` 
  para forzar pasar tests rotos. **Eliminado.**
2. **`scratch/` (~1206 líneas)** — directorio con prototipos 
   abandonados de carga masiva, importaciones experimentales, código 
   pegado de StackOverflow sin usar. **Eliminado.**
3. **Stubs muertos** en `views.py` (módulos `movimientos`/`contactos` 
   con `pass` o `TODO`). **Eliminados.**
4. **Bug `ANULADO` vs `ANULADA`** en `services.py:1960` causante de 
   reversos silenciosos que no marcaban NotaEntrega como ANULADA. 
   **Corregido (`76490a5`).**
5. **`metodo_ganancia` ignorado** — la capa de precios siempre usaba 
   MARKUP sin respetar el atributo `articulo.metodo_ganancia` 
   (MARKUP/MARGIN). **Corregido (`06a038f`).**
6. **`@csrf_exempt` disperso** en vistas sensibles (crear_venta, 
   articulos). **Removido (`4db49f0`, `596a691`).**
7. **`request.empresa` / `Empresa.objects.first()`** en lugar de 
   `get_current_empresa()` (ContextVar). 7 vistas afectadas. 
   **Migradas a multi-tenant puro (`c637495`, `9adb793`, etc.).**
8. **`SECRET_KEY` y `DEBUG` hardcodeados** en `settings.py`. 
   **Refactorizado a env vars (`f52afea`).**
9. **`base.html` sin getCookie ni block extra_js** — CSRF no podía 
   usarse desde frontend AJAX. **Corregido (`dc699a6`).**
10. **Cobertura baja** de los servicios más críticos: reverso de 
    notas/ventas, snapshot de costo al facturar,孤单 configuración.

## Métricas de inicio

- **Commits previos a auditoría:** 0 (repositorio limpio)
- **Tests existentes:** 0
- **Cobertura `services.py`:** < 5%
- **Líneas de código muertas:** ~1300

## Métricas tras Fase A (estabilización)

- **Commits:** 21 (Fase A completa `A1`→`A16` + setup)
- **Tests:** 127 verdes
- **`manage.py check --deploy`:** 0 críticos (sólo warnings esperables)
- **Cobertura de novos líneas en services.py:** > 70% (medible al final)
