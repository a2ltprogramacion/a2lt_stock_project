#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script para generar datos de prueba/demo para A2LT Stock.
Crea una empresa demo con:
- 30+ articulos (5 con seriales, 15-50 seriales cada uno)
- 15 clientes
- 5 proveedores
- 10 documentos de compra
- 23 notas de entrega (ventas)
- Seriales para los articulos con serial
- Movimientos de Kardex correspondientes
"""

import os
import sys
import random
from decimal import Decimal
from datetime import datetime, timedelta, date

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a2lt_stock_project.settings')
import django
django.setup()

from django.db import transaction
from inventory.models import (
    Empresa, ConfiguracionEmpresa, Almacen, Articulo, Contacto,
    Moneda, TasaCambio, SerialArticulo, NotaEntrega, DetalleNotaEntrega,
    DocumentoCompra, DetalleDocumentoCompra, MovimientoKardex,
)
from inventory.services import procesar_venta, registrar_compra_proveedor, registrar_movimiento
from inventory.managers import set_current_empresa


def run():
    """Funcion principal para generar todos los datos demo."""
    print("=" * 50)
    print("GENERANDO DATOS DEMO PARA A2LT STOCK")
    print("=" * 50)
    
    try:
        with transaction.atomic():
            # 1. Obtener/crear empresa demo
            empresa_demo, created = Empresa.objects.get_or_create(
                rif='J-DEMO-001',
                defaults={
                    'nombre': 'Empresa Demo A2LT',
                    'direccion': 'Av. Principal, Centro Comercial A2LT, Piso 1',
                    'telefono': '0212-555-0000',
                    'correo': 'demo@a2ltstock.com',
                    'activa': True,
                }
            )
            print(f"Empresa: {empresa_demo.nombre} (ID: {empresa_demo.id}) {'[NUEVA]' if created else '[EXISTENTE]'}")
            
            empresa_id = empresa_demo.id
            
            # Configurar contexto de tenant
            from inventory.managers import set_current_empresa
            set_current_empresa(empresa_id)
            
            # 2. Configuracion
            config, _ = ConfiguracionEmpresa.global_objects.get_or_create(
                empresa_id=empresa_id,
                defaults={
                    'tasa_bcv': Decimal('40.0000'),
                    'tasa_mercado': Decimal('42.0000'),
                    'factor_cobertura': Decimal('1.0500'),
                    'margen_global': Decimal('30.00'),
                    'descuento_global': Decimal('5.00'),
                    'prefijo_nota_entrega': 'NE',
                    'correlativo_inicial_nota': 1,
                    'prefijo_factura_compra': 'FC',
                    'correlativo_inicial_factura_compra': 1,
                    'prefijo_nota_credito': 'NC',
                    'correlativo_inicial_nota_credito': 1,
                    'ivas_disponibles': [0, 8, 16],
                    'usa_almacen_cuarentena': False,
                }
            )
            print("Configuracion: OK")
            
            # 3. Monedas y tasas
            usd, _ = Moneda.global_objects.get_or_create(
                empresa_id=empresa_id, codigo='USD',
                defaults={'nombre': 'Dolar Americano', 'simbolo': '$', 'decimales': 2, 'es_base': True, 'activa': True}
            )
            ves, _ = Moneda.global_objects.get_or_create(
                empresa_id=empresa_id, codigo='VES',
                defaults={'nombre': 'Bolivar Venezolano', 'simbolo': 'Bs', 'decimales': 2, 'es_base': False, 'activa': True}
            )
            
            TasaCambio.global_objects.get_or_create(
                empresa_id=empresa_id,
                moneda_origen=usd,
                moneda_destino=ves,
                defaults={
                    'tasa': Decimal('42.0000'),
                    'fecha': date.today(),
                    'fuente': 'MANUAL',
                    'notas': 'Tasa inicial demo'
                }
            )
            print("Monedas y tasas: OK")
            
            # 4. Almacen
            almacen, _ = Almacen.global_objects.get_or_create(
                empresa_id=empresa_id,
                nombre='Almacen Principal',
                defaults={'es_principal': True, 'activo': True}
            )
            almacen_id = almacen.id
            print("Almacen: OK")
            
            # 5. Contactos - 15 Clientes y 5 Proveedores
            clientes = []
            for i in range(1, 16):
                cliente, _ = Contacto.global_objects.get_or_create(
                    identificacion=f'V-{10000000+i:08d}',
                    defaults={
                        'empresa_id': empresa_id,
                        'nombre': f'Cliente Demo {i}',
                        'tipo': 'CLIENTE',
                        'telefono': f'0212-500{i:04d}',
                        'direccion': f'Calle {i}, Urbanizacion Demo, Caracas',
                        'correo': f'cliente{i}@demo.com',
                    }
                )
                clientes.append(cliente)
            print(f"Clientes: {len(clientes)}")
            
            proveedores = []
            for i in range(1, 6):
                prov, _ = Contacto.global_objects.get_or_create(
                    identificacion=f'J-{20000000+i:08d}',
                    defaults={
                        'empresa_id': empresa_id,
                        'nombre': f'Proveedor Demo {i}',
                        'tipo': 'PROVEEDOR',
                        'telefono': f'0212-600{i:04d}',
                        'direccion': f'Avenida Industrial {i}, Zona Industrial, Valencia',
                        'correo': f'proveedor{i}@demo.com',
                    }
                )
                proveedores.append(prov)
            print(f"Proveedores: {len(proveedores)}")
            
            # 6. ARTICULOS - 30 articulos (5 con serial, 25 sin serial)
            articulos_data = [
                # 5 CON SERIAL
                {'sku': 'NOTE-001', 'nombre': 'Laptop HP 15" Core i5', 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('450.00'), 'precio': Decimal('650.00'), 'iva': Decimal('16.00'),
                 'descripcion': 'Laptop HP 15.6" con procesador Intel Core i5 de 12va generacion, 8GB RAM DDR4, 512GB SSD NVMe, pantalla Full HD IPS antirreflejo, teclado numerico, Windows 11 Pro. Ideal para oficina y estudio.',
                 'ficha_tecnica': 'Procesador: Intel Core i5-1235U (12va gen, 10 nucleos, hasta 4.4 GHz)\nMemoria: 8GB DDR4-3200 (expandible a 16GB)\nAlmacenamiento: 512GB SSD PCIe NVMe M.2\nPantalla: 15.6" Full HD (1920x1080) IPS 250 nits\nGraficos: Intel Iris Xe Graphics\nConectividad: WiFi 6, Bluetooth 5.2, USB-C 3.2, USB-A 3.2, HDMI 1.4b, RJ45\nBateria: 3 celdas 41Wh, carga rapida 45W\nPeso: 1.69 kg\nOS: Windows 11 Pro 64-bit',
                 'social_quick': '🚀 Laptop HP 15" Core i5 - Tu compañera perfecta para trabajo y estudio. Rendimiento solido, bateria duradera, diseno elegante. ¡Disponible ya! #HP #Laptop #Corei5 #Trabajo #Estudio #Oferta',
                 'social_cross': '💡 Combina tu Laptop HP con: 🎧 Auriculares Bluetooth 5.0 ($58) | 🖱️ Mouse Inalambrico ($38) | 🎒 Mochila Laptop 15.6" ($45). ¡Arma tu kit completo!',
                 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('450.00'), 'precio': Decimal('650.00'), 'iva': Decimal('16.00')},
                {'sku': 'NOTE-002', 'nombre': 'Laptop Dell 14" Core i7', 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('600.00'), 'precio': Decimal('850.00'), 'iva': Decimal('16.00'),
                 'descripcion': 'Laptop Dell Latitude 14" con Intel Core i7-1265U, 16GB RAM DDR5, 1TB SSD NVMe, pantalla Full HD+, teclado retroiluminado, lector huella, Windows 11 Pro. Ejecutiva y portatil.',
                 'ficha_tecnica': 'Procesador: Intel Core i7-1265U (12va gen, 10 nucleos, hasta 4.8 GHz)\nMemoria: 16GB DDR5-4800 (soldada)\nAlmacenamiento: 1TB SSD PCIe NVMe M.2\nPantalla: 14" Full HD+ (1920x1200) IPS 300 nits, antirreflejo\nGraficos: Intel Iris Xe Graphics\nConectividad: WiFi 6E, Bluetooth 5.2, 2x Thunderbolt 4, USB-A 3.2, HDMI 2.0, RJ45\nBateria: 4 celdas 54Wh, ExpressCharge 60 min\nPeso: 1.26 kg\nOS: Windows 11 Pro 64-bit',
                 'social_quick': '💼 Dell Latitude 14" Core i7 - Potencia ejecutiva en formato ultraportatil. Rendimiento premium, seguridad empresarial, movilidad total. #Dell #Latitude #Corei7 #Business #Portatil',
                 'social_cross': '💼 Completa tu setup ejecutivo: 🎒 Mochila Dell Premier 14" ($65) | 🎧 Auriculares USB-C ($78) | 🔌 Hub USB-C 7-en-1 ($48). Productividad sin limites!',
                 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('600.00'), 'precio': Decimal('850.00'), 'iva': Decimal('16.00')},
                {'sku': 'PHON-001', 'nombre': 'Smartphone Samsung Galaxy S23', 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('500.00'), 'precio': Decimal('750.00'), 'iva': Decimal('16.00'),
                 'descripcion': 'Samsung Galaxy S23 5G 128GB Phantom Black. Snapdragon 8 Gen 2, 8GB RAM, pantalla Dynamic AMOLED 2X 6.1" 120Hz, triple camara 50MP+12MP+10MP, bateria 3900mAh, IP68, One UI 5.1.',
                 'ficha_tecnica': 'Procesador: Snapdragon 8 Gen 2 for Galaxy (4nm, 3.36 GHz)\nMemoria: 8GB RAM LPDDR5X\nAlmacenamiento: 128GB UFS 4.0\nPantalla: 6.1" Dynamic AMOLED 2X FHD+ (2340x1080) 120Hz, 1750 nits\nCamara: Triple 50MP (f/1.8) + 12MP UW (f/2.2) + 10MP 3x Tele (f/2.4)\nVideo: 8K@30fps, 4K@60fps\nBateria: 3900 mAh, carga 25W cable, 15W wireless, 4.5W reverse\nConectividad: 5G, WiFi 6E, Bluetooth 5.3, NFC, UWB\nDimensiones: 146.3 x 70.9 x 7.6 mm, 168g\nIP68, Gorilla Glass Victus 2',
                 'social_quick': '📱 Galaxy S23 - Potencia flagship en tu bolsillo. Camara pro, rendimiento bestia, diseno premium. ¡Consiguelo ya! #Samsung #GalaxyS23 #Smartphone #5G #Fotografia',
                 'social_cross': '📱 Protege tu Galaxy: 🛡️ Case Spigen Ultra Hybrid ($18) | 🛡️ Vidrio templado ESR ($12) | 🔌 Cargador 25W Samsung ($22) | 🎧 Galaxy Buds2 Pro ($159). Proteccion total!',
                 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('500.00'), 'precio': Decimal('750.00'), 'iva': Decimal('16.00')},
                {'sku': 'PHON-002', 'nombre': 'Smartphone iPhone 15 128GB', 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('700.00'), 'precio': Decimal('1050.00'), 'iva': Decimal('16.00'),
                 'descripcion': 'iPhone 15 128GB Negro. Chip A16 Bionic, pantalla Super Retina XDR 6.1", Dynamic Island, camara dual 48MP+12MP, USB-C, Face ID, iOS 17. Diseño aluminio + vidrio color-infundido.',
                 'ficha_tecnica': 'Chip: A16 Bionic (4nm, 6-core CPU, 5-core GPU, 16-core Neural Engine)\nMemoria: 6GB RAM\nAlmacenamiento: 128GB\nPantalla: 6.1" Super Retina XDR OLED (2556x1179) 2000 nits, Dynamic Island\nCamara: Principal 48MP f/1.6 + Ultra gran angular 12MP f/2.4\nVideo: 4K@60fps, Cinematic 4K@30fps, Action mode\nBateria: ~20h video, carga 20W (50% en 30min), MagSafe 15W, Qi 7.5W\nConectividad: 5G, WiFi 6, Bluetooth 5.3, NFC, Ultra Wideband\nDimensiones: 147.6 x 71.6 x 7.8 mm, 171g\nIP68, Ceramic Shield, iOS 17',
                 'social_quick': '🍎 iPhone 15 - La evolucion inteligente. Dynamic Island, USB-C, camara 48MP, chip A16. Innovacion que se siente. #Apple #iPhone15 #Innovacion #Tecnologia',
                 'social_cross': '🍎 Completa tu ecosistema: 🎧 AirPods Pro 2 ($249) | ⌚ Apple Watch SE ($249) | 🛡️ Case MagSafe ($49) | 🔌 Cargador 20W ($19). Experiencia Apple completa!',
                 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('700.00'), 'precio': Decimal('1050.00'), 'iva': Decimal('16.00')},
                {'sku': 'TABL-001', 'nombre': 'Tablet iPad Air 10.9"', 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('350.00'), 'precio': Decimal('520.00'), 'iva': Decimal('16.00'),
                 'descripcion': 'iPad Air 10.9" 64GB Gris Espacial. Chip M1, pantalla Liquid Retina 10.9" True Tone, Touch ID, USB-C, camara 12MP ultra gran angular, Center Stage, WiFi 6, hasta 10h bateria. Compatible Apple Pencil 2 y Magic Keyboard.',
                 'ficha_tecnica': 'Chip: Apple M1 (8-core CPU, 8-core GPU, 16-core Neural Engine)\nMemoria: 8GB RAM unificada\nAlmacenamiento: 64GB\nPantalla: 10.9" Liquid Retina (2360x1640) True Tone, P3, 500 nits, antirreflejo\nCamara: 12MP f/1.8 gran angular + 12MP f/2.4 ultra gran angular (Center Stage)\nVideo: 4K@60fps, 1080p@60fps\nBateria: 28.6 Wh, hasta 10h web/video, carga 20W USB-C\nConectividad: WiFi 6, Bluetooth 5.0, USB-C 3.1 Gen 2\nDimensiones: 247.6 x 178.5 x 6.1 mm, 461g\nTouch ID en boton superior, USB-C 3.1 Gen 2, soporte Apple Pencil 2',
                 'social_quick': '📱 iPad Air M1 - Potencia de escritorio, portabilidad de tablet. Ideal para creativos, estudiantes, profesionales. #iPadAir #M1 #Apple #Creatividad #Productividad',
                 'social_cross': '🎨 Desata tu creatividad: ✏️ Apple Pencil 2 ($129) | ⌨️ Magic Keyboard ($299) | 🛡️ Smart Folio ($79). Tu estudio portatil completo!',
                 'tipo': 'FISICO', 'usa_serial': True, 'costo': Decimal('350.00'), 'precio': Decimal('520.00'), 'iva': Decimal('16.00')},
            
            print("\n=== CREANDO ARTICULOS ===")
            for data in articulos_data:
                art, _ = Articulo.global_objects.get_or_create(
                    sku=data['sku'],
                    defaults={
                        'empresa_id': empresa_id,
                        'nombre': data['nombre'],
                        'tipo': data['tipo'],
                        'usa_serial': data['usa_serial'],
                        'costo': data['costo'],
                        'precio_divisa': data['precio'],
                        'iva_porcentaje': data['iva'],
                        'activo': True,
                    }
                )
                # Registrar movimiento de entrada inicial (stock 100)
                registrar_movimiento(
                    articulo=art,
                    almacen=Almacen.global_objects.filter(empresa_id=empresa_id, es_principal=True).first(),
                    tipo='ENTRADA',
                    cantidad=Decimal('100'),
                    concepto='CARGA_MASIVA_SUMA',
                    detalle_adicional='Stock inicial demo',
                    nota_entrega=None,
                    usuario='Demo Setup'
                )
            
            total_articulos = Articulo.global_objects.filter(empresa_id=empresa_id).count()
            con_serial = Articulo.global_objects.filter(empresa_id=empresa_id, usa_serial=True).count()
            print(f"Articulos: {total_articulos} total, {con_serial} con serial")
            
            # 6. Seriales para los 5 articulos con serial (15-50 c/u)
            print("\n=== GENERANDO SERIALES ===")
            from inventory.models import SerialArticulo
            
            almacen = Almacen.global_objects.filter(empresa_id=empresa_id, es_principal=True).first()
            articulos_con_serial = list(Articulo.global_objects.filter(empresa_id=empresa_id, usa_serial=True))
            
            for art in articulos_con_serial:
                num_seriales = random.randint(15, 50)
                for i in range(num_seriales):
                    serial = f'{art.sku[:4]}-{random.randint(100000, 999999):06d}-{i+1:03d}'
                    SerialArticulo.global_objects.get_or_create(
                        serial=serial,
                        defaults={
                            'empresa_id': empresa_id,
                            'articulo_id': art.sku,
                            'almacen_id': almacen.id,
                            'estado': 'DISPONIBLE',
                        }
                    )
                print(f"  {art.sku}: {num_seriales} seriales")
            
            total_seriales = SerialArticulo.global_objects.filter(empresa_id=empresa_id).count()
            print(f"Total seriales: {total_seriales}")
            
            # 7. Documentos de Compra (10)
            print("\n=== GENERANDO COMPRAS ===")
            proveedores = list(Contacto.global_objects.filter(empresa_id=empresa_id, tipo='PROVEEDOR'))
            articulos_todos = list(Articulo.global_objects.filter(empresa_id=empresa_id))
            
            tipos_compra = ['FACTURA_COMPRA', 'NOTA_ENTREGA_PROVEEDOR', 'REGISTRO_MENOR']
            
            for i in range(10):
                proveedor = random.choice(proveedores)
                tipo = random.choice(tipos_compra)
                
                items = random.sample(articulos_todos, random.randint(3, 6))
                lista_items = []
                for art in items:
                    cantidad = random.randint(5, 20)
                    costo_base = art.costo * Decimal(str(random.uniform(0.85, 1.15))).quantize(Decimal('0.01'))
                    iva_pct = art.iva_porcentaje
                    item_data = {
                        'articulo_sku': art.sku,
                        'cantidad': Decimal(str(random.randint(5, 20))),
                        'costo_base': art.costo * Decimal(str(random.uniform(0.85, 1.15))).quantize(Decimal('0.01')),
                        'iva_porcentaje': art.iva_porcentaje
                    }
                    # Para articulos con serial, agregar seriales
                    art_obj = Articulo.global_objects.get(sku=art.sku, empresa_id=empresa_id)
                    if art_obj.usa_serial:
                        seriales_disp = list(SerialArticulo.global_objects.filter(
                            empresa_id=empresa_id,
                            articulo_id=art.sku,
                            estado='DISPONIBLE'
                        )[:cantidad])
                        if len(seriales_disp) < cantidad:
                            # Ajustar cantidad
                            pass
                        if seriales_disp:
                            item_data['seriales'] = [s.serial for s in seriales_disp[:int(cantidad)]]
                    lista_items.append(item_data)
                
                if tipo == 'FACTURA_COMPRA':
                    num_factura = f'FC-{date.today().year}-{i+1:05d}'
                else:
                    num_factura = ''
                
                try:
                    registrar_compra_proveedor(
                        empresa_id=empresa_id,
                        proveedor_id=proveedor.identificacion,
                        lista_items=lista_items,
                        almacen_id=almacen_id,
                        tipo_documento=tipo,
                        numero_factura=num_factura,
                        fecha_compra=date.today() - timedelta(days=random.randint(1, 30))
                    )
                    print(f"  Compra {i+1}: {tipo} - {len(items)} items")
                except Exception as e:
                    print(f"  ERROR compra {i+1}: {e}")
            
            # 8. Ventas / Notas de Entrega (23)
            print("\n=== GENERANDO VENTAS ===")
            clientes = list(Contacto.global_objects.filter(empresa_id=empresa_id, tipo='CLIENTE'))
            articulos_todos = list(Articulo.global_objects.filter(empresa_id=empresa_id))
            tipos_venta = ['NOTA_ENTREGA', 'FACTURA']
            
            for i in range(23):
                cliente = random.choice(clientes)
                tipo = random.choice(tipos_venta)
                
                items_venta = random.sample(articulos_todos, random.randint(2, 8))
                lista_items = []
                for art in items_venta:
                    cantidad = random.randint(1, 10)
                    item_data = {
                        'articulo_sku': art.sku,
                        'cantidad': Decimal(str(random.randint(1, 10))),
                        'precio_base': art.precio_divisa
                    }
                    # Para articulos con serial, asignar seriales
                    art_obj = Articulo.global_objects.get(sku=art.sku, empresa_id=empresa_id)
                    if art_obj.usa_serial:
                        seriales_disp = list(SerialArticulo.global_objects.filter(
                            empresa_id=empresa_id,
                            articulo_id=art.sku,
                            estado='DISPONIBLE'
                        )[:cantidad])
                        if seriales_disp:
                            item_data['seriales'] = [s.serial for s in seriales_disp[:int(cantidad)]]
                    lista_items.append(item_data)
                
                num_factura = f'FAC-V-{date.today().year}-{i+1:05d}' if tipo == 'FACTURA' else ''
                
                try:
                    procesar_venta(
                        empresa_id=empresa_id,
                        cliente_id=cliente.identificacion,
                        lista_items=lista_items,
                        almacen_id=almacen_id,
                        tipo_documento=tipo,
                        numero_factura=num_factura,
                        descuento_global=Decimal(str(random.uniform(0, 5))).quantize(Decimal('0.01')) if random.random() > 0.7 else Decimal('0.00'),
                        usuario='Demo User'
                    )
                    print(f"  Venta {i+1}: {tipo} - {len(items_venta)} items")
                except Exception as e:
                    print(f"  ERROR venta {i+1}: {e}")
            
            # Resumen final
            print("\n=== RESUMEN FINAL ===")
            print(f"Empresa: {Empresa.objects.get(id=empresa_id).nombre}")
            print(f"Configuracion: {'Si' if ConfiguracionEmpresa.global_objects.filter(empresa_id=empresa_id).exists() else 'No'}")
            print(f"Almacen: {Almacen.global_objects.filter(empresa_id=empresa_id).count()}")
            print(f"Clientes: {Contacto.global_objects.filter(empresa_id=empresa_id, tipo='CLIENTE').count()}")
            print(f"Proveedores: {Contacto.global_objects.filter(empresa_id=empresa_id, tipo='PROVEEDOR').count()}")
            print(f"Articulos: {Articulo.global_objects.filter(empresa_id=empresa_id).count()} (con serial: {Articulo.global_objects.filter(empresa_id=empresa_id, usa_serial=True).count()})")
            print(f"Seriales: {SerialArticulo.global_objects.filter(empresa_id=empresa_id).count()}")
            print(f"Compras: {DocumentoCompra.global_objects.filter(empresa_id=empresa_id).count()}")
            print(f"Ventas: {NotaEntrega.global_objects.filter(empresa_id=empresa_id).count()}")
            print(f"Movimientos Kardex: {MovimientoKardex.global_objects.filter(empresa_id=empresa_id).count()}")
            print("\n=== DATOS DEMO GENERADOS EXITOSAMENTE ===")
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    from decimal import Decimal
    from datetime import date
    run()