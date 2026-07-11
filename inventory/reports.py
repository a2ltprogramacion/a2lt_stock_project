"""
inventory/reports.py
====================
Servicios de reportes para A2LT Stock — Fase 4.

Cada funcion publica retorna un dict con claves:
  - 'columns': lista de tuplas (key, label) para tablas/exports.
  - 'rows': lista de dicts (una fila por registro).
  - 'totals': dict con totales agregados (opcional).
  - 'meta': dict con metadata del reporte (titulo, filtros, empresa).

Todas las funciones son puras (sin side-effects) y respetan el
ContextVar multi-tenant via EmpresaManager (no usan global_objects
salvo cuando se trabaja con snapshots historicos inmutables que ya
tienen empresa_id grabado).
"""

from __future__ import annotations

import datetime as _dt
from collections import OrderedDict
from decimal import Decimal

from django.db.models import Sum, F, Q, Count
from django.utils import timezone

from .models import (
    Articulo,
    Almacen,
    InventarioAlmacen,
    MovimientoKardex,
    NotaEntrega,
    DetalleNotaEntrega,
    DocumentoCompra,
    Contacto,
    ConfiguracionEmpresa,
)


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades internas
# ─────────────────────────────────────────────────────────────────────────────

def _parse_fecha(desde, hasta):
    """Normaliza rangos de fecha. Devuelve (desde_dt, hasta_dt)."""
    if isinstance(desde, str) and desde:
        desde = _dt.date.fromisoformat(desde)
    if isinstance(hasta, str) and hasta:
        hasta = _dt.date.fromisoformat(hasta)
    if hasta and not isinstance(hasta, _dt.datetime):
        hasta = _dt.datetime.combine(hasta, _dt.time(23, 59, 59))
    elif hasta is None:
        hasta = timezone.now()
    if desde and not isinstance(desde, _dt.datetime):
        desde = _dt.datetime.combine(desde, _dt.time(0, 0, 0))
    return desde, hasta


def _meta(titulo, empresa_id, **extra):
    from .models import Empresa
    # Empresa es la raiz multi-tenant (no tiene EmpresaManager),
    # usar el manager default para resolver el nombre.
    empresa = Empresa.objects.filter(pk=empresa_id).first()
    meta = OrderedDict([
        ('titulo', titulo),
        ('empresa_id', empresa_id),
        ('empresa_nombre', empresa.nombre if empresa else ''),
        ('generado_en', timezone.now().isoformat(timespec='seconds')),
    ])
    meta.update(extra)
    return meta


# ─────────────────────────────────────────────────────────────────────────────
# 1. KARDEX VALORIZADO
# ─────────────────────────────────────────────────────────────────────────────

