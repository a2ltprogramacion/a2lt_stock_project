"""
DATA-02 — Eliminación del N+1 en el cálculo de stock de combos del dashboard.

El dashboard calculaba el stock de cada combo recorriendo, en Python, cada
almacén activo y llamando a ``services.calcular_stock_combo()`` por cada
combinación (combo, almacén). Esa función ejecuta 1 query para leer la receta
y 1 query por componente, por lo que el número de queries crecía con el número
de combos y de almacenes (N+1).

Estos tests fijan:
  * el número de queries del dashboard es constante respecto al número de combos;
  * el total de queries se mantiene por debajo de un umbral razonable;
  * la semántica del cálculo (mínimo por receta, máximo entre almacenes,
    receta vacía = 0, componente sin inventario = 0 en ese almacén);
  * ``calcular_stock_combo`` (individual) sigue funcionando como regresión.
"""

from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test import Client, TestCase
from django.test.utils import CaptureQueriesContext

from inventory import services as svc
from inventory.models import Almacen, Articulo, Empresa, InventarioAlmacen, RecetaCombo
from inventory.managers import set_current_empresa


class DashboardCombosBaseTest(TestCase):
    """Base con tenant, usuario autenticado y helpers de datos."""

    def setUp(self):
        self.empresa = Empresa.objects.create(
            nombre='DATA-02 Corp', rif='J-DATA02-001', activa=True
        )
        set_current_empresa(self.empresa.pk)

        self.user = User.objects.create_user('data02_user', password='pw12345')
        self.user.perfil.empresas_permitidas.add(self.empresa)
        self.user.perfil.empresa_activa = self.empresa
        self.user.perfil.save()

        self.client = Client()
        self.client.login(username='data02_user', password='pw12345')
        session = self.client.session
        session['empresa_id'] = self.empresa.pk
        session.save()

    def _crear_almacen(self, nombre):
        return Almacen.objects.create(
            empresa=self.empresa, nombre=nombre, es_principal=False
        )

    def _crear_fisico(self, sku):
        return Articulo.objects.create(
            empresa=self.empresa,
            sku=sku,
            nombre=f'Componente {sku}',
            tipo='FISICO',
            categoria='OTROS',
            costo=Decimal('10.00'),
            precio_divisa=Decimal('15.00'),
        )

    def _crear_combo(self, sku):
        return Articulo.objects.create(
            empresa=self.empresa,
            sku=sku,
            nombre=f'Combo {sku}',
            tipo='COMBO',
            categoria='OTROS',
            costo=Decimal('0.00'),
            precio_divisa=Decimal('30.00'),
        )

    def _crear_receta(self, combo, componente, cantidad):
        return RecetaCombo.objects.create(
            combo=combo, componente=componente,
            cantidad_requerida=Decimal(str(cantidad)),
        )

    def _stock(self, articulo, almacen, cantidad):
        """Crea la fila de inventario (idempotente: unique articulo+almacen)."""
        fila, _ = InventarioAlmacen.objects.get_or_create(
            empresa=self.empresa,
            articulo=articulo,
            almacen=almacen,
            defaults={
                'cantidad_disponible': Decimal(str(cantidad)),
                'stock_minimo': Decimal('0.00'),
            },
        )
        return fila

    def _stock_combo_en_contexto(self, sku, response):
        for item in response.context['combos']:
            if item['sku'] == sku:
                return item['stock']
        self.fail(f"El combo '{sku}' no aparece en el contexto del dashboard.")

    def _contar_queries_dashboard(self):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get('/dashboard/')
        self.assertEqual(response.status_code, 200)
        return len(ctx.captured_queries)

    def _crear_combo_con_componentes(self, indice, almacenes, componentes):
        """
        Crea un combo con 3 componentes (o los disponibles) y stock en cada
        almacén, de modo que todas las filas de inventario existan.
        """
        combo = self._crear_combo(f'COMBO-Q{indice}')
        for j, componente in enumerate(componentes):
            self._crear_receta(combo, componente, cantidad=(j % 2) + 1)
            for almacen in almacenes:
                # Stock holgado para que el combo sea armable en ambos almacenes.
                self._stock(componente, almacen, 100 + indice)
        return combo


