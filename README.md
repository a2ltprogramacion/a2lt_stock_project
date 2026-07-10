# A2LT Stock

Sistema on-premise de control de inventario y punto de venta multi-tenant, 
dirigido al mercado venezolano de telecom/electrónica. Inspirado en el 
flujo operativo de Profit Plus 2K, modernizado con Django 6 y Tailwind CSS.

**Para Venezuela** — soporta BCV + tasa mercado + factor de cobertura 
cambiaria, con snapshots inmutables de tasas en cada transacción.

---

## Características principales

- **Multi-tenant seguro** — cada comercio (empresa) tiene sus propios 
  datos, filtrados via ContextVar (no por schema ni tenant_id manual).
- **Multi-moneda** — USD, VES y futuras. Cada compra/venta graba el 
  snapshot de la tasa aplicada para auditoría histórica.
- **Kardex inmutable** — toda modifica de stock pasa por 
  `services.registrar_movimiento()`; el costo_unitario_snapshot de cada 
  detalle de venta es inalterable.
- **8 reportes operativos** — Kardex Valorizado, Inventario Valorizado, 
  Ventas por Período, Cuentas por Cobrar (CxC), Cuentas por Pagar (CxP), 
  Top Artículos Vendidos, Artículos Sin Movimiento (obsoletos), y 
  Estado de Resultados simple. Exportables a CSV (BOM utf-8 para Excel) 
  y PDF (A4 landscape con reportlab).
- **Dashboard con KPIs live** — valoración USD/VES del inventario, 
  volumen de ventas del mes, conteo de notas, alertas de reposición, 
  disponibilidad de combos virtuales calculada en tiempo real, última 
  sincronización de tasa persistida.
- **Backup atómico** — `manage.py backup_db` genera un snapshot 
  consistente via SQLite `VACUUM INTO` sin bloquear escrituras, con 
  opción de retención automática.
- **Combos virtuales** — stock calculado dinamicamente como 
  `min(floor(S(a_i)/q_i))` sobre los componentes físicos.
- **Reversos auditados** — anular NotaEntrega o DocumentoCompra 
  genera contramovimientos de kardex con motivo persistido.

## Stack

- **Backend:** Django 6.0.6 (Python 3.11+), SQLite WAL — sin PostgreSQL, 
  sin Celery, sin DRF (reglas del producto).
- **Frontend:** Tailwind CSS (CDN), Chart.js, FontAwesome. Sin build JS.
- **PDF:** reportlab 5.0.
- **Excel:** openpyxl 3.1.
- **Tests:** Django TestCase/TransactionTestCase — 157 tests verdes.

## Instalación rápida

```bash
git clone <repo-url> a2lt_stock_project
cd a2lt_stock_project
python -m venv .venv
.venv\Scripts\activate           # Windows
# source .venv/bin/activate      # Linux/macOS
pip install -r requirements.txt

# Crear .env con SECRET_KEY y DEBUG
echo "SECRET_KEY=desarrollo-inseguro-cambiar-en-prod" > .env
echo "DEBUG=True" >> .env

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Abrir http://127.0.0.1:8000

## Documentación

- `docs/AUDITORIA_INICIAL.md` — hallazgos previos a la Fase A.
- `docs/PLAN.md` — plan de estabilización completo (Etapas A, B, 
  Fase 3, 4, 5, 6 y reglas de calidad).
- `docs/ROADMAP.md` — features post-100% (cuentas por cobrar/pagar, 
  factura electrónica Seniat, bitácora de auditoría).
- `docs/OPERACION.md` — guía de instalación detallada, módulos, 
  troubleshooting y reglas operativas.

## Producción

Para producción on-premise se recomienda:

1. Crear `.env` con `DEBUG=False` y `SECRET_KEY` aleatoria de 64+ chars.
2. Programar backup nocturno via Programador de Tareas (Windows) o 
   cron (Linux):
   ```bash
   0 2 * * * cd /opt/a2lt_stock && .venv/bin/python manage.py backup_db --retention 7
   ```
3. Servir con Gunicorn (Linux) o WhiteNoise + IIS (Windows). Ver 
   `docs/OPERACION.md` para detalles.

## Tests

```bash
python manage.py test inventory                  # suite completa (~2min)
python manage.py test inventory.tests.TestDashboardLiveData -v 2    # rápidos
```

## Reglas sagradas

1. **Stock**: solo se modifica via `services.registrar_movimiento()`. 
   Nunca UPDATE directo a `InventarioAlmacen.cantidad_disponible`.
2. **Tenant**: usar `get_current_empresa()` (ContextVar), nunca 
   `Empresa.objects.first()` ni `request.empresa`.
3. **Snapshots**: los campos `tasa_bcv_aplicada`, 
   `factor_cobertura_aplicado`, `costo_unitario_snapshot`, 
   `precio_unitario_usd` y `precio_unitario_bs` grabados en cada 
   compra/venta son inmutables post-factura.
4. **@login_required**: defense-in-depth junto a `TenantMiddleware` 
   que valida 5 condiciones (autenticación, perfil, empresa_id en 
   sesión, empresa activa, empresa permitida para el usuario).

## Licencia

Propietaria. © 2026 A2LT Soluciones (Ing. Angel Argenis León Torres).
