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
    Contacto,
    DetalleDocumentoCompra,
    DetalleNotaCredito,
    DetalleNotaEntrega,
    DocumentoCompra,
    Empresa,
    NotaCredito,
    NotaEntrega,
)


def _buscar_migracion(prefijo):
    """Devuelve el módulo de la migración con ese prefijo (o None)."""
    from inventory import migrations as mig_pkg

    for info in pkgutil.iter_modules(mig_pkg.__path__):
        if info.name.startswith(prefijo):
            return importlib.import_module(f'inventory.migrations.{info.name}')
    return None


def _migracion_0024():
    """Devuelve el módulo de la migración 0024 (o None si aún no existe)."""
    return _buscar_migracion('0024_')


def _migracion_0031():
    """Devuelve el módulo de la migración 0031 (o None si aún no existe)."""
    return _buscar_migracion('0031_')


def _datos_precio():
    """Snapshots mínimos exigidos por el modelo (ADR-18)."""
    return {
        'precio_base': Decimal('10.0000'),
        'precio_ajustado': Decimal('10.0000'),
        'precio_directo_bcv': Decimal('400.00'),
        'precio_ajustado_bcv': Decimal('400.00'),
    }


def _costos_compra():
    """Snapshots de costos válidos para una línea de compra (ADR-18)."""
    return {
        'costo_base': Decimal('10.0000'),
        'costo_ajustado': Decimal('10.5000'),
        'costo_directo_bcv': Decimal('400.00'),
        'costo_ajustado_bcv': Decimal('420.00'),
        'costo_unitario_snapshot': Decimal('10.0000'),
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


class TestData08ExtensionBacklog(TestCase):
    """DATA-08 (extensión backlog): campos monetarios pendientes.

    Contratos bajo prueba (10 ``CheckConstraint`` nuevas, migración 0031)
    ---------------------------------------------------------------------
    ``ConfiguracionEmpresa`` (3 — se AÑADEN a la lista existente de 0024):
      * ``descuento_global_rango``   : ``0 <= descuento_global <= 100``.
      * ``factor_redondeo_positivo`` : ``factor_redondeo > 0`` (el
        help_text del campo lo promete desde 0018: un múltiplo de
        redondeo 0 rompe el módulo).
      * ``tasa_mercado_no_negativa`` : ``tasa_mercado >= 0``. La
        invariante DATA-05 la deriva en ``save()``, pero ``bulk_create()``
        y SQL crudo saltan esa capa: el esquema es la última línea.

    ``DetalleDocumentoCompra`` (4 — Meta nueva, antes sin constraints):
      * ``cantidad_compra_positiva``  : ``cantidad > 0``.
      * ``costos_compra_no_negativos``: los 5 snapshots de costo ``>= 0``
        en UNA constraint combinada (una fila con cualquier costo
        negativo no es una compra: es un descargo mal persistido).
      * ``descuento_compra_rango``    : ``0 <= descuento_aplicado <= 100``.
      * ``iva_compra_rango``          : ``0 <= iva_porcentaje <= 100``.

    ``DetalleNotaCredito`` (3 — se AÑADEN a ``detalle_nc_un_origen_exacto``):
      * ``cantidad_devuelta_positiva``: ``cantidad_devuelta > 0`` (una
        devolución de 0 unidades no tiene sentido; el service ya valida,
        el esquema respalda).
      * ``montos_nc_no_negativos``    : precio_unitario_snapshot,
        subtotal_devuelto_usd, iva_usd y linea_total_usd ``>= 0``
        (combinada).
      * ``iva_nc_rango``              : ``0 <= iva_porcentaje_snapshot
        <= 100``.

    Diagnóstico previo (PASO 0, BD real pre-migración): 0 ofensores en
    los 10 checks (2 configs, 61 detalles de compra, 0 NC). Por eso la
    0031 es SOLO ``AddConstraint`` ×10, sin ``RunPython`` de backfill.

    Método
    ------
    Idéntico al de las clases de arriba: los rechazos se prueban con
    ``bulk_create()`` (NO pasa por ``save()`` —ni la recalculación de
    los derivados de la NC ni la coerción DATA-05— ni por ``clean()``),
    envueltos en ``transaction.atomic()`` para que el ``IntegrityError``
    no envenene la transacción del test. Los límites VÁLIDOS (descuento
    0/100, tasa_mercado 0, factor 0.01, cantidad 0.0001, iva 0/100,
    costos 0, montos NC 0) se prueban como ACEPTACIÓN: garantizan que el
    CHECK no es demasiado estricto.
    """

    # ------------------------------------------------------------------
    # Fixture: tenant completo (empresa + config + almacén + artículo +
    # proveedor + compra + nota + línea de venta + NC) por los caminos
    # legítimos (objects.create → correlativos), y luego las líneas bajo
    # prueba vía bulk_create (sin señales ni guards).
    # ------------------------------------------------------------------
    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'DATA08X {self._testMethodName[:28]}',
            rif=f'J-DATA08X-{sufijo:08d}',
            activa=True,
        )
        token = set_current_empresa(self.empresa.id)
        self.addCleanup(reset_current_empresa, token)

        self.almacen = Almacen.objects.create(
            empresa=self.empresa,
            nombre='DATA08X Almacén Principal',
            es_principal=True,
        )
        self.articulo = Articulo.objects.create(
            empresa=self.empresa,
            sku=f'DATA08X-ART-{sufijo:08d}',
            nombre='Artículo DATA08X',
            tipo='FISICO',
            categoria='OTROS',
            costo=Decimal('10.00'),
            precio_divisa=Decimal('15.00'),
        )
        self.proveedor = Contacto.objects.create(
            empresa=self.empresa,
            nombre='Proveedor DATA08X',
            tipo='PROVEEDOR',
            identificacion=f'J-DATA08X-PRV-{sufijo:08d}',
            rif=f'J-DATA08X-PRV-{sufijo:08d}',
            nombre_asesor='Asesor DATA08X',
        )
        self.compra = DocumentoCompra.objects.create(
            empresa=self.empresa,
            proveedor=self.proveedor,
            monto_total_usd=Decimal('100.0000'),
        )
        self.nota = NotaEntrega.objects.create(
            empresa=self.empresa,
            almacen=self.almacen,
        )
        # Línea de venta válida (constraints 0024 vigentes) — origen de la NC.
        self.detalle_venta = DetalleNotaEntrega.objects.bulk_create([
            DetalleNotaEntrega(
                nota_entrega=self.nota,
                articulo=self.articulo,
                almacen=self.almacen,
                cantidad=Decimal('2.0000'),
                iva_porcentaje=Decimal('16.00'),
                descuento_aplicado=Decimal('0.00'),
                **_datos_precio(),
            ),
        ])[0]
        self.nc = NotaCredito.objects.create(
            empresa=self.empresa,
            nota_entrega=self.nota,
            motivo='DATA-08 extensión backlog',
        )

    # ------------------------------------------------------------------
    # Helpers — Config (slot OneToOne libre, mismo patrón de arriba)
    # ------------------------------------------------------------------
    def _empresa_con_slot_libre(self, etiqueta):
        """
        Empresa nueva cuyo slot OneToOne de configuración quedó libre.

        La señal ``post_save`` siembra una config válida al crear la
        empresa; se elimina para que el INSERT del test sea el único
        intento sobre ese slot y el ``IntegrityError`` solo pueda venir
        del CHECK bajo prueba.
        """
        sufijo = abs(hash(f'{self._testMethodName}-{etiqueta}')) % (10 ** 8)
        empresa = Empresa.objects.create(
            nombre=f'DATA08X {etiqueta} {self._testMethodName[:22]}',
            rif=f'J-DATA08X-{sufijo:08d}',
            activa=True,
        )
        ConfiguracionEmpresa.global_objects.filter(empresa=empresa).delete()
        return empresa

    def _rechaza_config(self, etiqueta, **overrides):
        """bulk_create() de Config con valores inválidos DEBE reventar."""
        empresa = self._empresa_con_slot_libre(etiqueta)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConfiguracionEmpresa.global_objects.bulk_create([
                    ConfiguracionEmpresa(empresa=empresa, **overrides)
                ])
        self.assertFalse(
            ConfiguracionEmpresa.global_objects.filter(empresa=empresa).exists(),
            msg='El rollback no debe dejar persistida la configuración inválida.',
        )

    def _acepta_config(self, etiqueta, **overrides):
        """bulk_create() de Config con un límite VÁLIDO debe persistir."""
        empresa = self._empresa_con_slot_libre(etiqueta)
        try:
            ConfiguracionEmpresa.global_objects.bulk_create([
                ConfiguracionEmpresa(empresa=empresa, **overrides)
            ])
        except IntegrityError as exc:
            self.fail(f'La BD rechazó un límite VÁLIDO ({etiqueta}): {exc}')
        self.assertTrue(
            ConfiguracionEmpresa.global_objects.filter(empresa=empresa).exists(),
            msg=f'La configuración válida ({etiqueta}) debe persistir.',
        )

    # ------------------------------------------------------------------
    # Helpers — líneas de compra
    # ------------------------------------------------------------------
    def _detalle_compra(self, **overrides):
        """Línea de compra válida + overrides (bulk_create no pasa por save)."""
        datos = {
            'documento_compra': self.compra,
            'articulo': self.articulo,
            'almacen': self.almacen,
            'cantidad': Decimal('1.0000'),
            'descuento_aplicado': Decimal('0.00'),
            'iva_porcentaje': Decimal('16.00'),
            **_costos_compra(),
        }
        datos.update(overrides)
        return DetalleDocumentoCompra(**datos)

    def _rechaza_compra(self, **overrides):
        """bulk_create() de línea de compra inválida DEBE reventar."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DetalleDocumentoCompra.objects.bulk_create([
                    self._detalle_compra(**overrides)
                ])
        self.assertEqual(
            DetalleDocumentoCompra.objects.count(), 0,
            msg='El rollback no debe dejar persistida la línea inválida.',
        )

    def _acepta_compra(self, esperado=1, **overrides):
        """bulk_create() de línea de compra en límite VÁLIDO persiste."""
        try:
            DetalleDocumentoCompra.objects.bulk_create([
                self._detalle_compra(**overrides)
            ])
        except IntegrityError as exc:
            self.fail(f'La BD rechazó un límite VÁLIDO en compra: {exc}')
        self.assertEqual(
            DetalleDocumentoCompra.objects.count(), esperado,
            msg='La línea válida debe persistir.',
        )

    # ------------------------------------------------------------------
    # Helpers — líneas de NC
    # ------------------------------------------------------------------
    def _detalle_nc(self, **overrides):
        """Línea de NC válida + overrides (bulk_create no recalcula nada)."""
        datos = {
            'nota_credito': self.nc,
            'detalle_origen_venta': self.detalle_venta,
            'articulo': self.articulo,
            'almacen': self.almacen,
            'cantidad_devuelta': Decimal('1.0000'),
            'precio_unitario_snapshot': Decimal('20.0000'),
            'iva_porcentaje_snapshot': Decimal('16.00'),
            'subtotal_devuelto_usd': Decimal('20.0000'),
            'iva_usd': Decimal('3.2000'),
            'linea_total_usd': Decimal('23.2000'),
        }
        datos.update(overrides)
        return DetalleNotaCredito(**datos)

    def _rechaza_nc(self, **overrides):
        """bulk_create() de línea de NC inválida DEBE reventar."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DetalleNotaCredito.objects.bulk_create([
                    self._detalle_nc(**overrides)
                ])
        self.assertEqual(
            DetalleNotaCredito.objects.count(), 0,
            msg='El rollback no debe dejar persistida la línea inválida.',
        )

    def _acepta_nc(self, esperado=1, **overrides):
        """bulk_create() de línea de NC en límite VÁLIDO persiste."""
        try:
            DetalleNotaCredito.objects.bulk_create([
                self._detalle_nc(**overrides)
            ])
        except IntegrityError as exc:
            self.fail(f'La BD rechazó un límite VÁLIDO en NC: {exc}')
        self.assertEqual(
            DetalleNotaCredito.objects.count(), esperado,
            msg='La línea válida debe persistir.',
        )

    # -- 1. descuento_global en [0, 100] ------------------------------------
    def test_data08_config_rechaza_descuento_global_fuera_de_rango(self):
        for descuento in (Decimal('-1.00'), Decimal('101.00')):
            with self.subTest(descuento_global=descuento):
                self._rechaza_config(
                    f'desc-global-{descuento}', descuento_global=descuento,
                )
        # Límites válidos: 0% y 100% son descuentos legales.
        self._acepta_config(
            'descuento_global=0.00', descuento_global=Decimal('0.00'),
        )
        self._acepta_config(
            'descuento_global=100.00', descuento_global=Decimal('100.00'),
        )

    # -- 2. factor_redondeo > 0 ----------------------------------------------
    def test_data08_config_rechaza_factor_redondeo_no_positivo(self):
        self._rechaza_config(
            'factor-redondeo-cero', factor_redondeo=Decimal('0.00'),
        )
        # Límite válido: el múltiplo mínimo persiste.
        self._acepta_config(
            'factor_redondeo=0.01', factor_redondeo=Decimal('0.01'),
        )

    # -- 3. tasa_mercado >= 0 --------------------------------------------------
    def test_data08_config_rechaza_tasa_mercado_negativa(self):
        self._rechaza_config(
            'tasa-mercado-negativa', tasa_mercado=Decimal('-1.0000'),
        )
        # Límite válido: tasa mercado 0 (degradación sin tasas) persiste.
        self._acepta_config(
            'tasa_mercado=0.0000', tasa_mercado=Decimal('0.0000'),
        )

    # -- 4. cantidad de compra > 0 ---------------------------------------------
    def test_data08_compra_rechaza_cantidad_no_positiva(self):
        for cantidad in (Decimal('0.0000'), Decimal('-1.0000')):
            with self.subTest(cantidad=cantidad):
                self._rechaza_compra(cantidad=cantidad)
        # Límite válido: la unidad mínima persiste.
        self._acepta_compra(esperado=1, cantidad=Decimal('0.0001'))

    # -- 5. costos de compra >= 0 (constraint combinada) ------------------------
    def test_data08_compra_rechaza_costos_negativos(self):
        casos = [
            ('costo_base=-1.0000', {'costo_base': Decimal('-1.0000')}),
            ('costo_ajustado_bcv=-1.00', {'costo_ajustado_bcv': Decimal('-1.00')}),
        ]
        for etiqueta, overrides in casos:
            with self.subTest(caso=etiqueta):
                self._rechaza_compra(**overrides)
        # Límite válido: costo 0 es legal (regalías, bonificaciones).
        self._acepta_compra(
            esperado=1,
            costo_base=Decimal('0.0000'),
            costo_ajustado=Decimal('0.0000'),
            costo_directo_bcv=Decimal('0.00'),
            costo_ajustado_bcv=Decimal('0.00'),
            costo_unitario_snapshot=Decimal('0.0000'),
        )

    # -- 6. iva y descuento de compra en [0, 100] -------------------------------
    def test_data08_compra_rechaza_iva_descuento_fuera_de_rango(self):
        casos = [
            ('iva_porcentaje=101.00', {'iva_porcentaje': Decimal('101.00')}),
            ('descuento_aplicado=-1.00', {'descuento_aplicado': Decimal('-1.00')}),
        ]
        for etiqueta, overrides in casos:
            with self.subTest(caso=etiqueta):
                self._rechaza_compra(**overrides)
        # Límites válidos: 0 y 100 en ambos porcentuales.
        self._acepta_compra(esperado=1, iva_porcentaje=Decimal('0.00'))
        self._acepta_compra(esperado=2, iva_porcentaje=Decimal('100.00'))
        self._acepta_compra(esperado=3, descuento_aplicado=Decimal('0.00'))
        self._acepta_compra(esperado=4, descuento_aplicado=Decimal('100.00'))

    # -- 7. cantidad_devuelta > 0 -------------------------------------------------
    def test_data08_nc_rechaza_cantidad_devuelta_no_positiva(self):
        self._rechaza_nc(cantidad_devuelta=Decimal('0.0000'))
        # Límite válido: la unidad mínima persiste.
        self._acepta_nc(esperado=1, cantidad_devuelta=Decimal('0.0001'))

    # -- 8. montos de NC >= 0 (constraint combinada) ------------------------------
    def test_data08_nc_rechaza_montos_negativos(self):
        casos = [
            ('subtotal_devuelto_usd=-1',
             {'subtotal_devuelto_usd': Decimal('-1.0000')}),
            ('linea_total_usd=-1',
             {'linea_total_usd': Decimal('-1.0000')}),
        ]
        for etiqueta, overrides in casos:
            with self.subTest(caso=etiqueta):
                self._rechaza_nc(**overrides)
        # Límite válido: devolución con precio 0 (garantía/cortesía) —
        # los cuatro montos en 0 persisten.
        self._acepta_nc(
            esperado=1,
            precio_unitario_snapshot=Decimal('0.0000'),
            subtotal_devuelto_usd=Decimal('0.0000'),
            iva_usd=Decimal('0.0000'),
            linea_total_usd=Decimal('0.0000'),
        )

    # -- 9. iva_porcentaje_snapshot de NC en [0, 100] -----------------------------
    def test_data08_nc_rechaza_iva_snapshot_fuera_de_rango(self):
        for iva in (Decimal('-0.50'), Decimal('150.00')):
            with self.subTest(iva_porcentaje_snapshot=iva):
                self._rechaza_nc(iva_porcentaje_snapshot=iva)
        # Límites válidos: 0 y 100.
        self._acepta_nc(esperado=1, iva_porcentaje_snapshot=Decimal('0.00'))
        self._acepta_nc(esperado=2, iva_porcentaje_snapshot=Decimal('100.00'))

    # -- 10. La migración 0031 añade exactamente los 10 constraints -----------------
    def test_data08_migracion_0031_anade_diez_constraints(self):
        migracion = _migracion_0031()
        self.assertIsNotNone(
            migracion,
            msg='No existe ninguna migración inventory/migrations/0031_*',
        )

        operaciones = list(migracion.Migration.operations)
        self.assertEqual(
            len(operaciones), 10,
            msg=(
                'La 0031 debe contener exactamente 10 operaciones '
                f'(encontradas: {len(operaciones)}). El diagnóstico de esta '
                'extensión halló 0 ofensores: no hace falta RunPython.'
            ),
        )

        esperados = {
            'configuracionempresa': {
                'descuento_global_rango',
                'factor_redondeo_positivo',
                'tasa_mercado_no_negativa',
            },
            'detalledocumentocompra': {
                'cantidad_compra_positiva',
                'costos_compra_no_negativos',
                'descuento_compra_rango',
                'iva_compra_rango',
            },
            'detallenotacredito': {
                'cantidad_devuelta_positiva',
                'montos_nc_no_negativos',
                'iva_nc_rango',
            },
        }

        encontrados = {}
        for i, op in enumerate(operaciones):
            self.assertIsInstance(
                op, AddConstraint,
                msg=(
                    f'La operación #{i + 1} de la 0031 debe ser AddConstraint '
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
                msg=f'El constraint "{nombre}" aparece duplicado en la 0031.',
            )
            previos.add(nombre)

        self.assertEqual(
            encontrados, esperados,
            msg='Falta al menos uno de los 10 constraints documentados.',
        )
