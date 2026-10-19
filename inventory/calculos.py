"""
Cálculos financieros únicos de documentos (DATA-01).

Este módulo es la **única fuente de verdad** para subtotales, IVA, descuento
global y totales de una Nota de Entrega/Factura o de un Documento de Compra.

Antes de DATA-01 el mismo bloque de cálculo estaba copiado en cuatro vistas de
``inventory/views.py`` (detalle/pantalla y PDF, tanto para ventas como para
compras). La duplicación ya había provocado una divergencia real: el PDF de
nota imprimía el IVA en Bs bruto mientras la pantalla mostraba el neto.

Reglas
------
* Las propiedades del modelo de detalle son la fuente de verdad:
  ``subtotal_usd``, ``subtotal_bs``, ``iva_usd`` e ``iva_bs`` ya incorporan el
  descuento individual de la línea.
* El ``descuento_global`` del documento se aplica proporcionalmente al
  subtotal y al IVA (USD y Bs).
* Todos los resultados monetarios se cuantizan a 2 decimales (céntimos).
"""

from decimal import Decimal, InvalidOperation

CENTIMOS = Decimal('0.01')
CIEN = Decimal('100')
CERO = Decimal('0')


def _a_decimal(valor, nombre='descuento_global'):
    """Convierte de forma segura un valor a ``Decimal``."""
    if valor is None:
        return Decimal('0')
    if isinstance(valor, Decimal):
        return valor
    try:
        return Decimal(str(valor))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError(
            f'{nombre} debe ser un número decimal entre 0 y 100.'
        )


def _centimos(valor):
    """Cuantiza un ``Decimal`` a 2 decimales."""
    return _a_decimal(valor).quantize(CENTIMOS)


def _cantidad(detalle):
    return _a_decimal(getattr(detalle, 'cantidad', Decimal('1')), 'cantidad')


def _subtotal_usd_fallback(detalle):
    """Fallback USD: ``cantidad * precio_base`` / ``cantidad * costo_base``."""
    for campo in ('precio_base', 'costo_base'):
        if hasattr(detalle, campo):
            return _cantidad(detalle) * _a_decimal(getattr(detalle, campo))
    return Decimal('0')


def _subtotal_bs_fallback(detalle, usa_precio_ajustado):
    """
    Fallback Bs: ``cantidad * precio_ajustado_bcv`` (o ``costo_ajustado_bcv``).

    Con ``usa_precio_ajustado=False`` se usa el precio directo BCV, que es el
    mismo criterio que tenían las vistas cuando no aplicaban factor.
    """
    campos = (
        ('precio_ajustado_bcv', 'costo_ajustado_bcv')
        if usa_precio_ajustado
        else ('precio_directo_bcv', 'costo_directo_bcv')
    )
    for campo in campos:
        if hasattr(detalle, campo):
            return _cantidad(detalle) * _a_decimal(getattr(detalle, campo))
    return Decimal('0')


def _iva_fallback(detalle, subtotal_usd, subtotal_bs):
    """Fallback de IVA a partir del porcentaje snapshot de la línea."""
    porcentaje = _a_decimal(getattr(detalle, 'iva_porcentaje', Decimal('0')))
    factor_iva = porcentaje / CIEN
    return (subtotal_usd * factor_iva, subtotal_bs * factor_iva)


def _sumar(detalles, propiedad, fallback):
    """Suma una propiedad del detalle, usando ``fallback`` si no existe."""
    total = Decimal('0')
    for detalle in detalles:
        valor = getattr(detalle, propiedad, None)
        if valor is None:
            valor = fallback(detalle)
        total += _a_decimal(valor)
    return total


def calcular_factor_descuento(descuento_global):
    """
    Devuelve el factor multiplicativo ``1 - descuento_global / 100``.

    Es la **única** implementación del factor de descuento global del sistema.
    Valida que el porcentaje esté entre 0 y 100 (``None`` = 0).

    Raises
    ------
    ValueError
        Si ``descuento_global`` no es numérico o está fuera de ``[0, 100]``.
    """
    descuento = _a_decimal(descuento_global)
    if not descuento.is_finite() or descuento < CERO or descuento > CIEN:
        raise ValueError(
            'descuento_global debe estar entre 0 y 100.'
        )
    return Decimal('1') - (descuento / CIEN)


