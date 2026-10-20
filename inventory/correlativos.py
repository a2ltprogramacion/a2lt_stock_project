"""
inventory/correlativos.py
=========================
EST-03 — Servicio central de correlativos por (empresa, tipo de documento).

Contexto arquitectónico (decisión aprobada):
    SQLite no implementa ``SELECT ... FOR UPDATE``
    (``has_select_for_update=False``): Django ignora la cláusula sin error, de
    modo que el lock de fila NO protege en el backend real. La corrección ante
    concurrencia se apoya en:
        1. ``UniqueConstraint`` sobre el número del documento, y
        2. el bucle de reintento ante ``IntegrityError`` implementado aquí
           (``guardar_con_reintento`` recalcula el número y reintenta).

    ``select_for_update()`` SÍ se usa en la lectura del ``Correlativo``: aporta
    serialización real en PostgreSQL y es inocuo en SQLite.

Todos los accesos a datos usan managers SIN filtro de tenant
(``global_objects`` / ``Correlativo.objects``): fuera de una request el
``EmpresaManager`` devolvería ``.none()`` y veríamos una "BD vacía" falsa.
"""

import logging
import time

from django.apps import apps
from django.db import IntegrityError, transaction
from django.db.models import Max

from .models import ConfiguracionEmpresa, Correlativo

logger = logging.getLogger(__name__)


TIPO_NOTA_ENTREGA = Correlativo.TIPO_NOTA_ENTREGA
TIPO_FACTURA_COMPRA = Correlativo.TIPO_FACTURA_COMPRA
TIPO_NOTA_CREDITO = Correlativo.TIPO_NOTA_CREDITO

TIPOS_DOCUMENTO = (
    TIPO_NOTA_ENTREGA,
    TIPO_FACTURA_COMPRA,
    TIPO_NOTA_CREDITO,
)

# Mapeo único tipo -> datos del documento. Centralizar aquí evita repetir la
# misma lógica en tres sitios (modelo, campo inicial, prefijo, campo display).
DOC_CONFIG = {
    TIPO_NOTA_ENTREGA: {
        'model': 'NotaEntrega',
        'inicial_field': 'correlativo_inicial_nota',
        'prefijo_field': 'prefijo_nota_entrega',
        'display_field': 'numero_nota',
        'prefijo_default': 'NE',
    },
    TIPO_FACTURA_COMPRA: {
        'model': 'DocumentoCompra',
        'inicial_field': 'correlativo_inicial_factura_compra',
        'prefijo_field': 'prefijo_factura_compra',
        'display_field': 'numero_interno',
        'prefijo_default': 'FC',
    },
    TIPO_NOTA_CREDITO: {
        'model': 'NotaCredito',
        'inicial_field': 'correlativo_inicial_nota_credito',
        'prefijo_field': 'prefijo_nota_credito',
        'display_field': 'numero_control',
        'prefijo_default': 'NC',
    },
}


def _config(tipo_documento):
    try:
        return DOC_CONFIG[tipo_documento]
    except KeyError:
        raise ValueError(
            f'Tipo de documento de correlativo desconocido: {tipo_documento!r}'
        )


def _modelo_documento(tipo_documento):
    return apps.get_model('inventory', _config(tipo_documento)['model'])


def _valor_inicial(empresa_id, tipo_documento):
    """Correlativo inicial configurado para la empresa (mínimo 1)."""
    conf = _config(tipo_documento)
    valor = (
        ConfiguracionEmpresa.global_objects
        .filter(empresa_id=empresa_id)
        .values_list(conf['inicial_field'], flat=True)
        .first()
    )
    try:
        return max(1, int(valor or 1))
    except (TypeError, ValueError):
        return 1


def leer_prefijo(empresa_id, tipo_documento):
    """Prefijo configurado para la empresa (o el default del tipo)."""
    conf = _config(tipo_documento)
    valor = (
        ConfiguracionEmpresa.global_objects
        .filter(empresa_id=empresa_id)
        .values_list(conf['prefijo_field'], flat=True)
        .first()
    )
    return valor or conf['prefijo_default']


