"""
EST-01 — Kárdex inmutable: señales pre_save/pre_delete + KardexQuerySet + bypass.

Contexto
--------
La Regla Sagrada era unidireccional: nada fuera de ``registrar_movimiento``
podía mover stock, pero el kárdex mismo era mutable con un simple
``.delete()`` / ``.update()`` / ``create()`` directo — borrando la
trazabilidad forense que la Regla Sagrada promete (REQ-EST01-01..08,
spec §2.1).

Este módulo fija el contrato del guard:

* ``pre_delete`` bloquea borrado de instancia, de queryset (bulk) y de
  cascada (``Empresa.delete()`` con kárdex); el collector de Django envía
  TODAS las señales ``pre_delete`` antes de ejecutar cualquier DELETE SQL,
  por lo que el raise aborta la operación completa sin borrados parciales.
* ``pre_save`` bloquea INSERT/UPDATE directo (Regla Sagrada
  bidireccional): el único creador legítimo es ``registrar_movimiento``,
  que entra en su contexto interno ``escritura_kardex_autorizada``.
* ``KardexQuerySet`` bloquea ``.update()`` y ``bulk_create()`` — vías que
  NO emiten señales y dejarían el guard con bypass conocido.
* ``kardex_bypass(motivo)`` es el escape hatch auditado (WARNING al
  entrar, contador ContextVar apilable/reentrante).

Las cascadas SET_NULL de la baja de usuarios (Gherkin EST04-05) no
disparan el guard por diseño: el collector las resuelve con el
``_base_manager`` plano sobre ``UpdateQuery`` crudo (sin señales, sin
QuerySet custom) y la fila de kárdex persiste con FK NULL + snapshot.
"""

from decimal import Decimal

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase

from inventory.kardex_guard import bypass_activo, kardex_bypass
from inventory.managers import set_current_empresa
from inventory.models import (
    Almacen,
    Articulo,
    Empresa,
    KardexProtegidoError,
    MovimientoKardex,
    NotaEntrega,
)


