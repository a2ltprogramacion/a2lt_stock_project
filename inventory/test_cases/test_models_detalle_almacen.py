"""
DATA-03 — ``DetalleNotaEntrega.almacen`` obligatorio (NOT NULL).

Contexto
--------
``DetalleNotaEntrega.almacen`` nació como ``null=True, blank=True`` porque la
cabecera ya guardaba el almacén. Eso permitió líneas huérfanas: una venta con
origen físico distinto por línea (multi-almacén) podía quedar sin trazabilidad
de Kárdex si algún camino de creación omitía el campo.

La cabecera ``NotaEntrega.almacen`` es NOT NULL, por lo que el backfill de las
líneas huérfanas es inequívoco: ``detalle.almacen = nota_entrega.almacen``.

Estos tests fijan cuatro contratos:
  1. El campo del modelo deja de ser nullable/blank.
  2. La BD rechaza una línea sin almacén (saltándose ``save()`` con
     ``bulk_create``).
  3. La migración 0022 rellena desde la cabecera ANTES del ``AlterField``.
  4. ``procesar_venta`` asigna almacén a TODAS las líneas.

Nota sobre el test de la migración
----------------------------------
Una vez aplicada la migración, SQLite no permite crear una línea huérfana
(el ``UPDATE ... SET almacen_id=NULL`` viola el NOT NULL). Por eso el test
verifica la estructura de la migración (RunPython antes del AlterField) y
ejecuta la función de backfill con los ``apps`` reales dos veces para
comprobar que es idempotente y que su SQL es válido. La creación del huérfano
por SQL crudo solo es posible *antes* de la migración, no en la BD de tests
que ya corre con 0022 aplicada.
"""

import importlib
import pkgutil
from decimal import Decimal

from django.apps import apps as global_apps
from django.db import IntegrityError, transaction
from django.db.migrations.operations import AlterField, RunPython
from django.db.models import PROTECT
from django.test import TestCase

from inventory import services as svc
from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import (
    Almacen,
    Articulo,
    ConfiguracionEmpresa,
    DetalleNotaEntrega,
    Empresa,
    NotaEntrega,
)


