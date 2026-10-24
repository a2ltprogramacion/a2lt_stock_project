"""EST-01 (G1): inmutabilidad del kárdex — bypass contextual + señales pre_save/pre_delete.

Módulo ÚNICO auditable (REQ-EST01-04: la allowlist es verificable por grep/ADR)
que aísla el enforcement del resto de la app:

* ``kardex_guard`` importa de ``models``; ``services``/``seed_db``/tests
  importan de aquí; ``models.py`` solo lo importa perezosamente dentro de
  ``KardexQuerySet`` (sin ciclos).
* ``inventory/signals.py`` queda como hoy (siembra post_save de Empresa,
  negocio) y ``services.py`` no engorda con enforcement.

Mecanismo: ``contextvars.ContextVar`` con CONTADOR apilable (reentrante;
thread/async-safe por diseño). El bypass público loguea WARNING con el
motivo al entrar (REQ-EST01-03); el contexto interno del service loguea
INFO — el camino legítimo no genera ruido de WARNING (REQ-EST01-06). El
``finally`` con ``reset(token)`` impide fugas de contexto ante excepciones.
"""

import contextvars
import logging
from contextlib import contextmanager

from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver

from .models import KardexProtegidoError, MovimientoKardex

logger = logging.getLogger(__name__)

# Contador apilable: 0 = guards activos; > 0 = hay un contexto autorizado vivo.
_nivel = contextvars.ContextVar('kardex_bypass_nivel', default=0)


def bypass_activo() -> bool:
    """True si algún contexto (bypass público o escritura del service) está vivo."""
    return _nivel.get() > 0


@contextmanager
def kardex_bypass(motivo: str):
    """REQ-EST01-03 — escape hatch de la allowlist (ADR). WARNING audible por diseño."""
    logger.warning('[KARDEX BYPASS] activado: %s', motivo)
    token = _nivel.set(_nivel.get() + 1)
    try:
        yield
    finally:
        _nivel.reset(token)


@contextmanager
def escritura_kardex_autorizada(concepto: str = ''):
    """REQ-EST01-05/06 — contexto INTERNO de registrar_movimiento; mismo contador, log INFO."""
    logger.info('[KARDEX] escritura autorizada via services (concepto=%s)', concepto)
    token = _nivel.set(_nivel.get() + 1)
    try:
        yield
    finally:
        _nivel.reset(token)


def bloquear_kardex(operacion: str, instance=None):
    """REQ-EST01-08 — log ERROR (modelo, operación, pk, traceback) y luego raise."""
    logger.error(
        '[EST-01] Bloqueado %s de MovimientoKardex (pk=%s). Use services.registrar_movimiento '
        'o kardex_guard.kardex_bypass (allowlist ADR).',
        operacion, getattr(instance, 'pk', None), exc_info=True,
    )
    raise KardexProtegidoError(
        f'Kárdex inmutable: {operacion} prohibido. '
        'Vía legítima: services.registrar_movimiento.'
    )


# Conexión con sender=clase REAL (opción (a) del G1, REQ-EST01-05/07):
# los modelos históricos de migraciones (clases reconstruidas por
# ModelState, id distinto, sin relación de subclase) NO disparan estos
# receivers — las migraciones quedan exentas por diseño.
@receiver(pre_save, sender=MovimientoKardex)      # INSERT y UPDATE directos
def _kardex_pre_save(sender, instance, **kwargs):
    if not bypass_activo():
        bloquear_kardex('INSERT/UPDATE directo', instance)


@receiver(pre_delete, sender=MovimientoKardex)    # instancia + bulk + cascada
def _kardex_pre_delete(sender, instance, **kwargs):
    if not bypass_activo():
        bloquear_kardex('DELETE', instance)
