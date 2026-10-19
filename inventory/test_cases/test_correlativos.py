"""
Tests para EST-03 — Correlativos sin race condition.

Contexto arquitectónico (decisión aprobada):
    SQLite NO implementa ``SELECT ... FOR UPDATE``
    (``has_select_for_update=False``): Django ignora la cláusula sin error.
    Por tanto el lock NO protege en el backend real. La protección efectiva es:
        1. ``UniqueConstraint`` sobre el número del documento, y
        2. un bucle de reintento ante ``IntegrityError`` que recalcula el número.
    ``select_for_update()`` SÍ se usa (aporta en PostgreSQL, inocuo en SQLite),
    pero la corrección NO depende de él.

Estos tests RED deben fallar antes de implementar el modelo ``Correlativo``,
el módulo ``inventory.correlativos`` y los constraints nuevos.
"""

import importlib
from decimal import Decimal
from unittest.mock import patch

from django.apps import apps as global_apps
from django.db import IntegrityError, transaction
from django.test import TestCase

from inventory import correlativos as correlativos_service
from inventory.managers import reset_current_empresa, set_current_empresa
from inventory.models import (
    Almacen,
    ConfiguracionEmpresa,
    Contacto,
    Correlativo,
    DocumentoCompra,
    Empresa,
    NotaCredito,
    NotaEntrega,
)