def _migracion_0022():
    """Devuelve el módulo de la migración 0022 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0022_'):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


def _datos_precio():
    """Snapshots mínimos exigidos por el modelo (ADR-18)."""
    return {
        'precio_base': Decimal('10.0000'),
        'precio_ajustado': Decimal('10.0000'),
        'precio_directo_bcv': Decimal('400.00'),
        'precio_ajustado_bcv': Decimal('400.00'),
    }


class TestData03DetalleAlmacen(TestCase):
    """DATA-03: el almacén de la línea es obligatorio y trazable."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA03 {self._testMethodName[:28]}',
            rif=f'J-DATA03-{sufijo:08d}',
            activa=True,
        )
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)

        self.almacen = Almacen.objects.create(
            empresa=self.empresa,
            nombre='DATA03 Almacén Principal',
            es_principal=True,
        )
        self.articulo = Articulo.objects.create(
            empresa=self.empresa,
            sku='DATA03-ART-1',
            nombre='Artículo DATA03',
            tipo='FISICO',
            categoria='OTROS',
            costo=Decimal('10.00'),
            precio_divisa=Decimal('15.00'),
        )
        self.nota = NotaEntrega.objects.create(
            empresa=self.empresa,
            almacen=self.almacen,
        )

    # -- 1. Contrato del modelo -----------------------------------------
    def test_data03_campo_almacen_no_es_nullable(self):
        campo = DetalleNotaEntrega._meta.get_field('almacen')
        self.assertFalse(
            campo.null,
            msg='DetalleNotaEntrega.almacen debe ser NOT NULL (null=False).',
        )
        self.assertFalse(
            campo.blank,
            msg='DetalleNotaEntrega.almacen debe ser obligatorio (blank=False).',
        )
        self.assertIs(
            campo.remote_field.on_delete,
            PROTECT,
            msg='El almacén de la línea debe conservar on_delete=PROTECT.',
        )

    # -- 2. La BD rechaza una línea sin almacén -------------------------
    def test_data03_bd_rechaza_detalle_sin_almacen(self):
        # bulk_create() NO pasa por save() ni por validación del modelo:
        # si la BD acepta NULL, el esquema es el problema.
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DetalleNotaEntrega.objects.bulk_create([
                    DetalleNotaEntrega(
                        nota_entrega=self.nota,
                        articulo=self.articulo,
                        almacen_id=None,
                        cantidad=Decimal('1.00'),
                        **_datos_precio(),
                    )
                ])

        self.assertEqual(
            DetalleNotaEntrega.objects.filter(
                nota_entrega=self.nota, almacen__isnull=True
            ).count(),
            0,
            msg='La transacción debe haberse revertido sin dejar huérfanos.',
        )

    # -- 3. La migración rellena antes de exigir NOT NULL ---------------
    def test_data03_migracion_rellena_desde_cabecera(self):
        migracion = _migracion_0022()
        self.assertIsNotNone(
            migracion,
            msg='No existe ninguna migración inventory/migrations/0022_*',
        )

        operaciones = list(migracion.Migration.operations)
        idx_backfill = next(
            (
                i for i, op in enumerate(operaciones)
                if isinstance(op, RunPython)
                and op.code is not None
                and 'rellenar_almacen_detalle' in getattr(op.code, '__name__', '')
            ),
            None,
        )
        self.assertIsNotNone(
            idx_backfill,
            msg=(
                'La migración 0022 debe incluir un RunPython llamado '
                '*_rellenar_almacen_detalle*'
            ),
        )

        idx_alter = next(
            (
                i for i, op in enumerate(operaciones)
                if isinstance(op, AlterField) and op.name == 'almacen'
            ),
            None,
        )
        self.assertIsNotNone(
            idx_alter,
            msg='La migración 0022 debe alterar el campo almacen.',
        )
        self.assertLess(
            idx_backfill,
            idx_alter,
            msg='El RunPython de backfill debe ir ANTES del AlterField.',
        )

        # La función existe con el nombre documentado y usa apps.get_model().
        self.assertIsNotNone(getattr(migracion, '_rellenar_almacen_detalle', None))

        # Idempotente y con SQL válido sobre los apps reales. (No hay huérfanos
        # posibles en la BD de tests: la columna ya es NOT NULL.)
        #
        # EST-02 fase 2 (ADR-35): el backfill usa .update() masivo — canal
        # bloqueado por DocumentoQuerySet en el modelo REAL. En producción la
        # migración corre sobre el registry histórico (queryset plano, inmune
        # por diseño, receivers con sender=clase real); el bypass es necesario
        # SOLO aquí porque este test usa global_apps deliberadamente para
        # validar el SQL real. Uso legítimo documentado del escape hatch
        # compartido (REQ-EST02-07; mismo precedente que el fixture de kárdex
        # viejo de EST-01 en tests.py).
        from inventory.kardex_guard import kardex_bypass

        with kardex_bypass('fixture DATA-03: backfill de la migración 0022'):
            migracion._rellenar_almacen_detalle(global_apps, None)
            migracion._rellenar_almacen_detalle(global_apps, None)
        self.assertFalse(
            DetalleNotaEntrega.objects.filter(almacen__isnull=True).exists(),
            msg='Después del backfill no debe quedar ninguna línea huérfana.',
        )

    # -- 4. procesar_venta asigna almacén en cada línea -----------------
    def test_data03_procesar_venta_asigna_almacen_en_cada_linea(self):
        config = ConfiguracionEmpresa.objects.get(empresa=self.empresa)
        config.tasa_bcv = Decimal('40.00')
        config.factor_cobertura = Decimal('1.00')
        config.save()

        articulo_2 = Articulo.objects.create(
            empresa=self.empresa,
            sku='DATA03-ART-2',
            nombre='Artículo DATA03 #2',
            tipo='FISICO',
            categoria='OTROS',
            costo=Decimal('20.00'),
            precio_divisa=Decimal('25.00'),
        )

        svc.registrar_movimiento(
            self.articulo, self.almacen, 'ENTRADA', Decimal('10'), 'DATA03 init'
        )
        svc.registrar_movimiento(
            articulo_2, self.almacen, 'ENTRADA', Decimal('10'), 'DATA03 init'
        )

        nota = svc.procesar_venta(
            cliente_id=None,
            lista_items=[
                {
                    'articulo_sku': self.articulo.sku,
                    'cantidad': '2',
                    'precio_unitario_usd': '15.00',
                },
                {
                    'articulo_sku': articulo_2.sku,
                    'cantidad': '1',
                    'precio_unitario_usd': '25.00',
                },
            ],
            almacen_id=self.almacen.pk,
            usuario='data03',
        )

        detalles = list(nota.detalles.all())
        self.assertEqual(len(detalles), 2)
        for detalle in detalles:
            self.assertEqual(
                detalle.almacen_id,
                nota.almacen_id,
                msg=(
                    'Toda línea debe registrar el almacén de origen para la '
                    'trazabilidad del Kárdex.'
                ),
            )
