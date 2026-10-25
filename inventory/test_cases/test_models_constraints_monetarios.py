"""
DATA-08 — ``CheckConstraint`` de rangos sobre montos monetarios.

Contratos bajo prueba
---------------------
``ConfiguracionEmpresa`` (3 constraints):
  * ``tasa_bcv_no_negativa``     : ``tasa_bcv >= 0``.
  * ``factor_cobertura_positivo``: ``factor_cobertura > 0`` (divisor/multiplicador
    de la política cambiaria; 0 rompe la derivación de DATA-05).
  * ``margen_rango_valido``      : ``0 <= margen_global < 100`` (semirango
    superior ABIERTO: con método MARGIN y margen=100, ``costo / (1 - 100/100)``
    divide por cero).

``DetalleNotaEntrega`` (3 constraints):
  * ``cantidad_positiva`` : ``cantidad > 0`` (una línea sin unidades no es venta).
  * ``iva_rango``         : ``0 <= iva_porcentaje <= 100`` (snapshot).
  * ``descuento_rango``   : ``0 <= descuento_aplicado <= 100``.

Diagnóstico previo (PASO 0, BD real pre-migración): 0 ofensores en los
6 checks (2 configs y 35 detalles). Por eso la migración 0024 es SOLO
``AddConstraint`` ×6, sin ``RunPython`` de backfill.

Nota sobre ``iva_porcentaje`` / ``descuento_aplicado``
------------------------------------------------------
Ambos son ``DecimalField`` con ``default=Decimal('0.00')`` y SIN
``null=True``: la columna es NOT NULL, así que el CHECK no necesita la
cláusula ``isnull`` tolerante de DATA-04. Se usa la forma simple
``Q(campo__gte=0, campo__lte=100)``.

Método
------
Todos los rechazos se prueban con ``bulk_create()`` (NO pasa por
``save()`` —saltando la coerción de DATA-05— ni por ``clean()``): si la
BD acepta la fila, el esquema es el problema. Para que el
``IntegrityError`` solo pueda venir del CHECK (y no de la unicidad
OneToOne de ``ConfiguracionEmpresa.empresa``), cada caso usa una empresa
cuya config auto-sembrada por la señal ``post_save`` fue eliminada.
"""

import importlib
import pkgutil
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.migrations.operations import AddConstraint
from django.test import TestCase

from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import (
    Almacen,
    Articulo,
    ConfiguracionEmpresa,
    DetalleNotaEntrega,
    Empresa,
    NotaEntrega,
)


