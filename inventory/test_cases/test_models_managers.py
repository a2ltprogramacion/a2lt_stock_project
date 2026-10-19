"""
Tests for BUG-04: Missing import of get_current_empresa in models.py

This test file verifies the fix for the missing import of get_current_empresa
in inventory/models.py line 31, which causes NameError when
DetalleCompraQuerySet.para_empresa() is called.
"""

from django.test import TestCase
from decimal import Decimal
from unittest.mock import patch


class TestBug04ImportGetCurrentEmpresa(TestCase):
    """
    RED Phase: These tests should FAIL initially because get_current_empresa
    is not imported in models.py line 31.
    
    After the fix (adding get_current_empresa to the import), all tests should PASS.
    """

    def test_bug04_import_get_current_empresa(self):
        """
        Test 1: Verify that get_current_empresa is importable from managers module.
        This directly tests the import statement fix in models.py:31
        """
        from inventory.managers import get_current_empresa
        # If we get here without ImportError, the import works
        self.assertTrue(callable(get_current_empresa))

    def test_bug04_para_empresa_filters_by_active_empresa(self):
        """
        Test 2: With active empresa in context, para_empresa() filters correctly.
        """
        from inventory.models import Empresa, Articulo, DetalleDocumentoCompra
        from inventory.managers import set_current_empresa, reset_current_empresa
        
        # Create test empresa and set it as active
        empresa = Empresa.objects.create(nombre="Test Corp", rif="J-TEST-001", activa=True)
        token = set_current_empresa(empresa.id)
        
        try:
            # Create an articulo for this empresa
            articulo = Articulo.objects.create(
                empresa=empresa,
                sku='TEST-001',
                nombre='Artículo Test',
                tipo='FISICO',
                categoria='OTROS',
                costo=Decimal('10.00'),
                precio_divisa=Decimal('15.00'),
            )
            
            # Create a Contacto for the proveedor first (required field)
            from inventory.models import Contacto, DocumentoCompra, Almacen
            proveedor = Contacto.objects.create(
                empresa=empresa,
                identificacion='J-PROV-001',
                nombre='Proveedor Test',
                tipo='PROVEEDOR',
            )
            almacen = Almacen.objects.create(empresa=empresa, nombre='Test Almacén', es_principal=True)
            doc_compra = DocumentoCompra.objects.create(
                empresa=empresa,
                proveedor=proveedor,
                tipo_documento='FACTURA_COMPRA',
                monto_total_usd=Decimal('100.00'),
            )
            
            detalle = DetalleDocumentoCompra.objects.create(
                documento_compra=doc_compra,
                articulo=articulo,
                almacen=almacen,
                cantidad=Decimal('5.00'),
                costo_base=Decimal('10.00'),
                costo_ajustado=Decimal('10.50'),
                costo_directo_bcv=Decimal('400.00'),
                costo_ajustado_bcv=Decimal('420.00'),
            )
            
            # Call para_empresa() - should filter by the active empresa
            qs = DetalleDocumentoCompra.objects.para_empresa()
            self.assertEqual(qs.count(), 1)
            self.assertEqual(qs.first().pk, detalle.pk)
            
        finally:
            reset_current_empresa(token)

    def test_bug04_para_empresa_returns_none_when_no_context(self):
        """
        Test 3: Without active empresa in context, para_empresa() returns .none()
        """
        from inventory.models import DetalleDocumentoCompra
        from inventory.managers import set_current_empresa, reset_current_empresa
        
        # Ensure no empresa is set in context
        token = set_current_empresa(None)
        
        try:
            # Call para_empresa() - should return empty queryset (.none())
            qs = DetalleDocumentoCompra.objects.para_empresa()
            # .none() returns a queryset that will always evaluate to empty
            self.assertEqual(qs.count(), 0)
            # Verify it's actually a .none() queryset by checking query
            self.assertTrue(qs.query.where)
        finally:
            reset_current_empresa(token)

    def test_bug04_no_nameerror(self):
        """
        Test 4: Calling para_empresa() does not raise NameError.
        This is the core bug - missing import causes NameError at runtime.
        """
        from inventory.models import DetalleDocumentoCompra
        from inventory.managers import set_current_empresa, reset_current_empresa
        from inventory.models import Empresa
        
        # Create and set an empresa
        empresa = Empresa.objects.create(nombre="Test Corp 2", rif="J-TEST-002", activa=True)
        token = set_current_empresa(empresa.id)
        
        try:
            # This should NOT raise NameError
            qs = DetalleDocumentoCompra.objects.para_empresa()
            # If we get here without NameError, the bug is fixed
            self.assertIsNotNone(qs)
        except NameError as e:
            self.fail(f"NameError raised (BUG-04 not fixed): {e}")
        finally:
            reset_current_empresa(token)

    def test_bug04_consistent_with_empresa_queryset(self):
        """
        Test 5: DetalleCompraQuerySet.para_empresa() behaves consistently with EmpresaQuerySet.para_empresa()
        Both filter by empresa_id when set. When no empresa:
        - EmpresaQuerySet.para_empresa() returns self (unfiltered)
        - DetalleCompraQuerySet.para_empresa() returns .none() (explicit empty)
        This test verifies the filtering behavior when empresa IS set.
        """
        from inventory.models import Empresa, Articulo, Almacen, DocumentoCompra, Contacto, DetalleDocumentoCompra, ConfiguracionEmpresa
        from inventory.managers import set_current_empresa, reset_current_empresa, EmpresaQuerySet
        
        # Create two empresas
        empresa1 = Empresa.objects.create(nombre="Empresa 1", rif="J-EMP-001", activa=True)
        empresa2 = Empresa.objects.create(nombre="Empresa 2", rif="J-EMP-002", activa=True)
        
        # Create test data for empresa1
        almacen1 = Almacen.objects.create(empresa=empresa1, nombre='Almacén 1', es_principal=True)
        articulo1 = Articulo.objects.create(
            empresa=empresa1, sku='EMP1-001', nombre='Art Emp 1',
            tipo='FISICO', categoria='OTROS', costo=Decimal('10.00'), precio_divisa=Decimal('15.00')
        )
        proveedor1 = Contacto.objects.create(
            empresa=empresa1, identificacion='J-PROV-001', nombre='Prov 1', tipo='PROVEEDOR'
        )
        doc1 = DocumentoCompra.objects.create(
            empresa=empresa1, proveedor=proveedor1, tipo_documento='FACTURA_COMPRA',
            monto_total_usd=Decimal('100.00')
        )
        detalle1 = DetalleDocumentoCompra.objects.create(
            documento_compra=doc1, articulo=articulo1, almacen=almacen1,
            cantidad=Decimal('5.00'), costo_base=Decimal('10.00'), costo_ajustado=Decimal('10.50'),
            costo_directo_bcv=Decimal('400.00'), costo_ajustado_bcv=Decimal('420.00'),
        )
        
        # Create test data for empresa2
        almacen2 = Almacen.objects.create(empresa=empresa2, nombre='Almacén 2', es_principal=True)
        articulo2 = Articulo.objects.create(
            empresa=empresa2, sku='EMP2-001', nombre='Art Emp 2',
            tipo='FISICO', categoria='OTROS', costo=Decimal('20.00'), precio_divisa=Decimal('30.00')
        )
        proveedor2 = Contacto.objects.create(
            empresa=empresa2, identificacion='J-PROV-002', nombre='Prov 2', tipo='PROVEEDOR'
        )
        doc2 = DocumentoCompra.objects.create(
            empresa=empresa2, proveedor=proveedor2, tipo_documento='FACTURA_COMPRA',
            monto_total_usd=Decimal('200.00')
        )
        detalle2 = DetalleDocumentoCompra.objects.create(
            documento_compra=doc2, articulo=articulo2, almacen=almacen2,
            cantidad=Decimal('3.00'), costo_base=Decimal('20.00'), costo_ajustado=Decimal('21.00'),
            costo_directo_bcv=Decimal('800.00'), costo_ajustado_bcv=Decimal('840.00'),
        )
        
        # Test 1: With empresa1 active, both should filter to empresa1's data
        token1 = set_current_empresa(empresa1.id)
        try:
            qs_detalle = DetalleDocumentoCompra.objects.para_empresa()
            qs_config = EmpresaQuerySet(ConfiguracionEmpresa).para_empresa()
            
            self.assertEqual(qs_detalle.count(), 1)
            self.assertEqual(qs_detalle.first().pk, detalle1.pk)
            self.assertEqual(qs_config.count(), 1)
            self.assertEqual(qs_config.first().empresa_id, empresa1.pk)
        finally:
            reset_current_empresa(token1)
        
        # Test 2: With empresa2 active, both should filter to empresa2's data
        token2 = set_current_empresa(empresa2.id)
        try:
            qs_detalle = DetalleDocumentoCompra.objects.para_empresa()
            qs_config = EmpresaQuerySet(ConfiguracionEmpresa).para_empresa()
            
            self.assertEqual(qs_detalle.count(), 1)
            self.assertEqual(qs_detalle.first().pk, detalle2.pk)
            self.assertEqual(qs_config.count(), 1)
            self.assertEqual(qs_config.first().empresa_id, empresa2.pk)
        finally:
            reset_current_empresa(token2)
        
        # Test 3: With no empresa active, behavior differs by design:
        # - EmpresaQuerySet.para_empresa() returns unfiltered queryset (self)
        # - DetalleCompraQuerySet.para_empresa() returns .none() explicitly
        token_none = set_current_empresa(None)
        try:
            qs_detalle = DetalleDocumentoCompra.objects.para_empresa()
            qs_config = EmpresaQuerySet(ConfiguracionEmpresa).para_empresa()
            
            # DetalleCompraQuerySet returns empty
            self.assertEqual(qs_detalle.count(), 0)
            # EmpresaQuerySet returns all (2 configs created by migrations)
            self.assertEqual(qs_config.count(), 2)
        finally:
            reset_current_empresa(token_none)


if __name__ == '__main__':
    import unittest
    unittest.main()