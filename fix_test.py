import re
with open("inventory/tests.py", "r", encoding="utf-8") as f:
    text = f.read()

bad_text = """        # Artículo normal
        self.mouse = crear_articulo_fisico(self.empresa, sku='M-REF', nombre='Mouse Reembolsable')
        from inventory.services import procesar_devolucion_venta
        from inventory.models import MovimientoKardex"""

good_text = """        # Artículo normal
        self.mouse = crear_articulo_fisico(self.empresa, sku='M-REF', nombre='Mouse Reembolsable')
        self.mouse.costo = Decimal('2.00')
        self.mouse.save()
        seed_inventario(self.mouse, self.almacen, cantidad=10)
        
        # Artículo con Serial
        self.phone = crear_articulo_fisico(self.empresa, sku='P-REF', nombre='Smartphone Reembolsable')
        self.phone.usa_serial = True
        self.phone.costo = Decimal('100.00')
        self.phone.save()
        seed_inventario(self.phone, self.almacen, cantidad=3)
        
        # Crear 2 seriales físicos
        self.serial1 = SerialArticulo.objects.create(empresa=self.empresa, articulo=self.phone, almacen=self.almacen, serial='IMEI-R1')
        self.serial2 = SerialArticulo.objects.create(empresa=self.empresa, articulo=self.phone, almacen=self.almacen, serial='IMEI-R2')

        # VENDER ambos artículos para poder devolverlos
        lista_items = [
            {'articulo_sku': 'M-REF', 'cantidad': 4, 'precio_unitario_usd': 5.0, 'seriales': []},
            {'articulo_sku': 'P-REF', 'cantidad': 2, 'precio_unitario_usd': 150.0, 'seriales': ['IMEI-R1', 'IMEI-R2']}
        ]
        self.nota_venta = procesar_venta(cliente_id=None, lista_items=lista_items, almacen_id=self.almacen.id, usuario='Admin')
        
    def test_devolucion_parcial_exitosa_costo_historico(self):
        \"\"\"Test de devolución parcial de 2 mouses a costo histórico, sin cuarentena.\"\"\"
        from inventory.services import procesar_devolucion_venta
        from inventory.models import MovimientoKardex"""

text = text.replace(bad_text, good_text)

with open("inventory/tests.py", "w", encoding="utf-8") as f:
    f.write(text)