class TestCorrelativosEST03(TestCase):
    """Suite EST-03: contador de correlativos atómico por (empresa, tipo)."""

    def setUp(self):
        sufijo = abs(hash(self._testMethodName)) % (10 ** 8)
        self.empresa = Empresa.objects.create(
            nombre=f'EST03 {self._testMethodName[:30]}',
            rif=f'J-EST03-{sufijo:08d}',
            activa=True,
        )
        self.config = ConfiguracionEmpresa.global_objects.get(empresa=self.empresa)
        self.almacen = Almacen.global_objects.filter(empresa=self.empresa).first()
        self.proveedor = Contacto.objects.create(
            empresa=self.empresa,
            identificacion=f'J-PROV-{sufijo:08d}',
            nombre='Proveedor EST03',
            tipo='PROVEEDOR',
        )

    # -- Helpers ---------------------------------------------------------
    def _activar_tenant(self, empresa):
        token = set_current_empresa(empresa.id)
        self.addCleanup(reset_current_empresa, token)

    def _sin_tenant(self):
        token = set_current_empresa(None)
        self.addCleanup(reset_current_empresa, token)

    # -- 1. Modelo Correlativo ------------------------------------------
    def test_est03_modelo_correlativo_tiene_unique_por_empresa_y_tipo(self):
        from django.db.models import UniqueConstraint

        unique_fields = [
            list(c.fields)
            for c in Correlativo._meta.constraints
            if isinstance(c, UniqueConstraint) and c.fields
        ]
        self.assertIn(['empresa', 'tipo_documento'], unique_fields)

        Correlativo.objects.create(
            empresa=self.empresa,
            tipo_documento=correlativos_service.TIPO_NOTA_ENTREGA,
            ultimo_numero=1,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Correlativo.objects.create(
                    empresa=self.empresa,
                    tipo_documento=correlativos_service.TIPO_NOTA_ENTREGA,
                    ultimo_numero=2,
                )

    # -- 2-5. siguiente_numero ------------------------------------------
    def test_est03_siguiente_numero_arranca_en_correlativo_inicial(self):
        self.config.correlativo_inicial_nota = 1
        self.config.save()
        self._activar_tenant(self.empresa)

        self.assertEqual(
            correlativos_service.siguiente_numero(
                self.empresa.id, correlativos_service.TIPO_NOTA_ENTREGA
            ),
            1,
        )
        nota = NotaEntrega.objects.create(empresa=self.empresa, almacen=self.almacen)
        self.assertEqual(nota.numero, 1)

    def test_est03_siguiente_numero_continua_desde_max_del_documento(self):
        self._activar_tenant(self.empresa)
        for n in range(1, 6):
            NotaEntrega.objects.create(
                empresa=self.empresa, numero=n, almacen=self.almacen
            )

        self.assertEqual(
            correlativos_service.siguiente_numero(
                self.empresa.id, correlativos_service.TIPO_NOTA_ENTREGA
            ),
            6,
        )
        nota = NotaEntrega.objects.create(empresa=self.empresa, almacen=self.almacen)
        self.assertEqual(nota.numero, 6)

    def test_est03_siguiente_numero_ignora_documentos_de_otra_empresa(self):
        self._activar_tenant(self.empresa)
        for n in range(1, 11):
            NotaEntrega.objects.create(
                empresa=self.empresa, numero=n, almacen=self.almacen
            )

        otra = Empresa.objects.create(
            nombre='EST03 Otra', rif='J-EST03-OTRA', activa=True
        )
        token = set_current_empresa(otra.id)
        self.addCleanup(reset_current_empresa, token)

        self.assertEqual(
            correlativos_service.siguiente_numero(
                otra.id, correlativos_service.TIPO_NOTA_ENTREGA
            ),
            1,
        )

    def test_est03_correlativo_no_usa_el_manager_tenant_filtrado(self):
        # Sin contexto de request: el manager por defecto de Correlativo NO
        # debe devolver .none() (trampa conocida del EmpresaManager).
        self._sin_tenant()
        Correlativo.objects.create(
            empresa=self.empresa,
            tipo_documento=correlativos_service.TIPO_NOTA_ENTREGA,
            ultimo_numero=4,
        )

        self.assertEqual(Correlativo.objects.count(), 1)
        self.assertEqual(
            correlativos_service.siguiente_numero(
                self.empresa.id, correlativos_service.TIPO_NOTA_ENTREGA
            ),
            5,
        )

    # -- 6-8. Wiring de los modelos -------------------------------------
    def test_est03_notaentrega_incrementa_correlativo_y_actualiza_tabla(self):
        self._activar_tenant(self.empresa)
        ne1 = NotaEntrega.objects.create(empresa=self.empresa, almacen=self.almacen)
        ne2 = NotaEntrega.objects.create(empresa=self.empresa, almacen=self.almacen)

        self.assertEqual([ne1.numero, ne2.numero], [1, 2])
        corr = Correlativo.objects.get(
            empresa=self.empresa,
            tipo_documento=correlativos_service.TIPO_NOTA_ENTREGA,
        )
        self.assertEqual(corr.ultimo_numero, 2)

    def test_est03_documentocompra_incrementa_correlativo(self):
        self._activar_tenant(self.empresa)
        doc1 = DocumentoCompra.objects.create(
            empresa=self.empresa,
            proveedor=self.proveedor,
            tipo_documento='FACTURA_COMPRA',
            monto_total_usd=Decimal('10.0000'),
        )
        doc2 = DocumentoCompra.objects.create(
            empresa=self.empresa,
            proveedor=self.proveedor,
            tipo_documento='FACTURA_COMPRA',
            monto_total_usd=Decimal('20.0000'),
        )

        self.assertEqual([doc1.numero, doc2.numero], [1, 2])
        self.assertEqual(doc1.numero_interno, 'FC-00000001')
        self.assertEqual(doc2.numero_interno, 'FC-00000002')
        corr = Correlativo.objects.get(
            empresa=self.empresa,
            tipo_documento=correlativos_service.TIPO_FACTURA_COMPRA,
        )
        self.assertEqual(corr.ultimo_numero, 2)

    def test_est03_notacredito_asigna_numero_y_numero_control_unicos(self):
        self._activar_tenant(self.empresa)
        nota = NotaEntrega.objects.create(empresa=self.empresa, almacen=self.almacen)

        nc1 = NotaCredito.objects.create(
            empresa=self.empresa, nota_entrega=nota, motivo='Devolución 1'
        )
        nc2 = NotaCredito.objects.create(
            empresa=self.empresa, nota_entrega=nota, motivo='Devolución 2'
        )

        self.assertNotEqual(nc1.numero, nc2.numero)
        self.assertNotEqual(nc1.numero_control, nc2.numero_control)
        self.assertEqual(nc1.numero_control, f'NC-{nc1.numero:08d}')
        self.assertEqual(nc2.numero_control, f'NC-{nc2.numero:08d}')

    # -- 9. Reintento ante IntegrityError -------------------------------
    def test_est03_reintenta_ante_integrity_error_sin_duplicar_numero(self):
        self._activar_tenant(self.empresa)
        existente = NotaEntrega.objects.create(
            empresa=self.empresa, almacen=self.almacen
        )
        self.assertEqual(existente.numero, 1)

        llamadas = {'n': 0}
        real = correlativos_service.siguiente_numero

        def flaky(empresa_id, tipo_documento):
            llamadas['n'] += 1
            if llamadas['n'] == 1:
                return 1  # colisiona con el documento existente
            return real(empresa_id, tipo_documento)

        with patch('inventory.correlativos.siguiente_numero', side_effect=flaky):
            nueva = NotaEntrega.objects.create(
                empresa=self.empresa, almacen=self.almacen
            )

        self.assertEqual(nueva.numero, 2)
        self.assertGreaterEqual(llamadas['n'], 2)
        self.assertEqual(
            NotaEntrega.global_objects.filter(empresa=self.empresa).count(), 2
        )
        self.assertEqual(
            NotaEntrega.global_objects.filter(
                empresa=self.empresa, numero=2
            ).count(),
            1,
        )

    # -- 10-11. Constraints de unicidad ---------------------------------
    def test_est03_constraint_numero_duplicado_en_documentocompra_levanta_integrity_error(
        self,
    ):
        self._activar_tenant(self.empresa)
        DocumentoCompra.objects.create(
            empresa=self.empresa,
            proveedor=self.proveedor,
            monto_total_usd=Decimal('1.0000'),
            numero=7,
            numero_interno='MAN-1',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DocumentoCompra.objects.create(
                    empresa=self.empresa,
                    proveedor=self.proveedor,
                    monto_total_usd=Decimal('2.0000'),
                    numero=7,
                    numero_interno='MAN-2',
                )

    def test_est03_constraint_numero_control_duplicado_en_notacredito_levanta_integrity_error(
        self,
    ):
        self._activar_tenant(self.empresa)
        nota = NotaEntrega.objects.create(empresa=self.empresa, almacen=self.almacen)
        NotaCredito.objects.create(
            empresa=self.empresa,
            nota_entrega=nota,
            motivo='a',
            numero=1,
            numero_control='NC-00000001',
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                NotaCredito.objects.create(
                    empresa=self.empresa,
                    nota_entrega=nota,
                    motivo='b',
                    numero=2,
                    numero_control='NC-00000001',
                )

    # -- 12. Migración de siembra ---------------------------------------
    def test_est03_existe_migracion_de_siembra_de_correlativos(self):
        self._activar_tenant(self.empresa)
        for n in range(1, 4):
            NotaEntrega.objects.create(
                empresa=self.empresa, numero=n, almacen=self.almacen
            )
        Correlativo.objects.all().delete()

        migracion = importlib.import_module(
            'inventory.migrations.0020_sembrar_correlativos'
        )
        migracion.sembrar_correlativos(global_apps, None)

        filas = Correlativo.objects.filter(empresa=self.empresa)
        self.assertEqual(filas.count(), 3)
        ne_row = filas.get(tipo_documento=correlativos_service.TIPO_NOTA_ENTREGA)
        self.assertEqual(ne_row.ultimo_numero, 3)

        # Idempotencia: una segunda ejecución no duplica ni retrocede.
        migracion.sembrar_correlativos(global_apps, None)
        self.assertEqual(Correlativo.objects.filter(empresa=self.empresa).count(), 3)
        self.assertEqual(
            Correlativo.objects.get(
                empresa=self.empresa,
                tipo_documento=correlativos_service.TIPO_NOTA_ENTREGA,
            ).ultimo_numero,
            3,
        )