def _migracion_0024():
    """Devuelve el módulo de la migración 0024 (o None si aún no existe)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith('0024_'):
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


class TestData08ConfigMontos(TestCase):
    """DATA-08: la BD rechaza configuraciones financieras fuera de rango."""

    def _empresa_con_slot_libre(self, etiqueta):
        """
        Empresa nueva cuyo slot OneToOne de configuración quedó libre.

        La señal ``post_save`` siembra una config válida al crear la
        empresa; se elimina para que el INSERT del test sea el único
        intento sobre ese slot. Así el ``IntegrityError`` solo puede
        venir del CHECK bajo prueba, nunca de la unicidad OneToOne.
        """
        sufijo = abs(hash(f'{self._testMethodName}-{etiqueta}')) % (10 ** 8)
        empresa = Empresa.objects.create(
            nombre=f'DATA08 {etiqueta} {self._testMethodName[:22]}',
            rif=f'J-DATA08-{sufijo:08d}',
            activa=True,
        )
        ConfiguracionEmpresa.global_objects.filter(empresa=empresa).delete()
        return empresa

    def _rechaza(self, etiqueta, **overrides):
        """bulk_create() con valores inválidos DEBE reventar en la BD."""
        empresa = self._empresa_con_slot_libre(etiqueta)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # bulk_create() NO pasa por save() (coerción DATA-05) ni
                # por clean(): el rechazo tiene que venir del esquema.
                ConfiguracionEmpresa.global_objects.bulk_create([
                    ConfiguracionEmpresa(empresa=empresa, **overrides)
                ])
        self.assertFalse(
            ConfiguracionEmpresa.global_objects.filter(empresa=empresa).exists(),
            msg='El rollback no debe dejar persistida la configuración inválida.',
        )

    # -- 1. tasa_bcv >= 0 -------------------------------------------------
    def test_data08_config_rechaza_tasa_bcv_negativa(self):
        self._rechaza('bcv-negativo', tasa_bcv=Decimal('-1.0000'))

    # -- 2. factor_cobertura > 0 ------------------------------------------
    def test_data08_config_rechaza_factor_cero(self):
        self._rechaza('factor-cero', factor_cobertura=Decimal('0.0000'))

    # -- 3. margen_global en [0, 100) --------------------------------------
    def test_data08_config_rechaza_margen_fuera_de_rango(self):
        for margen in (Decimal('-1.00'), Decimal('100.00')):
            with self.subTest(margen=margen):
                self._rechaza(f'margen-{margen}', margen_global=margen)

    # -- 4. Límites válidos aceptados --------------------------------------
    def test_data08_config_acepta_limites_validos(self):
        casos = [
            ('tasa_bcv=0.0000', {'tasa_bcv': Decimal('0.0000')}),
            ('factor=0.0001', {'factor_cobertura': Decimal('0.0001')}),
            ('margen=0.00', {'margen_global': Decimal('0.00')}),
            ('margen=99.99', {'margen_global': Decimal('99.99')}),
        ]
        for etiqueta, overrides in casos:
            with self.subTest(caso=etiqueta):
                empresa = self._empresa_con_slot_libre(etiqueta)
                try:
                    ConfiguracionEmpresa.global_objects.bulk_create([
                        ConfiguracionEmpresa(empresa=empresa, **overrides)
                    ])
                except IntegrityError as exc:
                    self.fail(
                        f'La BD rechazó un límite VÁLIDO ({etiqueta}): {exc}'
                    )
                self.assertTrue(
                    ConfiguracionEmpresa.global_objects.filter(
                        empresa=empresa
                    ).exists(),
                    msg=f'La configuración válida ({etiqueta}) debe persistir.',
                )


class TestData08DetalleMontos(TestCase):
    """DATA-08: la BD rechaza líneas de nota con montos fuera de rango."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA08 {self._testMethodName[:28]}',
            rif=f'J-DATA08D-{sufijo:08d}',
            activa=True,
        )
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)

        self.almacen = Almacen.objects.create(
            empresa=self.empresa,
            nombre='DATA08 Almacén Principal',
            es_principal=True,
        )
        self.articulo = Articulo.objects.create(
            empresa=self.empresa,
            sku=f'DATA08-ART-{sufijo:08d}',
            nombre='Artículo DATA08',
            tipo='FISICO',
            categoria='OTROS',
            costo=Decimal('10.00'),
            precio_divisa=Decimal('15.00'),
        )
        self.nota = NotaEntrega.objects.create(
            empresa=self.empresa,
            almacen=self.almacen,
        )

    def _detalle(self, **overrides):
        """Lnea válida + overrides; bulk_create() no pasa por save()."""
        datos = {
            'nota_entrega': self.nota,
            'articulo': self.articulo,
            'almacen': self.almacen,
            'cantidad': Decimal('1.00'),
            'iva_porcentaje': Decimal('16.00'),
            'descuento_aplicado': Decimal('0.00'),
            **_datos_precio(),
        }
        datos.update(overrides)
        return DetalleNotaEntrega(**datos)

    # -- 5. cantidad > 0 ----------------------------------------------------
    def test_data08_detalle_rechaza_cantidad_no_positiva(self):
        for cantidad in (Decimal('0.00'), Decimal('-1.00')):
            with self.subTest(cantidad=cantidad):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        DetalleNotaEntrega.objects.bulk_create([
                            self._detalle(cantidad=cantidad)
                        ])
                self.assertEqual(
                    DetalleNotaEntrega.objects.count(), 0,
                    msg='El rollback no debe dejar persistida la línea inválida.',
                )

    # -- 6. iva_porcentaje en [0, 100] ---------------------------------------
    def test_data08_detalle_rechaza_iva_fuera_de_rango(self):
        for iva in (Decimal('-0.50'), Decimal('100.50')):
            with self.subTest(iva=iva):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        DetalleNotaEntrega.objects.bulk_create([
                            self._detalle(iva_porcentaje=iva)
                        ])
                self.assertEqual(
                    DetalleNotaEntrega.objects.count(), 0,
                    msg='El rollback no debe dejar persistida la línea inválida.',
                )

    # -- 7. descuento_aplicado en [0, 100] -----------------------------------
    def test_data08_detalle_rechaza_descuento_fuera_de_rango(self):
        for descuento in (Decimal('-1.00'), Decimal('101.00')):
            with self.subTest(descuento=descuento):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        DetalleNotaEntrega.objects.bulk_create([
                            self._detalle(descuento_aplicado=descuento)
                        ])
                self.assertEqual(
                    DetalleNotaEntrega.objects.count(), 0,
                    msg='El rollback no debe dejar persistida la línea inválida.',
                )

    # -- 8. Límites válidos aceptados ------------------------------------------
    def test_data08_detalle_acepta_limites_validos(self):
        casos = [
            ('cantidad=0.01', {'cantidad': Decimal('0.01')}),
            ('iva=0.00', {'iva_porcentaje': Decimal('0.00')}),
            ('iva=100.00', {'iva_porcentaje': Decimal('100.00')}),
            ('descuento=0.00', {'descuento_aplicado': Decimal('0.00')}),
            ('descuento=100.00', {'descuento_aplicado': Decimal('100.00')}),
        ]
        persistidas = 0
        for etiqueta, overrides in casos:
            with self.subTest(caso=etiqueta):
                try:
                    DetalleNotaEntrega.objects.bulk_create([
                        self._detalle(**overrides)
                    ])
                except IntegrityError as exc:
                    self.fail(
                        f'La BD rechazó un límite VÁLIDO ({etiqueta}): {exc}'
                    )
                persistidas += 1
                self.assertEqual(
                    DetalleNotaEntrega.objects.count(), persistidas,
                    msg=f'La línea válida ({etiqueta}) debe persistir.',
                )


