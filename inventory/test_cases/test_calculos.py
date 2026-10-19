"""
DATA-01 — Cálculo único de totales, IVA y descuento.

Contexto
--------
El cálculo de totales/IVA/descuento estaba duplicado en cuatro sitios de
``inventory/views.py``:

* ``vista_detalle_nota``
* ``generar_pdf_nota``
* ``vista_detalle_compra``
* ``generar_pdf_compra``

La duplicación ya había producido una divergencia real: el PDF de nota
imprimía el IVA en Bs **bruto** (``total_iva_bs``) mientras la pantalla
mostraba el **neto** (``total_iva_bs * factor_descuento``).

Estos tests fijan el contrato de ``inventory/calculos.py`` como única fuente
de verdad y blindan el refactor contra futuras re-duplicaciones.

Nota sobre el test del PDF
--------------------------
``pypdf`` y ``PyPDF2`` no están instalados en este entorno y no se instalan
dependencias para un test. Por eso ``test_pdf_nota_muestra_iva_bs_neto``
parchea ``reportlab.platypus.SimpleDocTemplate.build`` para capturar el
``story`` que la vista construye y verificar el ``Paragraph`` con el texto
"Total IVA Bs".
"""

from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth.models import User
from django.http import HttpRequest, HttpResponse, QueryDict
from django.test import TestCase

from inventory import views
from inventory.calculos import (
    calcular_factor_descuento,
    calcular_totales_documento,
)


def _detalle(subtotal_usd, subtotal_bs, iva_usd, iva_bs):
    """Detalle mínimo con el contrato de propiedades del modelo."""
    return SimpleNamespace(
        subtotal_usd=Decimal(subtotal_usd),
        subtotal_bs=Decimal(subtotal_bs),
        iva_usd=Decimal(iva_usd),
        iva_bs=Decimal(iva_bs),
    )


def _detalles_conocidos():
    """Dos líneas con cifras fáciles de verificar a mano."""
    return [
        _detalle('100.00', '400.00', '16.00', '64.00'),
        _detalle('50.00', '200.00', '8.00', '32.00'),
    ]


class TestCalcularTotalesDocumento(TestCase):
    """Contrato puro de ``calcular_totales_documento``."""

    def test_calcular_totales_sin_descuento(self):
        totales = calcular_totales_documento(_detalles_conocidos(), Decimal('0'))

        self.assertEqual(totales['descuento_global'], Decimal('0'))
        self.assertEqual(totales['factor_descuento'], Decimal('1'))
        self.assertEqual(totales['subtotal_usd_bruto'], Decimal('150.00'))
        self.assertEqual(totales['subtotal_bs_bruto'], Decimal('600.00'))
        self.assertEqual(totales['total_iva_usd_bruto'], Decimal('24.00'))
        self.assertEqual(totales['total_iva_bs_bruto'], Decimal('96.00'))
        self.assertEqual(totales['subtotal_usd_neto'], Decimal('150.00'))
        self.assertEqual(totales['subtotal_bs_neto'], Decimal('600.00'))
        self.assertEqual(totales['total_iva_usd_neto'], Decimal('24.00'))
        self.assertEqual(totales['total_iva_bs_neto'], Decimal('96.00'))
        self.assertEqual(totales['monto_descuento_usd'], Decimal('0.00'))
        self.assertEqual(totales['monto_descuento_bs'], Decimal('0.00'))
        self.assertEqual(totales['total_usd_neto'], Decimal('174.00'))
        self.assertEqual(
            totales['total_bs_neto'],
            totales['subtotal_bs_neto'] + totales['total_iva_bs_neto'],
        )
        self.assertEqual(totales['total_bs_neto'], Decimal('696.00'))

    def test_calcular_totales_con_descuento_global_10(self):
        totales = calcular_totales_documento(_detalles_conocidos(), Decimal('10'))

        self.assertEqual(totales['factor_descuento'], Decimal('0.9'))
        self.assertEqual(totales['subtotal_usd_neto'], Decimal('135.00'))
        self.assertEqual(totales['subtotal_bs_neto'], Decimal('540.00'))
        self.assertEqual(totales['total_iva_usd_neto'], Decimal('21.60'))
        self.assertEqual(totales['total_iva_bs_neto'], Decimal('86.40'))
        self.assertEqual(totales['monto_descuento_usd'], Decimal('15.00'))
        self.assertEqual(totales['monto_descuento_bs'], Decimal('60.00'))
        self.assertEqual(totales['total_usd_neto'], Decimal('156.60'))
        self.assertEqual(totales['total_bs_neto'], Decimal('626.40'))

    def test_calcular_totales_descuento_100_deja_todo_en_cero(self):
        totales = calcular_totales_documento(_detalles_conocidos(), Decimal('100'))

        self.assertEqual(totales['factor_descuento'], Decimal('0'))
        self.assertEqual(totales['subtotal_usd_neto'], Decimal('0.00'))
        self.assertEqual(totales['subtotal_bs_neto'], Decimal('0.00'))
        self.assertEqual(totales['total_iva_usd_neto'], Decimal('0.00'))
        self.assertEqual(totales['total_iva_bs_neto'], Decimal('0.00'))
        self.assertEqual(totales['total_usd_neto'], Decimal('0.00'))
        self.assertEqual(totales['total_bs_neto'], Decimal('0.00'))
        # El descuento registrado es el 100% del bruto.
        self.assertEqual(totales['monto_descuento_usd'], Decimal('150.00'))
        self.assertEqual(totales['monto_descuento_bs'], Decimal('600.00'))

    def test_calcular_totales_rechaza_descuento_fuera_de_rango(self):
        for valor in (Decimal('-1'), Decimal('150')):
            with self.subTest(descuento=valor):
                with self.assertRaises(ValueError):
                    calcular_totales_documento(_detalles_conocidos(), valor)

    def test_calcular_factor_descuento_es_la_unica_implementacion(self):
        """El factor ``1 - d/100`` solo se calcula en ``calculos.py``."""
        self.assertEqual(
            calcular_factor_descuento(Decimal('10')), Decimal('0.9'),
        )
        self.assertEqual(calcular_factor_descuento(None), Decimal('1'))
        for valor in (Decimal('-1'), Decimal('150')):
            with self.subTest(descuento=valor):
                with self.assertRaises(ValueError):
                    calcular_factor_descuento(valor)