def siguiente_numero(empresa_id, tipo_documento):
    """Devuelve el próximo número correlativo para (empresa, tipo).

    Combina tres fuentes y toma el mayor + 1:
        - ``Max('numero')`` real de los documentos (sin filtro de tenant),
        - ``Correlativo.ultimo_numero`` (contador atómico),
        - ``correlativo_inicial_* - 1`` (base configurada).

    La lectura del ``Correlativo`` usa ``SELECT ... FOR UPDATE``. En SQLite es
    inocuo (Django ignora la cláusula); en PostgreSQL aporta serialización.
    La corrección NO depende de este lock.
    """
    modelo = _modelo_documento(tipo_documento)
    inicial = _valor_inicial(empresa_id, tipo_documento)

    with transaction.atomic():
        corr = (
            Correlativo.objects.select_for_update()
            .filter(empresa_id=empresa_id, tipo_documento=tipo_documento)
            .first()
        )
        ultimo_tabla = corr.ultimo_numero if corr else 0

    manager = getattr(modelo, 'global_objects', None) or modelo._default_manager
    max_doc = (
        manager.filter(empresa_id=empresa_id).aggregate(m=Max('numero'))['m'] or 0
    )

    return max(int(max_doc), int(ultimo_tabla), int(inicial) - 1) + 1


def registrar_numero_usado(empresa_id, tipo_documento, numero):
    """Upsert idempotente del contador que **nunca retrocede**.

    ``ultimo_numero = max(actual, numero)``. Es seguro llamarlo varias veces con
    el mismo número (reintentos, re-emisiones, migraciones).
    """
    numero = int(numero)
    with transaction.atomic():
        corr, created = (
            Correlativo.objects.select_for_update().get_or_create(
                empresa_id=empresa_id,
                tipo_documento=tipo_documento,
                defaults={'ultimo_numero': numero},
            )
        )
        if not created and numero > corr.ultimo_numero:
            corr.ultimo_numero = numero
            corr.save(update_fields=['ultimo_numero', 'actualizado_en'])
    return corr.ultimo_numero


def guardar_con_reintento(instancia, tipo_documento, obtener_prefijo=None, max_intentos=5):
    """Asigna ``numero`` (+ campo display) y persiste con reintento ante colisión.

    Cada intento:
        1. Se ejecuta dentro de ``transaction.atomic()`` (savepoint si ya hay
           transacción externa), de modo que un ``IntegrityError`` se revierte
           limpiamente y se puede reintentar.
        2. Recalcula el número con ``siguiente_numero`` (función a nivel de
           módulo → parcheable en tests).
        3. Persiste con ``_correlativo_gestionado=True`` para no re-entrar al
           camino de auto-correlativo del modelo ``save()``.

    Ante ``IntegrityError`` reintenta con backoff ``0.05 * (2 ** intento)``. Al
    agotar los intentos re-lanza la última excepción.
    """
    conf = _config(tipo_documento)
    display_field = conf['display_field']
    empresa_id = instancia.empresa_id
    display_proporcionado = bool(getattr(instancia, display_field, ''))
    ultima_excepcion = None

    for intento in range(max_intentos):
        try:
            with transaction.atomic():
                numero = siguiente_numero(empresa_id, tipo_documento)
                instancia.numero = numero

                if obtener_prefijo is not None:
                    prefijo = obtener_prefijo()
                else:
                    prefijo = leer_prefijo(empresa_id, tipo_documento)

                if not getattr(instancia, display_field, ''):
                    setattr(instancia, display_field, f'{prefijo}-{numero:08d}')

                instancia.save(_correlativo_gestionado=True)
                registrar_numero_usado(empresa_id, tipo_documento, numero)
            return instancia
        except IntegrityError as exc:
            ultima_excepcion = exc
            if intento >= max_intentos - 1:
                logger.error(
                    'EST-03: no se pudo asignar correlativo %s para empresa=%s '
                    'tras %s intentos: %s',
                    tipo_documento, empresa_id, max_intentos, exc,
                )
                raise
            # Restaurar el estado para el siguiente intento.
            instancia.numero = 0
            if not display_proporcionado:
                setattr(instancia, display_field, '')
            time.sleep(0.05 * (2 ** intento))

    # Inalcanzable: el bucle re-lanza al agotar intentos.
    raise ultima_excepcion
