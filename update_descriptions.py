import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'a2lt_stock_project.settings')
import django
django.setup()

from inventory.models import Articulo
from decimal import Decimal

eid = 34

articulos_con_data = {
    'NOTE-001': {
        'descripcion': 'Laptop HP 15.6" con procesador Intel Core i5 de 12va generacion, 8GB RAM DDR4, 512GB SSD NVMe, pantalla Full HD IPS antirreflejo, teclado numerico, Windows 11 Pro. Ideal para oficina y estudio.',
        'ficha_tecnica': 'Procesador: Intel Core i5-1235U (12va gen, 10 nucleos, hasta 4.4 GHz)\nMemoria: 8GB DDR4-3200 (expandible a 16GB)\nAlmacenamiento: 512GB SSD PCIe NVMe M.2\nPantalla: 15.6" Full HD (1920x1080) IPS 250 nits\nGraficos: Intel Iris Xe Graphics\nConectividad: WiFi 6, Bluetooth 5.2, USB-C 3.2, USB-A 3.2, HDMI 1.4b, RJ45\nBateria: 3 celdas 41Wh, carga rapida 45W\nPeso: 1.69 kg\nOS: Windows 11 Pro 64-bit',
        'social_quick': 'Laptop HP 15" Core i5 - Tu companera perfecta para trabajo y estudio. Rendimiento solido, bateria duradera, diseno elegante. Disponible ya! #HP #Laptop #Corei5 #Trabajo #Estudio #Oferta',
        'social_cross': 'Combina tu Laptop HP con: Auriculares Bluetooth 5.0 ($58) | Mouse Inalambrico ($38) | Mochila Laptop 15.6" ($45). Arma tu kit completo!'
    },
    'NOTE-002': {
        'descripcion': 'Laptop Dell Latitude 14" con Intel Core i7-1265U, 16GB RAM DDR5, 1TB SSD NVMe, pantalla Full HD+, teclado retroiluminado, lector huella, Windows 11 Pro. Ejecutiva y portatil.',
        'ficha_tecnica': 'Procesador: Intel Core i7-1265U (12va gen, 10 nucleos, hasta 4.8 GHz)\nMemoria: 16GB DDR5-4800 (soldada)\nAlmacenamiento: 1TB SSD PCIe NVMe M.2\nPantalla: 14" Full HD+ (1920x1200) IPS 300 nits, antirreflejo\nGraficos: Intel Iris Xe Graphics\nConectividad: WiFi 6E, Bluetooth 5.2, 2x Thunderbolt 4, USB-A 3.2, HDMI 2.0, RJ45\nBateria: 4 celdas 54Wh, ExpressCharge 60 min\nPeso: 1.26 kg\nOS: Windows 11 Pro 64-bit',
        'social_quick': 'Dell Latitude 14" Core i7 - Potencia ejecutiva en formato ultraportatil. Rendimiento premium, seguridad empresarial, movilidad total. #Dell #Latitude #Corei7 #Business #Portatil',
        'social_cross': 'Completa tu setup ejecutivo: Mochila Dell Premier 14" ($65) | Auriculares USB-C ($78) | Hub USB-C 7-en-1 ($48). Productividad sin limites!'
    },
    'PHON-001': {
        'descripcion': 'Samsung Galaxy S23 5G 128GB Phantom Black. Snapdragon 8 Gen 2, 8GB RAM, pantalla Dynamic AMOLED 2X 6.1" 120Hz, triple camara 50MP+12MP+10MP, bateria 3900mAh, IP68, One UI 5.1.',
        'ficha_tecnica': 'Procesador: Snapdragon 8 Gen 2 for Galaxy (4nm, 3.36 GHz)\nMemoria: 8GB RAM LPDDR5X\nAlmacenamiento: 128GB UFS 4.0\nPantalla: 6.1" Dynamic AMOLED 2X FHD+ (2340x1080) 120Hz, 1750 nits\nCamara: Triple 50MP (f/1.8) + 12MP UW (f/2.2) + 10MP 3x Tele (f/2.4)\nVideo: 8K@30fps, 4K@60fps\nBateria: 3900 mAh, carga 25W cable, 15W wireless, 4.5W reverse\nConectividad: 5G, WiFi 6E, Bluetooth 5.3, NFC, UWB\nDimensiones: 146.3 x 70.9 x 7.6 mm, 168g\nIP68, Gorilla Glass Victus 2',
        'social_quick': 'Galaxy S23 - Potencia flagship en tu bolsillo. Camara pro, rendimiento bestia, diseno premium. Consiguelo ya! #Samsung #GalaxyS23 #Smartphone #5G #Fotografia',
        'social_cross': 'Protege tu Galaxy: Case Spigen Ultra Hybrid ($18) | Vidrio templado ESR ($12) | Cargador 25W Samsung ($22) | Galaxy Buds2 Pro ($159). Proteccion total!'
    },
    'PHON-002': {
        'descripcion': 'iPhone 15 128GB Negro. Chip A16 Bionic, pantalla Super Retina XDR 6.1", Dynamic Island, camara dual 48MP+12MP, USB-C, Face ID, iOS 17. Diseno aluminio + vidrio color-infundido.',
        'ficha_tecnica': 'Chip: A16 Bionic (4nm, 6-core CPU, 5-core GPU, 16-core Neural Engine)\nMemoria: 6GB RAM\nAlmacenamiento: 128GB\nPantalla: 6.1" Super Retina XDR OLED (2556x1179) 2000 nits, Dynamic Island\nCamara: Principal 48MP f/1.6 + Ultra gran angular 12MP f/2.4\nVideo: 4K@60fps, Cinematic 4K@30fps, Action mode\nBateria: ~20h video, carga 20W (50% en 30min), MagSafe 15W, Qi 7.5W\nConectividad: 5G, WiFi 6, Bluetooth 5.3, NFC, Ultra Wideband\nDimensiones: 147.6 x 71.6 x 7.8 mm, 171g\nIP68, Ceramic Shield, iOS 17',
        'social_quick': 'iPhone 15 - La evolucion inteligente. Dynamic Island, USB-C, camara 48MP, chip A16. Innovacion que se siente. #Apple #iPhone15 #Innovacion #Tecnologia',
        'social_cross': 'Completa tu ecosistema: AirPods Pro 2 ($249) | Apple Watch SE ($249) | Case MagSafe ($49) | Cargador 20W ($19). Experiencia Apple completa!'
    },
    'TABL-001': {
        'descripcion': 'iPad Air 10.9" 64GB Gris Espacial. Chip M1, pantalla Liquid Retina 10.9" True Tone, Touch ID, USB-C, camara 12MP ultra gran angular, Center Stage, WiFi 6, hasta 10h bateria. Compatible Apple Pencil 2 y Magic Keyboard.',
        'ficha_tecnica': 'Chip: Apple M1 (8-core CPU, 8-core GPU, 16-core Neural Engine)\nMemoria: 8GB RAM unificada\nAlmacenamiento: 64GB\nPantalla: 10.9" Liquid Retina (2360x1640) True Tone, P3, 500 nits, antirreflejo\nCamara: 12MP f/1.8 gran angular + 12MP f/2.4 ultra gran angular (Center Stage)\nVideo: 4K@60fps, 1080p@60fps\nBateria: 28.6 Wh, hasta 10h web/video, carga 20W USB-C\nConectividad: WiFi 6, Bluetooth 5.0, USB-C 3.1 Gen 2\nDimensiones: 247.6 x 178.5 x 6.1 mm, 461g\nTouch ID en boton superior, USB-C 3.1 Gen 2, soporte Apple Pencil 2',
        'social_quick': 'iPad Air M1 - Potencia de escritorio, portabilidad de tablet. Ideal para creativos, estudiantes, profesionales. #iPadAir #M1 #Apple #Creatividad #Productividad',
        'social_cross': 'Desata tu creatividad: Apple Pencil 2 ($129) | Magic Keyboard ($299) | Smart Folio ($79). Tu estudio portatil completo!'
    }
}

eid = 34
for sku, data in articulos_con_data.items():
    art = Articulo.global_objects.filter(empresa_id=eid, sku=sku).first()
    if art:
        art.descripcion = data['descripcion']
        art.ficha_tecnica = data['ficha_tecnica']
        art.social_quick = data['social_quick']
        art.social_cross = data['social_cross']
        art.save(update_fields=['descripcion', 'ficha_tecnica', 'social_quick', 'social_cross'])
        print(f'Updated {sku}')

print('Done!')