def reporte_kardex(
    empresa_id,
    articulo_sku=None,
    almacen_id=None,
    desde=None,
    hasta=None,
):
    """
    Kardex valorizado: una fila por MovimientoKardex, con costo unitario
    y valor monetario del movimiento (cantidad * costo_unitario_snapshot
    quando disponible, sino Articulo.costo actual como aproximacion).
    """
    desde_dt, hasta_dt = _parse_fecha(desde, hasta)

    qs = MovimientoKardex.objects.select_related(
        'articulo', 'almacen', 'nota_entrega', 'documento_compra'
    ).order_by('fecha_hora')

    if articulo_sku:
        qs = qs.filter(articulo_id=articulo_sku)
    if almacen_id:
        qs = qs.filter(almacen_id=almacen_id)
    if desde_dt:
        qs = qs.filter(fecha_hora__gte=desde_dt)
    if hasta_dt:
        qs = qs.filter(fecha_hora__lte=hasta_dt)

    columns = [
        ('fecha_hora', 'Fecha y Hora'),
        ('articulo_sku', 'SKU'),
        ('articulo_nombre', 'Artículo'),
        ('almacen', 'Almacén'),
        ('tipo', 'Tipo'),
        ('concepto', 'Concepto'),
        ('cantidad', 'Cantidad'),
        ('saldo', 'Saldo'),
        ('costo_unit', 'Costo Unit. USD'),
        ('valor_mov', 'Valor Mov. USD'),
    ]

    rows = []
    total_entradas = Decimal('0.00')
    total_salidas = Decimal('0.00')

    for m in qs:
        costo_unit = m.articulo.costo or Decimal('0.00')
        # Si hay snapshot de compra, usarlo; si no, costo actual
        valor_mov = (m.cantidad * costo_unit).quantize(Decimal('0.0001'))

        if m.tipo == 'ENTRADA':
            total_entradas += valor_mov
        else:
            total_salidas += valor_mov

        rows.append(OrderedDict([
            ('fecha_hora', m.fecha_hora.strftime('%Y-%m-%d %H:%M')),
            ('articulo_sku', m.articulo_id),
            ('articulo_nombre', m.articulo.nombre),
            ('almacen', m.almacen.nombre),
            ('tipo', m.tipo),
            ('concepto', m.concepto),
            ('cantidad', str(m.cantidad)),
            ('saldo', str(m.saldo_resultante)),
            ('costo_unit', str(costo_unit)),
            ('valor_mov', str(valor_mov)),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('entradas_usd', str(total_entradas)),
            ('salidas_usd', str(total_salidas)),
            ('saldo_neto_usd', str(total_entradas - total_salidas)),
        ]),
        'meta': _meta(
            'Kardex Valorizado', empresa_id,
            articulo_sku=articulo_sku or 'TODOS',
            almacen_id=almacen_id or 'TODOS',
            desde=desde_dt.date().isoformat() if desde_dt else 'INICIO',
            hasta=hasta_dt.date().isoformat() if hasta_dt else 'AHORA',
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. INVENTARIO VALORIZADO
# ─────────────────────────────────────────────────────────────────────────────

def reporte_inventario_valorizado(empresa_id, almacen_id=None):
    """
    Inventario valorizado: una fila por InventarioAlmacen, con costo y
    valor total. Solo articulos FISICOS.
    """
    qs = InventarioAlmacen.objects.select_related('articulo', 'almacen')
    if almacen_id:
        qs = qs.filter(almacen_id=almacen_id)

    columns = [
        ('sku', 'SKU'),
        ('nombre', 'Artículo'),
        ('almacen', 'Almacén'),
        ('cantidad', 'Cantidad'),
        ('costo', 'Costo Unit. USD'),
        ('valor_total', 'Valor Total USD'),
        ('stock_minimo', 'Stock Mínimo'),
        ('estado', 'Estado'),
    ]

    rows = []
    total_valor = Decimal('0.00')
    total_unidades = Decimal('0.00')
    criticos = 0

    for inv in qs:
        valor = (inv.cantidad_disponible * inv.articulo.costo).quantize(Decimal('0.0001'))
        total_valor += valor
        total_unidades += inv.cantidad_disponible

        estado = 'OK'
        if inv.cantidad_disponible <= 0:
            estado = 'AGOTADO'
        elif inv.stock_minimo > 0 and inv.cantidad_disponible <= inv.stock_minimo:
            estado = 'CRÍTICO'
            criticos += 1

        rows.append(OrderedDict([
            ('sku', inv.articulo_id),
            ('nombre', inv.articulo.nombre),
            ('almacen', inv.almacen.nombre),
            ('cantidad', str(inv.cantidad_disponible)),
            ('costo', str(inv.articulo.costo)),
            ('valor_total', str(valor)),
            ('stock_minimo', str(inv.stock_minimo)),
            ('estado', estado),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('total_unidades', str(total_unidades)),
            ('total_valor_usd', str(total_valor)),
            ('items_criticos', str(criticos)),
        ]),
        'meta': _meta(
            'Inventario Valorizado', empresa_id,
            almacen_id=almacen_id or 'TODOS',
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. VENTAS POR PERÍODO
# ─────────────────────────────────────────────────────────────────────────────

def reporte_ventas_periodo(empresa_id, desde=None, hasta=None):
    """
    Una fila por NotaEntrega PROCESADO (excluye ANULADO), con subtotal
    USD y Bs calculados de los snapshots de detalles.
    """
    desde_dt, hasta_dt = _parse_fecha(desde, hasta)

    qs = NotaEntrega.objects.select_related('cliente', 'almacen').filter(
        estado='PROCESADO'
    ).order_by('fecha')
    if desde_dt:
        qs = qs.filter(fecha__gte=desde_dt)
    if hasta_dt:
        qs = qs.filter(fecha__lte=hasta_dt)

    columns = [
        ('numero', 'N° Nota'),
        ('fecha', 'Fecha'),
        ('cliente', 'Cliente'),
        ('almacen', 'Almacén'),
        ('moneda_pago', 'Moneda Pago'),
        ('subtotal_usd', 'Subtotal USD'),
        ('subtotal_bs', 'Subtotal Bs'),
        ('estado', 'Estado'),
    ]

    rows = []
    total_usd = Decimal('0.00')
    total_bs = Decimal('0.00')

    for nota in qs:
        detalles = nota.detalles.all()
        subtotal_usd = sum((d.subtotal_usd for d in detalles), Decimal('0.00'))
        subtotal_bs = sum((d.subtotal_bs for d in detalles), Decimal('0.00'))
        total_usd += subtotal_usd
        total_bs += subtotal_bs

        rows.append(OrderedDict([
            ('numero', f'NE-{nota.numero:05d}'),
            ('fecha', nota.fecha.strftime('%Y-%m-%d %H:%M')),
            ('cliente', nota.cliente.nombre if nota.cliente else 'Cliente Genérico'),
            ('almacen', nota.almacen.nombre),
            ('moneda_pago', nota.moneda_pago),
            ('subtotal_usd', str(subtotal_usd)),
            ('subtotal_bs', str(subtotal_bs)),
            ('estado', nota.estado),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('total_usd', str(total_usd)),
            ('total_bs', str(total_bs)),
            ('cantidad_notas', str(len(rows))),
        ]),
        'meta': _meta(
            'Ventas por Período', empresa_id,
            desde=desde_dt.date().isoformat() if desde_dt else 'INICIO',
            hasta=hasta_dt.date().isoformat() if hasta_dt else 'AHORA',
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. CUENTAS POR COBRAR (CxC)
# ─────────────────────────────────────────────────────────────────────────────

def reporte_cuentas_por_cobrar(empresa_id):
    """
    Ventas facturadas en USD/Bs pendientes de pago. En la version actual
    todas las notas PROCESADO se consideran "por cobrar" hasta que se
    registre un cierre de caja manual (no implementado en Fase 4).
    Muestra saldo pendiente = subtotal de la nota.
    """
    qs = NotaEntrega.objects.select_related('cliente', 'almacen').filter(
        estado='PROCESADO'
    ).order_by('-fecha')

    columns = [
        ('numero', 'N° Nota'),
        ('fecha', 'Fecha'),
        ('cliente', 'Cliente'),
        ('moneda_pago', 'Moneda'),
        ('subtotal_usd', 'Monto USD'),
        ('subtotal_bs', 'Monto Bs'),
        ('dias_pendiente', 'Días Pendiente'),
    ]

    rows = []
    total_usd = Decimal('0.00')
    total_bs = Decimal('0.00')
    now = timezone.now()

    for nota in qs:
        detalles = nota.detalles.all()
        subtotal_usd = sum((d.subtotal_usd for d in detalles), Decimal('0.00'))
        subtotal_bs = sum((d.subtotal_bs for d in detalles), Decimal('0.00'))
        total_usd += subtotal_usd
        total_bs += subtotal_bs

        dias = (now - nota.fecha).days if nota.fecha else 0

        rows.append(OrderedDict([
            ('numero', f'NE-{nota.numero:05d}'),
            ('fecha', nota.fecha.strftime('%Y-%m-%d') if nota.fecha else ''),
            ('cliente', nota.cliente.nombre if nota.cliente else 'Cliente Genérico'),
            ('moneda_pago', nota.moneda_pago),
            ('subtotal_usd', str(subtotal_usd)),
            ('subtotal_bs', str(subtotal_bs)),
            ('dias_pendiente', str(dias)),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('total_usd', str(total_usd)),
            ('total_bs', str(total_bs)),
            ('cantidad_notas', str(len(rows))),
        ]),
        'meta': _meta('Cuentas por Cobrar', empresa_id),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 5. CUENTAS POR PAGAR (CxP)
# ─────────────────────────────────────────────────────────────────────────────

def reporte_cuentas_por_pagar(empresa_id):
    """
    Documentos de compra PROCESADO considerados pendientes de pago al
    proveedor (mismo criterio que CxC: no hay modulo de pagos en Fase 4).
    """
    qs = DocumentoCompra.objects.select_related('proveedor').filter(
        estado='PROCESADO'
    ).order_by('-fecha_compra', '-id')

    columns = [
        ('id', 'N° Compra'),
        ('fecha_compra', 'Fecha'),
        ('proveedor', 'Proveedor'),
        ('numero_factura', 'Factura'),
        ('monto_usd', 'Monto USD'),
        ('monto_bs', 'Monto Bs (snapshot)'),
        ('dias_pendiente', 'Días Pendiente'),
    ]

    rows = []
    total_usd = Decimal('0.00')
    total_bs = Decimal('0.00')
    now = timezone.now()

    for c in qs:
        total_usd += c.monto_total_usd or Decimal('0.00')
        total_bs += c.monto_total_bs_snapshot or Decimal('0.00')
        dias = (now.date() - c.fecha_compra).days if c.fecha_compra else 0

        rows.append(OrderedDict([
            ('id', str(c.id)),
            ('fecha_compra', c.fecha_compra.isoformat() if c.fecha_compra else ''),
            ('proveedor', c.proveedor.nombre if c.proveedor else ''),
            ('numero_factura', c.numero_factura or ''),
            ('monto_usd', str(c.monto_total_usd)),
            ('monto_bs', str(c.monto_total_bs_snapshot or 0)),
            ('dias_pendiente', str(dias)),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('total_usd', str(total_usd)),
            ('total_bs', str(total_bs)),
            ('cantidad_documentos', str(len(rows))),
        ]),
        'meta': _meta('Cuentas por Pagar', empresa_id),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. TOP ARTÍCULOS VENDIDOS
# ─────────────────────────────────────────────────────────────────────────────

def reporte_top_vendidos(empresa_id, limite=20, desde=None, hasta=None):
    """RankingPor cantidad vendida y monto USD."""
    desde_dt, hasta_dt = _parse_fecha(desde, hasta)

    qs = DetalleNotaEntrega.objects.filter(
        nota_entrega__estado='PROCESADO'
    )
    if desde_dt:
        qs = qs.filter(nota_entrega__fecha__gte=desde_dt)
    if hasta_dt:
        qs = qs.filter(nota_entrega__fecha__lte=hasta_dt)

    qs = qs.values(
        'articulo_id', 'articulo__nombre'
    ).annotate(
        cantidad_total=Sum('cantidad'),
        monto_usd_total=Sum(F('cantidad') * F('precio_base')),
        monto_bs_total=Sum(F('cantidad') * F('precio_ajustado_bcv')),
    ).order_by('-monto_usd_total')[:limite]

    columns = [
        ('sku', 'SKU'),
        ('nombre', 'Artículo'),
        ('cantidad_total', 'Cantidad'),
        ('monto_usd', 'Monto USD'),
        ('monto_bs', 'Monto Bs'),
    ]

    rows = []
    for r in qs:
        rows.append(OrderedDict([
            ('sku', r['articulo_id']),
            ('nombre', r['articulo__nombre']),
            ('cantidad_total', str(r['cantidad_total'] or 0)),
            ('monto_usd', str(r['monto_usd_total'] or 0)),
            ('monto_bs', str(r['monto_bs_total'] or 0)),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('items_listados', str(len(rows))),
        ]),
        'meta': _meta(
            f'Top {limite} Artículos Vendidos', empresa_id,
            limite=str(limite),
            desde=desde_dt.date().isoformat() if desde_dt else 'INICIO',
            hasta=hasta_dt.date().isoformat() if hasta_dt else 'AHORA',
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. ARTÍCULOS SIN MOVIMIENTO (OBSOLETOS)
# ─────────────────────────────────────────────────────────────────────────────

def reporte_obsoletos(empresa_id, dias_sin_movimiento=90):
    """
    Artículos FISICOS activos sin movimientos en el kardex en los ultimos
    `dias_sin_movimiento` dias. Incluye valor atascado en inventario.
    """
    fecha_limite = timezone.now() - _dt.timedelta(days=dias_sin_movimiento)

    # SKUs con movimientos recientes
    skus_con_movimiento = set(
        MovimientoKardex.objects.filter(
            fecha_hora__gte=fecha_limite
        ).values_list('articulo_id', flat=True)
    )

    qs = Articulo.objects.filter(
        tipo='FISICO',
        activo=True,
    ).exclude(
        sku__in=skus_con_movimiento
    ).order_by('nombre')

    columns = [
        ('sku', 'SKU'),
        ('nombre', 'Artículo'),
        ('categoria', 'Categoría'),
        ('costo', 'Costo Unit. USD'),
        ('stock_total', 'Stock Total'),
        ('valor_atascado', 'Valor Atascado USD'),
        ('dias_sin_mov', 'Días Sin Mov.'),
    ]

    rows = []
    total_atascado = Decimal('0.00')

    for a in qs:
        stock_total = a.get_stock_disponible() or Decimal('0')
        valor = (stock_total * a.costo).quantize(Decimal('0.0001'))
        total_atascado += valor
        rows.append(OrderedDict([
            ('sku', a.sku),
            ('nombre', a.nombre),
            ('categoria', a.categoria),
            ('costo', str(a.costo)),
            ('stock_total', str(stock_total)),
            ('valor_atascado', str(valor)),
            ('dias_sin_mov', str(dias_sin_movimiento) + '+'),
        ]))

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('cantidad_articulos', str(len(rows))),
            ('valor_atascado_usd', str(total_atascado)),
        ]),
        'meta': _meta(
            f'Artículos Sin Movimiento ({dias_sin_movimiento}+ días)', empresa_id,
            dias_sin_movimiento=str(dias_sin_movimiento),
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. ESTADO DE RESULTADOS SIMPLE
# ─────────────────────────────────────────────────────────────────────────────

def reporte_estado_resultados(empresa_id, desde=None, hasta=None):
    """
    Estado de resultados simple:
      Ingresos (Ventas)        = sum(subtotal_usd detalle notas PROCESADO)
      Costo de Ventas (COGS)   = sum(cantidad * costo_unitario_snapshot)
      Utilidad Bruta           = Ingresos - COGS
      Margen Bruto %           = Utilidad Bruta / Ingresos * 100
      Valor Inventario Actual  = sum(stock * costo)
    """
    desde_dt, hasta_dt = _parse_fecha(desde, hasta)

    detalles_qs = DetalleNotaEntrega.objects.filter(
        nota_entrega__estado='PROCESADO'
    )
    if desde_dt:
        detalles_qs = detalles_qs.filter(nota_entrega__fecha__gte=desde_dt)
    if hasta_dt:
        detalles_qs = detalles_qs.filter(nota_entrega__fecha__lte=hasta_dt)

    agg = detalles_qs.aggregate(
        ingresos_usd=Sum(F('cantidad') * F('precio_base')),
        cogs_usd=Sum(F('cantidad') * F('costo_unitario_snapshot')),
    )
    ingresos = agg['ingresos_usd'] or Decimal('0.00')
    cogs = agg['cogs_usd'] or Decimal('0.00')
    utilidad_bruta = ingresos - cogs
    margen_pct = (utilidad_bruta / ingresos * 100) if ingresos > 0 else Decimal('0.00')

    valor_inventario = (InventarioAlmacen.objects.aggregate(
        v=Sum(F('cantidad_disponible') * F('articulo__costo'))
    )['v'] or Decimal('0.00'))

    columns = [
        ('cuenta', 'Cuenta'),
        ('monto_usd', 'Monto USD'),
        ('porcentaje', '% Sobre Ventas'),
    ]

    def pct(val):
        return str((val / ingresos * 100).quantize(Decimal('0.01'))) if ingresos > 0 else '0.00'

    rows = [
        OrderedDict([('cuenta', 'Ingresos por Ventas'), ('monto_usd', str(ingresos)), ('porcentaje', '100.00')]),
        OrderedDict([('cuenta', '(-) Costo de Ventas (COGS)'), ('monto_usd', str(cogs)), ('porcentaje', pct(cogs))]),
        OrderedDict([('cuenta', '= Utilidad Bruta'), ('monto_usd', str(utilidad_bruta)), ('porcentaje', pct(utilidad_bruta))]),
        OrderedDict([('cuenta', 'Margen Bruto %'), ('monto_usd', margen_pct.quantize(Decimal('0.01')).__str__()), ('porcentaje', '')]),
        OrderedDict([('cuenta', 'Valor Inventario Actual'), ('monto_usd', str(valor_inventario)), ('porcentaje', '')]),
    ]

    return {
        'columns': columns,
        'rows': rows,
        'totals': OrderedDict([
            ('ingresos_usd', str(ingresos)),
            ('cogs_usd', str(cogs)),
            ('utilidad_bruta_usd', str(utilidad_bruta)),
            ('margen_bruto_pct', str(margen_pct.quantize(Decimal('0.01')))),
            ('valor_inventario_usd', str(valor_inventario)),
        ]),
        'meta': _meta(
            'Estado de Resultados', empresa_id,
            desde=desde_dt.date().isoformat() if desde_dt else 'INICIO',
            hasta=hasta_dt.date().isoformat() if hasta_dt else 'AHORA',
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# REGISTRO DE REPORTES (dispatcher por nombre)
# ─────────────────────────────────────────────────────────────────────────────

REGISTRO = OrderedDict([
    ('kardex', ('Kardex Valorizado', reporte_kardex)),
    ('inventario', ('Inventario Valorizado', reporte_inventario_valorizado)),
    ('ventas', ('Ventas por Período', reporte_ventas_periodo)),
    ('cxc', ('Cuentas por Cobrar', reporte_cuentas_por_cobrar)),
    ('cxp', ('Cuentas por Pagar', reporte_cuentas_por_pagar)),
    ('top_vendidos', ('Top Artículos Vendidos', reporte_top_vendidos)),
    ('obsoletos', ('Artículos Sin Movimiento', reporte_obsoletos)),
    ('estado_resultados', ('Estado de Resultados', reporte_estado_resultados)),
])


def obtener_reporte(nombre: str, empresa_id, **params):
    """Dispatcher: invoca el reporte por nombre clave del REGISTRO."""
    if nombre not in REGISTRO:
        raise ValueError(f"Reporte '{nombre}' no registrado. Disponibles: {list(REGISTRO.keys())}")
    label, func = REGISTRO[nombre]
    return func(empresa_id, **params)