class TestConsistenciaVistas(TestCase):
    """Aceptación DATA-01: pantalla y PDF comparten los mismos números."""

    def setUp(self):
        from inventory.services import registrar_movimiento

        self.empresa = self._crear_empresa()
        self.almacen = self._crear_almacen()
        self.art1 = self._crear_articulo('DATA01-01', 'Artículo DATA01 1')
        self.art2 = self._crear_articulo('DATA01-02', 'Artículo DATA01 2')
        registrar_movimiento(self.art1, self.almacen, 'ENTRADA', Decimal('500'), 'Stock DATA-01')
        registrar_movimiento(self.art2, self.almacen, 'ENTRADA', Decimal('500'), 'Stock DATA-01')
        self.user = User.objects.create_user('data01_user', password='test1234')

    @staticmethod
    def _crear_empresa():
        from inventory.models import Empresa
        from inventory.managers import set_current_empresa

        empresa = Empresa.objects.create(
            nombre='DATA-01 Corp', rif='J-DATA01-001', activa=True,
        )
        set_current_empresa(empresa.id)
        return empresa

    def _crear_almacen(self):
        from inventory.models import Almacen

        return Almacen.objects.create(
            empresa=self.empresa, nombre='Almacén DATA-01', es_principal=True,
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

    def _request(self):
        request = HttpRequest()
        request.method = 'GET'
        request.user = self.user
        request.session = {'empresa_id': self.empresa.pk}
        return request

    def _contexto_detalle_nota(self, nota):
        with patch('inventory.views.render') as mock_render:
            mock_render.return_value = HttpResponse('ok')
            response = views.vista_detalle_nota(self._request(), nota.pk)
        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()
        return mock_render.call_args[0][2]

    def test_totales_consistentes_pdf_vs_pantalla(self):
        for factor in ('1.0000', '1.4000', '2.0000'):
            with self.subTest(factor_cobertura=factor):
                nota = self._crear_nota(factor)
                totales = calcular_totales_documento(
                    list(nota.detalles.all()), nota.descuento_global,
                )
                contexto = self._contexto_detalle_nota(nota)

                self.assertEqual(contexto['total_usd'], totales['subtotal_usd_neto'])
                self.assertEqual(contexto['total_bs'], totales['total_bs_neto'])
                self.assertEqual(
                    contexto['total_iva_usd'], totales['total_iva_usd_neto'],
                )
                self.assertEqual(
                    contexto['total_iva_bs'], totales['total_iva_bs_neto'],
                )
                self.assertEqual(
                    contexto['monto_descuento_usd'],
                    totales['monto_descuento_usd'],
                )
                # Los netos incorporan de verdad el descuento global.
                self.assertNotEqual(
                    totales['total_iva_bs_neto'],
                    totales['total_iva_bs_bruto'],
                )

    def test_las_cuatro_vistas_usan_el_helper(self):
        import inspect

        for funcion in (
            views.vista_detalle_nota,
            views.generar_pdf_nota,
            views.vista_detalle_compra,
            views.generar_pdf_compra,
        ):
            with self.subTest(funcion=funcion.__name__):
                fuente = inspect.getsource(funcion)
                self.assertIn('calcular_totales_documento(', fuente)

    def test_pdf_nota_muestra_iva_bs_neto(self):
        """
        Vía usada: mock de ``SimpleDocTemplate.build`` (pypdf/PyPDF2 ausentes).

        El PDF debe imprimir el IVA en Bs NETO (con el descuento global
        aplicado), igual que ``generar_pdf_compra`` y la pantalla.
        """
        from reportlab.platypus import SimpleDocTemplate

        nota = self._crear_nota('1.4000', descuento_global=Decimal('10'))
        totales = calcular_totales_documento(
            list(nota.detalles.all()), nota.descuento_global,
        )
        esperado_neto = f"Total IVA Bs: {totales['total_iva_bs_neto']:.2f} Bs"
        esperado_bruto = f"Total IVA Bs: {totales['total_iva_bs_bruto']:.2f} Bs"
        # El bug solo es visible cuando el descuento cambia el número impreso.
        self.assertNotEqual(esperado_neto, esperado_bruto)

        with patch.object(SimpleDocTemplate, 'build') as mock_build:
            response = views.generar_pdf_nota(self._request(), nota.pk)

        self.assertEqual(response.status_code, 200)
        mock_build.assert_called_once()
        story = mock_build.call_args[0][0]
        textos = [
            getattr(flowable, 'text', '')
            for flowable in story
            if getattr(flowable, 'text', '')
        ]
        parrafos_iva_bs = [t for t in textos if 'Total IVA Bs' in t]

        self.assertEqual(len(parrafos_iva_bs), 1)
        self.assertIn(esperado_neto, parrafos_iva_bs[0])
        self.assertNotIn(esperado_bruto, parrafos_iva_bs[0])

    # ── Listado de notas: última duplicación del cálculo (cierre DATA-01) ────

    def _contexto_listado_notas(self):
        """
        Vía usada: invocación directa de la vista con ``render`` parcheado.

        ``vista_listado_notas_entrega`` solo depende de ``request.GET`` y del
        tenant activo (fijado en ``setUp`` con ``set_current_empresa``), igual
        que el resto de tests de vistas de este archivo.
        """
        request = self._request()
        request.GET = QueryDict('')
        with patch('inventory.views.render') as mock_render:
            mock_render.return_value = HttpResponse('ok')
            response = views.vista_listado_notas_entrega(request)
        self.assertEqual(response.status_code, 200)
        mock_render.assert_called_once()
        return mock_render.call_args[0][2]

    def test_listado_notas_usa_el_helper(self):
        import inspect

        fuente = inspect.getsource(views.vista_listado_notas_entrega)
        self.assertIn('calcular_totales_documento(', fuente)

    def test_listado_notas_respeta_descuento_de_linea(self):
        """
        El listado debe usar ``d.subtotal_usd`` (descuento de línea incluido)
        y no el cálculo naive ``cantidad * precio_base``.
        """
        nota = self._crear_nota(
            '1.0000',
            descuento_global=Decimal('0'),
            iva_porcentaje=Decimal('0'),
            descuento_linea=Decimal('10'),
        )
        detalles = list(nota.detalles.all())
        # Precondición: la línea realmente tiene descuento individual.
        self.assertEqual(detalles[0].descuento_aplicado, Decimal('10'))

        esperado = calcular_totales_documento(detalles, nota.descuento_global)

        # Cálculo naive que usaba el listado (ignora descuento de línea).
        naive_subtotal = sum(d.cantidad * d.precio_base for d in detalles)
        naive_iva = sum(d.iva_usd for d in detalles)
        naive_total = naive_subtotal + naive_iva

        contexto = self._contexto_listado_notas()
        fila = next(n for n in contexto['notas'] if n.pk == nota.pk)

        self.assertEqual(fila.total_doc_usd_listado, esperado['total_usd_neto'])
        self.assertEqual(
            fila.total_usd_listado, esperado['subtotal_usd_neto'],
        )
        self.assertEqual(
            fila.total_iva_usd_listado, esperado['total_iva_usd_neto'],
        )
        self.assertNotEqual(fila.total_doc_usd_listado, naive_total)
        self.assertLess(fila.total_doc_usd_listado, naive_total)

    def test_no_queda_factor_desc_en_views(self):
        fuente = Path(views.__file__).read_text(encoding='utf-8')

        self.assertEqual(fuente.count('factor_desc ='), 0)
        self.assertNotIn('factor_desc =', fuente)

    def test_servicios_usan_el_factor_compartido(self):
        """``services.py`` delega el factor global en ``inventory.calculos``."""
        from inventory import services

        fuente = Path(services.__file__).read_text(encoding='utf-8')

        self.assertIn('calcular_factor_descuento(', fuente)
        self.assertNotIn("Decimal('1') - (descuento_global", fuente)
