import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a2lt_stock_project.settings')
import django
django.setup()

from inventory.models import (
    Empresa, ConfiguracionEmpresa, Almacen, Articulo, Contacto,
    Moneda, TasaCambio, SerialArticulo, NotaEntrega, DetalleNotaEntrega,
    DocumentoCompra, DetalleDocumentoCompra, MovimientoKardex,
)

eid = 34
e = Empresa.objects.get(id=34)
print(f'Empresa: {e.nombre} (ID: {e.id})')
print(f'Configuracion: {ConfiguracionEmpresa.global_objects.filter(empresa_id=34).exists()}')
print(f'Almacen: {Almacen.global_objects.filter(empresa_id=34).count()}')
print(f'Clientes: {Contacto.global_objects.filter(empresa_id=34, tipo="CLIENTE").count()}')
print(f'Proveedores: {Contacto.global_objects.filter(empresa_id=34, tipo="PROVEEDOR").count()}')
print(f'Articulos: {Articulo.global_objects.filter(empresa_id=34).count()} (con serial: {Articulo.global_objects.filter(empresa_id=34, usa_serial=True).count()})')
print(f'Seriales: {SerialArticulo.global_objects.filter(empresa_id=34).count()}')
print(f'Compras: {DocumentoCompra.global_objects.filter(empresa_id=34).count()}')
print(f'Ventas: {NotaEntrega.global_objects.filter(empresa_id=34).count()}')
print(f'Movimientos Kardex: {MovimientoKardex.global_objects.filter(empresa_id=34).count()}')

from inventory.models import Articulo, SerialArticulo
for art in Articulo.global_objects.filter(empresa_id=34, usa_serial=True):
    count = SerialArticulo.global_objects.filter(empresa_id=34, articulo_id=art.sku).count()
    print(f'  {art.sku}: {art.nombre} - seriales: {count}')

print('Done!')