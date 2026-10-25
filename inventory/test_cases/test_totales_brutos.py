"""
EST-06 — Totales honestos vía fuente única (REQ-EST06-01/02/03/04).

Contexto
--------
``total_documento_bs`` prometía "total del documento" pero computaba
``subtotal_bs + total_iva_bs`` — un BRUTO que NO aplica
``descuento_global``. DATA-01 ya movió los totales reales a
``inventory/calculos.py`` (única fuente de verdad), y las 5 vistas usan
``calculos.calcular_totales_documento``; la property estaba huérfana.

Decisión Gate G1 (§6.6): rename a ``total_bs_bruto`` + delegación total en
``calculos``; ``total_documento_bs`` desaparece SIN alias deprecado (un
alias con la misma firma y distinto valor sería una trampa silenciosa).

Contrato fijado por estos tests
--------------------------------
* La property NO tiene aritmética propia (REQ-EST06-01): ensambla dos
  claves ya cuantizadas por ``calcular_totales_documento``.
* Con ``descuento_global > 0`` el bruto es distinguible del neto
  (REQ-EST06-04: par bruto/neto honesto).
* ``models.py`` no vuelve a contener la fórmula duplicada (guard de
  inspección de fuente, patrón de ``test_calculos.py``).
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase

from inventory.calculos import calcular_totales_documento


class TestTotalBsBruto(TestCase):
    """EST-06: ``total_bs_bruto`` en NotaEntrega y DocumentoCompra."""

    def setUp(self):
        from inventory.services import registrar_movimiento

        self.empresa = self._crear_empresa()
        self.almacen = self._crear_almacen()
        self.art1 = self._crear_articulo('DATA01-01', 'Artículo DATA01 1')
        self.art2 = self._crear_articulo('DATA01-02', 'Artículo DATA01 2')
        registrar_movimiento(self.art1, self.almacen, 'ENTRADA', Decimal('500'), 'Stock EST-06')
        registrar_movimiento(self.art2, self.almacen, 'ENTRADA', Decimal('500'), 'Stock EST-06')
        self.user = User.objects.create_user('est06_user', password='test1234')

    @staticmethod
    def _crear_empresa():
        from inventory.models import Empresa
        from inventory.managers import set_current_empresa

        empresa = Empresa.objects.create(
            nombre='EST-06 Corp', rif='J-EST06-001', activa=True,
        )
        set_current_empresa(empresa.id)
        return empresa

    def _crear_almacen(self):
        from inventory.models import Almacen

        return Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén EST-06', es_principal=True,
        )

    def _crear_articulo(self, sku, nombre):
        from inventory.models import Articulo

        return Articulo.objects.create(
            empresa=self.empresa, sku=sku, nombre=nombre,
            tipo='FISICO', categoria='OTROS',
            costo=Decimal('5.00'), precio_divisa=Decimal('10.00'),
            iva_porcentaje=Decimal('16.00'),
        )

    def _crear_nota(
        self, factor_cobertura, descuento_global=Decimal('7.50'),
        iva_porcentaje=Decimal('16.00'), descuento_linea=Decimal('0'),
    ):
        from inventory.models import ConfiguracionEmpresa
        from inventory.services import procesar_venta

        config = ConfiguracionEmpresa.objects.get(empresa=self.empresa)
        config.factor_cobertura = Decimal(factor_cobertura)
        config.tasa_bcv = Decimal('60.0000')
        config.save()

        return procesar_venta(
            lista_items=[
                {
                    'articulo_sku': 'DATA01-01',
                    'cantidad': Decimal('3'),
                    'precio_base': Decimal('33.33'),
                    'iva_porcentaje': iva_porcentaje,
                    'descuento_aplicado': descuento_linea,
                },
                {
                    'articulo_sku': 'DATA01-02',
                    'cantidad': Decimal('2'),
                    'precio_base': Decimal('10.00'),
                    'iva_porcentaje': iva_porcentaje,
                    'descuento_aplicado': descuento_linea,
                },
            ],
            almacen_id=self.almacen.pk,
            tipo_documento='FACTURA',
            numero_factura=f'DATA01-{factor_cobertura}-{descuento_global}',
            descuento_global=descuento_global,
        )

    def test_nota_total_bs_bruto_es_bruto_y_difiere_del_neto(self):
        """
        EST06-01 (Gherkin): la property delega en ``calculos`` y devuelve el
        BRUTO — SIN aplicar ``descuento_global`` — por lo que con descuento
        se distingue del neto que muestran pantallas y PDF (REQ-EST06-02/04).
        """
        nota = self._crear_nota('1.0000', descuento_global=Decimal('10'))
        totales = calcular_totales_documento(
            list(nota.detalles.all()), nota.descuento_global,
        )

        self.assertEqual(
            nota.total_bs_bruto,
            totales['subtotal_bs_bruto'] + totales['total_iva_bs_bruto'],
        )
        self.assertNotEqual(nota.total_bs_bruto, totales['total_bs_neto'])

    def test_compra_total_bs_bruto_delega_con_descuento_de_compra(self):
        """
        EST06-04 (Gherkin): ``DocumentoCompra`` padece el mismo defecto y
        recibe idéntico tratamiento — la property delega en ``calculos`` y
        expone el bruto, distinguible del neto cuando hay descuento global.
        """
        from inventory.models import (
            Contacto, DocumentoCompra, DetalleDocumentoCompra,
        )

        proveedor = Contacto.objects.create(
            empresa=self.empresa,
            identificacion='J-PROV-EST06',
            nombre='Proveedor EST-06',
            tipo='PROVEEDOR',
            rif='J-PROV-EST06',
            nombre_asesor='Asesor',
        )
        # tasa_bcv_aplicada es necesaria para que iva_bs != 0 en los detalles.
        compra = DocumentoCompra.objects.create(
            empresa=self.empresa,
            proveedor=proveedor,
            tipo_documento='FACTURA_COMPRA',
            monto_total_usd=Decimal('100.00'),
            descuento_global=Decimal('10'),
            tasa_bcv_aplicada=Decimal('60.0000'),
        )
        DetalleDocumentoCompra.objects.create(
            documento_compra=compra, articulo=self.art1, almacen=self.almacen,
            cantidad=Decimal('5.00'),
            costo_base=Decimal('10.00'),
            costo_ajustado=Decimal('10.50'),
            costo_directo_bcv=Decimal('400.00'),
            costo_ajustado_bcv=Decimal('420.00'),
            iva_porcentaje=Decimal('16.00'),
        )
        DetalleDocumentoCompra.objects.create(
            documento_compra=compra, articulo=self.art2, almacen=self.almacen,
            cantidad=Decimal('2.00'),
            costo_base=Decimal('25.00'),
            costo_ajustado=Decimal('26.00'),
            costo_directo_bcv=Decimal('1000.00'),
            costo_ajustado_bcv=Decimal('1040.00'),
            iva_porcentaje=Decimal('16.00'),
        )
        totales = calcular_totales_documento(
            list(compra.detalles.all()), compra.descuento_global,
        )

        self.assertEqual(
            compra.total_bs_bruto,
            totales['subtotal_bs_bruto'] + totales['total_iva_bs_bruto'],
        )
        self.assertNotEqual(compra.total_bs_bruto, totales['total_bs_neto'])

    def test_models_py_no_contiene_formula_duplicada(self):
        """
        EST06-05 (Gherkin) / REQ-EST06-01: guard de inspección de fuente.
        ``models.py`` no puede volver a definir ``total_documento_bs`` ni
        computar importes por su cuenta (``subtotal_bs + total_iva_bs``):
        la única aritmética permitida es ensamblar claves de ``calculos``.
        Patrón del test de fuente de ``test_calculos.py``.
        """
        import inspect

        import inventory.models as models_mod

        fuente = inspect.getsource(models_mod)
        self.assertNotIn('def total_documento_bs', fuente)
        self.assertNotIn('self.subtotal_bs + self.total_iva_bs', fuente)