class TestData08MigracionMonetaria(TestCase):
    """DATA-08: la migración 0024 añade exactamente los 6 constraints."""

    def test_data08_migracion_anade_seis_constraints(self):
        migracion = _migracion_0024()
        self.assertIsNotNone(
            migracion,
            msg='No existe ninguna migración inventory/migrations/0024_*',
        )

        operaciones = list(migracion.Migration.operations)
        self.assertEqual(
            len(operaciones), 6,
            msg=(
                'La 0024 debe contener exactamente 6 operaciones '
                f'(encontradas: {len(operaciones)}). El diagnóstico de DATA-08 '
                'halló 0 ofensores: no hace falta RunPython de backfill.'
            ),
        )

        esperados = {
            'configuracionempresa': {
                'tasa_bcv_no_negativa',
                'factor_cobertura_positivo',
                'margen_rango_valido',
            },
            'detallenotaentrega': {
                'cantidad_positiva',
                'iva_rango',
                'descuento_rango',
            },
        }

        encontrados = {}
        for i, op in enumerate(operaciones):
            self.assertIsInstance(
                op, AddConstraint,
                msg=(
                    f'La operación #{i + 1} de la 0024 debe ser AddConstraint '
                    '(el diagnóstico halló 0 ofensores: sin backfill).'
                ),
            )
            nombre = getattr(op.constraint, 'name', None)
            self.assertIn(
                op.model_name, esperados,
                msg=f'El constraint "{nombre}" está en un modelo inesperado '
                    f'("{op.model_name}").',
            )
            self.assertIn(
                nombre, esperados[op.model_name],
                msg=f'Constraint con nombre no documentado: "{nombre}".',
            )
            previos = encontrados.setdefault(op.model_name, set())
            self.assertNotIn(
                nombre, previos,
                msg=f'El constraint "{nombre}" aparece duplicado en la 0024.',
            )
            previos.add(nombre)

        self.assertEqual(
            encontrados, esperados,
            msg='Falta al menos uno de los 6 constraints documentados.',
        )