def calcular_totales_documento(
    detalles, descuento_global, *, usa_precio_ajustado=True,
):
    """
    Calcula todos los totales de un documento a partir de sus detalles.

    Parámetros
    ----------
    detalles:
        Iterable de detalles (Nota de Entrega o Documento de Compra).
    descuento_global:
        Porcentaje global del documento (0-100). ``None`` se interpreta como 0.
    usa_precio_ajustado:
        Solo afecta al *fallback* cuando el detalle no expone propiedades del
        modelo: ``True`` usa ``*_ajustado_bcv``; ``False`` usa ``*_directo_bcv``.

    Returns
    -------
    dict
        ``descuento_global``, ``factor_descuento``, los brutos
        (``subtotal_*_bruto``, ``total_iva_*_bruto``), los netos
        (``subtotal_*_neto``, ``total_iva_*_neto``), los montos de descuento y
        los totales finales ``total_usd_neto`` / ``total_bs_neto``.
        Todos los importes están cuantizados a 2 decimales.
    """
    descuento = _a_decimal(descuento_global)
    factor_descuento = calcular_factor_descuento(descuento)

    detalles = list(detalles)

    subtotal_usd_bruto = _sumar(
        detalles, 'subtotal_usd', _subtotal_usd_fallback,
    )
    subtotal_bs_bruto = _sumar(
        detalles,
        'subtotal_bs',
        lambda d: _subtotal_bs_fallback(d, usa_precio_ajustado),
    )

    def _iva_usd_fallback(detalle):
        return _iva_fallback(
            detalle,
            _subtotal_usd_fallback(detalle),
            _subtotal_bs_fallback(detalle, usa_precio_ajustado),
        )[0]

    def _iva_bs_fallback(detalle):
        return _iva_fallback(
            detalle,
            _subtotal_usd_fallback(detalle),
            _subtotal_bs_fallback(detalle, usa_precio_ajustado),
        )[1]

    total_iva_usd_bruto = _sumar(detalles, 'iva_usd', _iva_usd_fallback)
    total_iva_bs_bruto = _sumar(detalles, 'iva_bs', _iva_bs_fallback)

    subtotal_usd_neto = _centimos(subtotal_usd_bruto * factor_descuento)
    subtotal_bs_neto = _centimos(subtotal_bs_bruto * factor_descuento)
    total_iva_usd_neto = _centimos(total_iva_usd_bruto * factor_descuento)
    total_iva_bs_neto = _centimos(total_iva_bs_bruto * factor_descuento)

    monto_descuento_usd = _centimos(subtotal_usd_bruto - subtotal_usd_neto)
    monto_descuento_bs = _centimos(subtotal_bs_bruto - subtotal_bs_neto)

    total_usd_neto = _centimos(subtotal_usd_neto + total_iva_usd_neto)
    total_bs_neto = _centimos(subtotal_bs_neto + total_iva_bs_neto)

    return {
        'descuento_global': descuento,
        'factor_descuento': factor_descuento,
        'subtotal_usd_bruto': _centimos(subtotal_usd_bruto),
        'subtotal_bs_bruto': _centimos(subtotal_bs_bruto),
        'total_iva_usd_bruto': _centimos(total_iva_usd_bruto),
        'total_iva_bs_bruto': _centimos(total_iva_bs_bruto),
        'subtotal_usd_neto': subtotal_usd_neto,
        'subtotal_bs_neto': subtotal_bs_neto,
        'total_iva_usd_neto': total_iva_usd_neto,
        'total_iva_bs_neto': total_iva_bs_neto,
        'monto_descuento_usd': monto_descuento_usd,
        'monto_descuento_bs': monto_descuento_bs,
        'total_usd_neto': total_usd_neto,
        'total_bs_neto': total_bs_neto,
    }


def calcular_lineas(detalles, *, campo_usd, campo_bs):
    """
    Asigna ``line_usd`` / ``line_bs`` a cada detalle y devuelve la lista.

    Se usan las propiedades ``subtotal_usd`` / ``subtotal_bs`` del modelo
    (que ya aplican el descuento individual de la línea). Si un detalle no las
    expone, se cae a ``cantidad * campo_usd`` / ``cantidad * campo_bs``.

    ``campo_usd`` y ``campo_bs`` documentan el campo monetario de la línea
    (``precio_base``/``costo_base`` y ``precio_ajustado_bcv``/
    ``costo_ajustado_bcv``) y solo se usan en ese fallback.
    """
    resultado = []
    for detalle in detalles:
        subtotal_usd = getattr(detalle, 'subtotal_usd', None)
        subtotal_bs = getattr(detalle, 'subtotal_bs', None)

        if subtotal_usd is None:
            subtotal_usd = (
                _cantidad(detalle)
                * _a_decimal(getattr(detalle, campo_usd, Decimal('0')))
            )
        if subtotal_bs is None:
            subtotal_bs = (
                _cantidad(detalle)
                * _a_decimal(getattr(detalle, campo_bs, Decimal('0')))
            )

        detalle.line_usd = _a_decimal(subtotal_usd)
        detalle.line_bs = _a_decimal(subtotal_bs)
        resultado.append(detalle)

    return resultado