class KardexInmutableBase(TestCase):
    """Fixture común (patrón test_usuario_fk._crear_empresa): tenant en sesión + kárdex legítimo."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nombre='EST01 Corp', rif='J-EST01-001', activa=True,
        )
        set_current_empresa(self.empresa.id)
        self.almacen = Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén EST-01', es_principal=True,
        )
        self.articulo = Articulo.objects.create(
            empresa=self.empresa, sku='EST01-001', nombre='Artículo EST-01',
            tipo='FISICO', categoria='OTROS',
            costo=Decimal('5.00'), precio_divisa=Decimal('10.00'),
        )
        from inventory.services import registrar_movimiento

        self.mov = registrar_movimiento(
            self.articulo, self.almacen, 'ENTRADA', Decimal('10'),
            'AJUSTE_ENTRADA', usuario='Admin',
        )


class TestKardexGuard(KardexInmutableBase):
    """REQ-EST01-01/02/05/06/08: guards activos + escape hatch apilable."""

    def _datos_movimiento(self, saldo_resultante=Decimal('11')):
        return dict(
            empresa=self.empresa,
            articulo=self.articulo,
            almacen=self.almacen,
            tipo='ENTRADA',
            cantidad=Decimal('1'),
            saldo_resultante=saldo_resultante,
            concepto='AJUSTE_ENTRADA',
            usuario_nombre='test',
        )

    # ── 1. Borrados bloqueados: instancia, queryset y global (REQ-EST01-01) ──

    def test_delete_instancia_y_queryset_bloqueados(self):
        total = MovimientoKardex.global_objects.count()

        # NOTA (patrón Django): el raise de pre_delete ocurre DENTRO del
        # transaction.atomic(savepoint=False) del collector de Django, que
        # marca needs_rollback en la transacción exterior. En producción eso
        # ES el rollback total deseado; en el fixture lo aislamos con un
        # savepoint propio para poder seguir consultando en el mismo test.
        with self.assertRaises(KardexProtegidoError):
            with transaction.atomic():
                self.mov.delete()
        self.assertEqual(
            MovimientoKardex.global_objects.count(), total,
            'el borrado de instancia no debe tocar ninguna fila',
        )

        with self.assertRaises(KardexProtegidoError):
            with transaction.atomic():
                MovimientoKardex.objects.all().delete()
        self.assertEqual(
            MovimientoKardex.global_objects.count(), total,
            'el borrado bulk por queryset no debe tocar ninguna fila',
        )

        with self.assertRaises(KardexProtegidoError):
            with transaction.atomic():
                MovimientoKardex.global_objects.all().delete()
        self.assertEqual(
            MovimientoKardex.global_objects.count(), total,
            'el borrado bulk sin filtro de tenant tampoco',
        )

    # ── 2. INSERT directo y bulk_create bloqueados (REQ-EST01-05) ────────────

    def test_create_directo_y_bulk_create_bloqueados(self):
        antes = MovimientoKardex.global_objects.count()

        with self.assertRaises(KardexProtegidoError):
            MovimientoKardex.objects.create(**self._datos_movimiento())
        self.assertEqual(
            MovimientoKardex.global_objects.count(), antes,
            'el create directo no debe insertar filas',
        )

        m1 = MovimientoKardex(**self._datos_movimiento())
        m2 = MovimientoKardex(**self._datos_movimiento(Decimal('12')))
        with self.assertRaises(KardexProtegidoError):
            MovimientoKardex.global_objects.bulk_create([m1, m2])
        self.assertEqual(
            MovimientoKardex.global_objects.count(), antes,
            'bulk_create no inserta filas (no emite pre_save: lo bloquea KardexQuerySet)',
        )

    # ── 3. Bypass: permite todo, loggea WARNING y es apilable (REQ-EST01-03) ──

    def test_bypass_permite_todo_loggea_warning_y_es_apilable(self):
        with self.assertLogs('inventory.kardex_guard', level='WARNING') as captura:
            with kardex_bypass('prueba guard'):
                self.assertTrue(bypass_activo())

                mov_directo = MovimientoKardex.objects.create(
                    **self._datos_movimiento()
                )
                MovimientoKardex.objects.filter(pk=mov_directo.pk).update(
                    detalle_adicional='x',
                )

                with kardex_bypass('nivel 2'):
                    self.assertTrue(bypass_activo())
                    mov_directo.delete()

        self.assertIn('prueba guard', ' '.join(captura.output))
        self.assertFalse(bypass_activo(), 'al salir del bypass el contador vuelve a 0')

        # Tras salir del contexto, el guard vuelve a bloquear todo.
        with self.assertRaises(KardexProtegidoError):
            MovimientoKardex.objects.create(**self._datos_movimiento())


class TestKardexUpdateTeardown(KardexInmutableBase):
    """REQ-EST01-02 completa + Gherkin EST01-04/05/08: .update() en ambos managers,
    cascada de Empresa.delete() bloqueada y services.eliminar_tenant como única vía."""

    def test_update_bloqueado_en_objects_y_global_objects(self):
        with self.assertRaises(KardexProtegidoError):
            MovimientoKardex.objects.filter(pk=self.mov.pk).update(cantidad=Decimal('999'))
        self.mov.refresh_from_db()
        self.assertEqual(self.mov.cantidad, Decimal('10'), 'la cantidad persiste intacta')

        with self.assertRaises(KardexProtegidoError):
            MovimientoKardex.global_objects.filter(empresa=self.empresa).update(
                detalle_adicional='x',
            )
        self.mov.refresh_from_db()
        self.assertEqual(
            self.mov.detalle_adicional, '',
            'global_objects (sin filtro de tenant) también bloquea .update()',
        )

    def test_empresa_delete_directo_con_kardex_bloqueado(self):
        # El borrado directo de un tenant con datos queda BLOQUEADO con
        # rollback total (nada se toca). En este esquema la PRIMERA
        # excepción es ProtectedError: los FK PROTECT preexistentes de
        # MovimientoKardex/InventarioAlmacen hacia Articulo/Almacen
        # abortan el collector durante collect(), ANTES de que exista
        # señal alguna (mismo comportamiento documentado en
        # test_tenant_lifecycle.py; precedente RESTRICT 5d137fa para
        # TasaCambio→Moneda). KardexProtegidoError es el backstop de
        # EST-01 y dispararía si esos FKs cambiaran a RESTRICT.
        # Aislamos con savepoint (ver NOTA en TestKardexGuard).
        with self.assertRaises((ProtectedError, KardexProtegidoError)):
            with transaction.atomic():
                self.empresa.delete()

        self.assertTrue(
            Empresa.objects.filter(pk=self.empresa.pk).exists(),
            'el rollback del collector preserva la empresa',
        )
        self.assertEqual(
            MovimientoKardex.global_objects.filter(empresa_id=self.empresa.pk).count(),
            1,
            'ni una fila de kárdex se toca: el borrado en cascada aborta completo',
        )

    def test_eliminar_tenant_teardown_completo_y_motivo_obligatorio(self):
        from inventory import services as svc

        empresa_id = self.empresa.pk
        otra = Empresa.objects.create(nombre='EST01 Otra', rif='J-EST01-OTRA')

        # Sin motivo auditable no hay teardown (Gherkin EST01-08).
        with self.assertRaises(ValueError):
            svc.eliminar_tenant(otra, motivo='')
        self.assertTrue(
            Empresa.objects.filter(pk=otra.pk).exists(),
            'sin motivo la empresa queda intacta',
        )

        with self.assertLogs('inventory.kardex_guard', level='WARNING') as captura:
            svc.eliminar_tenant(self.empresa, motivo='fin de prueba')
        self.assertIn('teardown tenant', ' '.join(captura.output))

        self.assertFalse(
            Empresa.objects.filter(pk=empresa_id).exists(),
            'eliminar_tenant debe desmontar la empresa completa',
        )
        self.assertEqual(
            MovimientoKardex.global_objects.filter(empresa_id=empresa_id).count(),
            0,
            'el kárdex del tenant cae a 0 dentro del bypass autorizado',
        )
        self.assertEqual(
            NotaEntrega.global_objects.filter(empresa_id=empresa_id).count(),
            0,
            'las notas del tenant caen a 0',
        )


class TestKardexCaminoLegitimo(KardexInmutableBase):
    """REQ-EST01-04/06/07: el camino legítimo queda intacto y los históricos exentos.

    Tests de regresión/verificación sobre el comportamiento mergeado en
    TASK-EST01-01/02 (el plan los define así: "GREEN: los 2 tests pasan
    sin tocar código").
    """

    def test_reverso_venta_inserta_compensatorio_sin_borrados(self):
        from inventory import services as svc

        nota = svc.procesar_venta(
            None,
            [{'articulo_sku': self.articulo.sku, 'cantidad': 2,
              'precio_unitario_usd': '20.00'}],
            self.almacen.pk,
            usuario='Admin',
        )
        n_movimientos = MovimientoKardex.global_objects.filter(
            empresa=self.empresa,
        ).count()

        # Gherkin EST01-10: el reverso NO lanza KardexProtegidoError...
        svc.reversar_nota_entrega(
            self.empresa.pk, nota.pk, 'error de prueba', usuario='Admin',
        )

        nota.refresh_from_db()
        self.assertEqual(nota.estado, 'ANULADO')
        # ...y solo INSERTA el compensatorio: N+1 movimientos, 0 borrados.
        self.assertEqual(
            MovimientoKardex.global_objects.filter(empresa=self.empresa).count(),
            n_movimientos + 1,
            'el reverso inserta un DEVOLUCION_VENTA (N+1); jamás borra kárdex',
        )
        self.assertTrue(
            MovimientoKardex.global_objects.filter(
                empresa=self.empresa, concepto='DEVOLUCION_VENTA',
            ).exists(),
            'el movimiento compensatorio DEVOLUCION_VENTA debe existir',
        )

    def test_receivers_cableados_solo_a_la_clase_real(self):
        from django.db.models.signals import pre_delete, pre_save
        from django.dispatch.dispatcher import _make_id

        # REQ-EST01-07: los receivers se conectan con sender=clase REAL.
        # El registry guarda lookup_key=(id(receiver), _make_id(sender));
        # para una clase, _make_id devuelve id(clase). Las clases
        # HISTÓRICAS de migraciones se reconstruyen por ModelState (id
        # distinto, sin relación de subclase) → sus señales no alcanzan
        # estos receivers y las RunPython quedan exentas (Gherkin EST01-09;
        # prueba end-to-end: roundtrip de la 0029 en la verificación final).
        for senal in (pre_save, pre_delete):
            senders_cableados = [r_key[1] for r_key, *_ in senal.receivers]
            self.assertIn(
                _make_id(MovimientoKardex),
                senders_cableados,
                f'{senal} debe tener un receiver con sender=MovimientoKardex real',
            )
