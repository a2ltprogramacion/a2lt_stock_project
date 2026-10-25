"""EST-01 (G1): inmutabilidad del kárdex — bypass contextual + señales pre_save/pre_delete.
EST-02 (G1): inmutabilidad de documentos emitidos — matriz de campos + mismos mecanismos.

Módulo ÚNICO auditable (REQ-EST01-04: la allowlist es verificable por grep/ADR)
que aísla el enforcement del resto de la app:

* ``kardex_guard`` importa de ``models``; ``services``/``seed_db``/tests
  importan de aquí; ``models.py`` solo lo importa perezosamente dentro de
  ``KardexQuerySet`` (sin ciclos).
* ``inventory/signals.py`` queda como hoy (siembra post_save de Empresa,
  negocio) y ``services.py`` no engorda con enforcement.
* EST-02 REUTILIZA el ContextVar/bypass de EST-01 (mecanismo compartido,
  REQ-EST02-07): ``seed_db --clear`` y ``services.eliminar_tenant`` siguen
  cubiertos por el MISMO escape hatch — no se crea un módulo paralelo.

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

from .models import (
    DetalleDocumentoCompra,
    DetalleNotaCredito,
    DetalleNotaEntrega,
    DocumentoCompra,
    DocumentoInmutableError,
    KardexProtegidoError,
    MovimientoKardex,
    NotaCredito,
    NotaEntrega,
)

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


# ─────────────────────────────────────────────────────────────────────────────
# EST-02 — Inmutabilidad de documentos emitidos (spec §2.2, REQ-EST02-01..07)
#
# Matriz de campos mutables tras emisión (el corazón del fix): una cabecera
# solo muta el par estado→ANULADO + motivo_anulacion (transición única
# PROCESADO→ANULADO, mismo save); las líneas Detalle* son 100% inmutables
# (matriz vacía — el re-save idempotente con valores idénticos pasa).
#
# Nota `cantidad_devuelta_acumulada`: NO es columna — es @property que SUMA
# las filas DetalleNotaCredito del related `devoluciones`. Su "writer
# legítimo" es el INSERT de DetalleNotaCredito en procesar_devolucion_*,
# que NO toca la fila origen → la matriz de líneas queda VACÍA por
# construcción (REQ-EST02-10).
# ─────────────────────────────────────────────────────────────────────────────

# La allowlist ENTERA de EST-02 vive en un símbolo auditable por grep/ADR.
MATRIZ = {
    NotaEntrega: {'estado', 'motivo_anulacion'},
    DocumentoCompra: {'estado', 'motivo_anulacion'},
    # pre_save conectado desde TASK-EST02-04 (§5): tras el refactor pre-create
    # la NC nace completa y no existe writer legítimo post-emisión.
    NotaCredito: {'estado', 'motivo_anulacion'},
    DetalleNotaEntrega: frozenset(),
    DetalleDocumentoCompra: frozenset(),
    DetalleNotaCredito: frozenset(),
}
CABECERAS = (NotaEntrega, DocumentoCompra, NotaCredito)


def bloquear_documento(operacion, instance, cambios=()):
    """REQ-EST02-01 — log ERROR forense (modelo, pk, campos, traceback) y raise."""
    logger.error(
        '[EST-02] %s de %s pk=%s cambios=%s. Vía legítima: services.reversar_*.',
        operacion, type(instance).__name__, getattr(instance, 'pk', None),
        sorted(cambios), exc_info=True,
    )
    raise DocumentoInmutableError(
        f'Documento emitido inmutable: {operacion} prohibido '
        f'(campos: {sorted(cambios)}). Use services.reversar_*.'
    )


def _documento_pre_save(sender, instance, raw=False, update_fields=None, **kwargs):
    """Un handler para los 6 senders: la lógica fetch→diff es idéntica;
    la matriz es un dict (datos, no código).

    * ``raw``: fixtures de loaddata quedan exentos (documentado Django).
    * ``bypass_activo()``: allowlist de EST-01 reutilizada (REQ-EST02-07).
    * ``instance.pk is None``: CREATE — el documento aún no está emitido.
    * El fetch usa ``_base_manager`` (NO ``objects``): ``EmpresaManager``
      retorna ``.none()`` sin request → el guard quedaría ciego en
      shell/tests/commands; ``_base_manager`` es el mecanismo uniforme en
      los 6 modelos.
    """
    if raw or bypass_activo() or instance.pk is None:
        return
    original = type(instance)._base_manager.filter(pk=instance.pk).first()
    if original is None:
        return
    mutables = MATRIZ[sender]
    if update_fields is not None and (ajenos_uf := set(update_fields) - mutables):
        # update_fields ajeno a la matriz → bloquear, aunque el valor no cambie.
        bloquear_documento('save(update_fields=…)', instance, ajenos_uf)
    changed = {
        f.name for f in sender._meta.concrete_fields
        if f.name != 'id' and (update_fields is None or f.name in update_fields)
        and f.value_from_object(instance) != f.value_from_object(original)
    }  # FK por attname → id, sin fetch adicional
    if not changed:
        return  # re-save idempotente (Gherkin EST02-06/08)
    if sender in CABECERAS:
        if original.estado == 'ANULADO':
            bloquear_documento('mutación de documento ANULADO', instance, changed)
        if 'estado' in changed and instance.estado != 'ANULADO':
            bloquear_documento('transición de estado ≠ ANULADO', instance, changed)
        if 'motivo_anulacion' in changed and 'estado' not in changed:
            bloquear_documento('motivo_anulacion sin transición', instance, changed)
    if (ajenos := changed - mutables):
        bloquear_documento('modificación de campos inmutables', instance, ajenos)


def _documento_pre_delete(sender, instance, **kwargs):
    """REQ-EST02-04: borrado de instancia, queryset bulk y cascada bloqueados
    (el collector de Django envía TODOS los pre_delete antes de ejecutar
    cualquier DELETE SQL → aborta completo, sin borrados parciales)."""
    if not bypass_activo():
        bloquear_documento('DELETE', instance)


# Conexión con sender=clase REAL (mismo criterio EST-01, REQ-EST02-07):
# los modelos históricos de migraciones no disparan estos receivers.
#
# ORDEN HISTÓRICO (§2→§5): el ``pre_save`` de NotaCredito se difirió a
# TASK-EST02-04 — ``procesar_devolucion_*`` terminaba con
# ``nc.save(update_fields=['monto_total_reembolso'])`` sobre NC PROCESADO y
# conectarlo antes rompía los 29 tests NC. Tras el refactor pre-create (§5)
# la NC NACE COMPLETA y no vuelve a salvarse: el guard ya cubre los 6
# modelos, la matriz queda aplicada al 100%.
#
# Divergencia reportada y aprobada por el coordinador (2026-10-24): el plan
# solo auditaba 4 mutaciones de documentos (spec §1.5); la realidad tenía
# 6 — los tails de creación procesar_venta:1598 (iva_total/iva_check) y
# registrar_compra_proveedor:2291 (totales) también mutaban cabeceras tras
# el INSERT. Resolución: patrón pre-create del §5 extendido a NE/DC (las
# cabeceras nacen completas) — NO relajar la matriz ni el handler.
for _modelo in (
    NotaEntrega, DocumentoCompra, NotaCredito,
    DetalleNotaEntrega, DetalleDocumentoCompra, DetalleNotaCredito,
):
    pre_save.connect(_documento_pre_save, sender=_modelo)
    pre_delete.connect(_documento_pre_delete, sender=_modelo)
