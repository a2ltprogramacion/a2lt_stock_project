# Roadmap Post-100% — A2LT Stock

**Fecha:** 2026-07-10

El sistema está completo en su núcleo funcional: multi-tenant seguro, 
multimoneda con snapshots inmutables, 8 reportes operativos, dashboard 
con KPIs live, backup automático, 157 tests verdes. Esta hoja de ruta 
prioriza las próximas features identificadas por el Ing. León Torres.

## Q3 2026 — Operación real en producción

1. **Pilotaje en 2 comercios** (semana 1-4)
   - Recoger feedback UX para iterar templates de reportes.
   - Validar el flujo completo: alta de empresa, compradores, ventas, 
     reversos, backup nocturno automatico via `cron --retention 7`.

2. **Documentar matrices de impresión** (sem 5-8)
   - Cada comercio tiene su propia matriz de coords de impresión 
     (`ConfiguracionEmpresa.print_offset_x`, `_y`, `row_spacing`). 
     Establecer una librería de presets comerciales por impresora.

## Q4 2026 — Features de monetización

3. **Módulo de Pagos y Cierres de Caja**
   - Registro de pagos parciales/totales contra `NotaEntrega` y 
     `DocumentoCompra` (Fase 4 las marca como "pendientes por defecto").
   - Cierre diario con conciliación USD/Bs/Efectivo.
   - Test: pago parcial + reverso de pago → debe mantener CxC correcto.

4. **Factura Electrónica Seniat (Venezuela)**
   - Generar XML conforme a normativa vigente para NotaEntrega.
   - Firma digital se aplica on-premise con certificado del cliente.
   - Reemplaza la actual "Nota de Entrega" en PDV.

5. **Bitácora de Auditoría por Usuario**
   - Cada `MovimientoKardex` ya graba `usuario` (`CharField`). Migrar 
     a `ForeignKey(User)`, dejar `CharField` como NombreUsuario snapshot.
   - Tabla nueva `AuditoriaAccion` con `usuario`, `accion`, `modelo`, 
     `pk_afectado`, `timestamp`, `cambios_json`.
   - Vista `/auditoria/` con filtros por fecha/usuario/accion.

## Q1 2027 — Escalabilidad

6. **API REST readonly para integraciones**
   - Evaluar DRF contra la regla "no DRF": votar Flutter/POS.
   - Si no DRF: usar `JsonResponse` + vistas minimalistas (mantiene 
     el espíritu on-premise).
   - Endpoints: `/api/inventario/`, `/api/ventas/periodo/`, 
     `/api/cuentas/`.

7. **Backup incremental con binlog-equivalente**
   - SQLite soporta session-backup via `backup_api`; implementar 
     backup incremental de cambios de la última hora.
   - Reducir tiempo de backup en comercios con 100K+ movimientos.

8. **Movil app vuestra** — soporte de venta desde el móvil
   - One-page PWA con Tailwind.
   - Lectura de seriales via camera-api.

## Repriorizaciones posibles

- Si comercios reportan lentitud: añadir índices en 
  `MovimientoKardex(fecha, articulo, almacen)`.
- Si se detectan fugas de datos multi-tenant: auditar cada vista 
  con `inspect` y firmar que todas llaman `get_current_empresa`.
- Si tests se vuelven lentos (>5min suite completa): partir 
  `services.py` (ADR-21 revoke).

## NO priorizar

- Migrar a PostgreSQL: SQLite WAL con `backup_db VACUUM INTO` 
  atiende sin issues el volumen on-premise.
- DRF + JWT: no alinea con el perfil monolítico on-premise.
- Celery: las cargas no son asíncronas críticas (sólo el backup).