class TestDashboardCombosQueryCount(DashboardCombosBaseTest):
    """DATA-02: el dashboard no debe disparar un N+1 por combo/almacén."""

    def test_dashboard_combos_query_count_es_constante(self):
        """
        Pasar de 2 a 6 combos no debe incrementar el número de queries.

        Antes del fix, cada combo extra añadía (almacenes × (1 + componentes))
        queries al dashboard.
        """
        almacenes = [
            self._crear_almacen('Almacén Q1'),
            self._crear_almacen('Almacén Q2'),
        ]
        componentes = [self._crear_fisico(f'CQ-{i}') for i in range(3)]

        for i in range(2):
            self._crear_combo_con_componentes(i, almacenes, componentes)

        queries_2 = self._contar_queries_dashboard()

        for i in range(2, 6):
            self._crear_combo_con_componentes(i, almacenes, componentes)

        queries_6 = self._contar_queries_dashboard()

        self.assertEqual(
            queries_6, queries_2,
            msg=(
                f"N+1 detectado: 2 combos={queries_2} queries, "
                f"6 combos={queries_6} queries."
            ),
        )

    def test_dashboard_combos_query_count_bajo_umbral(self):
        """6 combos × 2 almacenes × 3 componentes debe resolverse en < 25 queries."""
        almacenes = [
            self._crear_almacen('Almacén U1'),
            self._crear_almacen('Almacén U2'),
        ]
        componentes = [self._crear_fisico(f'CU-{i}') for i in range(3)]

        for i in range(6):
            self._crear_combo_con_componentes(i, almacenes, componentes)

        total = self._contar_queries_dashboard()

        self.assertLess(
            total, 25,
            msg=f"El dashboard disparó {total} queries (umbral: < 25).",
        )


class TestDashboardCombosSemantica(DashboardCombosBaseTest):
    """DATA-02: la optimización debe preservar la semántica exacta del cálculo."""

    def test_dashboard_stock_combo_correcto(self):
        """Receta A=2, B=3; stock A=10, B=9 → min(floor(10/2), floor(9/3)) = 3."""
        almacen = self._crear_almacen('Almacén Único')
        componente_a = self._crear_fisico('SEM-A')
        componente_b = self._crear_fisico('SEM-B')
        combo = self._crear_combo('COMBO-SEM')
        self._crear_receta(combo, componente_a, 2)
        self._crear_receta(combo, componente_b, 3)
        self._stock(componente_a, almacen, 10)
        self._stock(componente_b, almacen, 9)

        response = self.client.get('/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._stock_combo_en_contexto('COMBO-SEM', response), 3)

    def test_dashboard_combo_toma_el_maximo_entre_almacenes(self):
        """Almacén 1 da 2, almacén 2 da 5 → el contexto muestra 5."""
        almacen_1 = self._crear_almacen('Almacén Max 1')
        almacen_2 = self._crear_almacen('Almacén Max 2')
        componente_a = self._crear_fisico('MAX-A')
        componente_b = self._crear_fisico('MAX-B')
        combo = self._crear_combo('COMBO-MAX')
        self._crear_receta(combo, componente_a, 2)
        self._crear_receta(combo, componente_b, 3)

        # Almacén 1: min(floor(10/2), floor(6/3)) = 2
        self._stock(componente_a, almacen_1, 10)
        self._stock(componente_b, almacen_1, 6)
        # Almacén 2: min(floor(10/2), floor(15/3)) = 5
        self._stock(componente_a, almacen_2, 10)
        self._stock(componente_b, almacen_2, 15)

        response = self.client.get('/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._stock_combo_en_contexto('COMBO-MAX', response), 5)

    def test_dashboard_combo_sin_receta_es_cero(self):
        """Un combo sin receta definida debe mostrar stock 0."""
        self._crear_combo('COMBO-SIN-RECETA')

        response = self.client.get('/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            self._stock_combo_en_contexto('COMBO-SIN-RECETA', response), 0
        )

    def test_dashboard_combo_con_componente_sin_inventario_es_cero_en_ese_almacen(self):
        """
        Si al almacén 1 le falta un componente, aporta 0; el máximo debe
        reflejar solo el almacén 2 (que sí tiene todos los componentes).
        """
        almacen_1 = self._crear_almacen('Almacén Falta')
        almacen_2 = self._crear_almacen('Almacén Completo')
        componente_a = self._crear_fisico('FALTA-A')
        componente_b = self._crear_fisico('FALTA-B')
        combo = self._crear_combo('COMBO-FALTA')
        self._crear_receta(combo, componente_a, 2)
        self._crear_receta(combo, componente_b, 3)

        # Almacén 1: solo A (falta B) → 0
        self._stock(componente_a, almacen_1, 100)
        # Almacén 2: A=10, B=9 → 3
        self._stock(componente_a, almacen_2, 10)
        self._stock(componente_b, almacen_2, 9)

        response = self.client.get('/dashboard/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._stock_combo_en_contexto('COMBO-FALTA', response), 3)


class TestCalcularStockComboIndividual(DashboardCombosBaseTest):
    """Regresión: ``calcular_stock_combo`` individual sigue disponible e igual."""

    def test_calcular_stock_combo_individual_sigue_funcionando(self):
        almacen = self._crear_almacen('Almacén Legacy')
        componente_a = self._crear_fisico('LEG-A')
        componente_b = self._crear_fisico('LEG-B')
        combo = self._crear_combo('COMBO-LEG')
        self._crear_receta(combo, componente_a, 2)
        self._crear_receta(combo, componente_b, 3)
        self._stock(componente_a, almacen, 10)
        self._stock(componente_b, almacen, 9)

        self.assertEqual(svc.calcular_stock_combo(combo, almacen), 3)
